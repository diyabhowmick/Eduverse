"""Reviewer API. A converted book waits here; only a reviewer's approval of every page publishes it."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Book, ReviewPage
from ..security import require
from ..audit import log
from .. import content as C

router = APIRouter(prefix="/api/review", tags=["review"])
reviewer = require("reviewer", "super_admin")


def progress(db, bid):
    rows = db.query(ReviewPage).filter(ReviewPage.book_id == bid).all()
    c = {"pending": 0, "approved": 0, "rejected": 0}
    for r in rows:
        c[r.status] += 1
    return {**c, "total": len(rows)}


def get_book(db, bid, me=None) -> Book:
    b = db.get(Book, bid)
    if not b:
        raise HTTPException(404, "Book not found")
    if me is not None and me.role == "reviewer" and b.assigned_reviewer_id and b.assigned_reviewer_id != me.id:
        raise HTTPException(403, "This book is assigned to another reviewer")
    if not b.content_key:
        raise HTTPException(409, "This book has no converted content yet")
    return b


def editable(b: Book):
    if b.status != "in_review":
        raise HTTPException(409, "Only books in review can be changed")


def reviewer_name(db, uid):
    from ..models import User
    u = db.get(User, uid) if uid else None
    return u.name if u else ""


@router.get("/queue")
def queue(db: Session = Depends(get_db), me=Depends(reviewer)):
    out = []
    for b in db.query(Book).filter(Book.status.in_(("in_review", "processing", "rejected"))).order_by(Book.created_at):
        if me.role == "reviewer" and b.assigned_reviewer_id and b.assigned_reviewer_id != me.id:
            continue  # assigned to another reviewer
        rep = C.load_extra(b, "report.json") if b.content_key else None
        out.append({"id": b.id, "title": b.title, "subject": b.subject, "board": b.board, "grade": b.grade, "status": b.status,
                    "has_content": bool(b.content_key), "progress": progress(db, b.id), "review_note": b.review_note,
                    "flags": len(rep["needs_review"]) if rep else 0, "assigned_to": reviewer_name(db, b.assigned_reviewer_id),
                    "assigned_to_me": b.assigned_reviewer_id == me.id, "chapters": rep["chapters_in_file"] if rep else [],
                    "figures": rep["figures"]["kept"] if rep else 0})
    return out


@router.get("/history")
def history(db: Session = Depends(get_db), _=Depends(reviewer)):
    return [{"id": b.id, "title": b.title, "board": b.board, "grade": b.grade, "status": b.status, "reviewed_by": b.reviewed_by,
             "reviewed_at": b.reviewed_at, "review_note": b.review_note}
            for b in db.query(Book).filter(Book.reviewed_at.isnot(None)).order_by(Book.reviewed_at.desc())]


@router.get("/books/{bid}")
def book(bid: int, db: Session = Depends(get_db), me=Depends(reviewer)):
    b = get_book(db, bid, me)
    # so a super admin can tell "never started" from "started and stuck"
    b.last_opened_at = datetime.utcnow()
    db.commit()
    data = C.load(b); rep = C.load_extra(b, "report.json") or {}
    flags = {}
    for f in rep.get("needs_review", []):
        flags.setdefault(f["page"], []).append(f)
    chap_of = {}
    for ch in data["chapters"]:
        for blk, _ in C.walk(ch["blocks"]):
            chap_of.setdefault(blk.get("page"), ch["number"])
    from .. import m2
    choose = {}
    for f in m2.figures(data):
        if (f.get("m2") or {}).get("status") == "generated" and f["m2"].get("choice") == "pending":
            choose[f.get("page")] = choose.get(f.get("page"), 0) + 1
    pages = [{"page": r.page, "status": r.status, "comment": r.comment, "reviewer": r.reviewer, "flags": len(flags.get(r.page, [])),
              "chapter": chap_of.get(r.page), "choose": choose.get(r.page, 0)} for r in db.query(ReviewPage).filter(ReviewPage.book_id == bid).order_by(ReviewPage.page)]
    return {"id": b.id, "title": b.title, "subject": b.subject, "board": b.board, "grade": b.grade, "status": b.status,
            "detected": data["book"], "has_original_pdf": bool(b.original_key.lower().endswith(".pdf")) if b.original_key else False,
            "chapters": [{"number": c["number"], "title": c["title"], "partial": c.get("partial", False), "keywords": len(c["keywords"])} for c in data["chapters"]],
            "toc": data["toc"], "pages": pages, "progress": progress(db, bid), "report": {k: rep.get(k) for k in ("blocks", "figures", "sections", "ledger")},
            "flags": rep.get("needs_review", []), "m2": C.load_extra(b, "m2_report.json"), "to_choose": sum(choose.values())}


@router.get("/books/{bid}/pages/{page}")
def page(bid: int, page: int, db: Session = Depends(get_db), me=Depends(reviewer)):
    b = get_book(db, bid, me)
    data = C.load(b)
    flow = C.load_extra(b, "flow_pages.json") or {}
    rep = C.load_extra(b, "report.json") or {}
    r = db.get(ReviewPage, (bid, page))
    return {**C.page_view(data, page), "original": {"pdf": bool(C.original_page_png(b, page)) if b.original_key.lower().endswith(".pdf") else False,
                                                   "flow": flow.get(str(page), [])},
            "flags": [f for f in rep.get("needs_review", []) if f["page"] == page],
            "removed": [l for l in C.ledger(b) if l.get("page") == page and "removed" in l.get("what", "")],
            "status": r.status if r else "pending", "comment": r.comment if r else ""}


@router.get("/books/{bid}/pages/{page}/original.png")
def original_png(bid: int, page: int, db: Session = Depends(get_db)):
    png = C.original_page_png(get_book(db, bid), page)
    if not png:
        raise HTTPException(404, "No original PDF page")
    return Response(png, media_type="image/png")


class BlockEdit(BaseModel):
    text: str | None = None
    caption: str | None = None
    item: int | None = None        # list item index
    cell: list[int] | None = None  # [row, col] for tables
    latex: list[str] | None = None


@router.patch("/books/{bid}/blocks/{block_id}")
def edit_block(bid: int, block_id: str, body: BlockEdit, db: Session = Depends(get_db), me=Depends(reviewer)):
    b = get_book(db, bid, me); editable(b)
    data = C.load(b)
    ch, blk, _ = C.find_block(data, block_id)
    if not blk:
        raise HTTPException(404, "Block not found")
    before = None
    if body.caption is not None and blk["type"] in ("figure", "table"):
        before, blk["caption"] = blk.get("caption"), body.caption.strip()
    elif body.latex is not None and blk["type"] == "equation":
        before, blk["latex"] = blk["latex"], [x.strip() for x in body.latex if x.strip()]
    elif body.cell is not None and blk["type"] == "table":
        r, c = body.cell
        before, blk["rows"][r][c] = blk["rows"][r][c], (body.text or "").strip()
    elif body.text is not None:
        text = body.text.strip()
        if not text:
            raise HTTPException(422, "Text cannot be empty. Remove the block instead.")
        obj = blk["items"][body.item] if (blk["type"] == "list" and body.item is not None) else blk
        if "text" not in obj:
            raise HTTPException(422, "This block has no text to edit")
        before = obj["text"]; keep = {m[2] for m in obj.get("marks", [])}
        obj["text"] = text
        if blk["type"] in ("paragraph", "list"):
            C.remark(obj, ch["keywords"], keep)
    else:
        raise HTTPException(422, "Nothing to change")
    blk.setdefault("edits", []).append({"by": me.email, "at": datetime.utcnow().isoformat(timespec="seconds")})
    C.save(b, data)
    log(db, me, "review.edit", "book", bid, block=block_id, page=blk.get("page"), before=str(before)[:200])
    db.commit()
    return blk


@router.delete("/books/{bid}/blocks/{block_id}")
def delete_block(bid: int, block_id: str, db: Session = Depends(get_db), me=Depends(reviewer)):
    b = get_book(db, bid, me); editable(b)
    data = C.load(b)
    ch, blk, parent = C.find_block(data, block_id)
    if not blk:
        raise HTTPException(404, "Block not found")
    (parent["children"] if parent else ch["blocks"]).remove(blk)
    C.save(b, data)
    log(db, me, "review.remove_block", "book", bid, block=block_id, type=blk["type"], page=blk.get("page"), text=str(blk.get("text", blk.get("caption", "")))[:200])
    db.commit()
    return {"ok": True}


class KeywordIn(BaseModel):
    chapter: int
    term: str


@router.post("/books/{bid}/keywords")
def add_keyword(bid: int, body: KeywordIn, db: Session = Depends(get_db), me=Depends(reviewer)):
    b = get_book(db, bid, me); editable(b)
    data = C.load(b)
    ch = next((c for c in data["chapters"] if c["number"] == body.chapter), None)
    if not ch:
        raise HTTPException(404, "Chapter not found")
    term = body.term.strip(); key = " ".join(term.lower().split())
    if len(key) < 2:
        raise HTTPException(422, "Type the word to highlight")
    if any(k["key"] == key for k in ch["keywords"]):
        raise HTTPException(409, "This word is already highlighted")
    kw = {"term": term, "key": key, "id": f"k{ch['number']}-{key.replace(' ', '-')}", "score": 0, "signals": ["reviewer"], "count": 0,
          "definition": "", "prerequisite": False, "source": "reviewer", "first_block": None}
    if not C.mark_first(ch, kw):
        raise HTTPException(422, "This word does not appear in the unit's reading text")
    ch["keywords"].append(kw)
    C.save(b, data)
    log(db, me, "review.add_keyword", "book", bid, chapter=ch["number"], term=term)
    db.commit()
    return kw


@router.delete("/books/{bid}/keywords/{kid}")
def remove_keyword(bid: int, kid: str, db: Session = Depends(get_db), me=Depends(reviewer)):
    b = get_book(db, bid, me); editable(b)
    data = C.load(b)
    for ch in data["chapters"]:
        kw = next((k for k in ch["keywords"] if k["id"] == kid), None)
        if kw:
            ch["keywords"].remove(kw); C.unmark(ch, kid)
            C.save(b, data)
            log(db, me, "review.remove_keyword", "book", bid, chapter=ch["number"], term=kw["term"])
            db.commit()
            return {"ok": True}
    raise HTTPException(404, "Word not found")


class FigureChoice(BaseModel):
    choice: str  # generated | original


class Regenerate(BaseModel):
    summary: str | None = None  # the edited description to draw from
    use_model: bool = False     # skip the SVG redraw and ask the image model


def figure_block(data, block_id):
    ch, blk, _ = C.find_block(data, block_id)
    if not blk or blk["type"] != "figure":
        raise HTTPException(404, "Figure not found")
    return blk


@router.post("/books/{bid}/figures/{block_id}/choice")
def choose_figure(bid: int, block_id: str, body: FigureChoice, db: Session = Depends(get_db), me=Depends(reviewer)):
    """Which picture students see: the new one M2 made, or the original from the book."""
    b = get_book(db, bid, me); editable(b)
    if body.choice not in ("generated", "original"):
        raise HTTPException(422, "Choose generated or original")
    data = C.load(b); blk = figure_block(data, block_id)
    rec = blk.get("m2") or {}
    if body.choice == "generated" and rec.get("status") != "generated":
        raise HTTPException(409, "There is no new picture for this figure")
    rec["choice"] = body.choice
    blk["image"] = rec["image"] if body.choice == "generated" else rec.get("original", blk["image"])
    blk["m2"] = rec
    C.save(b, data)
    log(db, me, "review.figure_choice", "book", bid, block=block_id, choice=body.choice)
    db.commit()
    return {"id": block_id, "image": blk["image"], "m2": rec}


@router.post("/books/{bid}/figures/{block_id}/regenerate")
def regenerate_figure(bid: int, block_id: str, body: Regenerate, db: Session = Depends(get_db), me=Depends(reviewer)):
    """Draw the figure again, from the description as the reviewer left it."""
    from .. import m2
    b = get_book(db, bid, me); editable(b)
    data = C.load(b); blk = figure_block(data, block_id)
    if body.summary is not None and body.summary.strip():
        d = blk.get("desc") or {"kind": "image", "type": "photo", "parts": [], "relations": [], "data": [], "text_in_figure": []}
        d["summary"] = body.summary.strip()
        blk["desc"] = d
    cfg = m2.settings_of(db)
    report = C.load_extra(b, "m2_report.json") or {}
    specs = C.load_extra(b, "m1_specs.json") or {}
    rec = m2.redo_figure(b, blk, specs, cfg, report, allow_svg=not body.use_model and body.summary is None)
    m2.apply(blk, rec)
    C.save(b, data)
    C._store().put(f"{b.content_key}/m2_report.json", __import__("json").dumps(report).encode())
    for r in db.query(ReviewPage).filter(ReviewPage.book_id == bid, ReviewPage.page == blk.get("page"), ReviewPage.status == "approved"):
        r.status = "pending"  # the page changed, so it needs a fresh look
    log(db, me, "review.figure_regenerate", "book", bid, block=block_id, status=rec["status"], method=rec.get("method", ""))
    db.commit()
    if rec["status"] != "generated":
        raise HTTPException(422, rec.get("error") or "No new picture was made")
    return {"id": block_id, "m2": rec, "desc": blk.get("desc")}


class Decision(BaseModel):
    comment: str = ""


@router.post("/books/{bid}/pages/{page}/{decision}")
def decide_page(bid: int, page: int, decision: str, body: Decision, db: Session = Depends(get_db), me=Depends(reviewer)):
    b = get_book(db, bid, me); editable(b)
    if decision not in ("approve", "reject", "reopen"):
        raise HTTPException(404, "Unknown decision")
    r = db.get(ReviewPage, (bid, page))
    if not r:
        raise HTTPException(404, "Page not found")
    if decision == "approve":
        from .. import m2
        waiting = m2.pending_on_page(C.load(b), page)
        if waiting:
            raise HTTPException(409, f"Choose the original or the new picture for {', '.join(waiting)} first")
    if decision == "reject" and not body.comment.strip():
        raise HTTPException(422, "Say what is wrong on this page")
    r.status = {"approve": "approved", "reject": "rejected", "reopen": "pending"}[decision]
    r.comment, r.reviewer, r.updated_at = body.comment.strip(), me.email, datetime.utcnow()
    log(db, me, f"review.page_{decision}", "book", bid, page=page, comment=r.comment[:200])
    db.commit()
    return {"page": page, "status": r.status, "progress": progress(db, bid)}


@router.post("/books/{bid}/approve-all-remaining")
def approve_remaining(bid: int, db: Session = Depends(get_db), me=Depends(reviewer)):
    """Approve every page still pending (after looking through them). Rejected pages stay rejected."""
    from .. import m2
    b = get_book(db, bid, me); editable(b)
    data = C.load(b)
    n, held = 0, []
    for r in db.query(ReviewPage).filter(ReviewPage.book_id == bid, ReviewPage.status == "pending"):
        if m2.pending_on_page(data, r.page):
            held.append(r.page); continue  # a picture still needs a choice
        r.status, r.reviewer, r.updated_at = "approved", me.email, datetime.utcnow(); n += 1
    log(db, me, "review.approve_remaining", "book", bid, pages=n, held=held[:50])
    db.commit()
    return {"approved": n, "held": held, "progress": progress(db, bid)}


@router.post("/books/{bid}/publish")
def publish(bid: int, body: Decision, db: Session = Depends(get_db), me=Depends(reviewer)):
    b = get_book(db, bid, me); editable(b)
    p = progress(db, bid)
    if p["total"] == 0 or p["approved"] != p["total"]:
        raise HTTPException(409, f"Every page must be approved first: {p['approved']} of {p['total']} approved, {p['rejected']} rejected")
    b.status, b.live_at = "live", datetime.utcnow()
    b.reviewed_by, b.reviewed_at, b.review_note = me.email, datetime.utcnow(), body.comment.strip()
    log(db, me, "review.publish", "book", bid, title=b.title, pages=p["total"])
    db.commit()
    return {"status": b.status}


@router.post("/books/{bid}/send-back")
def send_back(bid: int, body: Decision, db: Session = Depends(get_db), me=Depends(reviewer)):
    b = get_book(db, bid, me); editable(b)
    if not body.comment.strip():
        raise HTTPException(422, "Say why the book is going back")
    b.status, b.review_note, b.reviewed_by, b.reviewed_at = "rejected", body.comment.strip(), me.email, datetime.utcnow()
    log(db, me, "review.send_back", "book", bid, title=b.title, comment=b.review_note[:200])
    db.commit()
    return {"status": b.status}


public = APIRouter(tags=["content"])


@public.get("/api/content/{bid}/{path:path}")
def content_file(bid: int, path: str, db: Session = Depends(get_db)):
    """Images of a converted book (figure crops and the M1 page images)."""
    if not (path.startswith("images/") or path.startswith("flow_images/")) or ".." in path:
        raise HTTPException(404, "Not found")
    b = db.get(Book, bid)
    if not b or not b.content_key:
        raise HTTPException(404, "Not found")
    try:
        data = C._store().get(f"{b.content_key}/{path}")
    except Exception:
        raise HTTPException(404, "Not found")
    ext = path.rsplit(".", 1)[-1].lower()
    return Response(data, media_type={"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif", "svg": "image/svg+xml"}.get(ext, "application/octet-stream"),
                    headers={"Cache-Control": "public, max-age=86400"})
