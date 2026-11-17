"""Usage dashboard API: model token use, cost, daily totals and failure rates from the stored request_usage."""
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from .auth import require_admin
from .config import get_settings
from .database import SessionLocal
from .models import BomExtraction, PurchaseOrderDocument, PurchaseOrderExtraction, TechPack, UsageArchive, User

router = APIRouter(prefix='/api/usage', tags=['Usage'])

WORST_DOCUMENTS = 10


def request_cost(entry, input_price=None, output_price=None):
    """
    Purpose: Work out what one model request cost.
    Input: entry - one request_usage record; input_price and output_price - optional USD per million tokens.
    Output: (cost in USD or None, True when it was estimated from the prices rather than recorded).
    """
    if isinstance(entry.get('cost_usd'), (int, float)):
        return entry['cost_usd'], False
    if input_price is None or output_price is None:
        return None, False
    if not isinstance(entry.get('input_tokens'), int) or not isinstance(entry.get('output_tokens'), int):
        return None, False
    return (entry['input_tokens'] * input_price + entry['output_tokens'] * output_price) / 1_000_000, True


def summarize(documents, days, today=None, input_price=None, output_price=None):
    """
    Purpose: Build the usage dashboard figures from stored extractions.
    Input: documents - dicts with kind ('techpack' or 'po'), id, filename, status, created (a date) and usage
    (the request_usage list); days - how many days to cover, ending today; today - override for tests;
    input_price and output_price - optional USD per million tokens for requests with no recorded cost.
    Output: a dict with totals, daily rows (every day, empty ones included), status and stage breakdowns,
    and the documents with the most failed requests. Cost is None when no request had a cost.
    """
    today = today or datetime.now(timezone.utc).date()
    first = today - timedelta(days=days - 1)
    daily = {first + timedelta(days=offset): defaultdict(float) for offset in range(days)}
    totals, statuses, stages = defaultdict(float), Counter(), defaultdict(lambda: defaultdict(float))
    cost_seen = estimated = False
    worst = []
    for doc in documents:
        if not first <= doc['created'] <= today:
            continue
        row, usage = daily[doc['created']], doc['usage'] or []
        failed = sum(1 for entry in usage if entry.get('status') != 'success')
        for bucket in (row, totals):
            bucket['documents'] += 1
            bucket['failed_documents'] += doc['status'] == 'failed'
        for entry in usage:
            ok = entry.get('status') == 'success'
            tokens = entry.get('total_tokens') if isinstance(entry.get('total_tokens'), int) else None
            cost, was_estimated = request_cost(entry, input_price, output_price)
            statuses[entry.get('status') or 'unknown'] += 1
            stage = stages[entry.get('stage') or 'unknown']
            for bucket in (row, totals, stage):
                bucket['requests'] += 1
                bucket['failed_requests'] += not ok
                bucket['total_tokens'] += tokens or 0
            for bucket in (row, totals):
                bucket['retries'] += (entry.get('attempt') or 1) > 1
                bucket['input_tokens'] += entry.get('input_tokens') or 0
                bucket['output_tokens'] += entry.get('output_tokens') or 0
                bucket['requests_without_tokens'] += tokens is None
            if cost is not None:
                cost_seen, estimated = True, estimated or was_estimated
                for bucket in (row, totals):
                    bucket['cost_usd'] += cost
        if failed:
            worst.append({'kind': doc['kind'], 'id': doc['id'], 'filename': doc['filename'], 'status': doc['status'],
                          'deleted': bool(doc.get('deleted')), 'requests': len(usage), 'failed_requests': failed,
                          'total_tokens': sum(e.get('total_tokens') or 0 for e in usage)})
    totals['failure_rate'] = totals['failed_requests'] / totals['requests'] if totals['requests'] else None
    totals['cost_usd'] = totals['cost_usd'] if cost_seen else None
    totals['cost_estimated'] = estimated
    return {
        'days': days,
        'totals': {key: (int(value) if isinstance(value, float) and key not in ('cost_usd', 'failure_rate') else value)
                   for key, value in totals.items()},
        'daily': [{'date': day.isoformat(), **{key: int(row[key]) for key in
                   ('documents', 'requests', 'failed_requests', 'total_tokens')},
                   'cost_usd': row['cost_usd'] if cost_seen else None} for day, row in daily.items()],
        'by_status': [{'status': status, 'count': count} for status, count in statuses.most_common()],
        'by_stage': [{'stage': name, **{key: int(value) for key, value in stage.items()}}
                     for name, stage in sorted(stages.items())],
        'worst_documents': sorted(worst, key=lambda item: (-item['failed_requests'], -item['total_tokens']))[:WORST_DOCUMENTS],
    }


