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
from .storage import get_storage

READ_PROMPT = """This is page {page} of {pages} of an exam question paper{exam}. Image 1 is the whole page. Images 2 and 3 are zoomed views of its left and right
halves: read the words and maths from those, and use image 1 for the layout and for figure_box. On a two column page read the left column top to bottom, then the right.
Copy {which} exactly, ignoring logos, headers and footers.
The section heading in force at the end of the previous page was: {section}. A heading applies only to questions printed after it, so questions above the first heading on this page belong to that section.
Return JSON: {{"questions": [{{
 "number": "question number as printed",
 "section": "the full heading in force for this question, e.g. Mathematics Section B",
 "text": "the question, with any table written out. Write all maths as LaTeX between $ signs, e.g. $x^2+1$. Do not solve or change anything",
 "options": [{{"key": "a", "text": "option, maths in $ signs"}}],
 "type": "mcq, multi (more than one correct), numeric (no options, the answer is a typed number) or written",
 "answer": "only if the answer is printed on this page, else empty",
 "marks": 0,
 "figure_box": [0, 0, 1, 1],
 "continued": false
}}]}}
Option keys are lower case a, b, c, d in printed order, even if the paper prints (1) (2) (3) (4) or (A) (B). Options often sit several on one line, or follow statements such as A. B. C. D. inside the question: always capture all of them.
figure_box is the diagram that belongs to the question, as fractions of image 1 from 0 to 1, or null if there is none. A table is not a diagram: write it out in the text as a LaTeX array, with null here. If the options are pictures, make figure_box include all of them and set each option's text to "Option A in the figure", and so on.
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


def clean(text: str) -> str:
    """A LaTeX \\text or \\newline can arrive with its backslash read as a tab or line break, or as stray HTML."""
    text = text.replace("\t" + "ext", "\\text").replace("\\newline", "\n").replace("</br>", "\n").replace("<br>", "\n").replace("<br/>", "\n")
    return "\n".join(f"${l.strip()}$" if "\\" in l and "$" not in l else l for l in text.split("\n"))


def maths(text: str) -> str:
    """Some models drop the $ signs on an option that is all maths, such as \\frac{1}{2}."""
    return f"${text}$" if "\\" in text and "$" not in text else text


def norm_question(q: dict, position: int, page: int) -> dict:
    options = [{"key": str(o.get("key", "")).lower(), "text": maths(clean(str(o.get("text", ""))))} for o in q.get("options") or [] if isinstance(o, dict)]
    qtype = q.get("type") if q.get("type") in ("mcq", "multi", "numeric", "written") else ("mcq" if options else "written")
    if not options and qtype == "mcq":
        qtype = "written"
    if not options and qtype == "written" and re.search(r"_{2,}", str(q.get("text") or "")):
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
    return {"number": str(q.get("number") or "").strip(" .):")[:20], "section": section[:60], "text": clean(str(q.get("text") or "")), "options": options,
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


def snap(box, images):
    """Models give rough coordinates. When a real picture sits there, use the picture's exact edges."""
    x0, y0, x1, y1 = box[0] - .04, box[1] - .04, box[2] + .04, box[3] + .04
    hits = []
    for b in images:
        w, h = min(x1, b[2]) - max(x0, b[0]), min(y1, b[3]) - max(y0, b[1])
        if w > 0 and h > 0 and w * h >= .3 * (b[2] - b[0]) * (b[3] - b[1]):
            hits.append(b)
    if not hits:
        return box
    return [min(b[0] for b in hits), min(b[1] for b in hits), max(b[2] for b in hits), max(b[3] for b in hits)]


def needs_reread(rows):
    """Question numbers absent from the run, and questions without options in a section where nearly all have them."""
    nums = sorted(n for n in (as_int(d["number"]) for d, _ in rows) if n)
    missing = [n for n in range(nums[0], nums[-1] + 1) if n not in nums] if nums else []
    lost, by_section = [], {}
    for d, _ in rows:
        by_section.setdefault(d["section"], []).append(d)
    for ds in by_section.values():
        if len(ds) >= 4 and sum(1 for d in ds if d["options"]) / len(ds) >= .7:
            lost += [as_int(d["number"]) for d in ds if not d["options"]]
    return missing, lost


