"""Exam packs: past question papers, chapter tagging, reviewer approval, and the student side
(papers by year window, topic-wise questions, chapter weightage, quick recap, mock tests)."""
import os, random, subprocess, sys, threading, uuid
from collections import Counter, defaultdict
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..db import get_db
from pathlib import Path
from fastapi import Response
from ..config import BASE
from ..db import SessionLocal
from ..models import Book, QuestionPaper, Question, MockAttempt, Setting
from ..security import require
from ..storage import get_storage
from ..audit import log
from ..defaults import AI
from .. import papers as P
from .. import content as C

router = APIRouter(prefix="/api/exams", tags=["exams"])
srouter = APIRouter(prefix="/api/student/exams", tags=["student exams"])
staff = require("super_admin", "reviewer")
sa = require("super_admin")
student = require("student")


# ---------------- shared ----------------
def pack_of(db, bid) -> Book:
    b = db.get(Book, bid)
    if not b or b.track != "exam":
        raise HTTPException(404, "Exam pack not found")
    return b


def public_options(options) -> list[dict]:
    """Options as the screen gets them: a picture option says it has one, never where it is stored."""
    return [{"key": o.get("key", ""), "text": o.get("text", ""), **({"has_figure": True} if o.get("figure") else {})} for o in options or []]


def keep_option_figures(old, new) -> list[dict]:
    """An edit sends options back without their stored pictures. Each option keeps its picture, matched by key."""
    pics = {o.get("key"): o["figure"] for o in old or [] if o.get("figure")}
    return [{"key": o.get("key", ""), "text": o.get("text", ""), **({"figure": pics[o.get("key")]} if o.get("key") in pics else {})} for o in new or []]


def q_out(q: Question, answers=True):
    d = {"id": q.id, "number": q.number, "section": q.section, "text": q.text, "options": public_options(q.options), "marks": q.marks,
         "chapter": q.chapter, "chapter_ref": q.chapter_ref or {}, "paper_id": q.paper_id, "qtype": q.qtype or ("mcq" if q.options else "written"),
         "page": q.page or 0, "has_figure": bool(q.figure_key),
         "more_figures": [n for n, k in enumerate(q.figures or [], 2) if k]}  # figures 2, 3, ... that exist
    if answers:
        d.update(answer=q.answer, solution=q.solution, answer_source=q.answer_source or "", confidence=q.confidence or "")
    return d


def paper_out(p: QuestionPaper, n=None):
    return {"id": p.id, "book_id": p.book_id, "year": p.year, "session": p.session, "title": p.title or f"{p.year} {p.session}".strip(),
            "status": p.status, "review_note": p.review_note, "reviewed_by": p.reviewed_by, "questions": n, "created_at": p.created_at,
            "is_pdf": (p.source_key or "").lower().endswith(".pdf"),
            "ai": {"status": p.ai_status or "", "stage": p.ai_stage or "", "done": p.ai_done or 0, "total": p.ai_total or 0, "error": p.ai_error or ""}}


def chapter_idx(db, pack: Book):
    data = []
    for bid in pack.linked_book_ids or []:
        b = db.get(Book, bid)
        if b and b.content_key:
            try:
                data.append((b.id, C.load(b)))
            except Exception:
                pass
    return P.chapter_index(data)


def retag(db, pack: Book, qs):
    idx = chapter_idx(db, pack)
    n = 0
    for q in qs:
        right = " ".join(o.get("text", "") for o in (q.options or []) if (o.get("key") or "").lower() == (q.answer or "").strip().lower())
        text = " ".join([q.text or "", " ".join(o.get("text", "") for o in (q.options or [])), right,
                         (q.answer or "") if not q.options else "", q.solution or ""])
        t = P.tag(text, idx) if idx else None
        if t:
            q.chapter, q.chapter_ref = t["title"], {"book_id": t["book_id"], "chapter": t["chapter"]}; n += 1
    return n


# ---------------- super admin: papers ----------------
@router.get("/{bid}/papers")
def list_papers(bid: int, db: Session = Depends(get_db), _=Depends(staff)):
    pack = pack_of(db, bid)
    counts = Counter(q.paper_id for q in db.query(Question).join(QuestionPaper).filter(QuestionPaper.book_id == bid))
    ps = db.query(QuestionPaper).filter(QuestionPaper.book_id == bid).order_by(QuestionPaper.year.desc(), QuestionPaper.session).all()
    linked = [{"id": b.id, "title": b.title} for b in db.query(Book).filter(Book.id.in_(pack.linked_book_ids or [0]))]
    return {"pack": {"id": pack.id, "title": pack.title, "exam": pack.exam, "board": pack.board, "level": pack.level, "status": pack.status, "linked": linked},
            "papers": [paper_out(p, counts.get(p.id, 0)) for p in ps]}


