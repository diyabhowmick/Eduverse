"""Flags and issues (Super Admin).

There is no issues table. A rejected review page IS the open issue:

    rejected                      open
    pending, with fixed_at set    somebody fixed it, waiting to be checked again
    approved, with a category     closed

The screen (frontend/src/pages/Issues.jsx) also shows which books have lost their
converted file and where files are being stored, because a container's own disk
is wiped on every deploy and that is the usual reason a book goes missing.
"""
import os
import shutil
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..audit import log
from ..config import settings
from ..db import get_db
from ..models import Book, ReviewPage
from ..security import super_admin
from ..storage import get_storage

router = APIRouter(prefix="/api/books", tags=["issues"])


def _flags():
    from .review import FLAGS, RERUNS
    return {k: l for k, l, _ in FLAGS}, dict(RERUNS)


def _state(r: ReviewPage) -> str:
    if r.status == "rejected":
        return "open"
    if r.status == "pending" and r.fixed_at:
        return "to_recheck"
    return "fixed"


def _flagged(db: Session):
    """Every page that has ever been flagged: rejected now, or carrying a category from an earlier flag."""
    return db.query(ReviewPage).filter((ReviewPage.status == "rejected") | (ReviewPage.category != "")).all()


@router.get("/issues")
def issues(status: str = "open", category: str = "", db: Session = Depends(get_db), _=Depends(super_admin)):
    cats, reruns = _flags()
    books = {b.id: b for b in db.query(Book).all()}
    out = []
    for r in _flagged(db):
        st = _state(r)
        if status != "all" and st != status:
            continue
        if category and r.category != category:
            continue
        b = books.get(r.book_id)
        if not b:
            continue
        out.append({"book_id": b.id, "book": b.title, "book_status": b.status, "page": r.page, "state": st,
                    "category": r.category, "category_label": cats.get(r.category, r.category or "Not given"),
                    "rerun": r.rerun, "rerun_label": reruns.get(r.rerun, ""), "comment": r.comment, "reviewer": r.reviewer,
                    "at": r.updated_at, "fixed_by": r.fixed_by})
    out.sort(key=lambda x: (x["at"] or datetime.min), reverse=True)
    return out


@router.get("/issues/summary")
def issues_summary(db: Session = Depends(get_db), _=Depends(super_admin)):
    cats, _r = _flags()
    by_state, by_cat, open_by_book = Counter(), Counter(), Counter()
    for r in _flagged(db):
        st = _state(r)
        by_state[st] += 1
        if st == "open":
            by_cat[r.category or "other"] += 1
            open_by_book[r.book_id] += 1
    return {"by_state": {k: by_state.get(k, 0) for k in ("open", "to_recheck", "fixed")},
            "by_category": [{"key": k, "label": cats.get(k, k), "n": n} for k, n in by_cat.most_common()],
            "open_by_book": {str(k): v for k, v in open_by_book.items()}}


class FixedIn(BaseModel):
    note: str = ""


@router.post("/{bid}/issues/{page}/fixed")
def mark_fixed(bid: int, page: int, body: FixedIn, db: Session = Depends(get_db), me=Depends(super_admin)):
    """Sends only this page back to a reviewer. Every other page keeps its state; a live book stays live."""
    r = db.get(ReviewPage, (bid, page))
    if not r:
        raise HTTPException(404, "Page not found")
    if r.status != "rejected":
        raise HTTPException(409, "This page has no open issue")
    r.status, r.fixed_at, r.fixed_by, r.updated_at = "pending", datetime.utcnow(), me.email, datetime.utcnow()
    if body.note.strip():
        r.comment = (r.comment + "\nFixed: " + body.note.strip()).strip()
    log(db, me, "review.page_fixed", "book", bid, page=page, note=body.note[:200])
    db.commit()
    return {"page": page, "status": r.status}


def _exists(store, key: str) -> bool:
    if hasattr(store, "s3"):
        try:
            store.s3.head_object(Bucket=store.bucket, Key=key)
            return True
        except Exception:
            return False
    return (store.root / key).exists()


