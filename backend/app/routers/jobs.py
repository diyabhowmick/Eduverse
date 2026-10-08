import io, json, shutil, subprocess, tempfile, threading, time, uuid, zipfile
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from ..config import settings
from ..db import get_db, SessionLocal
from ..models import Job, Book, ClassBook, Setting
from ..security import platform_admin
from ..storage import get_storage
from ..audit import log

router = APIRouter(prefix="/api/jobs", tags=["processing"])
ALLOWED = (".pdf", ".docx", ".doc")


def count_pages(data: bytes, name: str) -> int:
    if name.lower().endswith(".pdf"):
        try:
            from pypdf import PdfReader
            import io
            return len(PdfReader(io.BytesIO(data)).pages)
        except Exception:
            return data.count(b"/Type /Page") - data.count(b"/Type /Pages")
    return 0


def out(j: Job):
    return {"id": j.id, "stage": j.stage, "filename": j.filename, "status": j.status, "pages": j.pages,
            "pages_done": j.pages_done, "cost_credits": j.cost_credits, "error": j.error,
            "triggered_by": j.triggered_by, "created_at": j.created_at, "finished_at": j.finished_at,
            "book_id": j.book_id, "book": j.book.title if j.book else "", "book_status": j.book.status if j.book else "",
            "kind": j.kind or ("flow" if j.filename.lower().endswith(".docx") else "book"), "has_extras": bool(j.extras_key)}


def is_flow_docx(data: bytes) -> bool:
    """An M1 flow document uses the EV paragraph styles; a printed book saved as Word does not."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            doc = z.read("word/document.xml")
        return b'w:val="EVBody"' in doc or b'w:val="EVH1"' in doc
    except Exception:
        return False


def _update(job_id, **kw):
    """Progress writes from the worker thread, in their own short session."""
    db = SessionLocal()
    try:
        j = db.get(Job, job_id)
        for k, v in kw.items():
            setattr(j, k, v)
        db.commit()
    finally:
        db.close()


def _doc_to_docx(src: Path) -> Path:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise RuntimeError("A .doc file needs LibreOffice to convert it. Install LibreOffice or save the file as .docx or PDF.")
    subprocess.run([soffice, "--headless", "--convert-to", "docx", "--outdir", str(src.parent), str(src)],
                   capture_output=True, timeout=600)
    out = src.with_suffix(".docx")
    if not out.exists():
        raise RuntimeError("LibreOffice could not convert this .doc file")
    return out


class Cancelled(Exception):
    """Raised inside M1 when someone presses Stop. A decision, not an error."""


def _run_m1_extract(j: Job, store, job_id: int) -> bytes:
    """Printed book (PDF, Word) through M1 in this process. Returns the flow document and saves M1's extras."""
    import hashlib
    from .. import m1
    with SessionLocal() as sdb:
        values = m1.effective(sdb)
    extras = f"m1/{j.book_id}/{j.id}"
    store.put(f"{extras}/m1_settings.json", json.dumps(m1.masked(values), ensure_ascii=False, indent=1).encode())
    _update(job_id, extras_key=extras)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        src = tmp / ("input" + Path(j.filename).suffix.lower())
        src.write_bytes(store.get(j.storage_key))
        if src.suffix == ".doc":
            src = _doc_to_docx(src)
        outdir = tmp / "out"
        last = [0.0]

        def progress(stage, page, total):
            # M1 calls this once per page, which is the only moment the job can
            # be stopped cleanly. Without a check here, pressing Stop did
            # nothing until the whole book had finished.
            with SessionLocal() as cdb:
                cur = cdb.get(Job, job_id)
                if cur and cur.status == "cancelled":
                    raise Cancelled()
            now = time.time()
            if now - last[0] > 1 or page == total:
                last[0] = now
                _update(job_id, stage="M1 read" if stage == "scan" else "M1 build", pages=total, pages_done=page)

        res = m1.run(str(src), str(outdir), values, progress)
        flow = Path(res.files["flow_docx"])
        for name in ("report.html", "ledger.jsonl", "book.json"):
            f = outdir / name
            if f.exists():
                store.put(f"{extras}/{name}", f.read_bytes())
        specs = {}
        for fj in (outdir / "figures").glob("*.json") if (outdir / "figures").exists() else []:
            png = fj.with_suffix(".png")
            if png.exists():
                try:
                    specs[hashlib.sha1(png.read_bytes()).hexdigest()[:12]] = json.loads(fj.read_text(encoding="utf-8"))
                except Exception:
                    pass
        store.put(f"{extras}/m1_specs.json", json.dumps(specs, ensure_ascii=False).encode())
        store.put(f"{extras}/summary.json", json.dumps({"passed": res.passed, "failures": res.failures[:50],
                                                        "elapsed": round(res.elapsed, 1), "stats": {k: v for k, v in res.book.stats.items() if isinstance(v, (int, float, str))}},
                                                       ensure_ascii=False).encode())
        return flow.read_bytes(), specs


