"""Reads an M1 flow .docx into an ordered list of raw elements. No interpretation here."""
import hashlib, re
import docx
from docx.oxml.ns import qn
from docx.table import Table
from .omml import M, to_latex, plain, spaces_lost

A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


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
    for el in body.iterchildren():
        tag = el.tag.split("}")[1]
        if tag == "p":
            style = _style(el)
            text, bold = _runs(el)
            m = re.fullmatch(r"\s*Page\s+(\d+)\s*", text or "")
            # M1 writes this style as "EV Note"; some documents report it
            # without the space. Accept both, or every page marker is missed
            # and every block ends up on page 0.
            if m and (style or "").replace(" ", "") == "EVNote":
                page = int(m.group(1)); continue
            drawings = []
            for blip in el.iter(A + "blip"):
                rid = blip.get(R + "embed")
                if rid and rid in rels:
                    part = rels[rid].target_part
                    data = part.blob
                    h = hashlib.sha1(data).hexdigest()[:12]
                    ext = part.partname.ext or "png"
                    images[h] = (data, ext)
                    ext_el = None
                    for e in el.iter("{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}extent"):
                        ext_el = e; break
                    size = (int(ext_el.get("cx")) // 9525, int(ext_el.get("cy")) // 9525) if ext_el is not None else (0, 0)
                    drawings.append({"hash": h, "ext": ext, "size": size})
            maths = list(el.iter(M + "oMath"))
            item = {"kind": "p", "style": style, "text": text, "bold": bold, "page": page}
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
    return out, images