def make_paper(db, pack: Book, me, year: int, session: str, title: str, text: str, name: str, data: bytes, key_name: str = "", key_data: bytes = b""):
    if not 1950 <= year <= datetime.utcnow().year + 1:
        raise HTTPException(422, "Year looks wrong")
    key = ""
    if name:
        name = Path(name).name
        if not data:
            raise HTTPException(422, "The file is empty")
        from .. import hardening as H
        H.check_upload(name, data[:4096], len(data), (".pdf", ".docx", ".txt"))
        if name.lower().endswith(".pdf"):
            if H._PDF_ACTIVE.search(data):
                raise HTTPException(422, "This PDF contains scripts or embedded programs, so it was refused. Print it to a new PDF and upload that.")
        try:
            text = P.read_text_safe(name, data)
        except Exception as e:
            raise HTTPException(422, f"Could not read this file: {str(e)[:120]}")
        key = f"papers/{pack.id}/{uuid.uuid4().hex}_{name}"
        get_storage().put(key, data)
    qs = P.split_questions(text or "")
    matched = 0
    if key_name:
        try:
            matched = P.apply_key(qs, P.parse_key(P.read_text_safe(Path(key_name).name, key_data, tables=False)))
        except Exception as e:
            raise HTTPException(422, f"Could not read the answer key: {str(e)[:120]}")
    p = QuestionPaper(book_id=pack.id, year=year, session=session.strip(), title=title.strip(), source_key=key, status="draft")
    db.add(p); db.flush()
    rows = [Question(paper_id=p.id, position=i, **q) for i, q in enumerate(qs)]
    db.add_all(rows); db.flush()
    holes = P.lost_maths(qs)
    if holes:
        p.ai_error = ("The formulas in this file are drawn as pictures, so reading its text left gaps in questions and empty options. "
                      "Press Read with AI to read every page as an image and get the formulas, options and diagrams as printed.")
    tagged = retag(db, pack, rows)
    log(db, me, "paper.create", "paper", p.id, pack=pack.title, year=year, questions=len(rows))
    db.commit()
    return {**paper_out(p, len(rows)), "found": len(rows), "tagged": tagged, "key_matched": matched,
            "warning": p.ai_error if holes else "" if rows else "No numbered questions were found. Use Read with AI, or add them by hand."}


@router.post("/{bid}/papers")
async def add_paper(bid: int, year: int = Form(...), session: str = Form(""), title: str = Form(""), text: str = Form(""),
                    file: UploadFile | None = File(None), db: Session = Depends(get_db), me=Depends(sa)):
    pack = pack_of(db, bid)
    has_file = file is not None and file.filename
    return make_paper(db, pack, me, year, session, title, text, file.filename if has_file else "", await file.read() if has_file else b"")


@router.post("/test-sets")
async def add_test_set(exam: str = Form(...), level: str = Form("competitive"), board: str = Form(""), grade: str = Form(""), subject: str = Form(""),
                       university: str = Form(""), course: str = Form(""), semester: str = Form(""), price: float = Form(0), year: int = Form(...),
                       session: str = Form(""), title: str = Form(""), text: str = Form(""), file: UploadFile | None = File(None),
                       key_file: UploadFile | None = File(None), cover: UploadFile | None = File(None),
                       db: Session = Depends(get_db), me=Depends(sa)):
    """Add content: one exam test set. Joins the exam's pack, or creates that pack, then adds the paper to it."""
    exam, subject = exam.strip(), subject.strip()
    if not exam:
        raise HTTPException(422, "Choose which exam this is for")
    if level not in ("school", "degree", "competitive"):
        raise HTTPException(422, "Level must be school, degree or competitive")
    has_file = file is not None and file.filename
    if not has_file and not text.strip():
        raise HTTPException(422, "Upload the question paper or paste it")
    if price < 0:
        raise HTTPException(422, "The price cannot be negative")
    pack = db.query(Book).filter(Book.track == "exam", Book.exam == exam, Book.level == level, Book.board == board, Book.grade == grade,
                                 Book.subject == subject, Book.university == university, Book.course == course, Book.semester == semester).first()
    if not pack:
        pack = Book(title=" ".join(x for x in (exam, subject) if x), subject=subject, board=board, grade=grade, track="exam", level=level, exam=exam,
                    university=university, course=course, semester=semester, price=price, status="upcoming", content_type="exam")
        db.add(pack); db.flush()
        log(db, me, "book.create", "book", pack.id, title=pack.title)
    elif price:
        pack.price = price
    if cover is not None and cover.filename:
        from .books import save_cover
        save_cover(pack, cover.filename, await cover.read())
    has_key = key_file is not None and key_file.filename
    return make_paper(db, pack, me, year, session, title, text, file.filename if has_file else "", await file.read() if has_file else b"",
                      key_file.filename if has_key else "", await key_file.read() if has_key else b"")


@router.get("/papers/{pid}")
def get_paper(pid: int, db: Session = Depends(get_db), _=Depends(staff)):
    p = db.get(QuestionPaper, pid)
    if not p:
        raise HTTPException(404, "Paper not found")
    pack = db.get(Book, p.book_id)
    qs = db.query(Question).filter(Question.paper_id == pid).order_by(Question.position, Question.id).all()
    chapters = sorted({(t[1], t[2]) for t in chapter_idx(db, pack)}, key=lambda x: (str(x[0]), x[1])) if pack else []
    return {**paper_out(p, len(qs)), "pack": pack.title if pack else "", "questions": [q_out(q) for q in qs],
            "chapters": [{"number": n, "title": t} for n, t in chapters]}


class QIn(BaseModel):
    number: str | None = None
    section: str | None = None
    text: str | None = None
    options: list[dict] | None = None
    answer: str | None = None
    solution: str | None = None
    marks: float | None = None
    chapter: str | None = None
    qtype: str | None = None


def _editable(db, p: QuestionPaper, me):
    if p.status == "approved" and me.role != "super_admin":
        raise HTTPException(409, "This paper is approved. Ask the super admin to reopen it.")


LIVE_BLANK = "Students can already see this paper, so a question needs its text. Write the text, or reopen the paper to draft first."


