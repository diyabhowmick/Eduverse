from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from .config import settings
from .db import Base, engine, SessionLocal
from .routers import auth, admins, schools, pricing, books, jobs, platform, analytics, school, requests, explain, review, reviewers, student, teacher, pipeline, money, ask, factory
from .seed import ensure_core

app = FastAPI(title="EduVerse API", version="0.1.0")
for r in (auth, admins, schools, pricing, books, jobs, platform, analytics, school, requests, explain, review, reviewers, student, teacher, pipeline, money, ask, factory):
    app.include_router(r.router)
app.include_router(review.public)


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
