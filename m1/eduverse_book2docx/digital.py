"""The digital book.

`flow.docx` is for a human to edit. This is the other output: one semantic HTML
file where nothing is a picture of content. Maths is MathML, tables are real
tables, a figure with a spec is inline SVG, and every figure carries its
structured description in data attributes so a model reading the DOM sees
exactly what a reader sees.

Everything comes from book.json. Nothing is re-extracted and nothing is invented.
"""

from __future__ import annotations

import html
import json
import logging
import os
from typing import Dict, List, Optional

from .config import Config
from .coverage import is_readable

log = logging.getLogger(__name__)
from .schema import Block, Book, Page, Run

CSS = """
:root{--ink:#1a1a1a;--mut:#6b6b6b;--line:#e3e1da;--bg:#faf9f6;--red:#E0212F;
--panel:#f4f2ec;--note:#f4f6f8}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.65 Georgia,"Times New Roman",serif}
.wrap{max-width:820px;margin:0 auto;padding:40px 24px 96px}
header{border-bottom:2px solid var(--ink);padding-bottom:14px;margin-bottom:28px}
header h1{font:600 28px/1.2 Arial,Helvetica,sans-serif;margin:0 0 6px}
header .meta{font:13px/1.5 Arial,Helvetica,sans-serif;color:var(--mut)}
h1,h2,h3,h4{font-family:Arial,Helvetica,sans-serif;line-height:1.25;
margin:1.6em 0 .5em}
h1{font-size:26px}h2{font-size:21px}h3{font-size:17px}h4{font-size:15px}
p{margin:0 0 .9em}
ul,ol{margin:0 0 .9em 1.4em;padding:0}
li{margin:0 0 .35em}
figure{margin:1.6em 0}
figure svg,figure img{max-width:100%;height:auto;display:block;margin:0 auto;
background:#fff;border:1px solid var(--line);border-radius:6px}
figcaption{font:italic 13px/1.5 Arial,Helvetica,sans-serif;color:var(--mut);
text-align:center;margin-top:8px}
.desc{background:var(--note);border-radius:6px;padding:12px 14px;margin-top:10px;
font:13px/1.6 Arial,Helvetica,sans-serif;color:var(--ink)}
.desc b{display:block;font-size:11.5px;text-transform:uppercase;
letter-spacing:.04em;color:var(--mut);margin-bottom:5px}
.desc dl{margin:6px 0 0;display:grid;grid-template-columns:auto 1fr;gap:2px 10px}
.desc dt{color:var(--mut)}
.desc dd{margin:0}
table{border-collapse:collapse;width:100%;margin:1.4em 0;
font:14px/1.5 Arial,Helvetica,sans-serif;background:#fff}
th,td{border:1px solid var(--line);padding:7px 10px;text-align:left}
th{background:#f1efe8;font-weight:600}
td.num{text-align:right;font-variant-numeric:tabular-nums}
caption{caption-side:bottom;font:italic 13px/1.5 Arial,Helvetica,sans-serif;
color:var(--mut);padding-top:8px}
.panel{background:var(--panel);border-radius:8px;padding:14px 16px;margin:1.4em 0}
math{font-size:1.05em}
.eq{text-align:center;margin:1.2em 0}
.pagebreak{border:0;border-top:1px dashed var(--line);margin:36px 0 8px}
.pagebreak span{font:11px Arial,Helvetica,sans-serif;color:var(--mut);
background:var(--bg);padding:0 8px;position:relative;top:-9px}
.opaque{outline:2px dashed var(--red);outline-offset:3px}
@media print{body{background:#fff}.wrap{max-width:none}}
"""