def run_m1(job_id: int):
    """Printed book: M1 extracts it, the converter builds the digital book, M2 redraws the figures.
    M1 flow document: converter, then M2. Either way the book ends in the review queue. Nothing is published here."""
    from ..content import ingest_flow
    from .. import m1, m2
    db = SessionLocal()
    try:
        j = db.get(Job, job_id)
        if j.status == "cancelled":
            return
        store = get_storage()
        try:
            specs = {}
            if (j.kind or ("flow" if j.filename.lower().endswith(".docx") else "book")) == "flow":
                j.status, j.stage = "running", "Convert"; db.commit()
                flow = store.get(j.storage_key)
                j.book.flow_key = j.storage_key
            else:
                with m1.LOCK:  # one book through M1 at a time; the rest wait in the queue
                    db.refresh(j)
                    if j.status == "cancelled":
                        return
                    j.status, j.stage, j.pages_done = "running", "M1 read", 0; db.commit()
                    flow, specs = _run_m1_extract(j, store, job_id)
                db.expire_all(); j = db.get(Job, job_id)
                key = j.storage_key.rsplit("/", 1)[0] + "/flow.docx"
                store.put(key, flow); j.book.flow_key = key
                j.stage = "Convert"; db.commit()
            _rep = ingest_flow(db, j.book, flow)
            # Record what this book cost and how it was made, so the catalogue
            # can show cost per school rather than a bare total.
            try:
                from .. import costing
                det = (_rep or {}).get("detected") or {}
                routes = det.get("routes") or {}
                figs = ((_rep or {}).get("coverage") or {}).get("figures", 0)
                j.book.route_native = routes.get("native", 0) + routes.get("hybrid", 0)
                j.book.route_scanned = routes.get("scanned", 0)
                j.book.figures_n = figs
                j.book.split_by = (_rep or {}).get("split_by", "sections")
                j.book.headings_n = ((_rep or {}).get("counts") or {}).get("heading", 0)
                j.book.cost_usd = costing.book_cost(
                    j.book.route_scanned, figs)["total"]
            except Exception:
                pass
            # A book that had to be split by page still reaches the reviewer,
            # but the super admin should be told it is not a normal conversion.
            if _rep and _rep.get("split_warning"):
                # Job has no separate note field, and this is shown on the
                # Processing row already. It is a warning, not a failure: the
                # job still finishes and the book still reaches the reviewer.
                j.error = "Note: " + _rep["split_warning"][:480]
            if j.extras_key:
                try:
                    specs = specs or json.loads(store.get(f"{j.extras_key}/m1_specs.json"))
                except Exception:
                    pass
            store.put(f"{j.book.content_key}/m1_specs.json", json.dumps(specs, ensure_ascii=False).encode())
            j.pages = j.pages or j.book.pages
            if m2.settings_of(db).get("enabled"):
                j.book.status = "processing"  # the reviewer gets it once the figures are redrawn
                j.stage, j.pages_done = "M2", 0; db.commit()
                book = j.book
                m2.run_book(db, book, lambda d, t: _update(job_id, pages_done=d, pages=t))
                db.expire_all(); j = db.get(Job, job_id)
                j.book.status = "in_review"
            j.status, j.stage, j.finished_at = "done", "Done", datetime.utcnow()
            j.pages_done = j.pages = j.book.pages
        except Cancelled:
            # Stopped on purpose, so it is not a failure and the half-made book
            # is not offered to a reviewer.
            db.rollback(); j = db.get(Job, job_id)
            j.status, j.stage, j.finished_at = "cancelled", "Stopped", datetime.utcnow()
            j.error = ""
            if j.book and j.book.status == "processing":
                j.book.status = "upcoming"
        except Exception as e:
            db.rollback(); j = db.get(Job, job_id)
            j.status, j.error, j.finished_at = "failed", str(e)[-2000:], datetime.utcnow()
            if j.book and j.book.status == "processing" and j.book.content_key:
                j.book.status = "in_review"  # converted content is still reviewable
        db.commit()
    finally:
        db.close()