@router.post("/papers/{pid}/questions")
def add_question(pid: int, body: QIn, db: Session = Depends(get_db), me=Depends(staff)):
    p = db.get(QuestionPaper, pid)
    if not p:
        raise HTTPException(404, "Paper not found")
    _editable(db, p, me)
    if p.status == "approved" and not (body.text or "").strip():
        raise HTTPException(422, LIVE_BLANK)
    last = db.query(Question).filter(Question.paper_id == pid).order_by(Question.position.desc()).first()
    q = Question(paper_id=pid, position=(last.position + 1) if last else 0, **{k: v for k, v in body.model_dump().items() if v is not None})
    q.text = q.text or ""
    db.add(q); db.flush()
    log(db, me, "paper.question_add", "paper", pid)
    db.commit()
    return q_out(q)


@router.put("/questions/{qid}")
def edit_question(qid: int, body: QIn, db: Session = Depends(get_db), me=Depends(staff)):
    q = db.get(Question, qid)
    if not q:
        raise HTTPException(404, "Question not found")
    paper = db.get(QuestionPaper, q.paper_id)
    _editable(db, paper, me)
    ch = body.model_dump(exclude_none=True)
    if paper.status == "approved" and "text" in ch and not (ch["text"] or "").strip():
        raise HTTPException(422, LIVE_BLANK)
    if "answer" in ch and ch["answer"] != q.answer:
        q.answer_source, q.confidence = ("human" if ch["answer"] else ""), ""
    if "options" in ch:
        ch["options"] = keep_option_figures(q.options, ch["options"])
    for k, v in ch.items():
        setattr(q, k, v)
    if "chapter" in ch:
        q.chapter_ref = {}
        pack = db.get(Book, db.get(QuestionPaper, q.paper_id).book_id)
        for bid, num, title, _ in chapter_idx(db, pack):
            if title == q.chapter:
                q.chapter_ref = {"book_id": bid, "chapter": num}; break
    log(db, me, "paper.question_edit", "question", qid, fields=list(ch))
    db.commit()
    return q_out(q)


@router.delete("/questions/{qid}")
def delete_question(qid: int, db: Session = Depends(get_db), me=Depends(staff)):
    q = db.get(Question, qid)
    if not q:
        raise HTTPException(404, "Question not found")
    _editable(db, db.get(QuestionPaper, q.paper_id), me)
    db.delete(q)
    log(db, me, "paper.question_delete", "question", qid)
    db.commit()
    return {"ok": True}


def supervise_ai(paper_id: int, step: str):
    """The model work runs in its own process. If that process dies, the paper says so and the website stays up."""
    r = subprocess.run([sys.executable, "-m", "app.paper_ai", str(paper_id), step], capture_output=True, text=True, errors="replace",
                       env={**os.environ, "PYTHONPATH": str(BASE)})
    if r.returncode:
        with SessionLocal() as db:
            p = db.get(QuestionPaper, paper_id)
            if p and p.ai_status in ("queued", "running"):
                p.ai_status, p.ai_error = "failed", f"The AI step stopped unexpectedly (code {r.returncode}). {r.stderr[-400:]}"
                db.commit()


def start_ai(db, p: QuestionPaper, action: str, me):
    from .platform import openai_conf
    if me.role != "super_admin":
        raise HTTPException(403, "Not allowed for your role")
    if p.status == "approved":
        raise HTTPException(409, "This paper is approved. Reopen it first.")
    if p.ai_status in ("queued", "running"):
        raise HTTPException(409, "The AI is already working on this paper")
    if not openai_conf(db)[2]:
        raise HTTPException(422, "Add your OpenAI key first, in AI settings")
    if action == "read_ai" and not (p.source_key or "").lower().endswith(".pdf"):
        raise HTTPException(422, "Read with AI needs the paper uploaded as a PDF")
    p.ai_status, p.ai_stage, p.ai_done, p.ai_total, p.ai_error = "queued", "Starting", 0, 0, ""
    log(db, me, "paper." + action, "paper", p.id)
    db.commit()
    from ..tasks import enqueue
    enqueue("paper_ai", p.id, "read" if action == "read_ai" else "answers")
    return paper_out(p)


def _pack_live(db, p: QuestionPaper):
    """A pack goes live as soon as one of its papers is approved, whoever approved it (TRACKS.md).
    A retired pack stays retired: someone took it down on purpose."""
    pack = db.get(Book, p.book_id)
    if pack and pack.status not in ("live", "retired"):
        pack.status, pack.live_at = "live", datetime.utcnow()


def publish(db, p: QuestionPaper, me):
    """The person who checked the paper publishes it: approved, and its pack is live in the marketplace."""
    if me.role != "super_admin":
        raise HTTPException(403, "Not allowed for your role")
    if p.ai_status in ("queued", "running"):
        raise HTTPException(409, "The AI is still working on this paper")
    qs = db.query(Question).filter(Question.paper_id == p.id).all()
    if not qs:
        raise HTTPException(409, "Add at least one question before publishing")
    blank = sum(1 for q in qs if not q.text.strip())
    if blank:
        raise HTTPException(409, f"{blank} question(s) have no text. Fix or delete them first.")
    pack = db.get(Book, p.book_id)
    p.status, p.reviewed_by = "approved", me.name
    _pack_live(db, p)
    log(db, me, "paper.publish", "paper", p.id, pack=pack.title)
    db.commit()
    return paper_out(p)


