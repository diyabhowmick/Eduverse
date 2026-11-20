import contextlib, io, json, os, shutil, subprocess, sys, tempfile, threading, time, uuid, zipfile
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from ..config import settings, BASE
from ..db import get_db, SessionLocal
from ..models import Job, Book, Setting
from ..security import super_admin
from ..storage import get_storage
from ..audit import log

router = APIRouter(prefix="/api/jobs", tags=["processing"])
ALLOWED = (".pdf", ".docx", ".doc")


def count_pages(src: Path, name: str) -> int:
    """Pages in an uploaded file, read from disk so an 85 MB book is never held in memory."""
    if name.lower().endswith(".pdf"):
        try:
            from pypdf import PdfReader
            return len(PdfReader(str(src)).pages)
        except Exception:
            n = 0
            with open(src, "rb") as f:
                for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
                    n += chunk.count(b"/Type /Page") - chunk.count(b"/Type /Pages")
            return max(n, 0)
    return 0


def out(j: Job):
    return {"id": j.id, "stage": j.stage, "filename": j.filename, "status": j.status, "pages": j.pages,
            "pages_done": j.pages_done, "cost_credits": j.cost_credits, "error": j.error, "note": j.note or "",
            "stages": j.stages or {},
            "triggered_by": j.triggered_by, "created_at": j.created_at, "finished_at": j.finished_at,
            "book_id": j.book_id, "book": j.book.title if j.book else "", "book_status": j.book.status if j.book else "",
            "kind": j.kind or ("flow" if j.filename.lower().endswith(".docx") else "book"), "has_extras": bool(j.extras_key)}


def is_flow_docx(src: Path) -> bool:
    """An M1 flow document uses the EV paragraph styles; a printed book saved as Word does not."""
    try:
        with zipfile.ZipFile(src) as z:
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
        _mark(j, kw.get("stage"), pages=kw.get("pages"), done=kw.get("pages_done"))
        db.commit()
    finally:
        db.close()


def _mark(j: Job, name: str | None, *, pages=None, done=None, failed=None, error=None, end=False):
    """Record what each stage did, so a finished job can still answer
    "where did the time go". `stage` alone cannot: it holds only where the job
    is now, and every stage overwrites pages_done.

    Safe to call with the stage the job is already in — it just updates it.
    """
    st = dict(j.stages or {})
    name = name or j.stage
    if not name or name in ("Queued",):
        j.stages = st
        return
    now = datetime.utcnow().isoformat(timespec="seconds")
    cur = dict(st.get(name) or {})
    if not cur.get("started"):
        cur["started"] = now
        # Whatever ran before this is finished the moment a new stage starts.
        for other, v in st.items():
            if other != name and isinstance(v, dict) and v.get("started") and not v.get("finished"):
                v["finished"] = now
    if pages is not None:
        cur["pages"] = pages
    if done is not None:
        cur["done"] = done
    if failed is not None:
        cur["failed"] = failed
    if error is not None:
        cur["error"] = str(error)[:300]
    if end:
        cur["finished"] = now
    st[name] = cur
    j.stages = st            # reassign: SQLAlchemy does not see in-place JSON edits


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
        values = m1.with_env(m1.effective(sdb))
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
                j.status, j.stage = "running", "Convert"; _mark(j, "Convert"); db.commit()
                flow = store.get(j.storage_key)
                j.book.flow_key = j.storage_key
            else:
                with m1.LOCK:  # one book through M1 at a time; the rest wait in the queue
                    db.refresh(j)
                    if j.status == "cancelled":
                        return
                    j.status, j.stage, j.pages_done = "running", "M1 read", 0; _mark(j, "M1 read"); db.commit()
                    flow, specs = _run_m1_extract(j, store, job_id)
                db.expire_all(); j = db.get(Job, job_id)
                key = j.storage_key.rsplit("/", 1)[0] + "/flow.docx"
                store.put(key, flow); j.book.flow_key = key
                j.stage = "Convert"; _mark(j, "Convert"); db.commit()
            _rep = ingest_flow(db, j.book, flow)
            # A book that had to be split by heading or by page still reaches
            # the reviewer, but the super admin should be told it is not a
            # normal conversion. Kept in its own field: error is only shown on
            # a failed job, so a warning put there was never seen.
            j.note = (_rep or {}).get("split_warning", "")[:1000]
            if j.extras_key:
                try:
                    specs = specs or json.loads(store.get(f"{j.extras_key}/m1_specs.json"))
                except Exception:
                    pass
            store.put(f"{j.book.content_key}/m1_specs.json", json.dumps(specs, ensure_ascii=False).encode())
            j.pages = j.pages or j.book.pages
            if m2.settings_of(db).get("enabled"):
                j.book.status = "processing"  # the reviewer gets it once the figures are redrawn
                j.stage, j.pages_done = "M2", 0; _mark(j, "M2"); db.commit()
                book = j.book
                m2.run_book(db, book, lambda d, t: _update(job_id, pages_done=d, pages=t))
                db.expire_all(); j = db.get(Job, job_id)
                j.book.status = "in_review"
            _mark(j, j.stage, end=True)
            j.status, j.stage, j.finished_at = "done", "Done", datetime.utcnow()
            j.pages_done = j.pages = j.book.pages
        except Cancelled:
            # Stopped on purpose, so it is not a failure and the half-made book
            # is not offered to a reviewer.
            db.rollback(); j = db.get(Job, job_id)
            _mark(j, j.stage, end=True)
            j.status, j.stage, j.finished_at = "cancelled", "Stopped", datetime.utcnow()
            j.error = ""
            if j.book and j.book.status == "processing":
                j.book.status = "upcoming"
        except Exception as e:
            db.rollback(); j = db.get(Job, job_id)
            # Pin the error to the stage it happened in, so "where did it break"
            # is answerable after the fact and not only from the log.
            _mark(j, j.stage, error=str(e), end=True)
            j.status, j.error, j.finished_at = "failed", str(e)[-2000:], datetime.utcnow()
            if j.book and j.book.status == "processing" and j.book.content_key:
                j.book.status = "in_review"  # converted content is still reviewable
        db.commit()
    finally:
        db.close()