def resume_unfinished():
    """On startup: jobs cut off by a restart are queued and run again."""
    db = SessionLocal()
    try:
        ids = [j.id for j in db.query(Job).filter(Job.status.in_(("queued", "running")))]
        for j in db.query(Job).filter(Job.id.in_(ids)):
            j.status, j.pages_done = "queued", 0
        db.commit()
    finally:
        db.close()
    for jid in ids:
        threading.Thread(target=run_m1, args=(jid,), daemon=True).start()


@router.get("")
def list_jobs(db: Session = Depends(get_db), _=Depends(platform_admin)):
    return [out(j) for j in db.query(Job).order_by(Job.created_at.desc()).all()]


@router.get("/summary")
def summary(db: Session = Depends(get_db), _=Depends(platform_admin)):
    s = {k: 0 for k in ("queued", "running", "done", "failed", "cancelled")}
    credits = 0.0
    for j in db.query(Job).all():
        s[j.status] = s.get(j.status, 0) + 1
        credits += j.cost_credits
    return {**s, "credits_used": credits, "m1_configured": True}



@router.post("")
async def upload(file: UploadFile = File(...), title: str = Form(""), subject: str = Form(""), board: str = Form(""),
                 grade: str = Form(""), medium: str = Form("English"), book_id: int | None = Form(None),
                 reviewer_id: int | None = Form(None), kind: str = Form("auto"),
                 force: bool = Form(False),
                 db: Session = Depends(get_db), me=Depends(platform_admin)):
    if not file.filename.lower().endswith(ALLOWED):
        raise HTTPException(422, "Upload a PDF or Word file")
    data = await file.read()
    if not data:
        raise HTTPException(422, "The file is empty")

    # Never pay twice for the same book. One textbook serves every school on
    # that syllabus, so the same file arriving again should cost nothing. The
    # fingerprint column already existed; nothing read it until now.
    import hashlib
    file_fp = "f:" + hashlib.sha256(data).hexdigest()[:48]
    if not book_id and not force:
        twin = db.query(Book).filter(Book.file_sha == file_fp,
                                     Book.status.in_(("live", "in_review", "approved"))).first()
        if twin:
            n = db.query(ClassBook).filter(ClassBook.book_id == twin.id).count()
            raise HTTPException(409,
                f"We already have this book: {twin.title}. It was processed on "
                f"{twin.created_at:%d %b %Y}"
                + (f" and {n} class{'es' if n != 1 else ''} already read it" if n else "")
                + ". Assign the existing one instead, or tick 'process anyway'.")

    if book_id:
        book = db.get(Book, book_id)
        if not book:
            raise HTTPException(404, "Book not found")
        book.status = "processing"
    else:
        book = Book(title=title or file.filename.rsplit(".", 1)[0], subject=subject, board=board, grade=grade,
                    medium=medium, status="processing", file_sha=file_fp)
        db.add(book); db.flush()
    if reviewer_id:
        from ..models import User
        rv = db.get(User, reviewer_id)
        if not rv or rv.role != "reviewer" or rv.status != "active":
            raise HTTPException(422, "Choose an active reviewer")
        book.assigned_reviewer_id = reviewer_id
    if kind not in ("auto", "book", "flow"):
        raise HTTPException(422, "kind must be auto, book or flow")
    if kind == "auto":
        kind = "flow" if file.filename.lower().endswith(".docx") and is_flow_docx(data) else "book"
    if kind == "flow" and not file.filename.lower().endswith(".docx"):
        raise HTTPException(422, "An M1 flow document is a .docx file")
    if kind == "flow" and not is_flow_docx(data):
        raise HTTPException(422, "This Word file is not an M1 flow document. Choose Printed book to run M1 on it.")
    pages = count_pages(data, file.filename)
    book.pages = pages or book.pages
    key = f"originals/{book.id}/{uuid.uuid4().hex}_{file.filename}"
    get_storage().put(key, data)
    if kind == "book":
        book.original_key = key
    per_page = (db.get(Setting, "ai").value or {}).get("m1_credits_per_page", 1) if db.get(Setting, "ai") else 1
    j = Job(book_id=book.id, filename=file.filename, storage_key=key, pages=pages, kind=kind, stage="Queued",
            cost_credits=pages * per_page, triggered_by=me.email)
    db.add(j); db.flush()
    log(db, me, "job.create", "job", j.id, file=file.filename, pages=pages, book_id=book.id)
    db.commit()
    threading.Thread(target=run_m1, args=(j.id,), daemon=True).start()
    return out(j)


