import os
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def load_env(path: Path):
    """backend/.env, so the sign-in key and API keys survive a restart. Real environment variables win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        if v:
            os.environ.setdefault(k.strip(), v)


load_env(BASE / ".env")


def load_aws_secrets():
    """On AWS the secrets live in Secrets Manager, not in files: AWS_SECRET_ID names one JSON secret
    ({"JWT_SECRET": …, "SETTINGS_KEY": …, "DB_PASSWORD": …, "SUPERADMIN_PASSWORD": …}). Values already in the
    environment win. The instance's IAM role gives read access to that one secret only."""
    sid = os.getenv("AWS_SECRET_ID", "")
    if not sid:
        return
    import json
    import boto3
    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "ap-south-1"
    data = json.loads(boto3.client("secretsmanager", region_name=region).get_secret_value(SecretId=sid)["SecretString"])
    for k, v in data.items():
        if v not in (None, ""):
            os.environ.setdefault(k, str(v))


load_aws_secrets()
if not os.getenv("DATABASE_URL") and os.getenv("DB_HOST"):
    # RDS: the address comes from Terraform, the password from Secrets Manager
    from urllib.parse import quote
    os.environ["DATABASE_URL"] = (f"postgresql+psycopg://{os.getenv('DB_USER', 'eduverse')}:{quote(os.getenv('DB_PASSWORD', ''), safe='')}"
                                  f"@{os.environ['DB_HOST']}:{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_NAME', 'eduverse')}?sslmode=require")


def _db_url(url: str) -> str:
    """Railway and Heroku give postgres:// or postgresql:// URLs; SQLAlchemy would then look for
    psycopg2, which is not installed. Point them at psycopg 3 instead."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


class Settings:
    database_url = _db_url(os.getenv("DATABASE_URL", "postgresql+psycopg://eduverse:eduverse@localhost:5432/eduverse"))
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
