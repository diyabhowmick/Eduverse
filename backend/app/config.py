import os
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def _db_url() -> str:
    """Railway, Render and Heroku all inject DATABASE_URL as `postgresql://...`
    (Heroku still uses the older `postgres://`). SQLAlchemy reads a bare
    `postgresql://` as psycopg2, which is NOT what this project installs — it
    uses psycopg 3. Left alone, the first deploy dies on startup with
    `ModuleNotFoundError: No module named 'psycopg2'`, which says nothing about
    the real problem. So name the driver explicitly.
    """
    url = os.getenv("DATABASE_URL", "postgresql+psycopg://eduverse:eduverse@localhost:5432/eduverse")
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


class Settings:
    database_url = _db_url()
    jwt_secret = os.getenv("JWT_SECRET", "change-me-in-production")
    jwt_hours = int(os.getenv("JWT_HOURS", "12"))
    storage_backend = os.getenv("STORAGE_BACKEND", "local")  # local | s3
    storage_dir = Path(os.getenv("STORAGE_DIR", str(BASE / "data" / "storage")))
    s3_bucket = os.getenv("S3_BUCKET", "")
    s3_region = os.getenv("S3_REGION", "ap-south-1")
    frontend_dist = Path(os.getenv("FRONTEND_DIST", str(BASE.parent / "frontend" / "dist")))
    superadmin_email = os.getenv("SUPERADMIN_EMAIL", "superadmin@eduverse.local")
    superadmin_password = os.getenv("SUPERADMIN_PASSWORD", "ChangeMe@123")


settings = Settings()
