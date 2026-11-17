def extraction_progress(status, selected_pages, raw_pages):
    """Report completed material pages, without guessing elapsed-time progress."""
    pages = set(selected_pages or [])
    # A page skipped because it does not belong to the Tech Pack needs no reading, so it counts as done.
    completed = {entry.get('page') for entry in (raw_pages or [])
                 if entry.get('status') in ('completed', 'skipped')} & pages
    total, done = len(pages), len(completed)
    if status in ('needs_review', 'approved'):
        stage, done, percent = 'complete', total, 100
    elif status == 'failed':
        stage, percent = 'failed', (done * 100 // total if total else None)
    elif status == 'queued':
        stage, percent = 'queued', None
    elif not total:
        stage, percent = 'locating', None
    else:
        stage = 'finalizing' if done == total else 'extracting'
        percent = done * 100 // total
    return {'stage': stage, 'completed_pages': done, 'total_pages': total, 'percent': percent}