def summarize_by_user(documents, users, days, today=None, input_price=None, output_price=None):
    """
    Purpose: Total each person's model use and cost over the period, so an admin can see who spends what.
    Input: documents - as for summarize(), each also with user_id (None for uploads from before uploader tracking);
    users - {user_id: {'name', 'email'}}; days, today, input_price and output_price - as for summarize().
    Output: one dict per person with uploads, requests, failed_requests, input/output/total tokens and cost_usd
    (None when no request had a cost), cost_estimated, sorted by cost then tokens, highest first. Uploads with no
    known uploader are grouped under user_id None.
    """
    today = today or datetime.now(timezone.utc).date()
    first = today - timedelta(days=days - 1)
    people = defaultdict(lambda: defaultdict(float))
    costed, estimated = set(), set()
    for doc in documents:
        if not first <= doc['created'] <= today:
            continue
        key = doc.get('user_id') if doc.get('user_id') in users else None
        person = people[key]
        person['documents'] += 1
        for entry in doc['usage'] or []:
            cost, was_estimated = request_cost(entry, input_price, output_price)
            person['requests'] += 1
            person['failed_requests'] += entry.get('status') != 'success'
            for field in ('input_tokens', 'output_tokens', 'total_tokens'):
                person[field] += entry.get(field) if isinstance(entry.get(field), int) else 0
            if cost is not None:
                person['cost_usd'] += cost
                costed.add(key)
                if was_estimated:
                    estimated.add(key)
    result = [{'user_id': key, 'name': users[key]['name'] if key else 'Unassigned',
               'email': users[key]['email'] if key else 'Uploaded before uploader tracking',
               **{field: int(value) for field, value in person.items() if field != 'cost_usd'},
               'cost_usd': person['cost_usd'] if key in costed else None, 'cost_estimated': key in estimated}
              for key, person in people.items()]
    return sorted(result, key=lambda item: (-(item['cost_usd'] or 0), -item['total_tokens'], item['name'].lower()))


def load_documents(days):
    """
    Purpose: Read the stored usage of every Tech Pack and PO uploaded in about the last N days, including those since
    deleted (their usage was copied to the usage archive when they were deleted, so the totals do not shrink).
    Input: days - how many days back.
    Output: the document dicts summarize() and summarize_by_user() take, each with its uploader's user_id; a deleted
    document has 'deleted': True.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    documents = []
    with SessionLocal() as session:
        for kind, doc_model, extraction_model in (('techpack', TechPack, BomExtraction),
                                                  ('po', PurchaseOrderDocument, PurchaseOrderExtraction)):
            rows = session.execute(
                select(doc_model.id, doc_model.original_filename, doc_model.status, doc_model.created_at,
                       extraction_model.extracted_json['request_usage'], doc_model.uploaded_by)
                .join(extraction_model, extraction_model.document_id == doc_model.id)
                .where(doc_model.created_at >= since - timedelta(days=1))).all()
            documents += [{'kind': kind, 'id': str(row[0]), 'filename': row[1], 'status': row[2],
                           'created': row[3].astimezone(timezone.utc).date(), 'usage': row[4],
                           'user_id': str(row[5]) if row[5] else None} for row in rows]
        for row in session.scalars(select(UsageArchive).where(UsageArchive.document_created_at >= since - timedelta(days=1))):
            documents.append({'kind': row.kind, 'id': row.document_id, 'filename': row.filename, 'status': row.status,
                              'created': row.document_created_at.astimezone(timezone.utc).date(), 'usage': row.usage,
                              'user_id': str(row.uploaded_by) if row.uploaded_by else None, 'deleted': True})
    return documents


@router.get('/summary')
def usage_summary(days: int = Query(30, ge=1, le=365)):
    """
    Purpose: Give the usage dashboard its figures for the last N days (by upload date).
    Input: days - 1 to 365 (default 30).
    Output: the summary from summarize() covering Tech Packs and purchase orders together.
    """
    settings = get_settings()
    return summarize(load_documents(days), days, input_price=settings.llm_price_input_per_mtok,
                     output_price=settings.llm_price_output_per_mtok)


@router.get('/users', dependencies=[Depends(require_admin)])
def usage_by_user(days: int = Query(30, ge=1, le=365)):
    """
    Purpose: Show an admin each person's token use and cost for the last N days (by upload date).
    Input: days - 1 to 365 (default 30).
    Output: {'days', 'users': [...]} from summarize_by_user(); every active or past user with uploads appears,
    plus an 'Unassigned' row for uploads made before uploader tracking. Raises 403 for non-admins.
    """
    settings = get_settings()
    with SessionLocal() as session:
        users = {str(user.id): {'name': user.full_name, 'email': user.email} for user in session.scalars(select(User))}
    return {'days': days, 'users': summarize_by_user(load_documents(days), users, days,
                                                      input_price=settings.llm_price_input_per_mtok,
                                                      output_price=settings.llm_price_output_per_mtok)}
