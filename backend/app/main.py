from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from .config import settings
from .db import Base, engine, SessionLocal
from .routers import auth, admins, schools, pricing, books, jobs, platform, analytics, school, requests, explain, review, reviewers, student, teacher, pipeline, exams, learn
from .seed import ensure_core
from .content import ContentMissing

app = FastAPI(title="EduVerse API", version="0.1.0")


# A book whose converted file is missing from storage used to surface as a bare
# 500 — to a reviewer, a super admin, or a student trying to read it. Say what
# is actually wrong and what fixes it, once, for every route that reads a book.
@app.exception_handler(ContentMissing)
def _content_missing(request, exc):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=409, content={"detail": str(exc)})


for r in (auth, admins, schools, pricing, books, jobs, platform, analytics, school, requests, explain, review, reviewers, student, teacher, pipeline):
    app.include_router(r.router)
app.include_router(review.public)
app.include_router(exams.router)
app.include_router(exams.srouter)
app.include_router(learn.router)


@app.get("/api/taxonomy")
def taxonomy():
    """Boards, states, classes and exams the forms and the store offer. Public: the sign-up page needs it."""
    from .taxonomy import all_
    from .models import Setting
    from .defaults import FEATURES
    with SessionLocal() as db:
        f = db.get(Setting, "features")
        feats = {**FEATURES, **(f.value if f else {})}
    return {**all_(), "public_signup": feats.get("public_signup", True), "exam_track": feats.get("exam_track", True)}


def add_missing_columns():
    """Columns added after a database was created: add them in place so an existing install keeps its data."""
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    with engine.begin() as con:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name not in have:
                    default = col.default.arg if col.default is not None and not callable(col.default.arg) else None
                    ddl = f'ALTER TABLE {table.name} ADD COLUMN {col.name} {col.type.compile(engine.dialect)}'
                    if isinstance(default, str):
                        ddl += " DEFAULT '" + default.replace("'", "''") + "'"
                    elif isinstance(default, (int, float)):
                        ddl += f" DEFAULT {default}"
                    con.execute(text(ddl))


@app.on_event("startup")
def startup():
    Base.metadata.create_all(engine)
    add_missing_columns()
    with SessionLocal() as db:
        ensure_core(db)
    jobs.resume_unfinished()


@app.get("/api/health")
def health():
    return {"ok": True}


dist = settings.frontend_dist
if dist.exists():
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = (dist / path).resolve()
        if path and f.is_file() and dist.resolve() in f.parents:  # brand images and other public files
            return FileResponse(f)
        return FileResponse(dist / "index.html")