@router.get("/papers/{pid}/pages/{n}")
def paper_page(pid: int, n: int, db: Session = Depends(get_db), _=Depends(staff)):
    """One page of the original paper as a picture, shown beside the questions during review."""
    import pymupdf
    p = db.get(QuestionPaper, pid)
    if not p or not (p.source_key or "").lower().endswith(".pdf"):
        raise HTTPException(404, "No original page")
    with pymupdf.open(stream=get_storage().get(p.source_key), filetype="pdf") as doc:
        if not 1 <= n <= len(doc):
            raise HTTPException(404, "No such page")
        return Response(doc[n - 1].get_pixmap(dpi=130).tobytes("png"), media_type="image/png")


class FigureIn(BaseModel):
    page: int = 0
    box: list[float] | None = None  # fractions of the page; none removes the figure
    option: str = ""                # an option key: the picture is that option's, not the question's
    figure: int = 1                 # which of the question's figures: 1 is the first, a number one past the last adds one


@router.post("/questions/{qid}/figure")
def set_figure(qid: int, body: FigureIn, db: Session = Depends(get_db), me=Depends(staff)):
    """The reviewer draws the figure on the original page, or removes a wrong one."""
    import pymupdf
    q = db.get(Question, qid)
    if not q:
        raise HTTPException(404, "Question not found")
    p = db.get(QuestionPaper, q.paper_id)
    _editable(db, p, me)
    if body.option:
        return set_option_figure(db, q, p, body, me)
    if body.figure > 1:
        return set_more_figure(db, q, p, body, me)
    if body.box is None:
        q.figure_key = ""
    else:
        if len(body.box) != 4 or not (p.source_key or "").lower().endswith(".pdf"):
            raise HTTPException(422, "Draw the figure on a page of the original PDF")
        store = get_storage()
        with pymupdf.open(stream=store.get(p.source_key), filetype="pdf") as doc:
            if not 1 <= body.page <= len(doc):
                raise HTTPException(422, "No such page")
            pg = doc[body.page - 1]; r = pg.rect; b = body.box
            clip = pymupdf.Rect(b[0] * r.width, b[1] * r.height, b[2] * r.width, b[3] * r.height) & r
            if clip.is_empty or clip.width < 8 or clip.height < 8:
                raise HTTPException(422, "That area is too small")
            q.figure_key = f"papers/{p.book_id}/figures/{p.id}_{q.id}.png"
            store.put(q.figure_key, pg.get_pixmap(dpi=200, clip=clip).tobytes("png"))
    log(db, me, "paper.question_edit", "question", qid, fields=["figure"])
    db.commit()
    return q_out(q)


def _cut(p: QuestionPaper, page: int, box: list[float], key: str):
    """Cuts box out of a page of the original PDF and stores it at key."""
    import pymupdf
    if len(box) != 4 or not (p.source_key or "").lower().endswith(".pdf"):
        raise HTTPException(422, "Draw the picture on a page of the original PDF")
    store = get_storage()
    with pymupdf.open(stream=store.get(p.source_key), filetype="pdf") as doc:
        if not 1 <= page <= len(doc):
            raise HTTPException(422, "No such page")
        pg = doc[page - 1]; r = pg.rect
        clip = pymupdf.Rect(box[0] * r.width, box[1] * r.height, box[2] * r.width, box[3] * r.height) & r
        if clip.is_empty or clip.width < 8 or clip.height < 8:
            raise HTTPException(422, "That area is too small")
        store.put(key, pg.get_pixmap(dpi=200, clip=clip).tobytes("png"))


def set_more_figure(db, q: Question, p: QuestionPaper, body: FigureIn, me):
    """Figure 2, 3, ... of a question: redrawn, removed, or one more added at the end."""
    more = list(q.figures or [])
    i = body.figure - 2
    if i > len(more):
        raise HTTPException(422, f"Add figure {len(more) + 2} first")
    if i == len(more):
        if body.box is None:
            raise HTTPException(422, "There is no figure to remove")
        more.append("")
    if body.box is None:
        more[i] = ""
        while more and not more[-1]:
            more.pop()  # a removed last figure leaves no gap behind it
    else:
        key = f"papers/{p.book_id}/figures/{p.id}_{q.id}_f{body.figure}.png"
        _cut(p, body.page, body.box, key)
        more[i] = key
    q.figures = more  # a new list, so the JSON column is saved
    log(db, me, "paper.question_edit", "question", q.id, fields=["figure"], figure=body.figure)
    db.commit()
    return q_out(q)


def set_option_figure(db, q: Question, p: QuestionPaper, body: FigureIn, me):
    """The picture of one option, drawn on the original page or removed."""
    import pymupdf
    if not any(o.get("key") == body.option for o in q.options or []):
        raise HTTPException(422, "This question has no option " + body.option)
    key = ""
    if body.box is not None:
        if len(body.box) != 4 or not (p.source_key or "").lower().endswith(".pdf"):
            raise HTTPException(422, "Draw the picture on a page of the original PDF")
        store = get_storage()
        with pymupdf.open(stream=store.get(p.source_key), filetype="pdf") as doc:
            if not 1 <= body.page <= len(doc):
                raise HTTPException(422, "No such page")
            pg = doc[body.page - 1]; r = pg.rect; b = body.box
            clip = pymupdf.Rect(b[0] * r.width, b[1] * r.height, b[2] * r.width, b[3] * r.height) & r
            if clip.is_empty or clip.width < 8 or clip.height < 8:
                raise HTTPException(422, "That area is too small")
            key = f"papers/{p.book_id}/figures/{p.id}_{q.id}_{body.option}.png"
            store.put(key, pg.get_pixmap(dpi=200, clip=clip).tobytes("png"))
    opts = []
    for o in q.options or []:
        o = {k: v for k, v in o.items() if k != "figure"} if o.get("key") == body.option else dict(o)
        if o.get("key") == body.option and key:
            o["figure"] = key
        opts.append(o)
    q.options = opts  # a new list, so the JSON column is saved
    log(db, me, "paper.question_edit", "question", q.id, fields=["option_figure"], option=body.option)
    db.commit()
    return q_out(q)


