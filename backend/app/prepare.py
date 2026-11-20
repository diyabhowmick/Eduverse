"""Writes level 1 explanations ahead of students, for one book or exam pack, in its own process:
python -m app.prepare <job id>. Several requests run at once; one failing does not stop the rest."""
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from .db import SessionLocal
from .models import Book, Explanation, PrepJob
from . import explain_store as X
from .llm_client import call


def run(job_id: int):
    db = SessionLocal()
    try:
        j = db.get(PrepJob, job_id)
        book = db.get(Book, j.book_id)
        from .routers.learn import prep_items
        items = prep_items(db, book, j.styles)
        ai = X.ai_conf(db)
        pv = ai["providers"].get(ai["provider"], {"model": "test"})
        j.status, j.total = "running", len(items); db.commit()

        def ask(item):
            usage = {}
            text = call(ai["provider"], pv["model"], item["prompt"], base_url=pv.get("base_url"), api_key=pv.get("api_key") or None, timeout=240, usage=usage)
            return X.check(text), usage

        with ThreadPoolExecutor(max_workers=6) as pool:
            jobs = {pool.submit(ask, it): it for it in items}
            for job in as_completed(jobs):
                it = jobs[job]
                try:
                    left = X.budget_left(db)
                    if left is not None and left <= 0:
                        raise RuntimeError("Monthly AI budget used up")
                    text, usage = job.result()
                    db.add(Explanation(scope=it["scope"], anchor=it["anchor"], level=1, style=it["style"], lang=book.medium or "English", book_id=book.id,
                                       question_id=it["question_id"], term=it["term"][:200], text=text, model=pv["model"], source="prepared"))
                    X.record(db, "prepare", pv["model"], usage, None, book.id, False, it["term"], it["where"])
                    j.done += 1; j.tokens += usage.get("prompt", 0) + usage.get("completion", 0)
                except Exception as e:
                    j.failed += 1; j.error = str(e)[:400]
                db.commit()
        j.status = "failed" if items and j.failed == len(items) else "done"
        j.finished_at = datetime.utcnow(); db.commit()
    except Exception as e:
        db.rollback(); j = db.get(PrepJob, job_id)
        j.status, j.error, j.finished_at = "failed", str(e)[:800], datetime.utcnow(); db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    run(int(sys.argv[1]))
