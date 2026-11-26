"""Converted book content: ingest an M1 flow document through the converter, store it, and read or edit it page by page."""
import io, json, re, sys, tempfile, zipfile
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from sqlalchemy.orm import Session
from .config import settings
from .models import Book, ReviewPage
from .storage import get_storage

CONVERTER = Path(__import__("os").getenv("CONVERTER_PATH", str(Path(__file__).resolve().parents[2] / "converter")))
if str(CONVERTER) not in sys.path:
    sys.path.insert(0, str(CONVERTER))


def _store():
    return get_storage()


class ContentMissing(Exception):
    """The database says this book was converted, but its file is not in storage.

    This happens when a book was processed while no volume was mounted: the
    content went to the container's own disk and vanished on the next deploy,
    leaving the row behind. It is not a bug in the reader — the book has to be
    processed again — and it used to surface as a bare 500 for whoever opened
    it, including a student.
    """

    def __init__(self, book: Book):
        self.book = book
        super().__init__(
            f"The converted file for “{book.title}” is missing from storage "
            f"({book.content_key}). The book needs to be processed again.")


# A live book can be re-uploaded. The new version is processed and reviewed in
# content_key while students keep reading the published one in live_key; the
# swap happens on publish. These say which version a reader gets.
UPDATING = ("processing", "in_review", "rejected")


def serving(book: Book) -> bool:
    """Students can see and read this book now."""
    return book.status == "live" or (bool(book.live_key) and book.status in UPDATING)


def serving_filter():
    from sqlalchemy import and_, or_
    return or_(Book.status == "live", and_(Book.live_key != "", Book.live_key.isnot(None), Book.status.in_(UPDATING)))


def reader_key(book: Book) -> str:
    return book.live_key if (book.live_key and book.status != "live") else book.content_key


def load(book: Book, key: str | None = None) -> dict:
    try:
        return json.loads(_store().get((key or book.content_key) + "/book.json"))
    except FileNotFoundError:
        raise ContentMissing(book)
    except Exception as e:  # S3 says NoSuchKey instead of FileNotFoundError
        if "NoSuchKey" in str(e) or "Not Found" in str(e) or "404" in str(e):
            raise ContentMissing(book)
        raise


# Read-only copies of books, kept in memory for a minute. A reading student saves progress every 30 seconds and opens
# Home and the book now and then; each of those used to read and parse the whole book file (about 1 MB for a 300-page
# book) from storage. Never change what load_ro returns: it is shared. Reviewer edits use load() and save().
_RO: dict = {}
_RO_TTL = 60
_RO_MAX = 12


def load_ro(book: Book, key: str | None = None) -> dict:
    import time
    k = key or book.content_key
    hit = _RO.get(k)
    now = time.time()
    if hit and now - hit[0] < _RO_TTL:
        return hit[1]
    data = load(book, k)
    if len(_RO) >= _RO_MAX:
        _RO.pop(min(_RO, key=lambda x: _RO[x][0]), None)
    _RO[k] = (now, data)
    return data


def save(book: Book, data: dict):
    _store().put(book.content_key + "/book.json", json.dumps(data, ensure_ascii=False).encode())
    _RO.pop(book.content_key, None)


def load_extra(book: Book, name: str):
    try:
        return json.loads(_store().get(f"{book.content_key}/{name}"))
    except Exception:
        return None


def ledger(book: Book) -> list:
    try:
        return [json.loads(l) for l in _store().get(book.content_key + "/ledger.jsonl").decode().splitlines() if l.strip()]
    except Exception:
        return []