def supervise(job_id: int):
    """Runs the job in its own process, so a crash in PDF or image code fails that job and leaves the website up."""
    from .. import m1
    with SessionLocal() as db:
        j = db.get(Job, job_id)
        is_book = bool(j) and (j.kind or ("flow" if j.filename.lower().endswith(".docx") else "book")) != "flow"
    with (m1.LOCK if is_book else contextlib.nullcontext()):  # one book through M1 at a time; the rest wait in the queue
        r = subprocess.run([sys.executable, "-m", "app.jobrun", str(job_id)], capture_output=True, text=True, errors="replace",
                           env={**os.environ, "PYTHONPATH": str(BASE)})
    if r.returncode:
        with SessionLocal() as db:
            j = db.get(Job, job_id)
            if j and j.status in ("queued", "running"):
                j.status, j.finished_at = "failed", datetime.utcnow()
                j.error = f"The processing step stopped unexpectedly (code {r.returncode}).\n{r.stderr[-1500:]}"
                db.commit()


def start(job_id: int):
    threading.Thread(target=supervise, args=(job_id,), daemon=True).start()


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
        start(jid)


@router.get("")
def list_jobs(db: Session = Depends(get_db), _=Depends(super_admin)):
    return [out(j) for j in db.query(Job).order_by(Job.created_at.desc()).all()]


@router.get("/summary")
def summary(db: Session = Depends(get_db), _=Depends(super_admin)):
    s = {k: 0 for k in ("queued", "running", "done", "failed", "cancelled")}
    credits = 0.0
    for j in db.query(Job).all():
        s[j.status] = s.get(j.status, 0) + 1
        credits += j.cost_credits
    return {**s, "credits_used": credits, "m1_configured": True}



# ---------------------------------------------------------------- big uploads
#
# Railway's edge closes a request whose body has not finished uploading within
# five minutes, and ends any request after fifteen (Railway docs, Public
# Networking > Specs and limits). A Tamil Nadu textbook PDF is 75-85 MB, which
# needs a sustained 2.4 Mbps for the whole five minutes to get through in one
# request. On an ordinary Indian broadband link it does not make it: the edge
# drops the request part way, the backend never receives the file, and the
# browser is left holding a failure that never reached the application - which
# is why the upload "just failed" with nothing in the server log.
#
# So the browser sends the file in 4 MB pieces. Each piece is its own short
# request, far inside every limit, and a piece that fails is retried on its own
# instead of starting the whole book again.
PART_SIZE = 4 * 1024 * 1024
PART_DIR = Path(tempfile.gettempdir()) / "ev_upload_parts"
PARTS: dict[str, dict] = {}
_parts_lock = threading.Lock()


