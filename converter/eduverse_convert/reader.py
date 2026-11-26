"""Reads an M1 flow .docx into an ordered list of raw elements. No interpretation here."""
import hashlib, re
import docx
from docx.oxml.ns import qn
from docx.table import Table
from .omml import M, to_latex, plain, spaces_lost

A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _style(p):
    pp = p.find(qn("w:pPr"))
    st = pp.find(qn("w:pStyle")) if pp is not None else None
    return st.get(qn("w:val")) if st is not None else ""


def _text(el):
    return "".join(t.text or "" for t in el.iter(qn("w:t")))


def _runs(p):
    """Paragraph text with bold spans (character offsets)."""
    text, bold = "", []
    for r in p.iter(qn("w:r")):
        t = "".join(x.text or "" for x in r.iter(qn("w:t")))
        if not t:
            continue
        rp = r.find(qn("w:rPr"))
        b = rp is not None and rp.find(qn("w:b")) is not None and rp.find(qn("w:b")).get(qn("w:val"), "true") not in ("0", "false")
        if b:
            bold.append([len(text), len(text) + len(t)])
        text += t
    return text, bold


def parse_description(text: str) -> dict:
    """The M1 description table: 'Image description  (type)\\n<summary>\\nParts: ...\\nRelations: ...\\nData: ...\\nText in figure: ...'"""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    head = lines[0] if lines else ""
    m = re.match(r"(Image|Table) description\s*\(([^)]*)\)", head)
    d = {"kind": (m.group(1).lower() if m else "image"), "type": (m.group(2).strip() if m else ""), "summary": "", "parts": [], "relations": [], "data": [], "text_in_figure": []}
    body = []
    for l in lines[1:]:
        for key, name in (("Parts:", "parts"), ("Relations:", "relations"), ("Data:", "data"), ("Text in figure:", "text_in_figure"), ("Columns:", "columns"), ("Rows:", None)):
            if l.startswith(key):
                if name:
                    val = l[len(key):].strip()
                    sep = " | " if name == "text_in_figure" else ("; " if name in ("relations", "data") else ", ")
                    d[name] = [x.strip() for x in val.split(sep) if x.strip()]
                break
        else:
            body.append(l)
    d["summary"] = " ".join(body)
    if d["text_in_figure"]:  # M1 sometimes splits words into single letters
        tif = d["text_in_figure"]
        if sum(1 for x in tif if len(x) <= 1) > len(tif) * 0.6:
            d["text_in_figure"] = ["".join(x if x.strip() else " " for x in tif).strip()]
    return d


def read(path):
    doc = docx.Document(path)
    rels = doc.part.rels
    body = doc.element.body
    out, page = [], 0
    images = {}
    panel, last_rule = 0, None   # M1 rules every paragraph of a printed box; the rule colour alternates per box
    for el in body.iterchildren():
        tag = el.tag.split("}")[1]
        if tag == "p":
            style = _style(el)
            text, bold = _runs(el)
            m = re.fullmatch(r"\s*Page\s+(\d+)\s*", text or "")
            # Page marker style. Matched with spaces ignored so "EV Note" and
            # "EVNote" both count. (This was not the cause of the reviewer
            # hang; see PIPELINE_FIX.md. It is kept as a harmless guard.)
            if m and (style or "").replace(" ", "") == "EVNote":
                page = int(m.group(1)); continue
            drawings = []
            for blip in el.iter(A + "blip"):
                rid = blip.get(R + "embed")
                if rid and rid in rels:
                    part = rels[rid].target_part
                    data = part.blob
                    h = hashlib.sha1(data).hexdigest()[:12]
                    from .webimage import to_web
                    data, ext, _problem = to_web(data)   # a TIFF, BMP, EMF or WMF is stored as a PNG a browser can draw
                    images[h] = (data, ext)
                    ext_el = None
                    for e in el.iter("{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}extent"):
                        ext_el = e; break
                    size = (int(ext_el.get("cx")) // 9525, int(ext_el.get("cy")) // 9525) if ext_el is not None else (0, 0)
                    drawings.append({"hash": h, "ext": ext, "size": size})
            maths = list(el.iter(M + "oMath"))
            item = {"kind": "p", "style": style, "text": text, "bold": bold, "page": page}
            rule = None
            for top in el.iterfind(f"{W}pPr/{W}pBdr/{W}top"):
                rule = (top.get(W + "color") or "").upper()
            if rule in ("B9A57E", "B9A57F"):
                if rule != last_rule:
                    panel += 1
                item["panel"] = panel
                last_rule = rule
            elif text.strip() or drawings:
                last_rule = None
            if drawings:
                item["drawings"] = drawings
            if maths:
                item["math"] = [{"latex": to_latex(mm), "plain": plain(mm), "spaces_lost": spaces_lost(mm)} for mm in maths]
            if text.strip() or drawings or maths:
                out.append(item)
        elif tag == "tbl":
            t = Table(el, doc)
            rows = [[c.text.strip() for c in r.cells] for r in t.rows]
            # merged cells repeat in python-docx; drop exact repeats in a row
            rows = [[c for i, c in enumerate(r) if i == 0 or c != r[i - 1] or c == ""] for r in rows]
            if len(rows) == 1 and len(rows[0]) == 1 and re.match(r"(Image|Table) description", rows[0][0]):
                out.append({"kind": "desc", "desc": parse_description(rows[0][0]), "page": page})
            else:
                out.append({"kind": "table", "rows": rows, "page": page})
    return match_columns(out), images


COL_HEAD = re.compile(r"^(?:column\s*)?(?:[A-Z]|I{1,3}|IV)$", re.I)


def match_columns(items):
    """A "match the following" pair of columns printed without rules comes out
    of M1 row by row as loose short lines: A, B, item, item, item, item. Put
    them back into a two column table so a student sees what pairs with what."""
    out, i = [], 0
    while i < len(items):
        a = items[i]; b = items[i + 1] if i + 1 < len(items) else None
        if (b and a["kind"] == b["kind"] == "p" and not a.get("drawings") and not b.get("drawings")
                and COL_HEAD.match(a["text"].strip()) and COL_HEAD.match(b["text"].strip())
                and a["text"].strip().lower() != b["text"].strip().lower()):
            j = i + 2
            while j < len(items):
                x = items[j]
                tx = (x.get("text") or "").strip()
                if x["kind"] != "p" or x.get("drawings") or x.get("math") or not tx or len(tx) > 60 \
                        or tx.endswith((".", "?", ":")) or x.get("style") in ("EVH1", "EVH2", "EVH3") \
                        or x.get("panel") != a.get("panel"):
                    break
                j += 1
            cells = [items[k]["text"].strip() for k in range(i + 2, j)]
            if len(cells) % 2:
                cells = cells[:-1]; j -= 1
            if len(cells) >= 4:
                rows = [[a["text"].strip(), b["text"].strip()]] + [cells[k:k + 2] for k in range(0, len(cells), 2)]
                t = {"kind": "table", "rows": rows, "page": a["page"]}
                if a.get("panel") is not None:
                    t["panel"] = a["panel"]
                out.append(t); i = j; continue
        out.append(a); i += 1
    return out
