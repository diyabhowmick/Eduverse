"""One storage interface: local folder for dev, S3 for deployment. Switch with STORAGE_BACKEND."""
from pathlib import Path
from .config import settings


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, key: str, data: bytes) -> str:
        p = self.root / key
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return key

    def put_file(self, key: str, src: Path) -> str:
        """Store a file that is already on disk, without reading it into memory.

        A textbook is 75-85 MB; put(key, f.read_bytes()) holds the whole book
        in memory twice over, on top of whatever the upload itself is holding.
        """
        import shutil
        p = self.root / key
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(src, "rb") as a, open(p, "wb") as b:
            shutil.copyfileobj(a, b, 1024 * 1024)
        return key

    def get(self, key: str) -> bytes:
        return (self.root / key).read_bytes()

    def delete(self, key: str):
        p = self.path(key)
        if p.exists():
            p.unlink()

    def path(self, key: str) -> Path:
        return self.root / key


class S3Storage:
    def __init__(self, bucket: str, region: str):
        import boto3
        self.bucket = bucket
        self.s3 = boto3.client("s3", region_name=region)

    def put(self, key: str, data: bytes) -> str:
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=data)
        return key

    def put_file(self, key: str, src: Path) -> str:
        self.s3.upload_file(str(src), self.bucket, key)
        return key

    def get(self, key: str) -> bytes:
        return self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def delete(self, key: str):
        self.s3.delete_object(Bucket=self.bucket, Key=key)

    def signed_url(self, key: str, seconds: int = 900) -> str | None:
        """A short-lived link straight to S3 (or the CDN in front of it), so images do not pass through the API."""
        try:
            self.s3.head_object(Bucket=self.bucket, Key=key)
        except Exception:
            return None
        return self.s3.generate_presigned_url("get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=seconds)


def get_storage():
    if settings.storage_backend == "s3":
        return S3Storage(settings.s3_bucket, settings.s3_region)
    return LocalStorage(settings.storage_dir)