def _sweep_parts(hours=6):
    """Pieces left behind by an upload nobody finished."""
    for uid, u in list(PARTS.items()):
        if time.time() - u["at"] > hours * 3600:
            with _parts_lock:
                PARTS.pop(uid, None)
            shutil.rmtree(u["dir"], ignore_errors=True)
    if PART_DIR.exists():
        for d in PART_DIR.iterdir():
            with contextlib.suppress(Exception):
                if d.is_dir() and time.time() - d.stat().st_mtime > hours * 3600 and d.name not in PARTS:
                    shutil.rmtree(d, ignore_errors=True)


@router.post("/upload/start")
def upload_start(filename: str = Form(...), size: int = Form(0), me=Depends(super_admin)):
    """Begin a piece-by-piece upload. Returns the id the pieces are sent under."""
    name = Path(filename).name
    if not name.lower().endswith(ALLOWED):
        raise HTTPException(422, "Upload a PDF or Word file")
    _sweep_parts()
    free = shutil.disk_usage(tempfile.gettempdir()).free
    if size and free < size * 2 + 50 * 1024 * 1024:
        raise HTTPException(507, f"There is not enough room on the server for a {size // 1048576} MB file "
                                 f"({free // 1048576} MB free). Clear old uploads or give the service more disk.")
    uid = uuid.uuid4().hex
    d = PART_DIR / uid
    d.mkdir(parents=True, exist_ok=True)
    with _parts_lock:
        PARTS[uid] = {"filename": name, "dir": d, "by": me.email, "at": time.time(), "size": size, "got": 0}
    return {"upload_id": uid, "part_size": PART_SIZE, "parts": -(-size // PART_SIZE) if size else 0}


@router.post("/upload/part")
async def upload_part(upload_id: str = Form(...), index: int = Form(...), chunk: UploadFile = File(...),
                      me=Depends(super_admin)):
    """One piece of a file. Sending the same piece again simply overwrites it, so a retry is safe."""
    u = PARTS.get(upload_id)
    if not u:
        raise HTTPException(410, "This upload is no longer open — the server restarted, or it was left too long. Choose the file and start again.")
    if index < 0 or index > 100000:
        raise HTTPException(422, "Bad piece number")
    data = await chunk.read()
    p = u["dir"] / f"{index:06d}"
    p.write_bytes(data)
    with _parts_lock:
        u["got"] = sum(1 for _ in u["dir"].iterdir())
        u["at"] = time.time()
    return {"index": index, "bytes": len(data), "pieces_received": u["got"]}


def _assemble(uid: str) -> tuple[Path, str]:
    """Join the pieces into one file, in order, without holding it in memory."""
    u = PARTS.get(uid)
    if not u:
        raise HTTPException(410, "This upload is no longer open. Choose the file and start again.")
    parts = sorted(u["dir"].glob("[0-9]*"))
    if not parts:
        raise HTTPException(422, "No part of the file arrived. Try the upload again.")
    expected = -(-u["size"] // PART_SIZE) if u["size"] else len(parts)
    if len(parts) < expected:
        raise HTTPException(422, f"Only {len(parts)} of {expected} pieces of the file arrived. "
                                 f"The connection dropped part way — try the upload again.")
    whole = u["dir"] / "whole"
    with open(whole, "wb") as out_f:
        for p in parts:
            with open(p, "rb") as f:
                shutil.copyfileobj(f, out_f, 1024 * 1024)
            p.unlink()
    if u["size"] and whole.stat().st_size != u["size"]:
        raise HTTPException(422, f"The file arrived incomplete: {whole.stat().st_size // 1048576} MB of "
                                 f"{u['size'] // 1048576} MB. Try the upload again.")
    return whole, u["filename"]


@router.post("")
async def upload(file: UploadFile | None = File(None), upload_id: str = Form(""),
                 title: str = Form(""), subject: str = Form(""), board: str = Form(""),
                 grade: str = Form(""), medium: str = Form("English"), book_id: int | None = Form(None),
                 reviewer_id: int | None = Form(None), kind: str = Form("auto"),
                 content_type: str = Form("book"), level: str = Form("school"), university: str = Form(""), course: str = Form(""),
                 semester: str = Form(""), price: float = Form(0), cover: UploadFile | None = File(None),
                 db: Session = Depends(get_db), me=Depends(super_admin)):
    # The file arrives either in pieces (upload_id, the normal path for a book)
    # or whole in this one request (a small file, or an older client).
    tmp_dir = None
    if upload_id:
        src, filename = _assemble(upload_id)
    elif file is not None and file.filename:
        filename = Path(file.filename).name
        tmp_dir = Path(tempfile.mkdtemp(prefix="ev_up_"))
        src = tmp_dir / filename
        with open(src, "wb") as out_f:
            while True:
                b = await file.read(1024 * 1024)
                if not b:
                    break
                out_f.write(b)
    else:
        raise HTTPException(422, "Choose a file to upload")
    try:
        return await _create_job(db, me, src, filename, title=title, subject=subject, board=board, grade=grade,
                                 medium=medium, book_id=book_id, reviewer_id=reviewer_id, kind=kind,
                                 content_type=content_type, level=level, university=university, course=course,
                                 semester=semester, price=price, cover=cover)
    finally:
        with _parts_lock:
            u = PARTS.pop(upload_id, None) if upload_id else None
        for d in (u["dir"] if u else None, tmp_dir):
            if d:
                shutil.rmtree(d, ignore_errors=True)


async def _create_job(db: Session, me, src: Path, filename: str, *, title, subject, board, grade, medium,
                      book_id, reviewer_id, kind, content_type, level, university, course, semester, price, cover):
    if not filename.lower().endswith(ALLOWED):
        raise HTTPException(422, "Upload a PDF or Word file")
    if content_type not in ("book", "document"):
        raise HTTPException(422, "content_type must be book or document")
    if price < 0:
        raise HTTPException(422, "The price cannot be negative")
    if not src.exists() or src.stat().st_size == 0:
        raise HTTPException(422, "The file is empty")
    if book_id:
        book = db.get(Book, book_id)
        if not book:
            raise HTTPException(404, "Book not found")
        book.status = "processing"
    else:
        book = Book(title=title.strip() or filename.rsplit(".", 1)[0], subject=subject, board=board, grade=grade,
                    medium=medium, status="processing", track="textbook", level=level, university=university, course=course,
                    semester=semester, price=price, content_type=content_type)
        db.add(book); db.flush()
    if cover is not None and cover.filename:
        from .books import save_cover
        save_cover(book, cover.filename, await cover.read())
    if reviewer_id:
        from ..models import User
        rv = db.get(User, reviewer_id)
        if not rv or rv.role != "reviewer" or rv.status != "active":
            raise HTTPException(422, "Choose an active reviewer")
        book.assigned_reviewer_id = reviewer_id
    if kind not in ("auto", "book", "flow"):
        raise HTTPException(422, "kind must be auto, book or flow")
    if kind == "auto":
        kind = "flow" if filename.lower().endswith(".docx") and is_flow_docx(src) else "book"
    if kind == "flow" and not filename.lower().endswith(".docx"):
        raise HTTPException(422, "An M1 flow document is a .docx file")
    if kind == "flow" and not is_flow_docx(src):
        raise HTTPException(422, "This Word file is not an M1 flow document. Choose Printed book to run M1 on it.")
    pages = count_pages(src, filename)
    book.pages = pages or book.pages
    key = f"originals/{book.id}/{uuid.uuid4().hex}_{filename}"
    try:
        get_storage().put_file(key, src)
    except OSError as e:
        # The upload itself was fine; storage would not take it. Say so, because
        # "upload failed" sends everybody looking at the wrong end of the problem.
        raise HTTPException(500, f"The file uploaded but could not be saved to storage ({settings.storage_dir}): "
                                 f"{type(e).__name__}: {e}. Check the volume on the Flags and issues screen.")
    if kind == "book":
        book.original_key = key
    per_page = (db.get(Setting, "ai").value or {}).get("m1_credits_per_page", 1) if db.get(Setting, "ai") else 1
    j = Job(book_id=book.id, filename=filename, storage_key=key, pages=pages, kind=kind, stage="Queued",
            cost_credits=pages * per_page, triggered_by=me.email)
    db.add(j); db.flush()
    log(db, me, "job.create", "job", j.id, file=filename, pages=pages, book_id=book.id)
    db.commit()
    start(j.id)
    return out(j)


@router.post("/{jid}/retry")
def retry(jid: int, db: Session = Depends(get_db), me=Depends(super_admin)):
    j = db.get(Job, jid)
    if not j:
        raise HTTPException(404, "Job not found")
    if j.status not in ("failed", "cancelled"):
        raise HTTPException(409, "Only failed or cancelled jobs can be retried")
    j.status, j.error, j.note, j.finished_at, j.pages_done, j.stage = "queued", "", "", None, 0, "Queued"
    if j.book:
        j.book.status = "processing"
    log(db, me, "job.retry", "job", jid)
    db.commit()
    start(jid)
    return out(j)


@router.post("/{jid}/cancel")
def cancel(jid: int, db: Session = Depends(get_db), me=Depends(super_admin)):
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
def extras(jid: int, name: str, db: Session = Depends(get_db), _=Depends(super_admin)):
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
