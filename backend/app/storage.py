"""
storage module for storing and retrieving files from MinIO object storage
"""


from io import BytesIO
from minio import Minio
from .config import get_settings


def client():
    """
    Create a MinIO client using the settings from the .env file.
    """
    c = get_settings()
    return Minio(c.minio_endpoint, access_key=c.minio_access_key,
                 secret_key=c.minio_secret_key, secure=c.minio_secure)


def ensure_bucket():
    """
    Ensure that the MinIO bucket exists, and create it if it does not.
    """
    c = client()
    bucket = get_settings().minio_bucket
    if not c.bucket_exists(bucket):
        c.make_bucket(bucket)


def put_bytes(key: str, payload: bytes, mime: str):
    """
    Store a file in MinIO object storage with the given key, payload, and MIME type.
    """
    c = client()
    c.put_object(get_settings().minio_bucket, key, BytesIO(payload),
                 length=len(payload), content_type=mime)


def get_bytes(key: str) -> bytes:
    """
    Retrieve a file from MinIO object storage with the given key and return its bytes.
    """
    c = client()
    obj = c.get_object(get_settings().minio_bucket, key)
    try:
        return obj.read()
    finally:
        obj.close()
        obj.release_conn()
