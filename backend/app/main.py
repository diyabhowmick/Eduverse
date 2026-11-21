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


# Anything that goes wrong and was not foreseen used to leave the browser with
# Starlette's plain-text "Internal Server Error", which the frontend could not
# read, so every unexpected failure looked the same: "Request failed". The
# reason was only ever in the server log, which the person uploading cannot
# see. Put the reason in the response for whoever runs the platform, and always
# write the traceback to the log with a mark that is easy to search for.
@app.exception_handler(Exception)
def _unhandled(request, exc):
    import traceback
    from fastapi.responses import JSONResponse
    traceback.print_exc()
    print(f"[EV ERROR] {request.method} {request.url.path} -> {type(exc).__name__}: {exc}", flush=True)
    if _is_staff(request):
        return JSONResponse(status_code=500, content={
            "detail": f"{type(exc).__name__}: {exc}"[:600],
            "where": f"{request.method} {request.url.path}"})
    return JSONResponse(status_code=500, content={
        "detail": "Something went wrong on the server. The super admin can see the reason in the server log."})


def _is_staff(request) -> bool:
    """Only a super admin or platform admin is told what broke."""
    try:
        import jwt
        tok = (request.headers.get("authorization") or "").removeprefix("Bearer ").strip()
        role = jwt.decode(tok, settings.jwt_secret, algorithms=["HS256"]).get("role")
        return role in ("super_admin", "platform_admin")
    except Exception:
        return False


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


def relax_legacy_columns():
    """Columns left behind by an older version of EduVerse, which now block every insert.

    `create_all` adds tables and `add_missing_columns` adds columns, but neither
    ever removes one. A database carried forward from an earlier build still
    has that build's columns — `books.file_sha` is one. If such a column is
    NOT NULL with no default, nothing in the current code knows to fill it, so
    *every* insert into that table fails, and it fails a long way from its
    cause: adding a book died on `null value in column "file_sha"`.

    The column and its data are left alone. Only the constraint that makes the
    table unusable is lifted, and only for columns the models no longer define.
    """
    if engine.dialect.name != "postgresql":
        return   # SQLite cannot alter a constraint, and a fresh file never has this problem
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    for table in Base.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        known = {c.name for c in table.columns}
        pk = set(insp.get_pk_constraint(table.name).get("constrained_columns") or [])
        for col in insp.get_columns(table.name):
            name = col["name"]
            if name in known or name in pk or col.get("nullable") or col.get("default") is not None:
                continue
            try:
                with engine.begin() as con:
                    con.execute(text(f'ALTER TABLE {table.name} ALTER COLUMN "{name}" DROP NOT NULL'))
                print(f"[EV SCHEMA] {table.name}.{name} is left over from an older version of EduVerse and was "
                      f"blocking every insert into {table.name}. Its NOT NULL has been lifted; the data is untouched.",
                      flush=True)
            except Exception as e:
                print(f"[EV SCHEMA] could not relax {table.name}.{name}: {e}", flush=True)


@app.on_event("startup")
def startup():
    Base.metadata.create_all(engine)
    add_missing_columns()
    relax_legacy_columns()
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