def _figure_access(db, me, q: Question):
    paper = db.get(QuestionPaper, q.paper_id)
    if me.role == "student":
        owned_pack(db, me, paper.book_id)
        if paper.status != "approved":
            raise HTTPException(404, "No figure")


@router.get("/questions/{qid}/figure")
def question_figure(qid: int, db: Session = Depends(get_db), me=Depends(require("super_admin", "reviewer", "student"))):
    q = db.get(Question, qid)
    if not q or not q.figure_key:
        raise HTTPException(404, "No figure")
    _figure_access(db, me, q)
    return Response(get_storage().get(q.figure_key), media_type="image/png")


@router.get("/questions/{qid}/figures/{n}")
def more_figure(qid: int, n: int, db: Session = Depends(get_db), me=Depends(require("super_admin", "reviewer", "student"))):
    """Figure n of a question, where [[fig:n]] sits in its text. Figure 1 is the same as /figure."""
    q = db.get(Question, qid)
    if not q:
        raise HTTPException(404, "No figure")
    key = q.figure_key if n == 1 else ((q.figures or [])[n - 2] if 2 <= n < len(q.figures or []) + 2 else "")
    if not key:
        raise HTTPException(404, "No figure")
    _figure_access(db, me, q)
    return Response(get_storage().get(key), media_type="image/png")


@router.get("/questions/{qid}/options/{key}/figure")
def option_figure(qid: int, key: str, db: Session = Depends(get_db), me=Depends(require("super_admin", "reviewer", "student"))):
    q = db.get(Question, qid)
    pic = next((o.get("figure") for o in (q.options or [] if q else []) if o.get("key") == key), None)
    if not pic:
        raise HTTPException(404, "No figure")
    _figure_access(db, me, q)
    return Response(get_storage().get(pic), media_type="image/png")


@router.post("/papers/{pid}/{action}")
def paper_action(pid: int, action: str, body: dict | None = None, db: Session = Depends(get_db), me=Depends(staff)):
    p = db.get(QuestionPaper, pid)
    if not p:
        raise HTTPException(404, "Paper not found")
    note = (body or {}).get("note", "")
    moves = {  # action: (allowed from, to, who)
        "submit": (("draft", "rejected"), "in_review", ("super_admin",)),
        "approve": (("in_review",), "approved", ("reviewer", "super_admin")),
        "send_back": (("in_review",), "rejected", ("reviewer", "super_admin")),
        "reopen": (("approved",), "draft", ("super_admin",)),
    }
    if action in ("read_ai", "answer_ai"):
        return start_ai(db, p, action, me)
    if action == "publish":
        return publish(db, p, me)
    if action == "tidy":
        # Repairs text saved before the clean-up existed (tables, spacing, repeated options, order). No model call.
        if me.role != "super_admin":
            raise HTTPException(403, "Not allowed for your role")
        if p.ai_status in ("queued", "running"):
            raise HTTPException(409, "The AI is still working on this paper")
        from ..tidy import tidy_paper
        r = tidy_paper(db, pid, apply=True)
        log(db, me, "paper.tidy", "paper", pid, changed=len(r["changed"]), reordered=r["reordered"])
        db.commit()
        return {"changed": len(r["changed"]), "reordered": r["reordered"], "duplicates": r["duplicates"]}
    if action == "retag":
        if me.role != "super_admin":
            raise HTTPException(403, "Not allowed for your role")
        qs = db.query(Question).filter(Question.paper_id == pid).all()
        n = retag(db, db.get(Book, p.book_id), qs); db.commit()
        return {"tagged": n, "of": len(qs)}
    if action not in moves:
        raise HTTPException(404, "Unknown action")
    src, dst, who = moves[action]
    if me.role not in who:
        raise HTTPException(403, "Not allowed for your role")
    if p.status not in src:
        raise HTTPException(409, f"This paper is {p.status.replace('_', ' ')}, so it cannot be moved that way")
    if action == "submit" and not db.query(Question).filter(Question.paper_id == pid).count():
        raise HTTPException(409, "Add at least one question before sending it for review")
    if action == "send_back" and not note.strip():
        raise HTTPException(422, "Say what needs fixing")
    if action == "approve":
        # Same checks as publish(): a paper a student will see must have no blank questions.
        blank = db.query(Question).filter(Question.paper_id == pid).all()
        blank = sum(1 for q in blank if not (q.text or "").strip())
        if blank:
            raise HTTPException(409, f"{blank} question(s) have no text. Fix or delete them first.")
    p.status = dst
    if action in ("approve", "send_back"):
        p.reviewed_by, p.review_note = me.name, note
    if action == "approve":
        _pack_live(db, p)
    log(db, me, "paper." + action, "paper", pid, note=note)
    db.commit()
    return paper_out(p)


@router.delete("/papers/{pid}")
def delete_paper(pid: int, db: Session = Depends(get_db), me=Depends(sa)):
    p = db.get(QuestionPaper, pid)
    if not p:
        raise HTTPException(404, "Paper not found")
    db.query(Question).filter(Question.paper_id == pid).delete()
    db.delete(p)
    log(db, me, "paper.delete", "paper", pid)
    db.commit()
    return {"ok": True}