def render(book: Book, out_dir: str, cfg: Config) -> str:
    """Write digital/index.html and return its path."""
    ddir = os.path.join(out_dir, "digital")
    os.makedirs(ddir, exist_ok=True)

    body: List[str] = []
    for page in book.pages:
        body.append(f'<hr class="pagebreak"><p style="text-align:center;margin:0">'
                    f'<span style="font:11px Arial;color:#6b6b6b">'
                    f'page {page.page}</span></p>')
        i = 0
        blocks = page.blocks
        while i < len(blocks):
            b = blocks[i]
            if b.type == "list_item":
                run, i = _list_run(blocks, i)
                body.append(run)
                continue
            body.append(_block(b, blocks, out_dir, ddir))
            i += 1

    d = book.detected or {}
    title = (d.get("title") or d.get("subject") or "Digital textbook")
    meta_bits = [x for x in (d.get("board"),
                             f"class {d['grade']}" if d.get("grade") else None,
                             d.get("subject"),
                             f"{len(book.pages)} pages") if x]
    cov = (book.stats or {}).get("coverage", {})
    if cov:
        meta_bits.append(f"{cov.get('coverage', 0) * 100:.1f}% machine readable")

    doc = f"""<!doctype html>
<html lang="{html.escape(str(d.get('language') or 'en'))}"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(str(title))}</title>
<style>{CSS}</style></head><body><div class="wrap">
<header><h1>{html.escape(str(title))}</h1>
<div class="meta">{' &middot; '.join(html.escape(str(x)) for x in meta_bits)}</div></header>
{''.join(body)}
</div>
<script type="application/json" id="eduverse-book">{_index(book)}</script>
</body></html>"""

    path = os.path.join(ddir, "index.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(doc)
    return path


# ---------------------------------------------------------------------------

def _block(b: Block, blocks: List[Block], out_dir: str, ddir: str) -> str:
    ok, _why = is_readable(b)
    cls = "" if ok else ' class="opaque"'
    bid = f' id="{html.escape(b.id)}"'

    if b.type == "page_furniture":
        return ""
    if b.type == "heading":
        lv = max(1, min(4, b.level or 2))
        return f"<h{lv}{bid}{cls}>{_inline(b)}</h{lv}>"
    if b.type == "title":
        return f"<h1{bid}{cls}>{_inline(b)}</h1>"
    if b.type == "equation":
        return (f'<div class="eq"{bid}>{_math(b)}</div>'
                + _note_html(b, blocks, "Equation description"))
    if b.type == "table":
        return _table(b) + _note_html(b, blocks, "Table description")
    if b.type == "figure":
        return _figure(b, blocks, out_dir, ddir)
    if b.type == "figure_note":
        return ""                     # rendered inside its figure
    if b.type == "caption":
        return ""                     # rendered inside its figure
    if b.type == "box":
        return f'<div class="panel"{bid}>{_inline(b)}</div>'
    # boxed by the printed panel it sits in, not by the in_panel flag, which
    # a full page tint sets on everything
    if b.box >= 0:
        return (f'<p class="panel" data-box="{b.box}"{bid}{cls}>'
                f'{_inline(b)}</p>')
    return f"<p{bid}{cls}>{_inline(b)}</p>"


def _note_html(parent: Block, blocks: List[Block], label: str) -> str:
    note = next((c for c in blocks
                 if c.type == "figure_note" and c.caption_of == parent.id), None)
    if note is None or not (note.text or "").strip():
        return ""
    lines = [l for l in note.text.split("\n") if l.strip()]
    body = "".join(f"<div>{html.escape(l)}</div>" for l in lines)
    return (f'<div class="desc"><b>{html.escape(label)}</b>{body}</div>')


def _list_run(blocks: List[Block], i: int):
    kind = blocks[i].block_kind or "bullet"
    tag = "ol" if kind == "number" else "ul"
    items = []
    while i < len(blocks) and blocks[i].type == "list_item" \
            and (blocks[i].block_kind or "bullet") == kind:
        items.append(f'<li id="{html.escape(blocks[i].id)}">'
                     f'{_inline(_strip_bullet(blocks[i]))}</li>')
        i += 1
    return f"<{tag}>{''.join(items)}</{tag}>", i


def _strip_bullet(b: Block) -> Block:
    """The list markup draws the bullet, so the printed glyph must go, and the
    run offsets must move with it."""
    from .structure import BULLET_RE
    m = BULLET_RE.match(b.text or "")
    if not m:
        return b
    cut = m.end()
    return Block(id=b.id, page=b.page, type=b.type,
                 bbox_pt=b.bbox_pt, text=b.text[cut:],
                 runs=[Run(s=max(0, r.s - cut), e=max(0, r.e - cut),
                           bold=r.bold, italic=r.italic, underline=r.underline,
                           superscript=r.superscript, subscript=r.subscript,
                           color=r.color)
                       for r in (b.runs or []) if r.e > cut],
                 block_kind=b.block_kind)


def _inline(b: Block) -> str:
    """Text with its runs turned into real markup, offsets respected."""
    text = b.text or ""
    runs = sorted([r for r in (b.runs or []) if r.e > r.s], key=lambda r: r.s)
    if not runs:
        return html.escape(text)
    out: List[str] = []
    pos = 0
    for r in runs:
        s, e = max(0, min(r.s, len(text))), max(0, min(r.e, len(text)))
        if s > pos:
            out.append(html.escape(text[pos:s]))
        if e > s:
            frag = html.escape(text[s:e])
            if r.subscript:
                frag = f"<sub>{frag}</sub>"
            if r.superscript:
                frag = f"<sup>{frag}</sup>"
            if r.italic:
                frag = f"<em>{frag}</em>"
            if r.bold:
                frag = f"<strong>{frag}</strong>"
            if r.underline:
                frag = f"<u>{frag}</u>"
            out.append(frag)
            pos = e
    if pos < len(text):
        out.append(html.escape(text[pos:]))
    return "".join(out)


_MATHML_MISSING = []


def _mathml_converter():
    """latex2mathml is what turns a formula into content rather than a picture
    of a formula. Its absence used to be swallowed by a bare except, so every
    equation in the book quietly degraded to plain text and the scorecard
    still reported full coverage. Now it is recorded and reported once."""
    try:
        import latex2mathml.converter as conv
        return conv
    except Exception:
        if not _MATHML_MISSING:
            _MATHML_MISSING.append(True)
            log.warning("latex2mathml is not installed: the digital book will "
                        "hold plain LaTeX instead of MathML. "
                        "pip install latex2mathml")
        return None


def mathml_available() -> bool:
    return _mathml_converter() is not None


def _math(b: Block) -> str:
    """MathML where possible, so the formula is content and not a picture."""
    if b.latex and not b.math_unreadable:
        conv = _mathml_converter()
        if conv is not None:
            try:
                ml = conv.convert(b.latex)
                return (f'<span data-latex="{html.escape(b.latex)}" '
                        f'data-source="{html.escape(b.latex_source or "")}">'
                        f'{ml}</span>')
            except Exception:
                pass
        return (f'<code data-latex="{html.escape(b.latex)}">'
                f'{html.escape(b.latex)}</code>')
    if b.image_ref:
        return (f'<img class="opaque" src="../{html.escape(b.image_ref)}" '
                f'alt="equation not verified">')
    return f'<code class="opaque">{html.escape(b.text or "")}</code>'


def _table(b: Block) -> str:
    td = b.table
    if td is None:
        return ""
    grid: Dict = {(c.row, c.col): c for c in td.cells}
    skip = set()
    for c in td.cells:
        for r in range(c.row, c.row + c.row_span):
            for cc in range(c.col, c.col + c.col_span):
                if (r, cc) != (c.row, c.col):
                    skip.add((r, cc))

    rows: List[str] = []
    for r in range(td.rows):
        cells: List[str] = []
        for cc in range(td.cols):
            if (r, cc) in skip:
                continue
            cell = grid.get((r, cc))
            if cell is None:
                cells.append("<td></td>")
                continue
            tag = "th" if cell.is_header else "td"
            attrs = ""
            if cell.col_span > 1:
                attrs += f' colspan="{cell.col_span}"'
            if cell.row_span > 1:
                attrs += f' rowspan="{cell.row_span}"'
            txt = cell.text or ""
            if tag == "td" and _numeric(txt):
                attrs += ' class="num"'
            body = _inline(Block(id="x", page=0, type="paragraph",
                                 bbox_pt=[0, 0, 0, 0], text=txt,
                                 runs=list(cell.runs or [])))
            cells.append(f"<{tag}{attrs}>{body}</{tag}>")
        rows.append(f"<tr>{''.join(cells)}</tr>")

    head = ""
    if td.header_rows:
        head = f"<thead>{''.join(rows[:td.header_rows])}</thead>"
        rows = rows[td.header_rows:]
    return (f'<table id="{html.escape(b.id)}" data-source="'
            f'{html.escape(b.source or "")}">{head}'
            f"<tbody>{''.join(rows)}</tbody></table>")


def _figure(b: Block, blocks: List[Block], out_dir: str, ddir: str) -> str:
    m = b.figure
    inner = ""
    if m and m.svg_ref:
        svg_path = os.path.join(out_dir, m.svg_ref)
        if os.path.exists(svg_path):
            with open(svg_path, encoding="utf-8") as fh:
                inner = fh.read()          # inline, so it is DOM not a binary
    if not inner and b.image_ref:
        alt = html.escape((m.desc if m else "") or b.id)
        inner = (f'<img src="../{html.escape(b.image_ref)}" alt="{alt}" '
                 f'width="{int(b.width)}" height="{int(b.height)}">')

    cap = next((c for c in blocks
                if c.type == "caption" and c.caption_of == b.id), None)
    note = next((c for c in blocks
                 if c.type == "figure_note" and c.caption_of == b.id), None)

    bits = [inner]
    if cap is not None:
        bits.append(f"<figcaption>{_inline(cap)}</figcaption>")
    if m and ((m.desc or "").strip() or note is not None):
        rows = []
        if m.entities:
            rows.append(("Parts", ", ".join(m.entities)))
        if m.relationships:
            rows.append(("Relations", "; ".join(m.relationships)))
        if m.data_points:
            rows.append(("Data", "; ".join(m.data_points)))
        if m.text_in_image:
            rows.append(("Text in figure", " | ".join(m.text_in_image)))
        dl = "".join(f"<dt>{html.escape(k)}</dt><dd>{html.escape(v)}</dd>"
                     for k, v in rows)
        bits.append(
            f'<div class="desc"><b>Image description ({html.escape(m.fig_kind)})'
            f"</b>{html.escape(m.desc or '')}"
            + (f"<dl>{dl}</dl>" if dl else "") + "</div>")

    data = ""
    if m:
        data = (f' data-kind="{html.escape(m.fig_kind)}"'
                f' data-regenerable="{str(bool(m.regenerable)).lower()}"')
        if m.spec:
            data += (' data-spec="'
                     + html.escape(json.dumps(m.spec, ensure_ascii=False)) + '"')
    return (f'<figure id="{html.escape(b.id)}"{data}>'
            + "".join(bits) + "</figure>")


def _numeric(text: str) -> bool:
    t = (text or "").strip().replace(",", "").replace("%", "")
    if not t:
        return False
    try:
        float(t)
        return True
    except ValueError:
        return False


def _index(book: Book) -> str:
    """A compact machine index embedded in the page, so a model reading the
    document does not have to parse the prose back into structure."""
    out = {
        "book_id": book.book_id,
        "detected": book.detected,
        "coverage": (book.stats or {}).get("coverage", {}),
        "outline": [
            {"id": b.id, "page": b.page, "level": b.level, "text": b.text}
            for _, b in book.blocks() if b.type == "heading"
        ],
        "figures": [
            {"id": b.id, "page": b.page,
             "kind": b.figure.fig_kind if b.figure else None,
             "regenerable": bool(b.figure and b.figure.regenerable),
             "desc": (b.figure.desc if b.figure else "")}
            for _, b in book.blocks() if b.type == "figure"
        ],
        "equations": [
            {"id": b.id, "page": b.page, "latex": b.latex,
             "source": b.latex_source}
            for _, b in book.blocks()
            if b.type == "equation" and b.latex and not b.math_unreadable
        ],
        "tables": [
            {"id": b.id, "page": b.page,
             "rows": b.table.rows if b.table else 0,
             "cols": b.table.cols if b.table else 0,
             "source": b.source}
            for _, b in book.blocks() if b.type == "table"
        ],
    }
    return json.dumps(out, ensure_ascii=False, indent=1)
