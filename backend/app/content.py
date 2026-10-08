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


def load(book: Book) -> dict:
    return json.loads(_store().get(book.content_key + "/book.json"))


def save(book: Book, data: dict):
    _store().put(book.content_key + "/book.json", json.dumps(data, ensure_ascii=False).encode())


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
    for p in page_numbers(data):
        db.add(ReviewPage(book_id=book.id, page=p))
    book.pages = max(book.pages or 0, len(page_numbers(data)))
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
    png = doc[page - 1].get_pixmap(dpi=110).tobytes("png")
    store.put(key, png)
    return png
