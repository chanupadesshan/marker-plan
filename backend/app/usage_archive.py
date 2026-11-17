"""Keep the model usage of a document after it is deleted, so the Usage page does not lose what was spent."""
from datetime import datetime, timezone
from .models import UsageArchive


def archive_usage(session, kind, row):
    """
    Purpose: Copy a document's model usage into the permanent usage_archive table. Call it just before deleting the
    document, in the same transaction, so the usage is kept exactly when the document goes.
    Input: session - a database session; kind - 'techpack' or 'po'; row - the TechPack or PurchaseOrderDocument about to be deleted.
    Output: nothing. A document with no recorded usage adds no row.
    """
    usage = list(row.extraction.extracted_json.get('request_usage') or []) if row.extraction else []
    if not usage:
        return
    session.add(UsageArchive(kind=kind, document_id=str(row.id), filename=row.original_filename, status=row.status,
                             uploaded_by=row.uploaded_by, usage=usage,
                             document_created_at=row.created_at or datetime.now(timezone.utc)))
