"""Page view and the page check.

Page view shows the printed page exactly as the textbook prints it, with the book's real text laid over it in place,
invisible but selectable: a student can still tap highlighted words, select words to explain, highlight and take
notes. Two columns, side boxes, text wrapped round pictures and labels on diagrams all look exactly like the book,
because they are the book. The flowing Reading view stays for phones and for changing the text size.

Stored with each converted version, under <content_key>/layout/:
    index.json        {"available": true, "pages": [{"n": 3, "w": 595.3, "h": 841.9, "approx": false}, ...]}
    p0003.webp        the printed page
    p0003.json        {"n": 3, "w":..., "h":..., "lines": [[x0, y0, x1, y1, "text of the line"], ...], "approx": false}
    check.json        the page check: for each page, what the digital page is missing

Text positions come from the PDF itself when it has a text layer. A scanned page has none; there the positions come
from M1's reading of the page (each block's box and text), laid out line by line inside the block, which is close but
not exact, so the page is marked approx.

The page check compares the digital book with the original page:
    words      every word printed on the page (outside figures, headers and footers) is in the digital page
    order      the words come in the same order as on the page
    pictures   every figure M1 found is in the digital page, once
    edges      no picture is cut off at its edge
Each problem is written to the book's ledger, so the reviewer sees it on that page with the reason.
"""
from __future__ import annotations

import difflib
import io
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

DPI = 130           # page image resolution: sharp on a laptop, about 150 to 300 KB a page as WebP
QUALITY = 72
WORD = re.compile(r"[0-9A-Za-zऀ-෿À-ɏ]+")


def _norm_words(text: str) -> list[str]:
    import unicodedata
    text = unicodedata.normalize("NFKC", text or "")   # NH₂ and m² read as NH2 and m2 on both sides
    return [w.lower() for w in WORD.findall(text or "") if len(w) >= 2 or w.isdigit()]


def _pdf_bytes(book, store) -> bytes | None:
    key = book.original_key or ""
    if key.lower().endswith(".pdf"):
        return store.get(key)
    if key.lower().endswith((".docx", ".doc")):
        # A Word book has no fixed pages. LibreOffice lays it out as the printed book would be.
        office = shutil.which("soffice") or shutil.which("libreoffice")
        if not office:
            return None
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / ("book" + Path(key).suffix.lower())
            src.write_bytes(store.get(key))
            subprocess.run([office, "--headless", "--norestore", f"-env:UserInstallation=file://{tmp}/profile",
                            "--convert-to", "pdf", "--outdir", tmp, str(src)], capture_output=True, timeout=600)
            out = Path(tmp) / "book.pdf"
            return out.read_bytes() if out.exists() else None
    return None


def _lines_from_pdf(pg) -> list[list]:
    """Lines in the order the PDF holds them (which follows the columns), each with its box and text."""
    lines: dict = {}
    order = []
    for x0, y0, x1, y1, w, b, l, _n in pg.get_text("words"):
        k = (b, l)
        if k not in lines:
            lines[k] = [x0, y0, x1, y1, []]
            order.append(k)
        L = lines[k]
        L[0], L[1], L[2], L[3] = min(L[0], x0), min(L[1], y0), max(L[2], x1), max(L[3], y1)
        L[4].append(w)
    return [[round(L[0], 1), round(L[1], 1), round(L[2], 1), round(L[3], 1), " ".join(L[4])] for L in (lines[k] for k in order)]


