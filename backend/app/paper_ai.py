"""AI reading of question papers. Text extraction loses the maths in papers like JEE, so each page goes to the
OpenAI model as a picture. Answers come from the paper or its key first; the model only fills what is missing,
says how sure it is, and everything still goes past a human before a student sees it.
Runs in its own process: python -m app.paper_ai <paper id> <read|answers>"""
import base64, re, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from .db import SessionLocal
from .models import Book, Question, QuestionPaper, Setting
from .defaults import AI
from .llm_client import openai_json
from .qtext import clean, drop_echoed_options, question_number, strip_option_mark, similar, fig_markers, UNDRAWABLE
from .storage import get_storage

READ_PROMPT = """This is page {page} of {pages} of an exam question paper{exam}. Image 1 is the whole page. Images 2 and 3 are zoomed views of its left and right
halves: read the words and maths from those, and use image 1 for the layout and for figure boxes. On a two column page read the left column top to bottom, then the right.
Copy {which} exactly, ignoring logos, headers and footers.
The section heading in force at the end of the previous page was: {section}. A heading applies only to questions printed after it, so questions above the first heading on this page belong to that section.
Return JSON: {{"questions": [{{
 "number": "the question number exactly as printed, digits only: 7, not Q7 or 7.",
 "section": "the full heading in force for this question, e.g. Mathematics Section B",
 "text": "the question only, never its options, which go in options. Write any table out as described below, and put [[fig:1]], [[fig:2]] where each figure is printed. Write all maths as LaTeX between $ signs, e.g. $x^2+1$. Do not solve or change anything",
 "options": [{{"key": "a", "text": "the option's text only, without its (a) or a. mark, maths in $ signs", "figure_box": null}}],
 "type": "mcq, multi (more than one correct), numeric (no options, the answer is a typed number) or written",
 "marks": 0,
 "figures": [[0, 0, 1, 1]],
 "continued": false
}}]}}
Option keys are lower case a, b, c, d in printed order, even if the paper prints (1) (2) (3) (4) or (A) (B). Options often sit several on one line, or follow statements such as A. B. C. D. inside the question: always capture all of them.
Every option is read in full from the page, formulas included: an option printed only as a formula, such as (B) $-0.67\\,mgR_e$ or (A) $\\frac{{4Mg}}{{k}}$, is written as that formula, never left empty. Read the zoomed images for small subscripts and fractions.
A solved paper prints "Correct Option: A", "Answer:" or "Solution:" and worked steps after each question. None of that is part of the question: leave it out of text and options entirely, including any formulas, figures and diagrams inside a solution, and never make a question of it.
Do not repeat the options inside text. Statements labelled A. B. C. D. or (i) (ii) that the options refer to belong in text; the answer choices themselves do not.
Words stay plain words: never use \\textit, \\textbf, \\emph or any other LaTeX outside $ signs, and never put a sentence inside $ signs. Write italic names such as Selaginella as ordinary words. Keep the spaces between words.
Maths exactly as printed: a fraction stays a fraction ($\\frac{{31}}{{11x}}$), a limit keeps its subscript ($\\lim_{{t \\to x}}$), and every power, subscript, sign, bracket and set symbol is kept ($x^{{10}}$, $\\mathbb{{R}}^2$, $(0, \\infty)$). Never simplify, reorder or rewrite. Always pair \\left with \\right.
Keep the paper's layout: each statement, list entry and option on its own line; a system of equations as $$\\begin{{aligned}} ax + by &= 1 \\\\ bx + cy &= -1 \\end{{aligned}}$$ with one equation per line; a long displayed formula on its own line inside $$ signs.
Chemical formulas, ions and complexes in maths with every subscript and charge: $\\mathrm{{H_2SO_4}}$, $\\mathrm{{SO_4^{{2-}}}}$, $\\mathrm{{H_3O^+}}$, $\\mathrm{{[Co(NH_3)_5Cl]SO_4}}$.
An option printed over several lines keeps those lines: for example "Set-I: ..." on one line and "Set-II: ..." on the next, separated by a line break in its text.
figures holds every part of the question that cannot be written faithfully as text or LaTeX, as boxes [x0, y0, x1, y1] in fractions of image 1 from 0 to 1, in printed order, or [] if there is none. These are always figures: diagrams, graphs, circuits, apparatus, chemical structures, reaction schemes drawn with structures (take the whole scheme with the reagents over and under its arrows), and a List-I / List-II in which any entry is a structure or a graph. For such a list take the whole block, from the List-I and List-II headings to the last entry, as ONE figure, and write nothing of it in text: no table, no reagents, no entries. Never write a structure in code such as \\chemfig.
Never make a figure of something you have written in text: an equation, a reaction or mechanism written with arrows and rate constants, a formula, or a table of words or numbers is written in text only, never also cut out as a figure.
Put [[fig:1]], [[fig:2]] on its own line in text at exactly the place each figure is printed, so the question reads in the same order as the paper. Each box includes the whole figure with all its labels, arrows and axis values, and nothing else: not the question number, not the next question.
Write a table (for example Match List-I with List-II) on its own lines inside $$ signs as a LaTeX array with ruled borders, one printed row per line:
$$\\begin{{array}}{{|l|l|l|l|}} \\hline \\text{{List-I}} & & \\text{{List-II}} & \\\\ \\hline \\text{{A.}} & \\text{{Lenticels}} & \\text{{(i)}} & \\text{{Phellogen}} \\\\ \\hline \\end{{array}}$$
Put words in a cell inside \\text{{}} and maths in a cell without $ signs. Keep every row and column, in printed order, and the sentence after the table as ordinary text.
If the options are pictures (graphs, circuits, structures), give each option its own figure_box around just its picture, which sits beside or just below its own (A), (B), (C) or (D) mark, and set its text to any words printed with that picture, or "" if there are none. The question's figures then cover only the question's own figures.
Keep questions in printed order. Numbering may start again at 1 in a new section or subject: keep the printed number, never renumber.
continued is true only when the question began on the previous page. Never invent a question.
The page edge may cut off the end of a line. Never guess a number, sign, symbol or formula: where any is cut off or cannot be read, write [unclear] at that spot. Only finish a plain English word when it is certain."""

