from datetime import date
from app.usage_routes import request_cost, summarize, summarize_by_user

TODAY = date(2026, 10, 22)


def doc(created, usage, status='needs_review', kind='techpack', name='a.pdf'):
    return {'kind': kind, 'id': name, 'filename': name, 'status': status, 'created': created, 'usage': usage}


def call(status='success', tokens=100, attempt=1, stage='extraction', **extra):
    return {'status': status, 'total_tokens': tokens, 'input_tokens': tokens - 10, 'output_tokens': 10,
            'attempt': attempt, 'stage': stage, **extra}


def test_totals_failures_and_daily_rows():
    result = summarize([
        doc(TODAY, [call(cost_usd=0.01), call('token_limit', 50, attempt=1), call(attempt=2, cost_usd=0.02)], name='x.pdf'),
        doc(date(2026, 10, 20), [call(stage='classification', cost_usd=0.005)], status='failed', kind='po', name='y.pdf'),
        doc(date(2026, 1, 1), [call()], name='old.pdf'),
    ], days=3, today=TODAY)
    totals = result['totals']
    assert (totals['documents'], totals['failed_documents'], totals['requests'], totals['failed_requests']) == (2, 1, 4, 1)
    assert totals['retries'] == 1 and totals['total_tokens'] == 350
    assert totals['failure_rate'] == 0.25
    assert round(totals['cost_usd'], 4) == 0.035 and totals['cost_estimated'] is False
    assert [row['date'] for row in result['daily']] == ['2026-10-20', '2026-10-21', '2026-10-22']
    assert [row['requests'] for row in result['daily']] == [1, 0, 3]
    assert {item['status']: item['count'] for item in result['by_status']} == {'success': 3, 'token_limit': 1}
    assert result['worst_documents'][0]['filename'] == 'x.pdf' and result['worst_documents'][0]['failed_requests'] == 1


def test_cost_is_unavailable_without_recorded_cost_or_prices():
    result = summarize([doc(TODAY, [call()])], days=1, today=TODAY)
    assert result['totals']['cost_usd'] is None and result['daily'][0]['cost_usd'] is None


def test_cost_is_estimated_from_prices_and_marked():
    assert request_cost(call(tokens=1_000_010), 1.0, 2.0) == ((1_000_000 * 1.0 + 10 * 2.0) / 1_000_000, True)
    assert request_cost(call(cost_usd=0.5), 1.0, 2.0) == (0.5, False)
    result = summarize([doc(TODAY, [call(tokens=1_000_010)])], days=1, today=TODAY, input_price=1.0, output_price=2.0)
    assert result['totals']['cost_estimated'] is True


def test_usage_is_totalled_per_user_with_unassigned_uploads_separate():
    users = {'u1': {'name': 'Ann', 'email': 'ann@x.com'}, 'u2': {'name': 'Bob', 'email': 'bob@x.com'}}
    result = summarize_by_user([
        {**doc(TODAY, [call(cost_usd=0.01), call('token_limit', 50)], name='a.pdf'), 'user_id': 'u1'},
        {**doc(TODAY, [call(cost_usd=0.04)], kind='po', name='b.pdf'), 'user_id': 'u2'},
        {**doc(TODAY, [call()], name='c.pdf'), 'user_id': None},
        {**doc(TODAY, [call()], name='d.pdf'), 'user_id': 'deleted-user'},
        {**doc(date(2026, 1, 1), [call(cost_usd=9)], name='old.pdf'), 'user_id': 'u1'},
    ], users, days=3, today=TODAY)
    assert [item['name'] for item in result] == ['Bob', 'Ann', 'Unassigned']
    ann = result[1]
    assert (ann['documents'], ann['requests'], ann['failed_requests'], ann['total_tokens']) == (1, 2, 1, 150)
    assert round(ann['cost_usd'], 4) == 0.01 and ann['cost_estimated'] is False
    unassigned = result[2]
    assert unassigned['documents'] == 2 and unassigned['cost_usd'] is None


def test_empty_period_has_no_failure_rate():
    result = summarize([], days=2, today=TODAY)
    assert result['totals']['failure_rate'] is None and len(result['daily']) == 2