def _lines_from_m1(m1_page: dict) -> list[list]:
    """A scanned page: lay each block's text out line by line inside its box. Close, not exact."""
    out = []
    for b in sorted(m1_page.get("blocks", []), key=lambda b: b.get("order", 0)):
        if b.get("type") in ("figure", "table", "figure_note") or not (b.get("text") or "").strip():
            continue
        x0, y0, x1, y1 = b["bbox_pt"]
        size = b.get("font_size") or 11
        lh = size * 1.25
        n = max(1, round((y1 - y0) / lh))
        words = b["text"].split()
        per = max(1, -(-len(words) // n))
        for i in range(n):
            chunk = words[i * per:(i + 1) * per]
            if not chunk:
                break
            ly = y0 + i * (y1 - y0) / n
            out.append([round(x0, 1), round(ly, 1), round(x1, 1), round(ly + (y1 - y0) / n, 1), " ".join(chunk)])
    return out


def _inside(b, box, tol=2.0):
    return b[0] >= box[0] - tol and b[1] >= box[1] - tol and b[2] <= box[2] + tol and b[3] <= box[3] + tol


def _digital_page_text(page_view: dict) -> tuple[str, list[dict]]:
    """All text the digital page shows, in order, and its figures."""
    parts, figs = [], []

    def walk(blocks):
        for b in blocks:
            t = b.get("type")
            if t == "box":
                parts.append(b.get("title", ""))
                walk(b.get("children") or [])
            elif t in ("paragraph", "heading", "subheading", "marker"):
                parts.append((b.get("number", "") + " " + b.get("text", "")).strip())
            elif t == "list":
                parts.extend(i.get("text", "") for i in b.get("items", []))
            elif t == "table":
                parts.append(" ".join(" ".join(r) for r in b.get("rows", [])))
                parts.append(b.get("caption", ""))
            elif t == "figure":
                figs.append(b)
                parts.append(("Figure " + b.get("number", "") + " " + b.get("caption", "")).strip())
            elif t == "equation":
                parts.extend(b.get("plain") or [])
    for ch in page_view.get("chapters", []):
        # the chapter heading is printed on its first page but is not a block
        parts.append(f"Unit Chapter Lesson {ch.get('number', '')} {ch.get('title', '')}")
        walk(ch["blocks"])
    return " ".join(parts), figs


def check_page(n: int, lines: list, m1_page: dict | None, page_view: dict, store, key: str, furniture: list,
               page_img=None, page_w: float = 0) -> list[dict]:
    """What the digital page is missing compared with the printed page. Each item: {page, what, text}."""
    problems = []
    figs_m1 = [b["bbox_pt"] for b in (m1_page or {}).get("blocks", []) if b.get("type") == "figure"]
    expected = []
    for x0, y0, x1, y1, text in lines:
        box = [x0, y0, x1, y1]
        if any(_inside(box, f, 4) for f in figs_m1) or any(_inside(box, f, 2) for f in furniture):
            continue                       # labels inside a figure are in the picture; headers and page numbers are dropped on purpose
        expected.extend(_norm_words(text))
    digital, dfigs = _digital_page_text(page_view)
    got = _norm_words(digital)
    if len(expected) >= 8:
        from collections import Counter
        have = Counter(got)
        missing = []
        for w in expected:
            if have[w] > 0:
                have[w] -= 1
            else:
                missing.append(w)
        cover = 1 - len(missing) / len(expected)
        if cover < 0.97:
            problems.append({"page": n, "what": f"page check: {round((1 - cover) * 100)}% of the printed words are not in the digital page",
                             "text": "Missing words include: " + ", ".join(dict.fromkeys(missing))[:300]})
        elif got:
            # How much of the printed text comes out in the same order. Extra words in the digital page (a paragraph
            # that runs on from the page before) do not count against it.
            sm = difflib.SequenceMatcher(None, expected, got, autojunk=False)
            ratio = sum(m.size for m in sm.get_matching_blocks()) / len(expected)
            if ratio < 0.85:
                problems.append({"page": n, "what": "page check: the text is in a different order from the printed page",
                                 "text": f"Order match {round(ratio * 100)}%. Check columns, side boxes and text beside pictures."})
    if len(figs_m1) > len(dfigs):
        problems.append({"page": n, "what": f"page check: the printed page has {len(figs_m1)} figure(s), the digital page {len(dfigs)}",
                         "text": "A picture may be missing. Compare with the original page."})
    if page_img is not None:
        for i, f in enumerate(figs_m1):
            side = _cut_side(page_img, f, page_w, lines)
            if side:
                num = dfigs[i].get("number") if i < len(dfigs) else ""
                problems.append({"page": n, "what": "page check: a picture may be cut off",
                                 "text": f"Figure {num or i + 1}: the printed picture carries on past its {side} edge. Crop it again on the original page."})
    return problems


def _cut_side(img, box, page_w: float, lines) -> str:
    """Look just outside a figure on the printed page. Ink there that is not a line of text means the crop cut the
    picture. A photo that fills its own crop is fine: the page around it is blank."""
    import numpy as np
    s = img.width / page_w
    a = np.asarray(img.convert("L"), dtype=np.int16)
    x0, y0, x1, y1 = [int(v * s) for v in box]
    band = max(3, int(5 * s))
    text_boxes = [[int(l[0] * s), int(l[1] * s), int(l[2] * s), int(l[3] * s)] for l in lines]
    sides = {"top": (x0, max(0, y0 - band), x1, y0 - 1), "bottom": (x0, y1 + 1, x1, min(a.shape[0], y1 + band)),
             "left": (max(0, x0 - band), y0, x0 - 1, y1), "right": (x1 + 1, y0, min(a.shape[1], x1 + band), y1)}
    for name, (bx0, by0, bx1, by1) in sides.items():
        if bx1 - bx0 < 2 or by1 - by0 < 1:
            continue
        if any(not (bx1 < t[0] or bx0 > t[2] or by1 < t[1] or by0 > t[3]) for t in text_boxes):
            continue        # text right beside the picture is expected
        strip = a[by0:by1, bx0:bx1]
        if strip.size and (np.abs(strip - 255) > 60).mean() > 0.12:
            return name
    return ""


def build(book, store, m1_book: dict | None, page_view_of, log=print) -> dict:
    """Make the page images and text positions for this version of the book, and run the page check.
    page_view_of(n) returns the digital page n. Never fails the job: a book without Page view still works."""
    key = book.content_key
    try:
        pdf = _pdf_bytes(book, store)
    except Exception as e:
        log(f"page view: could not read the original ({e})")
        pdf = None
    if not pdf:
        store.put(f"{key}/layout/index.json", json.dumps({"available": False, "why": "no printed layout for this upload"}).encode())
        return {"available": False}
    import pymupdf
    from PIL import Image
    m1_pages = {p["page"]: p for p in (m1_book or {}).get("pages", [])}
    furniture = {}
    for e in (m1_book or {}).get("_ledger", []):
        if e.get("bbox") and str(e.get("reason", "")).startswith("furniture"):
            furniture.setdefault(e.get("page"), []).append(e["bbox"])
    pages, problems = [], []
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        for i, pg in enumerate(doc):
            n = i + 1
            lines = _lines_from_pdf(pg)
            approx = False
            if sum(len(l[4]) for l in lines) < 40 and m1_pages.get(n, {}).get("route") in ("scanned", "hybrid"):
                lines, approx = _lines_from_m1(m1_pages[n]), True
            pix = pg.get_pixmap(dpi=DPI)
            im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            buf = io.BytesIO()
            im.save(buf, "WEBP", quality=QUALITY, method=4)
            name = f"layout/p{n:04d}"
            store.put(f"{key}/{name}.webp", buf.getvalue())
            w, h = round(pg.rect.width, 1), round(pg.rect.height, 1)
            for l in lines:   # running headers, footers and page numbers: shown, but never marked as important words
                cx, cy = (l[0] + l[2]) / 2, (l[1] + l[3]) / 2
                if any(b[0] - 3 <= cx <= b[2] + 3 and b[1] - 3 <= cy <= b[3] + 3 for b in furniture.get(n, [])):
                    l.append(1)
            store.put(f"{key}/{name}.json", json.dumps({"n": n, "w": w, "h": h, "lines": lines, "approx": approx}, ensure_ascii=False).encode())
            pages.append({"n": n, "w": w, "h": h, "approx": approx})
            try:
                problems += check_page(n, lines, m1_pages.get(n), page_view_of(n), store, key, furniture.get(n, []), im, pg.rect.width)
            except Exception as e:
                log(f"page check skipped on page {n}: {e}")
    store.put(f"{key}/layout/index.json", json.dumps({"available": True, "dpi": DPI, "pages": pages}).encode())
    store.put(f"{key}/layout/check.json", json.dumps(problems, ensure_ascii=False).encode())
    if problems:   # into the book's ledger, so each problem shows on its page in the review screen
        try:
            old = store.get(f"{key}/ledger.jsonl").decode()
        except Exception:
            old = ""
        store.put(f"{key}/ledger.jsonl", (old.rstrip("\n") + "\n" if old.strip() else "")
                  .encode() + "\n".join(json.dumps(p, ensure_ascii=False) for p in problems).encode() + b"\n")
        try:   # the review screen counts flags from report.json, so the page check must land there too
            rep = json.loads(store.get(f"{key}/report.json"))
            have = {(f.get("page"), f.get("what")) for f in rep.get("needs_review", [])}
            rep.setdefault("needs_review", []).extend(p for p in problems if (p["page"], p["what"]) not in have)
            store.put(f"{key}/report.json", json.dumps(rep, ensure_ascii=False, indent=1).encode())
        except Exception as e:
            log(f"page check: could not add flags to the report ({e})")
    return {"available": True, "pages": len(pages), "problems": len(problems)}
