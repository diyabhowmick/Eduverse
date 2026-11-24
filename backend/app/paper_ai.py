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
 "answer": "only if the answer is printed on this page, else empty",
 "marks": 0,
 "figures": [[0, 0, 1, 1]],
 "continued": false
}}]}}
Option keys are lower case a, b, c, d in printed order, even if the paper prints (1) (2) (3) (4) or (A) (B). Options often sit several on one line, or follow statements such as A. B. C. D. inside the question: always capture all of them.
Do not repeat the options inside text. Statements labelled A. B. C. D. or (i) (ii) that the options refer to belong in text; the answer choices themselves do not.
Words stay plain words: never use \\textit, \\textbf, \\emph or any other LaTeX outside $ signs, and never put a sentence inside $ signs. Write italic names such as Selaginella as ordinary words. Keep the spaces between words.
Maths exactly as printed: a fraction stays a fraction ($\\frac{{31}}{{11x}}$), a limit keeps its subscript ($\\lim_{{t \\to x}}$), and every power, subscript, sign, bracket and set symbol is kept ($x^{{10}}$, $\\mathbb{{R}}^2$, $(0, \\infty)$). Never simplify, reorder or rewrite. Always pair \\left with \\right.
Keep the paper's layout: each statement, list entry and option on its own line; a system of equations as $$\\begin{{aligned}} ax + by &= 1 \\\\ bx + cy &= -1 \\end{{aligned}}$$ with one equation per line; a long displayed formula on its own line inside $$ signs.
Chemical formulas and ions in maths: $\\mathrm{{H_2SO_4}}$, $\\mathrm{{SO_4^{{2-}}}}$, $\\mathrm{{H_3O^+}}$.
figures holds every part of the question that cannot be written faithfully as text or LaTeX, as boxes [x0, y0, x1, y1] in fractions of image 1 from 0 to 1, in printed order, or [] if there is none. These are always figures: diagrams, graphs, circuits, apparatus, chemical structures, reaction schemes drawn with structures (take the whole scheme with the reagents over and under its arrows), and a List-I / List-II in which any entry is a structure or a graph (take both lists as one figure). Never write a structure in code such as \\chemfig, and never write that part in text as well.
Put [[fig:1]], [[fig:2]] on its own line in text at exactly the place each figure is printed, so the question reads in the same order as the paper. Each box includes the whole figure with all its labels, arrows and axis values, and nothing else. A table of words or numbers is not a figure: write it out in text.
Write a table (for example Match List-I with List-II) on its own lines inside $$ signs as a LaTeX array with ruled borders, one printed row per line:
$$\\begin{{array}}{{|l|l|l|l|}} \\hline \\text{{List-I}} & & \\text{{List-II}} & \\\\ \\hline \\text{{A.}} & \\text{{Lenticels}} & \\text{{(i)}} & \\text{{Phellogen}} \\\\ \\hline \\end{{array}}$$
Put words in a cell inside \\text{{}} and maths in a cell without $ signs. Keep every row and column, in printed order, and the sentence after the table as ordinary text.
If the options are pictures (graphs, circuits, structures), give each option its own figure_box around just its picture, and set its text to any words printed with that picture, or "" if there are none. The question's figures then cover only the question's own figures.
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
    answer = str(q.get("answer") or "").strip()
    if options:
        answer = answer.lower()
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


def read_page(page, i, total, exam, section, model, base_url, key, only=None, paper_id=None):
    which = f"only question numbers {', '.join(only)}, which were missed or lost their options on an earlier read" if only else "every question on this page"
    prompt = READ_PROMPT.format(page=i, pages=total, exam=exam, section=section or "there is no previous page or heading yet", which=which)
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
    """Every printed line of text as a box, in fractions of the page: the labels a diagram may have beside it."""
    r = page.rect
    out = []
    try:
        for b in page.get_text("dict")["blocks"]:
            for ln in b.get("lines", []):
                x0, y0, x1, y1 = ln["bbox"]
                out.append((x0 / r.width, y0 / r.height, x1 / r.width, y1 / r.height))
    except Exception:
        pass
    return out


def snap(box, images, drawn=(), lines=()):
    """Models give rough coordinates. When a real picture or a drawn diagram sits there, use its exact edges.
    A drawn diagram also takes in the short labels printed just beside its lines (R, A, 30 deg, axis values): a text line
    counts only when the whole line sits in that narrow band, so a line of the question's own text never does."""
    x0, y0, x1, y1 = box[0] - .04, box[1] - .04, box[2] + .04, box[3] + .04
    area = (x1 - x0) * (y1 - y0)
    hits, any_drawn = [], False
    for b, is_drawn in [(b, False) for b in images] + [(b, True) for b in drawn]:
        w, h = min(x1, b[2]) - max(x0, b[0]), min(y1, b[3]) - max(y0, b[1])
        size = (b[2] - b[0]) * (b[3] - b[1])
        # Most of the region lies in the model's box, and it is not a whole table grid or block far bigger than the box.
        if w > 0 and h > 0 and w * h >= .3 * size and size <= 3 * area:
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


def crop(doc, page_no, box, images, drawn_cache) -> bytes | None:
    """The figure at box on a page, snapped to what is really printed there, as a PNG at print quality."""
    import pymupdf
    try:
        box = [float(v) for v in box]
    except (TypeError, ValueError):
        return None
    if len(box) != 4 or not (0 < page_no <= len(doc)):
        return None
    pg = doc[page_no - 1]
    if page_no not in drawn_cache:
        drawn_cache[page_no] = (drawn_regions(pg), text_lines(pg))
    box = snap(box, images.get(page_no, []), *drawn_cache[page_no])
    r = pg.rect
    clip = pymupdf.Rect(box[0] * r.width, box[1] * r.height, box[2] * r.width, box[3] * r.height) & r
    if clip.is_empty or clip.width <= 8 or clip.height <= 8:
        return None
    return pg.get_pixmap(dpi=200, clip=clip).tobytes("png")


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
            for data, figs in rows:
                boxes = {o["key"]: o.pop("_box") for o in data["options"] if "_box" in o}
                q = Question(paper_id=paper_id, **data); db.add(q); db.flush()
                # Figure 1 is figure_key, as before; figures 2, 3, ... go in q.figures. A figure that cannot be cut out
                # keeps its place as "", so [[fig:N]] in the text still points at the right one.
                extra = []
                for n, (pg_no, box) in enumerate(figs or [], 1):
                    png = crop(doc, pg_no, box, images, drawn)
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
                        png = crop(doc, data["page"], boxes[o["key"]], images, drawn) if o["key"] in boxes else None
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
