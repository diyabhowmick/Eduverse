"""The factory — Platform Admin's three screens.

Platform Admin runs book production: what is being processed, where the
pipeline is failing, which keys are in use and what they are spending. Every
number here is a cost or a count. Nothing here says what a school pays.

Three endpoints, one per screen:

  /health          where the pipeline is breaking, and how often
  /keys            the three key slots and what has been spent
  /cost-settings   the handful of knobs that actually move the bill

The settings endpoint deliberately has no store of its own. It reads and
writes the places the values already live (M1 overrides, M2 settings, the AI
setting), because a second copy of "page quality" would quietly disagree with
the first one — which is the mistake the three separate key screens already
made.
"""
from collections import Counter
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Book, Job, Setting, User
from ..security import platform_admin
from ..audit import log
from .. import m1, m2, costing
from ..defaults import AI

router = APIRouter(prefix="/api/factory", tags=["factory"])


# --------------------------------------------------------------- pipeline health
def _why(error: str) -> str:
    """A failure's first line is the part worth counting. The traceback under it
    differs every time and would make every failure look unique."""
    first = (error or "").strip().splitlines()
    if not first:
        return "No reason recorded"
    line = first[0].strip()
    return (line[:120] + "…") if len(line) > 120 else line


@router.get("/health")
def health(days: int = 30, db: Session = Depends(get_db), _=Depends(platform_admin)):
    since = datetime.utcnow() - timedelta(days=max(1, days))
    jobs = db.query(Job).filter(Job.created_at >= since).all()
    by_status = Counter(j.status for j in jobs)

    failed = [j for j in jobs if j.status == "failed"]
    reasons = Counter(_why(j.error) for j in failed)

    # Minutes per page, from jobs that finished and know how many pages they did.
    paced = [j for j in jobs if j.status == "done" and j.finished_at and j.pages_done > 0]
    mins = [((j.finished_at - j.created_at).total_seconds() / 60) / j.pages_done
            for j in paced]

    books = db.query(Book).all()
    split = Counter(b.split_by or "not converted" for b in books)
    now = datetime.utcnow()

    return {
        "window_days": days,
        "jobs": {"total": len(jobs), "done": by_status.get("done", 0),
                 "failed": by_status.get("failed", 0),
                 "cancelled": by_status.get("cancelled", 0),
                 "running": by_status.get("running", 0),
                 "queued": by_status.get("queued", 0)},
        # The one number that says whether the pipeline is trustworthy.
        "success_rate": round(100 * by_status.get("done", 0) / len(jobs), 1) if jobs else None,
        "min_per_page": round(sum(mins) / len(mins), 2) if mins else None,
        # Grouped so a repeated failure reads as one problem, not twenty.
        "failures": [{"why": w, "n": n} for w, n in reasons.most_common(12)],
        "recent_failures": [
            {"id": j.id, "book_id": j.book_id, "filename": j.filename,
             "pages_done": j.pages_done, "pages": j.pages,
             "why": _why(j.error), "at": j.finished_at or j.created_at}
            for j in sorted(failed, key=lambda j: j.created_at, reverse=True)[:15]],
        # How books came out the other end. "pages" means the converter found no
        # sections and no headings, so every page became its own unit — readable,
        # but not a real chapter list.
        "split": dict(split),
        "poor_conversions": [
            {"id": b.id, "title": b.title, "pages": b.pages,
             "headings": b.headings_n, "status": b.status}
            for b in books if b.split_by == "pages"],
        "stuck_in_review": [
            {"id": b.id, "title": b.title,
             "days": (now - (b.assigned_at or b.created_at)).days,
             "reviewer": (db.get(User, b.assigned_reviewer_id).name
                          if b.assigned_reviewer_id and db.get(User, b.assigned_reviewer_id) else "Nobody")}
            for b in books
            if b.status == "in_review" and (now - (b.assigned_at or b.created_at)).days > 14],
        "no_figures": [
            {"id": b.id, "title": b.title, "pages": b.pages}
            for b in books if b.pages > 20 and b.figures_n == 0 and b.split_by],
    }