@router.get("/review/queue")
def review_queue(db: Session = Depends(get_db), _=Depends(staff)):
    counts = Counter(q.paper_id for q in db.query(Question).join(QuestionPaper).filter(QuestionPaper.status.in_(("in_review", "approved", "rejected"))))
    out = []
    for p in db.query(QuestionPaper).filter(QuestionPaper.status.in_(("in_review", "approved", "rejected"))).order_by(QuestionPaper.created_at.desc()):
        b = db.get(Book, p.book_id)
        out.append({**paper_out(p, counts.get(p.id, 0)), "pack": b.title if b else "", "exam": b.exam if b else ""})
    return out


# ---------------- student ----------------
def owned_pack(db, me, bid) -> Book:
    from .student import owned_ids
    b = pack_of(db, bid)
    if b.status != "live":
        raise HTTPException(404, "This exam pack is not available yet")
    if bid not in owned_ids(db, me):
        raise HTTPException(403, "Get this exam pack from the store first")
    return b


def approved_qs(db, bid, years=0, chapter=None):
    q = db.query(Question, QuestionPaper).join(QuestionPaper, Question.paper_id == QuestionPaper.id) \
        .filter(QuestionPaper.book_id == bid, QuestionPaper.status == "approved")
    if years:
        newest = max([p.year for p in db.query(QuestionPaper).filter(QuestionPaper.book_id == bid, QuestionPaper.status == "approved")] or [0])
        q = q.filter(QuestionPaper.year > newest - years)
    if chapter is not None:
        q = q.filter(Question.chapter == ("" if chapter == "Not tagged" else chapter))
    return q.order_by(QuestionPaper.year.desc(), Question.position).all()


@srouter.get("/{bid}")
def pack_home(bid: int, years: int = 10, db: Session = Depends(get_db), me=Depends(student)):
    b = owned_pack(db, me, bid)
    rows = approved_qs(db, bid, years)
    papers = {}
    for q, p in rows:
        papers.setdefault(p.id, {**paper_out(p, 0)}); papers[p.id]["questions"] += 1
    by_ch = Counter(q.chapter or "Not tagged" for q, _ in rows)
    marks = defaultdict(float)
    for q, _ in rows:
        marks[q.chapter or "Not tagged"] += q.marks or 0
    total = sum(by_ch.values()) or 1
    weight = [{"chapter": c, "questions": n, "share": round(n / total * 100), "marks": marks[c]} for c, n in by_ch.most_common()]
    all_years = sorted({p.year for p in db.query(QuestionPaper).filter(QuestionPaper.book_id == bid, QuestionPaper.status == "approved")}, reverse=True)
    attempts = db.query(MockAttempt).filter(MockAttempt.user_id == me.id, MockAttempt.book_id == bid, MockAttempt.submitted_at.isnot(None)) \
        .order_by(MockAttempt.submitted_at.desc()).limit(5).all()
    from ..taxonomy import marking_for
    return {"pack": {"id": b.id, "title": b.title, "exam": b.exam, "board": b.board, "level": b.level, "grade": b.grade, "subject": b.subject,
                     "marking": marking_for(b.exam)},
            "years": years, "available_years": all_years, "papers": list(papers.values()), "questions": len(rows), "weightage": weight,
            "linked_books": [{"id": x.id, "title": x.title} for x in db.query(Book).filter(Book.id.in_(b.linked_book_ids or [0]), Book.status == "live")],
            "attempts": [{"id": a.id, "score": a.score, "total": a.total, "when": a.submitted_at, "questions": len(a.question_ids), "title": a.title, "time_taken": a.time_taken} for a in attempts]}


@srouter.get("/{bid}/papers/{pid}")
def pack_paper(bid: int, pid: int, db: Session = Depends(get_db), me=Depends(student)):
    owned_pack(db, me, bid)
    p = db.get(QuestionPaper, pid)
    if not p or p.book_id != bid or p.status != "approved":
        raise HTTPException(404, "Paper not found")
    qs = db.query(Question).filter(Question.paper_id == pid).order_by(Question.position, Question.id).all()
    return {**paper_out(p, len(qs)), "questions": [q_out(q) for q in qs]}


@srouter.get("/{bid}/topics")
def pack_topics(bid: int, years: int = 10, db: Session = Depends(get_db), me=Depends(student)):
    owned_pack(db, me, bid)
    groups = defaultdict(list)
    for q, p in approved_qs(db, bid, years):
        groups[q.chapter or "Not tagged"].append({**q_out(q), "year": p.year, "session": p.session})
    return [{"chapter": c, "questions": v} for c, v in sorted(groups.items(), key=lambda kv: -len(kv[1]))]


class RecapIn(BaseModel):
    chapter: str