def ingest_flow(db: Session, book: Book, flow_bytes: bytes, log=lambda *a: None) -> dict:
    """Run the converter on an M1 flow document and put the result in the review queue. Never publishes."""
    from eduverse_convert.__main__ import convert
    from eduverse_convert.reader import read
    version = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    key = f"books/{book.id}/v{version}"
    store = _store()
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "flow.docx"; src.write_bytes(flow_bytes)
        out = Path(tmp) / "out"
        data, report = convert(src, out, log=log)
        # What the person uploading said beats what the converter guessed from the front pages.
        bk = data.get("book") or {}
        if book.subject and not bk.get("subject"):
            bk["subject"] = book.subject
            bk["title"] = " ".join(x for x in [book.subject, f"Standard {bk.get('class') or book.grade}" if (bk.get('class') or book.grade) else ""] if x)
            (out / "book.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        if not page_numbers(data):
            # Nothing a reviewer could open. Fail the job with a reason rather
            # than hand over a book with no pages.
            raise ValueError("The converter found no readable content in this flow document, so there are no pages to review. "
                             "Check that M1 finished and that the right file was uploaded.")
        for f in out.rglob("*"):
            rel = f.relative_to(out).as_posix()
            if f.is_file() and not rel.startswith("assets"):
                store.put(f"{key}/{rel}", f.read_bytes())
        # the M1 extraction itself, page by page, for the reviewer's left pane
        raw, images = read(src)
        pages = {}
        for e in raw:
            p = pages.setdefault(e["page"], [])
            if e["kind"] == "p":
                for d in e.get("drawings", []):
                    name = f"{d['hash']}.{d['ext']}"
                    store.put(f"{key}/flow_images/{name}", images[d["hash"]][0])
                    p.append({"kind": "image", "src": f"flow_images/{name}"})
                if e.get("text", "").strip():
                    p.append({"kind": "text", "style": e["style"], "text": e["text"]})
                for m in e.get("math", []):
                    p.append({"kind": "math", "latex": m["latex"]})
            elif e["kind"] == "table":
                p.append({"kind": "table", "rows": e["rows"]})
            elif e["kind"] == "desc":
                p.append({"kind": "desc", "text": e["desc"]["summary"][:400], "type": e["desc"]["type"]})
        store.put(f"{key}/flow_pages.json", json.dumps(pages, ensure_ascii=False).encode())
    b = data["book"]
    book.content_key, book.status, book.review_note = key, "in_review", ""
    book.reviewed_by, book.reviewed_at = "", None
    book.title = book.title or b.get("title", "")
    book.subject = book.subject or b.get("subject", "")
    book.board = book.board or b.get("board", "")
    book.grade = book.grade or b.get("class", "")
    book.edition = book.edition or b.get("edition", "")
    book.fingerprint = b.get("fingerprint", {}).get("text_sha256", "")[:64]
    db.query(ReviewPage).filter(ReviewPage.book_id == book.id).delete()
    # Every page of the original with content gets a review page, even when all of its text was joined onto the
    # page before (a paragraph that runs over). Before, such a page had no review page, so Publish refused the
    # book as "pages not in the digital book" with nothing the reviewer could do about it.
    review = sorted(set(page_numbers(data)) | {int(p) for p, items in pages.items() if items})
    for p in review:
        db.add(ReviewPage(book_id=book.id, page=p))
    book.pages = max(book.pages or 0, len(review))
    return report


def walk(blocks, box=None):
    for b in blocks:
        yield b, box
        if b["type"] == "box":
            yield from walk(b["children"], b)


def page_numbers(data) -> list[int]:
    ps = set()
    for ch in data["chapters"]:
        for b, _ in walk(ch["blocks"]):
            # "if b.get('page')" also skips page 0, which threw away a whole
            # book's pages. Only a missing page should be skipped.
            if b.get("page") is not None:
                ps.add(b["page"])
    return sorted(ps)


def page_view(data, page: int) -> dict:
    """Top level blocks on this page (a box is shown whole if any of it is on the page), with its chapter's keywords."""
    out, chapters = [], []
    for ch in data["chapters"]:
        blocks = []
        for b in ch["blocks"]:
            on = b.get("page") == page or b.get("page_end") == page
            if b["type"] == "box":
                on = on or any(c.get("page") == page for c, _ in walk(b["children"]))
            if on:
                blocks.append(b)
        if blocks:
            chapters.append({"number": ch["number"], "title": ch["title"],
                             "keywords": [{k: kw[k] for k in ("id", "term", "key", "definition", "signals", "prerequisite")} for kw in ch["keywords"]],
                             "sections": {s["id"]: (s["number"] + " " + s["title"]).strip() for s in ch["sections"]}, "blocks": blocks})
    return {"page": page, "chapters": chapters}


def find_block(data, block_id):
    for ch in data["chapters"]:
        for b, parent in walk(ch["blocks"]):
            if b["id"] == block_id:
                return ch, b, parent
    return None, None, None


def remark(obj, keywords, keep_ids):
    """Re-place highlights after the text changed: keep only the words that were highlighted here before."""
    text, marks, taken = obj.get("text", ""), [], []
    for kw in sorted([k for k in keywords if k["id"] in keep_ids], key=lambda k: -len(k["key"])):
        m = re.search(r"(?<![A-Za-z])" + re.escape(kw["key"]) + r"(?:s|es)?(?![A-Za-z])", text, re.I)
        if m and not any(not (m.end() <= a or m.start() >= z) for a, z in taken):
            marks.append([m.start(), m.end(), kw["id"]]); taken.append((m.start(), m.end()))
    obj["marks"] = sorted(marks)


def mark_first(ch, kw) -> bool:
    for b, box in walk(ch["blocks"]):
        if box is not None and box["kind"] in ("glossary", "references", "internet", "exercises"):
            continue
        objs = [b] if b["type"] == "paragraph" else (b["items"] if b["type"] == "list" else [])
        for obj in objs:
            m = re.search(r"(?<![A-Za-z])" + re.escape(kw["key"]) + r"(?:s|es)?(?![A-Za-z])", obj["text"], re.I)
            if m and not any(not (m.end() <= a or m.start() >= z) for a, z, _ in obj.get("marks", [])):
                obj.setdefault("marks", []).append([m.start(), m.end(), kw["id"]]); obj["marks"].sort()
                kw["first_block"] = b["id"]
                return True
    return False


def unmark(ch, kid):
    for b, _ in walk(ch["blocks"]):
        for obj in [b] + b.get("items", []):
            if obj.get("marks"):
                obj["marks"] = [m for m in obj["marks"] if m[2] != kid]


def original_page_png(book: Book, page: int) -> bytes | None:
    """Renders a page of the uploaded original PDF, cached in storage."""
    if not book.original_key or not book.original_key.lower().endswith(".pdf"):
        return None
    key = f"{book.content_key}/original/{page}.png"
    store = _store()
    try:
        return store.get(key)
    except Exception:
        pass
    import pymupdf
    doc = pymupdf.open(stream=store.get(book.original_key), filetype="pdf")
    if page < 1 or page > doc.page_count:
        return None
    png = doc[page - 1].get_pixmap(dpi=160).tobytes("png")
    store.put(key, png)
    return png
