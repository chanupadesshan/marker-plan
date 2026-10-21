"""
storage module for storing and retrieving files from MinIO object storage
"""


import logging
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


def delete_prefix(prefix: str) -> bool:
    """
    Remove every object under a key prefix (a document's PDF and page images).

    Best effort: the database row is already gone when this runs, so a storage failure
    leaves orphaned files to clean up later instead of failing the user's delete.
    """
    try:
        c = client()
        bucket = get_settings().minio_bucket
        for obj in c.list_objects(bucket, prefix=prefix, recursive=True):
            c.remove_object(bucket, obj.object_name)
        return True
    except Exception:
        logging.getLogger(__name__).warning("Could not remove stored files under %s", prefix, exc_info=True)
        return False


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