@srouter.post("/{bid}/recap")
def recap(bid: int, body: RecapIn, db: Session = Depends(get_db), me=Depends(student)):
    """Quick recap of one chapter, written live from the chapter's headings and the questions the exam keeps asking."""
    from .student import rules_for, day_row, count_explanation
    b = owned_pack(db, me, bid)
    r = rules_for(db, me)
    if day_row(db, me.id).explanations >= r["daily_limit"]:
        raise HTTPException(429, f"You have used today's {r['daily_limit']} AI answers. They reset tomorrow.")
    qs = [q for q, _ in approved_qs(db, bid, 0, body.chapter)][:12]
    heads = []
    for bid2, num, title, c in chapter_idx(db, b):
        if title == body.chapter:
            heads = [w for w, _ in c.most_common(25)]
    prompt = f"""You are EduVerse, preparing a student for {b.exam or 'their exam'} ({b.board or b.level}{', Class ' + b.grade if b.grade else ''}{', ' + b.subject if b.subject else ''}).
Write a QUICK RECAP of the chapter "{body.chapter}" for last-minute revision.

Key terms from the textbook chapter: {', '.join(heads) or 'not available'}
Questions this exam has asked from this chapter in past years:
{chr(10).join('- ' + q.text[:220] for q in qs) or '- none recorded'}

Give: the 6 to 10 points most likely to be examined, any formula or definition to memorise word for word,
two common mistakes, and one line on how this chapter is usually asked. Plain text, short lines, no markdown headings."""
    ai = (db.get(Setting, "ai").value if db.get(Setting, "ai") else AI)
    provider = os.getenv("AI_PROVIDER_OVERRIDE") or ai["provider"]
    pv = ai["providers"].get(provider, {"model": "test"})
    if provider == "mock":
        text = f"[Test model, not a real answer] Recap of {body.chapter}: {len(qs)} past questions, key terms {', '.join(heads[:8])}."
    else:
        from ..llm_client import call
        try:
            usage = {}
            text = call(provider, pv["model"], prompt, base_url=pv.get("base_url"), api_key=pv.get("api_key") or None, usage=usage).strip()
        except Exception as e:
            raise HTTPException(502, f"The {provider} model did not answer: {str(e)[:160]}")
        from .. import explain_store as X
        X.record(db, "recap", pv["model"], usage, me.id, bid, False, body.chapter, b.title)
    count_explanation(db, me, None, tokens=len(text) // 4)
    db.commit()
    return {"chapter": body.chapter, "text": text, "based_on": len(qs)}


class MockIn(BaseModel):
    count: int = 20
    years: int = 10
    chapter: str | None = None
    mcq_only: bool = False
    paper_id: int | None = None   # a whole past paper, in its printed order
    minutes: int = 0              # 0 = no time limit
    correct: float | None = None  # marks for a right answer; 0 = each question's own marks; not sent = the exam's scheme
    wrong: float | None = None    # marks taken off for a wrong answer, e.g. 1 in JEE Main; not sent = the exam's scheme


def subject_of(section: str) -> str:
    import re
    return re.split(r"\s+(?:section|part)\b", section or "", flags=re.I)[0].strip() or "General"


def mock_out(a: MockAttempt, qs):
    return {"id": a.id, "title": a.title, "minutes": a.minutes, "correct": a.mark_correct, "wrong": a.mark_wrong,
            "started_at": a.started_at, "questions": [{**q_out(q, answers=False), "subject": subject_of(q.section)} for q in qs]}


@srouter.post("/{bid}/mock")
def start_mock(bid: int, body: MockIn, db: Session = Depends(get_db), me=Depends(student)):
    pack = owned_pack(db, me, bid)
    if body.paper_id:
        paper = db.get(QuestionPaper, body.paper_id)
        if not paper or paper.book_id != bid or paper.status != "approved":
            raise HTTPException(404, "Paper not found")
        pick = db.query(Question).filter(Question.paper_id == paper.id).order_by(Question.position, Question.id).all()
        title = f"{paper.title or paper.year} {paper.session}".strip() if not paper.title else paper.title
    else:
        pool = [q for q, _ in approved_qs(db, bid, body.years, body.chapter)]
        if body.mcq_only:
            pool = [q for q in pool if (q.options or q.qtype == "numeric") and q.answer]
        pick = random.sample(pool, min(max(1, body.count), 100, len(pool))) if pool else []
        title = f"{body.chapter or 'Mixed'} practice test"
    if not pick:
        raise HTTPException(409, "No questions match these choices yet")
    from ..taxonomy import marking_for
    scheme = marking_for(pack.exam) or {"correct": 0, "wrong": 0}
    correct = scheme["correct"] if body.correct is None else body.correct
    wrong = scheme["wrong"] if body.wrong is None else body.wrong
    a = MockAttempt(user_id=me.id, book_id=bid, question_ids=[q.id for q in pick], answers={}, title=f"{pack.exam or pack.title}: {title}"[:200],
                    paper_id=body.paper_id, minutes=max(0, min(body.minutes, 600)), mark_correct=max(0, correct), mark_wrong=abs(wrong))
    db.add(a); db.commit()
    return mock_out(a, pick)


def same_answer(given: str, answer: str, numeric: bool, multi: bool) -> bool:
    answer = answer.strip().lower()
    if numeric:
        try:
            return abs(float(given) - float(answer)) < 1e-6
        except ValueError:
            return given == answer
    if multi:
        return bool(given) and {x.strip() for x in given.split(",")} == {x.strip() for x in answer.split(",")}
    return given == answer


def judge(q: Question, given: str):
    """True or False for questions with a checkable answer, None for written ones."""
    numeric = q.qtype == "numeric" and bool(q.answer)
    if not ((q.options and q.answer) or numeric):
        return None
    return same_answer(given, q.answer, numeric, q.qtype == "multi")


def note_progress(db, me, bid, q: Question, ok, bookmark=None):
    from ..models import QuestionProgress
    p = db.get(QuestionProgress, (me.id, q.id))
    if not p:
        p = QuestionProgress(user_id=me.id, question_id=q.id, book_id=bid, status="", bookmarked=False, tries=0); db.add(p)
    if ok is not None:
        p.status, p.tries = ("correct" if ok else "wrong"), (p.tries or 0) + 1
    if bookmark is not None:
        p.bookmarked = bookmark
    p.updated = datetime.utcnow()
    return p


class SubmitIn(BaseModel):
    answers: dict[str, str] = {}
    times: dict[str, int] = {}
    time_taken: int = 0
    unsure: list[int] = []


@srouter.post("/mock/{aid}/submit")
def submit_mock(aid: int, body: SubmitIn, db: Session = Depends(get_db), me=Depends(student)):
    a = db.get(MockAttempt, aid)
    if not a or a.user_id != me.id:
        raise HTTPException(404, "Test not found")
    if a.submitted_at:
        raise HTTPException(409, "This test is already submitted")
    qs = {q.id: q for q in db.query(Question).filter(Question.id.in_(a.question_ids))}
    score = total = 0.0
    right = wrong = blank = 0
    results = []
    for qid in a.question_ids:
        q = qs.get(qid)
        if not q:
            continue
        given = (body.answers.get(str(qid)) or "").strip().lower()
        ok = judge(q, given) if given else None
        auto = judge(q, "x") is not None
        w = a.mark_correct or q.marks or 1
        if auto:
            total += w
            if ok:
                score += w; right += 1
            elif given:
                score -= a.mark_wrong; wrong += 1
            else:
                blank += 1
            if given:
                note_progress(db, me, a.book_id, q, ok)
            if given or qid in body.unsure:
                from .. import study as S
                S.record(db, me.id, "exam", q, given, ok if given else None, book_id=a.book_id, origin="Mock test", not_sure=qid in body.unsure)
        results.append({**q_out(q), "subject": subject_of(q.section), "given": given, "correct": (ok if given else False) if auto else None,
                        "self_check": not auto, "time": int(body.times.get(str(qid), 0))})
    a.answers, a.score, a.total, a.submitted_at = body.answers, score, total, datetime.utcnow()
    a.times, a.time_taken = {k: int(v) for k, v in body.times.items()}, max(0, body.time_taken)
    db.commit()
    return {"id": a.id, "title": a.title, "score": score, "total": total, "right": right, "wrong": wrong, "blank": blank,
            "mark_correct": a.mark_correct, "mark_wrong": a.mark_wrong, "time_taken": a.time_taken, "minutes": a.minutes, "results": results}


# ---------------- practice, one question at a time ----------------
@srouter.get("/{bid}/practice")
def practice(bid: int, chapter: str = "", subject: str = "", year: int = 0, show: str = "all", db: Session = Depends(get_db), me=Depends(student)):
    from ..models import QuestionProgress
    owned_pack(db, me, bid)
    rows = approved_qs(db, bid, 0)
    state = {p.question_id: p for p in db.query(QuestionProgress).filter(QuestionProgress.user_id == me.id, QuestionProgress.book_id == bid)}
    subjects = sorted({subject_of(q.section) for q, _ in rows})
    chapters = sorted({q.chapter for q, _ in rows if q.chapter})
    years = sorted({p.year for _, p in rows}, reverse=True)

    def st(q):
        p = state.get(q.id)
        return {"status": p.status if p else "", "bookmarked": bool(p and p.bookmarked), "tries": p.tries if p else 0}
    counts = {"all": len(rows), "new": sum(1 for q, _ in rows if not st(q)["status"]), "wrong": sum(1 for q, _ in rows if st(q)["status"] == "wrong"),
              "saved": sum(1 for q, _ in rows if st(q)["bookmarked"])}
    out = []
    for q, p in rows:
        s = st(q)
        if (chapter and q.chapter != chapter) or (subject and subject_of(q.section) != subject) or (year and p.year != year):
            continue
        if (show == "new" and s["status"]) or (show == "wrong" and s["status"] != "wrong") or (show == "saved" and not s["bookmarked"]):
            continue
        out.append({**q_out(q), "subject": subject_of(q.section), "year": p.year, "session": p.session, "state": s})
    return {"questions": out, "subjects": subjects, "chapters": chapters, "years": years, "counts": counts}


class GivenIn(BaseModel):
    given: str = ""
    not_sure: bool = False


def pack_question(db, me, bid, qid) -> Question:
    owned_pack(db, me, bid)
    q = db.get(Question, qid)
    paper = db.get(QuestionPaper, q.paper_id) if q else None
    if not paper or paper.book_id != bid or paper.status != "approved":
        raise HTTPException(404, "Question not found")
    return q


@srouter.post("/{bid}/practice/{qid}/answer")
def practice_answer(bid: int, qid: int, body: GivenIn, db: Session = Depends(get_db), me=Depends(student)):
    q = pack_question(db, me, bid, qid)
    given = body.given.strip().lower()
    ok = judge(q, given) if given else None
    p = note_progress(db, me, bid, q, ok)
    if given:
        from .. import study as S
        S.record(db, me.id, "exam", q, given, ok, book_id=bid, origin="Practice", not_sure=body.not_sure)
    db.commit()
    return {"correct": ok, "answer": q.answer, "solution": q.solution, "state": {"status": p.status, "bookmarked": p.bookmarked, "tries": p.tries}}


@srouter.post("/{bid}/practice/{qid}/bookmark")
def practice_bookmark(bid: int, qid: int, db: Session = Depends(get_db), me=Depends(student)):
    from ..models import QuestionProgress
    q = pack_question(db, me, bid, qid)
    cur = db.get(QuestionProgress, (me.id, q.id))
    p = note_progress(db, me, bid, q, None, bookmark=not (cur and cur.bookmarked))
    db.commit()
    return {"bookmarked": p.bookmarked}
