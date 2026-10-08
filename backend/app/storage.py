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

    def get(self, key: str) -> bytes:
        return (self.root / key).read_bytes()

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

    def get(self, key: str) -> bytes:
        return self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()


def get_storage():
    if settings.storage_backend == "s3":
        return S3Storage(settings.s3_bucket, settings.s3_region)
    return LocalStorage(settings.storage_dir)
