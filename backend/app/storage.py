"""
storage module for storing and retrieving files from MinIO object storage
"""


import logging
from io import BytesIO
from minio import Minio
from .config import get_settings


def client():
    """
    Purpose: Create a MinIO client using the settings from the .env file.
    Input: none.
    Output: a connected Minio client.
    """
    c = get_settings()
    return Minio(c.minio_endpoint, access_key=c.minio_access_key,
                 secret_key=c.minio_secret_key, secure=c.minio_secure)


def ensure_bucket():
    """
    Purpose: Make sure the storage bucket exists, creating it if it does not.
    Input: none (the bucket name comes from the settings).
    Output: nothing.
    """
    c = client()
    bucket = get_settings().minio_bucket
    if not c.bucket_exists(bucket):
        c.make_bucket(bucket)


def put_bytes(key: str, payload: bytes, mime: str):
    """
    Purpose: Store a file in MinIO object storage.
    Input: key - the object path; payload - the file contents as bytes; mime - the content type, e.g. 'application/pdf'.
    Output: nothing.
    """
    c = client()
    c.put_object(get_settings().minio_bucket, key, BytesIO(payload),
                 length=len(payload), content_type=mime)


def delete_prefix(prefix: str) -> bool:
    """
    Purpose: Remove every object under a key prefix (a document's PDF and page images).
    Best effort: the database row is already gone when this runs, so a storage failure
    leaves orphaned files to clean up later instead of failing the user's delete.
    Input: prefix - the key prefix ending in '/', e.g. '<document id>/'.
    Output: True when everything was removed, False if storage failed (the error is logged).
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
    Purpose: Read a file from MinIO object storage.
    Input: key - the object path.
    Output: the file contents as bytes. Raises if the object does not exist or storage is unreachable.
    """
    c = client()
    obj = c.get_object(get_settings().minio_bucket, key)
    try:
        return obj.read()
    finally:
        obj.close()
        obj.release_conn()