# ------------------------------------------------------------- keys and spending
def _ai(db) -> dict:
    s = db.get(Setting, "ai")
    return s.value if s else AI


@router.get("/keys")
def keys(db: Session = Depends(get_db), _=Depends(platform_admin)):
    """Three keys, three screens, and what they have spent.

    They are genuinely separate: a key typed into one does nothing for the other
    two. This screen exists so that is visible in one place instead of being
    discovered when a book comes out blank.
    """
    m1v = m1.effective(db)
    m2v = m2.settings_of(db)
    aiv = _ai(db)
    ai_prov = aiv.get("provider", "ollama")
    ai_p = (aiv.get("providers") or {}).get(ai_prov, {})
    m2_prov = m2v.get("provider", "openai")
    m2_p = (m2v.get("providers") or {}).get(m2_prov, {})

    slots = [
        {"slot": "Reading books (M1)", "screen": "Book extraction (M1)", "path": "extraction",
         "provider": m1v.get("provider", "ollama"), "model": m1v.get("model", ""),
         "set": bool(m1v.get("openai_api_key")) or m1v.get("provider") == "ollama",
         "needed": not m1v.get("offline"),
         "does": "Reads every scanned page, describes figures, reads maths."},
        {"slot": "Redrawing figures (M2)", "screen": "Figure redraw (M2)", "path": "figures",
         "provider": m2_prov, "model": m2_p.get("model", ""),
         "set": bool(m2_p.get("api_key")) or m2_prov == "local",
         "needed": bool(m2v.get("enabled")),
         "does": "Draws a clean picture where the original scan is unusable."},
        {"slot": "Student explanations", "screen": "AI settings", "path": "ai",
         "provider": ai_prov, "model": ai_p.get("model", ""),
         "set": bool(ai_p.get("api_key")) or ai_prov == "ollama",
         "needed": True,
         "does": "Explains a keyword or answers a student's question."},
    ]

    books = db.query(Book).all()
    month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    this_month = [b for b in books if b.created_at >= month]
    done = [b for b in books if b.cost_usd > 0]

    return {
        "slots": slots,
        "missing": [s["slot"] for s in slots if s["needed"] and not s["set"]],
        "spend": {
            "all_time_usd": round(sum(b.cost_usd for b in books), 2),
            "this_month_usd": round(sum(b.cost_usd for b in this_month), 2),
            "books_all_time": len(books),
            "books_this_month": len(this_month),
            "avg_per_book_usd": round(sum(b.cost_usd for b in done) / len(done), 3) if done else 0,
            # A catalogue cost is paid once. It does not grow when a school reads
            # more, which is why this is the only spend line that matters.
            "most_expensive": sorted(
                [{"id": b.id, "title": b.title, "cost_usd": round(b.cost_usd, 3),
                  "pages": b.pages, "scanned": b.route_scanned}
                 for b in done], key=lambda r: -r["cost_usd"])[:8],
        },
        "monthly_token_budget": aiv.get("monthly_token_budget", 0),
        "rates": {"input_per_mtok": costing.IN_RATE, "output_per_mtok": costing.OUT_RATE},
    }


# ----------------------------------------------------------------- cost settings
# name -> (store, field, label, help). The store says where the value really
# lives; there is no fourth copy kept here.
KNOBS = [
    ("ocr_dpi", "m1", "Page picture quality",
     "How big a picture of each scanned page the model is sent. Lower is cheaper "
     "and faster; too low and small print is misread. 150 is the tested setting."),
    ("describe_figures", "m1", "Describe figures",
     "Off means figures keep their picture but get no written description. Saves "
     "two model calls per figure, and a blind student loses the description."),
    ("m2_enabled", "m2", "Redraw figures",
     "Off means no figure is ever regenerated. The largest single saving, and "
     "poor scans stay poor."),
    ("max_images_per_book", "m2", "Most figures redrawn per book",
     "A hard ceiling, so one figure-heavy book cannot run away with the bill."),
    ("daily_explanations_per_student", "ai", "Explanations per student per day",
     "The cap on a single student's asks. Per student, not a school pool — one "
     "keen reader would empty a pool by lunchtime."),
    ("monthly_token_budget", "ai", "Monthly token budget",
     "What the platform is allowed to spend in a month."),
]