ANSWER_PROMPT = """You are a careful subject expert preparing the answer key for {exam}.
Question{section}: {text}
{options}
Work it out step by step, check the result, then return JSON:
{{"answer": "{format}", "solution": "clear step by step working, maths as LaTeX between $ signs", "confidence": "high, medium or low"}}
Use low when the question is unclear, text is marked [unclear], a figure is needed and missing, or you are unsure."""


def conf(db, answering=False):
    s = db.get(Setting, "ai")
    ai = s.value if s else AI
    p = ai["providers"]["openai"]
    model = (ai.get("answer_model") or AI["answer_model"]) if answering else (ai.get("exam_model") or AI["exam_model"])
    return model, p.get("base_url"), p.get("api_key") or None


def progress(db, p, **kw):
    for k, v in kw.items():
        setattr(p, k, v)
    db.commit()


def norm_options(raw) -> list[dict]:
    """Keys a, b, c, d in printed order whatever the paper printed ((1), (A), a.), each text cleaned and without its own mark."""
    out = []
    for o in raw or []:
        if not isinstance(o, dict):
            continue
        k = str(o.get("key", "")).strip("() .").lower()
        if not re.fullmatch(r"[a-h]", k) or k in {x["key"] for x in out}:
            k = "abcdefgh"[len(out)] if len(out) < 8 else str(len(out) + 1)
        opt = {"key": k, "text": clean(strip_option_mark(k, str(o.get("text", ""))))}
        if re.fullmatch(r"(?i)option\s+[a-d1-4]\s+in the figure\.?|picture|image|figure", opt["text"].strip()):
            opt["text"] = ""
        if isinstance(o.get("figure_box"), list) and len(o["figure_box"]) == 4:
            opt["_box"] = o["figure_box"]  # cropped when the question is saved, then removed
        out.append(opt)
    return out


def norm_question(q: dict, position: int, page: int) -> dict:
    options = norm_options(q.get("options"))
    text = drop_echoed_options(clean(q.get("text")), options)
    qtype = q.get("type") if q.get("type") in ("mcq", "multi", "numeric", "written") else ("mcq" if options else "written")
    if not options and qtype in ("mcq", "multi"):
        qtype = "written"
    if not options and qtype == "written" and re.search(r"_{2,}", text):
        qtype = "numeric"  # a blank to fill and nothing to choose from
    answer = ""  # answers printed in the paper are not taken: they come from an uploaded key, Generate answers, or a person
    try:
        marks = float(q.get("marks") or 0)
    except (TypeError, ValueError):
        marks = 0
    section = str(q.get("section") or "").strip()
    if section.lower() in ("none", "null", "n/a") or section.startswith("there is no"):
        section = ""
    return {"number": question_number(q.get("number")), "section": section[:60], "text": text, "options": options,
            "qtype": qtype, "answer": answer, "answer_source": "paper" if answer else "", "marks": marks, "position": position, "page": page}