def add_rows(rows, found, i, section):
    for q in found:
        if q.get("continued") and rows:
            rows[-1][0]["text"] = (rows[-1][0]["text"] + " " + str(q.get("text") or "")).strip()
            rows[-1][0]["options"] += norm_question(q, 0, i)["options"]
            continue
        if str(q.get("text") or "").strip() or q.get("options"):
            d = norm_question(q, len(rows), i)
            d["section"] = d["section"] or section
            section = d["section"]
            rows.append((d, q.get("figure_box")))
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
            # A model skipping a question must not go unnoticed: ask again for exactly what is absent.
            for _ in range(2):
                missing, lost = needs_reread(rows)
                if not missing and not lost:
                    break
                progress(db, p, ai_stage="Checking for missed questions", ai_done=0, ai_total=0)
                pages = {}
                for n in missing + lost:
                    before = [d["page"] for d, _ in rows if 0 < as_int(d["number"]) <= n]
                    start = max(before) if before else 1
                    for pg in {start, min(start + 1, total)}:
                        pages.setdefault(pg, set()).add(n)
                for pg, nums in sorted(pages.items()):
                    prior = next((d["section"] for d, _ in reversed(rows) if d["page"] < pg), "")
                    for q in read_page(doc[pg - 1], pg, total, exam, prior, model, base_url, key, only=[str(n) for n in sorted(nums)], paper_id=paper_id):
                        n = as_int(q.get("number"))
                        if n not in nums:
                            continue
                        q["continued"] = False
                        d = norm_question(q, 0, pg)
                        d["section"] = d["section"] or prior
                        cur = next((r for r in rows if as_int(r[0]["number"]) == n), None)
                        if cur is None:
                            rows.append((d, q.get("figure_box")))
                        elif d["options"] and not cur[0]["options"]:
                            rows[rows.index(cur)] = (d, q.get("figure_box") or cur[1])
            rows.sort(key=lambda r: as_int(r[0]["number"]))
            for pos, (d, _) in enumerate(rows):
                d["position"] = pos
            missing, lost = needs_reread(rows)
            # Only now, with every page read, does the earlier attempt get replaced. A failure above keeps it.
            for q in db.query(Question).filter(Question.paper_id == paper_id).all():
                db.delete(q)
            db.flush()
            images = embedded_images(doc)
            for data, box in rows:
                q = Question(paper_id=paper_id, **data); db.add(q); db.flush()
                if isinstance(box, list) and len(box) == 4:
                    try:
                        box = snap([float(v) for v in box], images.get(data["page"], []))
                        pg = doc[data["page"] - 1]; r = pg.rect
                        clip = pymupdf.Rect(box[0] * r.width, box[1] * r.height, box[2] * r.width, box[3] * r.height) & r
                        if clip.width > 8 and clip.height > 8:
                            q.figure_key = f"papers/{p.book_id}/figures/{paper_id}_{q.id}.png"
                            store.put(q.figure_key, pg.get_pixmap(dpi=200, clip=clip).tobytes("png"))
                    except (TypeError, ValueError):
                        pass
        warn = []
        if missing:
            warn.append("Still missing after checking again: question " + ", ".join(map(str, missing)) + ". Add them by hand.")
        if lost:
            warn.append("No options found for question " + ", ".join(map(str, lost)) + ". Check them against the original.")
        progress(db, p, ai_status="done", ai_stage="Read", ai_done=total, ai_total=total, ai_error=" ".join(warn))
    except Exception as e:
        db.rollback(); p = db.get(QuestionPaper, paper_id)
        progress(db, p, ai_status="failed", ai_error=str(e)[:800])
    finally:
        db.close()


def ask_answer(q, exam, model, base_url, key, figure):
    """One model request. Runs on a worker thread, so it touches no database objects."""
    opts = "Options:\n" + "\n".join(f"({o['key']}) {o['text']}" for o in q["options"]) if q["options"] else ""
    fmt = {"mcq": "the single option letter", "multi": "the correct option letters separated by commas",
           "numeric": "the final number only"}.get(q["qtype"], "a short final answer")
    usage = {}
    r = openai_json(model, ANSWER_PROMPT.format(exam=exam, section=f" ({q['section']})" if q["section"] else "", text=q["text"], options=opts, format=fmt),
                    [data_url(figure)] if figure else [], base_url=base_url, api_key=key, timeout=600, usage=usage)
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
                                store.get(q.figure_key) if q.figure_key else None): q for q in todo}
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
