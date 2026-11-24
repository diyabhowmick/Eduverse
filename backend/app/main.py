from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from .config import settings
from .db import Base, engine, SessionLocal
from .routers import auth, admins, schools, pricing, books, jobs, platform, analytics, school, requests, explain, review, reviewers, student, teacher, pipeline, exams, learn, tests, voice, study
from .seed import ensure_core
from .content import ContentMissing

from . import hardening as H
H.check_config()
app = FastAPI(title="EduVerse API", version="0.2.0", docs_url=None if H.is_prod() else "/api/docs",
              redoc_url=None, openapi_url=None if H.is_prod() else "/api/openapi.json")


@app.middleware("http")
async def _security(request, call_next):
    # Very large JSON bodies are refused before they are read; file uploads have their own limits.
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > 2 * 1048576 and "multipart/form-data" not in request.headers.get("content-type", ""):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=413, content={"detail": "Request too large"})
    return H.add_headers(request, await call_next(request))


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
app.include_router(tests.router)
app.include_router(tests.srouter)
app.include_router(voice.router)
app.include_router(study.router)


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
def warm_voice():
    """Load Eddie's voice in the background so his first answer is not slow."""
    import threading
    from . import voice as V
    threading.Thread(target=lambda: V.engine() and V.say("Hi!"), daemon=True).start()


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
        # Keys saved before v44 were plain text; writing each setting back stores them encrypted.
        from .models import Setting
        from sqlalchemy.orm.attributes import flag_modified
        for st in db.query(Setting):
            st.value = dict(st.value or {}); flag_modified(st, "value")
        db.commit()
    jobs.resume_unfinished()
    from . import tasks
    tasks.start_embedded()


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/ready")
def ready():
    """For the load balancer and the deploy script: the database answers and storage is reachable."""
    from sqlalchemy import text
    from fastapi.responses import JSONResponse
    checks = {}
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = type(e).__name__
    try:
        from .storage import get_storage
        st = get_storage()
        if hasattr(st, "s3"):
            st.s3.head_bucket(Bucket=st.bucket)
        checks["storage"] = "ok"
    except Exception as e:
        checks["storage"] = type(e).__name__
    good = all(v == "ok" for v in checks.values())
    return JSONResponse(status_code=200 if good else 503, content={"ok": good, **checks, "version": app.version})


dist = settings.frontend_dist
if dist.exists():
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = (dist / path).resolve()
        if path and f.is_file() and dist.resolve() in f.parents:  # brand images and other public files
            return FileResponse(f)
        return FileResponse(dist / "index.html")