def data_url(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode()


def page_images(page) -> list[str]:
    """The whole page plus a zoom of each half. Models shrink a big image, and a shrunk page turns 5/2 into 5/6."""
    import pymupdf
    r = page.rect
    return [data_url(page.get_pixmap(dpi=150).tobytes("png"))] + [
        data_url(page.get_pixmap(dpi=220, clip=pymupdf.Rect(r.x0 + x0 * r.width, r.y0, r.x0 + x1 * r.width, r.y1)).tobytes("png"))
        for x0, x1 in ((0, .54), (.46, 1))]


def note_usage(paper_id, kind, model, usage):
    """Token counts for the cost dashboard, written in their own short session."""
    from . import explain_store as X
    with SessionLocal() as db:
        p = db.get(QuestionPaper, paper_id)
        X.record(db, kind, model, usage, None, p.book_id if p else None, False, "", f"paper {paper_id}")
        db.commit()


REDO_STRUCTURES = ("\nAn earlier read of this question wrote a chemical structure or drawing as code such as \\chemfig, which cannot be shown. "
                   "This time every structure, reaction scheme with structures, and List-I / List-II containing structures must be a figure "
                   "box with [[fig:N]] in text, and none of it written in text.")


def read_page(page, i, total, exam, section, model, base_url, key, only=None, paper_id=None, note=""):
    which = (f"only question number {', '.join(only)}" if note else
             f"only question numbers {', '.join(only)}, which were missed or lost their options on an earlier read") if only else "every question on this page"
    prompt = READ_PROMPT.format(page=i, pages=total, exam=exam, section=section or "there is no previous page or heading yet", which=which) + note
    usage = {}
    found = openai_json(model, prompt, page_images(page), base_url=base_url, api_key=key, usage=usage).get("questions") or []
    if paper_id:
        note_usage(paper_id, "paper_read", model, usage)
    return found


def as_int(number):
    m = re.search(r"\d+", str(number))
    return int(m.group()) if m else 0


def embedded_images(doc):
    """Exact positions of the pictures in the PDF, page by page, without logos repeated on most pages or tiny inline symbols."""
    found, seen = {}, {}
    for i, page in enumerate(doc, 1):
        r = page.rect
        boxes = [tuple(round(v, 3) for v in (b[0] / r.width, b[1] / r.height, b[2] / r.width, b[3] / r.height)) for b in (x["bbox"] for x in page.get_image_info())]
        found[i] = [b for b in boxes if b[2] - b[0] > .06 and b[3] - b[1] > .03]
        for b in set(boxes):
            seen[b] = seen.get(b, 0) + 1
    limit = max(2, len(doc) // 2)
    return {i: [b for b in bs if seen[b] < limit] for i, bs in found.items()}


def drawn_regions(page) -> list[tuple]:
    """Diagrams drawn as lines rather than pasted in as pictures (circuits, ray diagrams, graphs, structures), as fractions
    of the page. Each line of a diagram is its own path, so paths close together are merged into one region. Rules across
    the page, column separators and page frames are left out, since they belong to the layout and not to any question."""
    r = page.rect
    W, H = r.width, r.height
    try:
        paths = page.get_drawings()
    except Exception:
        return []
    rects = []
    for d in paths:
        b = d.get("rect")
        if b is None or b.is_empty and b.width == 0 and b.height == 0:
            continue
        w, h = b.width, b.height
        if (w > .6 * W and h < .02 * H) or (h > .6 * H and w < .02 * W) or w * h > .5 * W * H:
            continue
        rects.append([b.x0, b.y0, b.x1, b.y1])
    if not rects or len(rects) > 4000:
        return []
    gap = 6  # points: lines of one diagram touch or nearly touch
    clusters = []
    for x0, y0, x1, y1 in rects:
        c = [x0, y0, x1, y1]
        merged = True
        while merged:
            merged = False
            for o in clusters:
                if o[0] - gap <= c[2] and c[0] <= o[2] + gap and o[1] - gap <= c[3] and c[1] <= o[3] + gap:
                    c = [min(c[0], o[0]), min(c[1], o[1]), max(c[2], o[2]), max(c[3], o[3])]
                    clusters.remove(o); merged = True
                    break
        clusters.append(c)
    return [(c[0] / W, c[1] / H, c[2] / W, c[3] / H) for c in clusters if c[2] - c[0] > .04 * W and c[3] - c[1] > .02 * H]


def text_lines(page) -> list[tuple]:
    """Every printed line of text as (x0, y0, x1, y1, text), in fractions of the page: the labels a diagram may have
    beside it, and the question numbers and (A) (B) marks used to find where things are."""
    r = page.rect
    out = []
    try:
        for b in page.get_text("dict")["blocks"]:
            for ln in b.get("lines", []):
                x0, y0, x1, y1 = ln["bbox"]
                t = "".join(s.get("text", "") for s in ln.get("spans", []))
                out.append((x0 / r.width, y0 / r.height, x1 / r.width, y1 / r.height, t))
    except Exception:
        pass
    return out


def page_words(page) -> list[tuple]:
    """Every word as (x0, y0, x1, y1, word), in fractions of the page."""
    r = page.rect
    try:
        return [(w[0] / r.width, w[1] / r.height, w[2] / r.width, w[3] / r.height, w[4]) for w in page.get_text("words")]
    except Exception:
        return []


def _qmark(n: str) -> re.Pattern:
    """How a question number is printed at the start of its line: Q.3, Q3, Q 3, Question 3, 3. or 3)"""
    n = re.escape(str(n))
    return re.compile(rf"^\s*(?:Q(?:uestion|ues|n)?\s*\.?\s*{n}(?![0-9])\s*[.):]?|{n}\s*[.)])(?:\s|$)", re.I)


def question_band(lines, number, next_number=None):
    """(top, bottom) of the stretch of the page where question `number` is printed, from its number to the next
    question's, as fractions of the page. None when the number cannot be found at the left of a line."""
    if not as_int(number):
        return None
    lines = sorted(lines, key=lambda l: (l[1], l[0]))
    start = next((l for l in lines if l[0] < .3 and _qmark(number).match(l[4])), None)
    if start is None:
        return None
    end = None
    if next_number and as_int(next_number):
        end = next((l for l in lines if l[1] > start[3] - .002 and l[0] < .3 and _qmark(next_number).match(l[4])), None)
    return (start[1] - .004, (end[1] - .003) if end else .97)


_OPT_LABELS = {k: {f"({u})", f"({k})", f"({d})", f"{u}.", f"{u})", f"{k})", f"{d}.", f"{d})"} for k, u, d in zip("abcdefgh", "ABCDEFGH", "12345678")}


def _in_band(b, band):
    return band is None or band[0] <= (b[1] + b[3]) / 2 <= band[1]


def option_box(key, band, words, regions, images, lines):
    """The picture of option `key`, found from the page itself: its printed mark ((A), (1), A.) inside the question's
    stretch, and the drawing or picture in that mark's cell, which runs right to the next mark on the same row and down
    to the next row of marks. Labels printed in the drawing (OMe, Ph, HO) come with it. None if it cannot be found."""
    if band is None:
        return None
    marks = [w for w in words if _in_band(w, band) and any(w[4] in s for s in _OPT_LABELS.values())]
    mine = [w for w in marks if w[4] in _OPT_LABELS.get(key, ())]
    pics = [b for b in list(regions) + list(images) if _in_band(b, band)]
    for m in mine:
        cy, h = (m[1] + m[3]) / 2, m[3] - m[1]
        right = min([w[0] for w in marks if abs((w[1] + w[3]) / 2 - cy) < 1.5 * h and w[0] > m[2]] or [1.0])
        below = [w[1] for w in marks if w[1] > m[3] + .004 and m[0] - .05 <= w[0] < right]
        above = [w[3] for w in marks if w[3] < m[1] - .004 and m[0] - .05 <= w[0] < right]
        top = max([band[0]] + above)
        bottom = min([band[1]] + below)
        # The picture sits level with its mark or starts just under it; one higher up is the question's own figure.
        level = lambda b: b[1] <= m[3] + .03 and b[3] >= m[1] - .03 or m[3] - .005 <= b[1] <= m[3] + .04
        cell = [b for b in pics if m[0] - .01 <= (b[0] + b[2]) / 2 < right and top <= (b[1] + b[3]) / 2 <= bottom and level(b)]
        if not cell:
            continue
        box = [min(b[0] for b in cell), min(b[1] for b in cell), max(b[2] for b in cell), max(b[3] for b in cell)]
        for l in lines:  # the chemistry or axis labels around the drawing, never the (A) mark itself
            if _OPT_LABELS and any(l[4].strip() in s for s in _OPT_LABELS.values()):
                continue
            if box[0] - .045 <= l[0] and l[2] <= min(box[2] + .045, right) and box[1] - .025 <= l[1] and l[3] <= box[3] + .025:
                box = [min(box[0], l[0]), min(box[1], l[1]), max(box[2], l[2]), max(box[3], l[3])]
        return [box[0] - .006, box[1] - .006, box[2] + .006, box[3] + .006]
    return None


def _page_info(doc, page_no, cache):
    if page_no not in cache:
        pg = doc[page_no - 1]
        cache[page_no] = {"regions": drawn_regions(pg), "lines": text_lines(pg), "words": page_words(pg)}
    return cache[page_no]


def _render(doc, page_no, box) -> bytes | None:
    import pymupdf
    pg = doc[page_no - 1]; r = pg.rect
    clip = pymupdf.Rect(box[0] * r.width, box[1] * r.height, box[2] * r.width, box[3] * r.height) & r
    if clip.is_empty or clip.width <= 8 or clip.height <= 8:
        return None
    return pg.get_pixmap(dpi=200, clip=clip).tobytes("png")


def snap(box, images, drawn=(), lines=()):
    """Models give rough coordinates. When a real picture or a drawn diagram sits there, use its exact edges.
    A drawn diagram also takes in the short labels printed just beside its lines (R, A, 30 deg, axis values): a text line
    counts only when the whole line sits in that narrow band, so a line of the question's own text never does."""
    x0, y0, x1, y1 = box[0] - .025, box[1] - .025, box[2] + .025, box[3] + .025
    area = (x1 - x0) * (y1 - y0)
    hits, any_drawn = [], False
    for b, is_drawn in [(b, False) for b in images] + [(b, True) for b in drawn]:
        w, h = min(x1, b[2]) - max(x0, b[0]), min(y1, b[3]) - max(y0, b[1])
        size = (b[2] - b[0]) * (b[3] - b[1])
        # Most of the region lies in the model's box (a neighbour it only grazes stays out), and it is not a whole
        # table grid or block far bigger than the box.
        if w > 0 and h > 0 and w * h >= .4 * size and size <= 3 * area:
            hits.append(b); any_drawn |= is_drawn
    if not hits:
        return [box[0] - .005, box[1] - .005, box[2] + .005, box[3] + .005]
    out = [min(b[0] for b in hits), min(b[1] for b in hits), max(b[2] for b in hits), max(b[3] for b in hits)]
    if any_drawn:
        bx, by = .03, .02  # about 18 points across, 17 down, on an A4 page
        for l in lines:
            if out[0] - bx <= l[0] and l[2] <= out[2] + bx and out[1] - by <= l[1] and l[3] <= out[3] + by:
                out = [min(out[0], l[0]), min(out[1], l[1]), max(out[2], l[2]), max(out[3], l[3])]
    pad = .006
    return [out[0] - pad, out[1] - pad, out[2] + pad, out[3] + pad]


def crop(doc, page_no, box, images, cache, band=None) -> bytes | None:
    """The figure at box on a page, snapped to what is really printed there, as a PNG at print quality.
    band, when known, is the stretch of the page the question occupies: the figure is kept inside it, so a rough box
    can never take in the next question."""
    try:
        box = [float(v) for v in box]
    except (TypeError, ValueError):
        return None
    if len(box) != 4 or not (0 < page_no <= len(doc)):
        return None
    info = _page_info(doc, page_no, cache)
    regions, imgs, lines = info["regions"], images.get(page_no, []), info["lines"]
    if band and box[1] < band[1] and box[3] > band[0]:  # the box overlaps the question: keep to the question
        box = [box[0], max(box[1], band[0]), box[2], min(box[3], band[1])]
        regions = [b for b in regions if _in_band(b, band)]
        imgs = [b for b in imgs if _in_band(b, band)]
        lines = [l for l in lines if _in_band(l, band)]
    box = snap(box, imgs, regions, lines)
    if band and box[1] < band[1] and box[3] > band[0]:
        box = [box[0], max(box[1], band[0]), box[2], min(box[3], band[1])]
    return _render(doc, page_no, box)


def crop_option(doc, page_no, key, box, images, cache, band=None) -> bytes | None:
    """An option's picture: found from its printed (A) (B) mark when possible, else from the model's box."""
    if not (0 < page_no <= len(doc)):
        return None
    info = _page_info(doc, page_no, cache)
    found = option_box(key, band, info["words"], info["regions"], images.get(page_no, []), info["lines"])
    if found:
        return _render(doc, page_no, found)
    return crop(doc, page_no, box, images, cache, band)


BIG_JUMP = 10  # a gap wider than this is a misread number, not ten skipped questions


def run_ids(rows) -> list[int]:
    """Questions stay in the order they are printed. A paper whose numbering starts again (Physics 1-25, Chemistry 1-25)
    has one run per restart, so Physics Q4 and Chemistry Q4 are two questions, never mixed up or sorted together.
    A number going back counts as a restart only when it goes back to the start (1 to 3) or the section changes;
    otherwise it is a misread number inside the same run."""
    ids, run, prev, prev_sec = [], 0, 0, None
    for d, _ in rows:
        n = as_int(d["number"])
        if n and prev and n < prev and (n <= 3 or d["section"] != prev_sec):
            run += 1
        ids.append(run)
        if n:
            prev, prev_sec = n, d["section"]
    return ids


def numbering(rows):
    """What is wrong with the numbering, run by run: numbers absent, numbers read twice, and jumps too wide to be gaps.
    Also questions without options in a section where nearly all have them."""
    ids = run_ids(rows)
    missing, dupes, jumps, lost = [], [], [], []
    for run in sorted(set(ids)):
        mine = [(i, rows[i][0]) for i in range(len(rows)) if ids[i] == run]
        seen = {}
        for i, d in mine:
            n = as_int(d["number"])
            if n:
                seen.setdefault(n, []).append(i)
        dupes += [(run, n, idx) for n, idx in seen.items() if len(idx) > 1]
        nums = sorted(seen)
        for a, b in zip(nums, nums[1:]):
            if b - a > BIG_JUMP:
                jumps.append((mine[0][1]["section"], a, b))
            else:
                for n in range(a + 1, b):
                    page = next(rows[i][0]["page"] for i in reversed(seen[a]))
                    missing.append({"run": run, "n": n, "page": page, "section": rows[seen[a][-1]][0]["section"]})
        by_section = {}
        for i, d in mine:
            by_section.setdefault(d["section"], []).append(d)
        for ds in by_section.values():
            if len(ds) >= 4 and sum(1 for d in ds if d["options"]) / len(ds) >= .7:
                lost += [{"run": run, "n": as_int(d["number"]), "page": d["page"], "section": d["section"]} for d in ds if not d["options"] and as_int(d["number"])]
    return missing, lost, dupes, jumps


def needs_reread(rows):
    missing, lost, _, _ = numbering(rows)
    return missing, lost


def merge_duplicates(rows) -> list[str]:
    """The same question read twice, usually across a page break, is kept once: the fuller reading wins.
    Two different questions printed with the same number are both kept, and reported."""
    report = []
    while True:
        _, _, dupes, _ = numbering(rows)
        for run, n, idx in dupes:
            a, b = idx[0], idx[1]
            da, db_ = rows[a][0], rows[b][0]
            if not similar(da["text"], db_["text"]):
                continue
            keep, drop = (a, b) if (len(da["options"]), len(da["text"])) >= (len(db_["options"]), len(db_["text"])) else (b, a)
            box = rows[keep][1] or rows[drop][1]
            rows[keep] = (rows[keep][0], box)
            del rows[drop]
            break
        else:
            for run, n, idx in dupes:
                sec = rows[idx[0]][0]["section"]
                report.append(f"Question {n}{' in ' + sec if sec else ''} is printed twice with different text. Check its number against the original.")
            return report


def place(rows, run: int, n: int, d: dict, box):
    """Puts a re-read question back where it is printed: after the question before it in the same run."""
    ids = run_ids(rows)
    same = [i for i in range(len(rows)) if ids[i] == run]
    hit = next((i for i in same if as_int(rows[i][0]["number"]) == n), None)
    if hit is not None:
        if d["options"] and not rows[hit][0]["options"]:
            rows[hit] = (d, box or rows[hit][1])
        return
    before = [i for i in same if 0 < as_int(rows[i][0]["number"]) < n]
    at = (before[-1] + 1) if before else (same[0] if same else len(rows))
    rows.insert(at, (d, box))


def figure_boxes(q: dict, page: int) -> list[tuple]:
    """The question's figures as (page, box), in printed order. An older reply gives one figure_box instead."""
    raw = q.get("figures")
    if not isinstance(raw, list) or (len(raw) == 4 and all(isinstance(v, (int, float)) for v in raw)):
        raw = [raw] if isinstance(raw, list) and raw else []
    if not raw and isinstance(q.get("figure_box"), list):
        raw = [q["figure_box"]]
    return [(page, b) for b in raw if isinstance(b, list) and len(b) == 4]


def with_figures(d: dict, q: dict, page: int, offset: int = 0) -> list[tuple]:
    """Matches the [[fig:N]] marks in the text to the figures the page really has, and returns those figures."""
    boxes = figure_boxes(q, page)
    d["text"] = fig_markers(d["text"], len(boxes), offset)
    return boxes


def add_rows(rows, found, i, section):
    for q in found:
        if q.get("continued") and rows:
            last, have = rows[-1]
            more = norm_question(q, 0, i)
            boxes = with_figures(more, q, i, offset=len(have or []))  # its figures number on from the first page's
            last["options"] += [o for o in more["options"] if o["key"] not in {x["key"] for x in last["options"]}]
            last["text"] = drop_echoed_options((last["text"] + "\n" + more["text"]).strip(), last["options"])
            rows[-1] = (last, (have or []) + boxes)
            continue
        if str(q.get("text") or "").strip() or q.get("options"):
            d = norm_question(q, len(rows), i)
            d["section"] = d["section"] or section
            section = d["section"]
            rows.append((d, with_figures(d, q, i)))
    return section


def read(paper_id: int):
    import pymupdf
    db = SessionLocal()
    try:
        p = db.get(QuestionPaper, paper_id)
        pack = db.get(Book, p.book_id)
        model, base_url, key = conf(db)
        store = get_storage()
        exam = f" for {pack.exam}" if pack and pack.exam else ""
        with pymupdf.open(stream=store.get(p.source_key), filetype="pdf") as doc:
            total = len(doc)
            progress(db, p, ai_status="running", ai_stage="Reading pages", ai_done=0, ai_total=total, ai_error="")
            rows, section = [], ""
            for i, page in enumerate(doc, 1):
                section = add_rows(rows, read_page(page, i, total, exam, section, model, base_url, key, paper_id=paper_id), i, section)
                progress(db, p, ai_done=i)
            merge_duplicates(rows)
            # A model skipping a question must not go unnoticed: ask again for exactly what is absent.
            for _ in range(2):
                missing, lost = needs_reread(rows)
                if not missing and not lost:
                    break
                progress(db, p, ai_stage="Checking for missed questions", ai_done=0, ai_total=0)
                pages = {}  # page -> {number: what is wanted}
                for m in missing:
                    for pg in {m["page"], min(m["page"] + 1, total)}:
                        pages.setdefault(pg, {}).setdefault(m["n"], m)
                for m in lost:
                    pages.setdefault(m["page"], {}).setdefault(m["n"], m)
                for pg, want in sorted(pages.items()):
                    prior = next((d["section"] for d, _ in reversed(rows) if d["page"] < pg), "")
                    for q in read_page(doc[pg - 1], pg, total, exam, prior, model, base_url, key, only=[str(n) for n in sorted(want)], paper_id=paper_id):
                        w = want.get(as_int(question_number(q.get("number"))))
                        if not w:
                            continue
                        q["continued"] = False
                        d = norm_question(q, 0, pg)
                        d["section"] = d["section"] or w["section"] or prior
                        place(rows, w["run"], w["n"], d, with_figures(d, q, pg))
                merge_duplicates(rows)
            # A structure written as code (\chemfig) can never be shown. Ask once more for just that question, saying why.
            bad = [(idx, d) for idx, (d, _) in enumerate(rows) if UNDRAWABLE.search(d["text"] + " ".join(o["text"] for o in d["options"]))]
            if bad:
                progress(db, p, ai_stage="Redoing questions with structures", ai_done=0, ai_total=len(bad))
            for done_n, (idx, d) in enumerate(bad, 1):
                again = read_page(doc[d["page"] - 1], d["page"], total, exam, d["section"], model, base_url, key, only=[d["number"]], paper_id=paper_id,
                                  note=REDO_STRUCTURES)
                for q in again:
                    if as_int(question_number(q.get("number"))) != as_int(d["number"]):
                        continue
                    q["continued"] = False
                    nd = norm_question(q, d["position"], d["page"])
                    nd["section"] = d["section"]
                    if not UNDRAWABLE.search(nd["text"] + " ".join(o["text"] for o in nd["options"])):
                        rows[idx] = (nd, with_figures(nd, q, d["page"]))
                    break
                progress(db, p, ai_done=done_n)
            # Printed order, never sorted by number: sorting mixed up papers whose sections each start again at 1.
            for pos, (d, _) in enumerate(rows):
                d["position"] = pos
            twice = merge_duplicates(rows)
            missing, lost, _, jumps = numbering(rows)
            # Only now, with every page read, does the earlier attempt get replaced. A failure above keeps it.
            for q in db.query(Question).filter(Question.paper_id == paper_id).all():
                db.delete(q)
            db.flush()
            images, drawn = embedded_images(doc), {}
            undrawable = []
            for idx, (data, figs) in enumerate(rows):
                boxes = {o["key"]: o.pop("_box") for o in data["options"] if "_box" in o}
                q = Question(paper_id=paper_id, **data); db.add(q); db.flush()
                # Where this question sits on its first page, from its printed number to the next question's.
                nxt = rows[idx + 1][0]["number"] if idx + 1 < len(rows) and rows[idx + 1][0]["page"] == data["page"] else None
                band = question_band(_page_info(doc, data["page"], drawn)["lines"], data["number"], nxt) if 0 < data["page"] <= len(doc) else None
                # Figure 1 is figure_key, as before; figures 2, 3, ... go in q.figures. A figure that cannot be cut out
                # keeps its place as "", so [[fig:N]] in the text still points at the right one.
                extra = []
                for n, (pg_no, box) in enumerate(figs or [], 1):
                    png = crop(doc, pg_no, box, images, drawn, band if pg_no == data["page"] else None)
                    key_n = f"papers/{p.book_id}/figures/{paper_id}_{q.id}.png" if n == 1 else f"papers/{p.book_id}/figures/{paper_id}_{q.id}_f{n}.png"
                    if png:
                        store.put(key_n, png)
                    if n == 1:
                        q.figure_key = key_n if png else ""
                    else:
                        extra.append(key_n if png else "")
                q.figures = extra
                if UNDRAWABLE.search(q.text + " ".join(o.get("text", "") for o in data["options"])):
                    undrawable.append(q.number or str(len(undrawable) + 1))
                if boxes:
                    opts = []
                    for o in data["options"]:
                        o = dict(o)
                        png = crop_option(doc, data["page"], o["key"], boxes[o["key"]], images, drawn, band) if o["key"] in boxes else None
                        if png:
                            o["figure"] = f"papers/{p.book_id}/figures/{paper_id}_{q.id}_{o['key']}.png"
                            store.put(o["figure"], png)
                        opts.append(o)
                    q.options = opts
        def named(ms):
            return ", ".join(f"{m['n']}" + (f" ({m['section']})" if m["section"] else "") for m in ms)
        warn = []
        if missing:
            warn.append("Still missing after checking again: question " + named(missing) + ". Add them by hand.")
        if lost:
            warn.append("No options found for question " + named(lost) + ". Check them against the original.")
        for sec, a, b in jumps:
            warn.append(f"Numbering jumps from {a} to {b}{' in ' + sec if sec else ''}. One of these numbers may be misread; check it against the original.")
        warn += twice
        if undrawable:
            warn.append("Question " + ", ".join(undrawable) + " has a chemical structure or drawing written as code, which cannot be shown. "
                        "Use Redo figure to cut it from the original page, then delete that code from the question text.")
        progress(db, p, ai_status="done", ai_stage="Read", ai_done=total, ai_total=total, ai_error=" ".join(warn))
    except Exception as e:
        db.rollback(); p = db.get(QuestionPaper, paper_id)
        progress(db, p, ai_status="failed", ai_error=str(e)[:800])
    finally:
        db.close()


def ask_answer(q, exam, model, base_url, key, figure, option_figures=None, extra_figures=()):
    """One model request. Runs on a worker thread, so it touches no database objects.
    figure is the question's figure 1, extra_figures its figures 2, 3, ...; option_figures maps an option key to its picture."""
    images, n, named = [], 0, []
    for k, pic in enumerate([figure, *extra_figures], 1):
        if pic:
            images.append(data_url(pic)); n += 1
            named.append(f"[[fig:{k}]] is image {n}")
    lines = []
    for o in q["options"]:
        pic = (option_figures or {}).get(o["key"])
        if pic:
            images.append(data_url(pic)); n += 1
        lines.append(f"({o['key']}) {o['text']}" + (f" [the picture in image {n}]" if pic else ""))
    opts = "Options:\n" + "\n".join(lines) if lines else ""
    text = q["text"] + (f"\n(The figures: {'; '.join(named)}.)" if named else "")
    fmt = {"mcq": "the single option letter", "multi": "the correct option letters separated by commas",
           "numeric": "the final number only"}.get(q["qtype"], "a short final answer")
    usage = {}
    r = openai_json(model, ANSWER_PROMPT.format(exam=exam, section=f" ({q['section']})" if q["section"] else "", text=text, options=opts, format=fmt),
                    images, base_url=base_url, api_key=key, timeout=600, usage=usage)
    return r, usage


def answers(paper_id: int):
    """Fills only the questions with no answer. One question failing does not lose the others."""
    db = SessionLocal()
    try:
        p = db.get(QuestionPaper, paper_id)
        pack = db.get(Book, p.book_id)
        model, base_url, key = conf(db, answering=True)
        exam = (pack.exam if pack else "") or "this exam"
        todo = db.query(Question).filter(Question.paper_id == paper_id, Question.answer == "").order_by(Question.position).all()
        progress(db, p, ai_status="running", ai_stage="Writing answers", ai_done=0, ai_total=len(todo), ai_error="")
        store, failed, done = get_storage(), 0, 0
        with ThreadPoolExecutor(max_workers=6) as pool:
            jobs = {pool.submit(ask_answer, {"options": q.options or [], "qtype": q.qtype, "section": q.section, "text": q.text}, exam, model, base_url, key,
                                store.get(q.figure_key) if q.figure_key else None,
                                {o["key"]: store.get(o["figure"]) for o in q.options or [] if o.get("figure")},
                                [store.get(k) if k else None for k in q.figures or []]): q for q in todo}
            for job in as_completed(jobs):
                q = jobs[job]
                try:
                    r, usage = job.result()
                    from . import explain_store as X
                    X.record(db, "paper_answers", model, usage, None, p.book_id, False, "", f"paper {paper_id}")
                    answer = str(r.get("answer") or "").strip()
                    c = str(r.get("confidence") or "").lower()
                    q.solution, q.confidence = str(r.get("solution") or ""), c if c in ("high", "medium", "low") else "low"
                    if q.options:
                        answer = answer.lower().strip("() ")
                        if not {x.strip() for x in answer.split(",")} <= {o["key"] for o in q.options}:
                            answer, q.confidence = "", "low"  # not one of the printed options: leave it for the reviewer
                    q.answer, q.answer_source = answer, "ai" if answer else ""
                except Exception as e:
                    failed += 1
                    p.ai_error = f"{failed} question(s) could not be answered. Last error: {str(e)[:400]}"
                done += 1
                progress(db, p, ai_done=done)
        progress(db, p, ai_status="failed" if todo and failed == len(todo) else "done", ai_stage="Answers written")
    except Exception as e:
        db.rollback(); p = db.get(QuestionPaper, paper_id)
        progress(db, p, ai_status="failed", ai_error=str(e)[:800])
    finally:
        db.close()


if __name__ == "__main__":
    {"read": read, "answers": answers}[sys.argv[2]](int(sys.argv[1]))