@router.get("/content-check")
def content_check(db: Session = Depends(get_db), _=Depends(super_admin)):
    """Books the database says were converted whose file is not in storage. They fail for anyone who opens them."""
    store, out = get_storage(), []
    for b in db.query(Book).filter(Book.status.in_(("in_review", "approved", "live", "rejected"))):
        for key, which in ((b.content_key, "version in review"), (b.live_key, "live version")):
            if key and not _exists(store, key + "/book.json"):
                out.append({"id": b.id, "title": b.title, "status": b.status, "pages": b.pages, "content_key": key,
                            "why": f"The {which} ({key}) is not in storage"})
                break
        else:
            if b.status == "live" and not (b.content_key or b.live_key) and b.track != "exam":
                out.append({"id": b.id, "title": b.title, "status": b.status, "pages": b.pages, "content_key": "",
                            "why": "Live, but it was never converted"})
    return out


def _mount_of(path: Path) -> tuple[str, str]:
    """The mount point holding this path, and its filesystem type, from /proc/self/mounts."""
    best, fstype = "/", ""
    try:
        for line in Path("/proc/self/mounts").read_text().splitlines():
            parts = line.split()
            if len(parts) < 3:
                continue
            mp = parts[1].replace("\\040", " ")
            if (str(path) == mp or str(path).startswith(mp.rstrip("/") + "/")) and len(mp) >= len(best):
                best, fstype = mp, parts[2]
    except OSError:
        pass
    return best, fstype


def _count(root: Path) -> dict:
    files = size = 0
    if root.exists():
        for f in root.rglob("*"):
            if f.is_file():
                files += 1
                size += f.stat().st_size
    return {"files": files, "mb": round(size / 1048576, 1)}


def storage_report() -> dict:
    store = get_storage()
    probe_key = f"_probe/{uuid.uuid4().hex}.txt"
    try:
        store.put(probe_key, b"ok")
        ok = store.get(probe_key) == b"ok"
        store.delete(probe_key)
        writable, probe = ok, "" if ok else "read back something else"
    except Exception as e:
        writable, probe = False, f"{type(e).__name__}: {e}"[:200]
    if settings.storage_backend == "s3":
        return {"backend": "s3", "root": f"s3://{settings.s3_bucket}", "persistent": True, "on_volume": True,
                "writable": writable, "probe": probe,
                "verdict": "Files are in S3, so they survive every deploy." if writable else "S3 is set but cannot be written. Check the bucket and the instance's permissions."}
    root = Path(settings.storage_dir).resolve()
    mount, fstype = _mount_of(root)
    on_volume = mount != "/" and fstype not in ("overlay", "aufs", "tmpfs")
    out = {"backend": "local", "root": str(root), "mount": mount, "fstype": fstype, "on_volume": on_volume,
           "persistent": on_volume or os.getenv("STORAGE_PERSISTENT") == "1", "writable": writable, "probe": probe,
           "books": _count(root / "books"), "originals": _count(root / "originals")}
    try:
        du = shutil.disk_usage(root)
        out["free_gb"], out["total_gb"] = round(du.free / 1e9, 1), round(du.total / 1e9, 1)
    except OSError:
        pass
    if not writable:
        out["verdict"] = "The storage folder cannot be written, so uploads and conversions will fail."
    elif out["persistent"]:
        out["verdict"] = "Files are on a mounted volume, so they survive a deploy."
    else:
        out["verdict"] = ("Files are on the container's own disk. Every deploy wipes them, and books then open with "
                          "\"needs to be processed again\". Mount a volume at this folder (Railway: Volumes) or set "
                          "STORAGE_BACKEND=s3. If this disk is in fact permanent (your own server), set STORAGE_PERSISTENT=1.")
    return out


@router.get("/storage-check")
def storage_check(_=Depends(super_admin)):
    return storage_report()
