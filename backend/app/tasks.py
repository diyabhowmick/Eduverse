"""Durable background work, kept in the database instead of in a thread of the web server.

enqueue(kind, *args) records the work. A worker claims it, runs it, and marks it done. If the process dies
halfway (a redeploy, a crash), the claim expires and another worker, or the same one after restart, runs it again.
Every task kind is safe to run twice: each one picks up from what is already saved.

On one box the API runs a worker inside itself (EMBEDDED_WORKER=1, the default). To scale, run more API copies
with EMBEDDED_WORKER=0 and one or more worker containers: python -m app.worker"""
import os, socket, threading, time, traceback
from datetime import datetime, timedelta
from .db import SessionLocal, engine
from .models import Task

LEASE = timedelta(minutes=int(os.getenv("TASK_LEASE_MIN", "20")))  # a running task must check in within this time
MAX_ATTEMPTS = 3
SLOTS = {"m1": 1, "prep": 1, "paper_ai": 2, "transcribe": 2}                       # how many of each kind one worker runs at once
WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"


def _handlers():
    from .routers.jobs import supervise
    from .routers.learn import supervise_prep
    from .routers.exams import supervise_ai
    from .routers.study import transcribe
    return {"m1": supervise, "prep": supervise_prep, "paper_ai": supervise_ai, "transcribe": transcribe}


def enqueue(kind: str, *args, db=None) -> int:
    """Records the work once: the same kind and arguments already waiting or running is not queued again."""
    key = kind + ":" + ":".join(map(str, args))
    own = db is None
    db = db or SessionLocal()
    try:
        t = db.query(Task).filter(Task.key == key, Task.status.in_(("queued", "running"))).first()
        if not t:
            t = Task(kind=kind, args=list(args), key=key)
            db.add(t)
            db.commit() if own else db.flush()
        wake.set()
        return t.id
    finally:
        if own:
            db.close()


def _claim(db, kinds: list[str]) -> Task | None:
    now = datetime.utcnow()
    q = db.query(Task).filter(Task.kind.in_(kinds), ((Task.status == "queued") | ((Task.status == "running") & (Task.locked_until < now))))
    q = q.order_by(Task.id)
    if engine.dialect.name == "postgresql":
        q = q.with_for_update(skip_locked=True)
    t = q.first()
    if not t:
        return None
    if t.status == "running":            # its worker went away without finishing
        if t.attempts >= MAX_ATTEMPTS:
            t.status, t.finished_at, t.error = "failed", now, (t.error or "") + f"\nGave up after {t.attempts} attempts."
            db.commit()
            return None
    t.status, t.locked_by, t.locked_until, t.attempts = "running", WORKER_ID, now + LEASE, t.attempts + 1
    db.commit()
    return t


def _run(task_id: int, handlers):
    stop = threading.Event()

    def heartbeat():   # keeps the claim while a long book is still being read
        while not stop.wait(60):
            with SessionLocal() as db:
                t = db.get(Task, task_id)
                if t and t.status == "running" and t.locked_by == WORKER_ID:
                    t.locked_until = datetime.utcnow() + LEASE
                    db.commit()
    threading.Thread(target=heartbeat, daemon=True).start()
    with SessionLocal() as db:
        t = db.get(Task, task_id); kind, args = t.kind, list(t.args or [])
    err = ""
    try:
        handlers[kind](*args)
    except Exception:
        err = traceback.format_exc()[-2000:]
    finally:
        stop.set()
    with SessionLocal() as db:
        t = db.get(Task, task_id)
        if err and t.attempts < MAX_ATTEMPTS:
            t.status, t.error, t.locked_until = "queued", err, None
        else:
            t.status, t.error, t.finished_at = ("failed" if err else "done"), err, datetime.utcnow()
        db.commit()


wake = threading.Event()
_started = False


def loop(stop: threading.Event | None = None):
    """Claims and runs tasks until stopped. Each kind has its own number of slots."""
    handlers = _handlers()
    running: dict[str, int] = {k: 0 for k in SLOTS}
    lock = threading.Lock()

    def done(kind):
        with lock:
            running[kind] -= 1
        wake.set()

    while not (stop and stop.is_set()):
        free = [k for k, n in SLOTS.items() if running[k] < n]
        claimed = None
        if free:
            try:
                with SessionLocal() as db:
                    t = _claim(db, free)
                    claimed = (t.id, t.kind) if t else None
            except Exception as e:
                print(f"[EV TASKS] could not read the queue: {e}", flush=True)
        if claimed:
            tid, kind = claimed
            with lock:
                running[kind] += 1
            threading.Thread(target=lambda: (_run(tid, handlers), done(kind)), daemon=True).start()
            continue
        wake.wait(5); wake.clear()


def start_embedded():
    """The API's own worker, for a single box. Off when EMBEDDED_WORKER=0 (separate worker containers)."""
    global _started, _lockfile
    if _started or os.getenv("EMBEDDED_WORKER", "1") == "0":
        return
    # With several web processes (WEB_CONCURRENCY), only one of them runs background work, so two large books are
    # never read at once on the same box. The others serve requests only. The lock is let go when that process ends,
    # and the next one to start takes over.
    try:
        import fcntl
        _lockfile = open(os.getenv("EMBEDDED_WORKER_LOCK", "/tmp/eduverse-worker.lock"), "w")
        fcntl.flock(_lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        _start_retry()
        return
    except Exception:
        pass   # no file locks here (Windows): run as before
    _started = True
    threading.Thread(target=loop, daemon=True, name="ev-tasks").start()


_lockfile = None


def _start_retry():
    """Try again every minute: if the process holding the worker dies, another one picks the work up."""
    def again():
        import time
        while not _started:
            time.sleep(60)
            start_embedded()
    threading.Thread(target=again, daemon=True, name="ev-tasks-standby").start()