def _cost_values(db) -> dict:
    m1v, m2v, aiv = m1.effective(db), m2.settings_of(db), _ai(db)
    return {
        "ocr_dpi": m1v.get("ocr_dpi"),
        "describe_figures": bool(m1v.get("describe_figures")),
        "m2_enabled": bool(m2v.get("enabled")),
        "max_images_per_book": m2v.get("max_images_per_book"),
        "daily_explanations_per_student": aiv.get("daily_explanations_per_student"),
        "monthly_token_budget": aiv.get("monthly_token_budget"),
    }


@router.get("/cost-settings")
def get_cost_settings(db: Session = Depends(get_db), _=Depends(platform_admin)):
    vals = _cost_values(db)
    return {
        "values": vals,
        "knobs": [{"name": n, "store": st, "label": lb, "help": hp,
                   "screen": {"m1": "Book extraction (M1)", "m2": "Figure redraw (M2)",
                              "ai": "AI settings"}[st]}
                  for n, st, lb, hp in KNOBS],
        # What a typical book costs at the current settings, so a change can be
        # judged before it is saved. Both routes, because the gap between them
        # is the single largest saving available and it is free to take.
        "example": costing.estimate(288, "native", 330, 2000),
        "example_scanned": costing.estimate(288, "scanned", 330, 2000),
    }


@router.put("/cost-settings")
def put_cost_settings(body: dict, db: Session = Depends(get_db), me=Depends(platform_admin)):
    """Write each value back to the store it came from."""
    v = dict(body or {})
    changed = []

    def whole(name, lo, hi):
        try:
            n = int(float(v[name]))
        except (TypeError, ValueError):
            raise HTTPException(422, f"{name}: must be a whole number")
        if not lo <= n <= hi:
            raise HTTPException(422, f"{name}: must be between {lo} and {hi}")
        return n

    # --- M1 overrides
    if "ocr_dpi" in v or "describe_figures" in v:
        ov = m1.stored(db)
        if "ocr_dpi" in v:
            ov["ocr_dpi"] = whole("ocr_dpi", 72, 400)
        if "describe_figures" in v:
            ov["describe_figures"] = bool(v["describe_figures"])
        try:
            ov = m1.clean_overrides({**m1.effective(db), **ov})
        except ValueError as e:
            raise HTTPException(422, str(e))
        s = db.get(Setting, "m1")
        if s:
            s.value = {**(s.value or {}), "overrides": ov}
        else:
            db.add(Setting(key="m1", value={"overrides": ov}))
        changed += [k for k in ("ocr_dpi", "describe_figures") if k in v]

    # --- M2 settings
    if "m2_enabled" in v or "max_images_per_book" in v:
        cfg = m2.settings_of(db)
        if "m2_enabled" in v:
            cfg["enabled"] = bool(v["m2_enabled"])
        if "max_images_per_book" in v:
            cfg["max_images_per_book"] = whole("max_images_per_book", 0, 2000)
        s = db.get(Setting, "m2")
        if s:
            s.value = cfg
        else:
            db.add(Setting(key="m2", value=cfg))
        changed += [k for k in ("m2_enabled", "max_images_per_book") if k in v]

    # --- AI setting
    if "daily_explanations_per_student" in v or "monthly_token_budget" in v:
        cur = _ai(db)
        cfg = dict(cur)
        if "daily_explanations_per_student" in v:
            cfg["daily_explanations_per_student"] = whole("daily_explanations_per_student", 0, 10000)
        if "monthly_token_budget" in v:
            cfg["monthly_token_budget"] = whole("monthly_token_budget", 0, 10_000_000_000)
        s = db.get(Setting, "ai")
        if s:
            s.value = cfg
        else:
            db.add(Setting(key="ai", value=cfg))
        changed += [k for k in ("daily_explanations_per_student", "monthly_token_budget") if k in v]

    if not changed:
        raise HTTPException(422, "Nothing to save")
    log(db, me, "settings.cost", "setting", "cost", changed=sorted(changed))
    db.commit()
    return get_cost_settings(db)