@router.post("/{jid}/retry")
def retry(jid: int, db: Session = Depends(get_db), me=Depends(platform_admin)):
    j = db.get(Job, jid)
    if not j:
        raise HTTPException(404, "Job not found")
    if j.status not in ("failed", "cancelled"):
        raise HTTPException(409, "Only failed or cancelled jobs can be retried")
    j.status, j.error, j.finished_at, j.pages_done, j.stage = "queued", "", None, 0, "Queued"
    if j.book:
        j.book.status = "processing"
    log(db, me, "job.retry", "job", jid)
    db.commit()
    threading.Thread(target=run_m1, args=(jid,), daemon=True).start()
    return out(j)


@router.post("/{jid}/cancel")
def cancel(jid: int, db: Session = Depends(get_db), me=Depends(platform_admin)):
    j = db.get(Job, jid)
    if not j:
        raise HTTPException(404, "Job not found")
    if j.status not in ("queued", "running"):
        raise HTTPException(409, "This job has already finished")
    # A queued job stops at once; a running one stops at the next page, which
    # is the only safe place to put a half-read book down.
    j.status, j.finished_at = "cancelled", datetime.utcnow()
    log(db, me, "job.cancel", "job", jid)
    db.commit()
    return out(j)


EXTRAS = {"report": ("report.html", "text/html; charset=utf-8"), "settings": ("m1_settings.json", "application/json"),
          "ledger": ("ledger.jsonl", "text/plain; charset=utf-8"), "summary": ("summary.json", "application/json")}


@router.get("/{jid}/extras/{name}")
def extras(jid: int, name: str, db: Session = Depends(get_db), _=Depends(platform_admin)):
    """What M1 left behind for this job: its HTML report, the settings it ran with, its ledger."""
    from fastapi.responses import Response
    j = db.get(Job, jid)
    if not j or not j.extras_key or name not in EXTRAS:
        raise HTTPException(404, "Not found")
    fname, mt = EXTRAS[name]
    try:
        return Response(get_storage().get(f"{j.extras_key}/{fname}"), media_type=mt)
    except Exception:
        raise HTTPException(404, "Not found")
