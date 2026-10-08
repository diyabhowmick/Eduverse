"""FastAPI front end.

    uvicorn eduverse_book2docx.server:app --host 0.0.0.0 --port 8000

Upload a PDF or DOCX, watch it process, download flow.docx, book.json,
figures and the report. One worker thread by default so the two Ollama models
are never hammered by parallel jobs.
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import threading
import time
import traceback
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from .config import Config
from .ollama_client import OllamaClient
from .pipeline import run as run_pipeline
from .ui import INDEX_HTML

DATA_DIR = os.environ.get("EDUVERSE_DATA", os.path.abspath("eduverse_jobs"))
MAX_UPLOAD_MB = int(os.environ.get("EDUVERSE_MAX_UPLOAD_MB", "200"))
WORKERS = int(os.environ.get("EDUVERSE_WORKERS", "1"))
ALLOWED_EXT = {".pdf", ".docx", ".dotx"}

DOWNLOADABLE = {
    "flow.docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "layout.docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "book.json": "application/json",
    "report.html": "text/html",
    "digital/index.html": "text/html",
    "ledger.jsonl": "application/x-ndjson",
    "eduverse_base.docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


# ---------------------------------------------------------------------------
# Job model
# ---------------------------------------------------------------------------

@dataclass
class Job:
    id: str
    filename: str
    status: str = "queued"          # queued|running|ready|issues|failed
    stage: str = ""
    done: int = 0
    total: int = 0
    created: float = field(default_factory=time.time)
    started: Optional[float] = None
    finished: Optional[float] = None
    error: Optional[str] = None
    options: Dict[str, Any] = field(default_factory=dict)
    summary: Dict[str, Any] = field(default_factory=dict)
    files: List[str] = field(default_factory=list)

    def public(self) -> Dict[str, Any]:
        d = asdict(self)
        d["elapsed_s"] = round(
            (self.finished or time.time()) - (self.started or self.created), 1)
        d["percent"] = (round(100 * self.done / self.total)
                        if self.total else (100 if self.status == "ready" else 0))
        return d


class JobStore:
    def __init__(self, root: str):
        self.root = root
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()
        os.makedirs(root, exist_ok=True)
        self._rehydrate()

    def _rehydrate(self) -> None:
        """Jobs finished before a restart stay downloadable."""
        for jid in sorted(os.listdir(self.root)):
            meta = os.path.join(self.root, jid, "job.json")
            if not os.path.exists(meta):
                continue
            try:
                with open(meta, encoding="utf-8") as fh:
                    d = json.load(fh)
                d.pop("elapsed_s", None)
                d.pop("percent", None)
                job = Job(**d)
                if job.status in ("queued", "running"):
                    job.status = "failed"
                    job.error = "server restarted while this job was running"
                self._jobs[job.id] = job
            except Exception:
                continue

    def dir(self, jid: str) -> str:
        return os.path.join(self.root, jid)

    def add(self, job: Job) -> None:
        with self._lock:
            self._jobs[job.id] = job
        self.persist(job)

    def get(self, jid: str) -> Optional[Job]:
        return self._jobs.get(jid)

    def list(self) -> List[Job]:
        return sorted(self._jobs.values(), key=lambda j: -j.created)

    def persist(self, job: Job) -> None:
        os.makedirs(self.dir(job.id), exist_ok=True)
        tmp = os.path.join(self.dir(job.id), "job.json.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(asdict(job), fh, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp, os.path.join(self.dir(job.id), "job.json"))

    def delete(self, jid: str) -> bool:
        with self._lock:
            job = self._jobs.pop(jid, None)
        if job is None:
            return False
        shutil.rmtree(self.dir(jid), ignore_errors=True)
        return True


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

class Runner:
    def __init__(self, store: JobStore, workers: int = 1):
        self.store = store
        self.q: "queue.Queue[str]" = queue.Queue()
        self.threads = [
            threading.Thread(target=self._loop, daemon=True, name=f"ev-{i}")
            for i in range(max(1, workers))
        ]
        for t in self.threads:
            t.start()

    def submit(self, jid: str) -> None:
        self.q.put(jid)

    def _loop(self) -> None:
        while True:
            jid = self.q.get()
            try:
                self._process(jid)
            except Exception:
                job = self.store.get(jid)
                if job:
                    job.status = "failed"
                    job.error = traceback.format_exc(limit=4)
                    job.finished = time.time()
                    self.store.persist(job)
            finally:
                self.q.task_done()

    def _process(self, jid: str) -> None:
        job = self.store.get(jid)
        if job is None:
            return
        job.status = "running"
        job.started = time.time()
        self.store.persist(job)

        jdir = self.store.dir(jid)
        src = os.path.join(jdir, "input", job.filename)
        out = os.path.join(jdir, "out")

        cfg = _config_from(job.options)

        last = [0.0]

        def progress(stage: str, i: int, n: int) -> None:
            job.stage, job.done, job.total = stage, i, n
            now = time.time()
            if now - last[0] > 1.0 or i == n:      # do not thrash the disk
                last[0] = now
                self.store.persist(job)

        try:
            res = run_pipeline(src, out, cfg, progress=progress)
        except Exception:
            job.status = "failed"
            job.error = traceback.format_exc(limit=4)
            job.finished = time.time()
            self.store.persist(job)
            return

        # A book that failed its own gate is not ready. It used to be marked
        # ready with the failure sitting quietly inside the summary.
        job.status = "ready" if res.passed else "issues"
        job.stage = "done"
        job.finished = time.time()
        job.files = [n for n in DOWNLOADABLE if os.path.exists(os.path.join(out, n))]
        job.summary = {
            "pages": len(res.book.pages),
            "detected": res.book.detected,
            "counts": res.book.counts(),
            "ledger": {"detected": res.ledger.detected,
                       "emitted": res.ledger.emitted,
                       "dropped": res.ledger.dropped,
                       "balanced": res.ledger.balanced()},
            "written": res.stats,
            "coverage": res.coverage.summary() if res.coverage else None,
            "gate_passed": res.passed,
            "failures": res.failures,
            "figures": len([f for f in os.listdir(os.path.join(out, "figures"))
                            if f.endswith(".png")])
            if os.path.isdir(os.path.join(out, "figures")) else 0,
        }
        self.store.persist(job)


def _config_from(opts: Dict[str, Any]) -> Config:
    cfg = Config()
    cfg.page_lock = bool(opts.get("page_lock"))
    cfg.write_layout_docx = bool(opts.get("layout_docx"))
    cfg.show_page_markers = bool(opts.get("page_markers", True))
    cfg.describe_figures = bool(opts.get("describe", True))
    cfg.composite_split = bool(opts.get("split_composites", True))
    cfg.offline = bool(opts.get("offline"))
    if opts.get("dpi"):
        cfg.page_dpi = int(opts["dpi"])
        cfg.figure_dpi = int(opts["dpi"])
    if opts.get("ocr_model"):
        cfg.ocr_model = str(opts["ocr_model"])
    if opts.get("vlm_model"):
        cfg.vlm_model = str(opts["vlm_model"])
    if os.environ.get("OLLAMA_HOST"):
        cfg.ollama_host = os.environ["OLLAMA_HOST"]
    return cfg


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

store = JobStore(DATA_DIR)
runner = Runner(store, WORKERS)

app = FastAPI(title="EduVerse book to DOCX", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return INDEX_HTML


@app.get("/api/health")
def health() -> Dict[str, Any]:
    cfg = _config_from({})
    h = OllamaClient(cfg).health()
    return {
        "ok": True,
        "ollama": h,
        "models": {"ocr": cfg.ocr_model, "vlm": cfg.vlm_model},
        "workers": WORKERS,
        "queued": runner.q.qsize(),
        "data_dir": DATA_DIR,
        "max_upload_mb": MAX_UPLOAD_MB,
    }


@app.post("/api/jobs", status_code=202)
async def create_job(
    file: UploadFile = File(...),
    page_lock: bool = Form(False),
    layout_docx: bool = Form(False),
    page_markers: bool = Form(True),
    describe: bool = Form(True),
    split_composites: bool = Form(True),
    offline: bool = Form(False),
    dpi: Optional[int] = Form(None),
) -> Dict[str, Any]:
    name = os.path.basename(file.filename or "")
    ext = os.path.splitext(name)[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"expected {' or '.join(sorted(ALLOWED_EXT))}, got {ext or 'nothing'}")

    jid = uuid.uuid4().hex[:12]
    in_dir = os.path.join(store.dir(jid), "input")
    os.makedirs(in_dir, exist_ok=True)
    dest = os.path.join(in_dir, name)

    size = 0
    limit = MAX_UPLOAD_MB * 1024 * 1024
    with open(dest, "wb") as fh:
        while True:
            chunk = await file.read(1 << 20)
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                fh.close()
                shutil.rmtree(store.dir(jid), ignore_errors=True)
                raise HTTPException(413, f"file over {MAX_UPLOAD_MB} MB")
            fh.write(chunk)
    if size == 0:
        shutil.rmtree(store.dir(jid), ignore_errors=True)
        raise HTTPException(400, "empty file")

    job = Job(id=jid, filename=name, options={
        "page_lock": page_lock, "layout_docx": layout_docx,
        "page_markers": page_markers, "describe": describe,
        "split_composites": split_composites, "offline": offline,
        "dpi": dpi,
    })
    store.add(job)
    runner.submit(jid)
    return {"job_id": jid, "status": job.status,
            "poll": f"/api/jobs/{jid}", "size_bytes": size}


@app.get("/api/jobs")
def list_jobs(limit: int = 50) -> Dict[str, Any]:
    return {"jobs": [j.public() for j in store.list()[:limit]]}


@app.get("/api/jobs/{jid}")
def get_job(jid: str) -> Dict[str, Any]:
    job = store.get(jid)
    if job is None:
        raise HTTPException(404, "no such job")
    return job.public()


@app.delete("/api/jobs/{jid}")
def delete_job(jid: str) -> Dict[str, Any]:
    if not store.delete(jid):
        raise HTTPException(404, "no such job")
    return {"deleted": jid}


@app.get("/api/jobs/{jid}/files/{name}")
def download(jid: str, name: str):
    job = store.get(jid)
    if job is None:
        raise HTTPException(404, "no such job")
    if name not in DOWNLOADABLE:
        raise HTTPException(400, "not a downloadable file")
    path = os.path.join(store.dir(jid), "out", name)
    if not os.path.exists(path):
        raise HTTPException(404, f"{name} was not produced for this job")
    stem = os.path.splitext(job.filename)[0][:60]
    out_name = f"{stem}_{name}" if not name.startswith(stem) else name
    return FileResponse(path, media_type=DOWNLOADABLE[name], filename=out_name)


@app.get("/api/jobs/{jid}/digital", response_class=HTMLResponse)
def digital(jid: str):
    path = os.path.join(store.dir(jid), "out", "digital", "index.html")
    if not os.path.exists(path):
        raise HTTPException(404, "no digital book yet")
    with open(path, encoding="utf-8") as fh:
        return HTMLResponse(fh.read())


@app.get("/api/jobs/{jid}/report", response_class=HTMLResponse)
def report(jid: str):
    path = os.path.join(store.dir(jid), "out", "report.html")
    if not os.path.exists(path):
        raise HTTPException(404, "no report yet")
    with open(path, encoding="utf-8") as fh:
        return HTMLResponse(fh.read())


@app.get("/api/jobs/{jid}/book")
def book_json(jid: str):
    path = os.path.join(store.dir(jid), "out", "book.json")
    if not os.path.exists(path):
        raise HTTPException(404, "no book.json yet")
    with open(path, encoding="utf-8") as fh:
        return JSONResponse(json.load(fh))


@app.get("/api/jobs/{jid}/figures")
def list_figures(jid: str) -> Dict[str, Any]:
    fdir = os.path.join(store.dir(jid), "out", "figures")
    if not os.path.isdir(fdir):
        raise HTTPException(404, "no figures")
    names = sorted(f for f in os.listdir(fdir) if f.endswith(".png"))
    return {"figures": [{"name": n,
                         "url": f"/api/jobs/{jid}/asset/figures/{n}"}
                        for n in names]}


@app.get("/api/jobs/{jid}/asset/{kind}/{name}")
def asset(jid: str, kind: str, name: str):
    if kind not in ("figures", "pages"):
        raise HTTPException(400, "unknown asset kind")
    if "/" in name or "\\" in name or name.startswith("."):
        raise HTTPException(400, "bad name")
    path = os.path.join(store.dir(jid), "out", kind, name)
    if not os.path.exists(path):
        raise HTTPException(404, "no such asset")
    media = "application/json" if name.endswith(".json") else "image/png"
    return FileResponse(path, media_type=media)


def main() -> None:
    import uvicorn
    uvicorn.run("eduverse_book2docx.server:app",
                host=os.environ.get("EDUVERSE_HOST", "0.0.0.0"),
                port=int(os.environ.get("EDUVERSE_PORT", "8000")),
                reload=False)


if __name__ == "__main__":
    main()
