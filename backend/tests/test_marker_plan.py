"""Cutting-plan integration: PO/BOM mapping into solver inputs, solver invocation, result handling and the API."""
from decimal import Decimal
from fastapi import FastAPI
from fastapi.testclient import TestClient
from types import SimpleNamespace
from copy import deepcopy
from uuid import uuid4
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import pytest
from app import marker_plan, marker_plan_routes
from app import marker_plan_store
from app.auth import require_user
from app.models import AuditLog, MarkerPlanRecord
from app.marker_plan import (PlanMaterial, PlanOrder, PlanRequest, PlanSizeRow, PlanInputError, material_capacity,
                             order_demand, planner_input, run_material, whole_quantity)
from app.marker_planner import Lay, PlannerInput, PlanResult, validate_plan


def order(label, *rows):
    return PlanOrder(label=label, size_rows=[PlanSizeRow(size=size, quantity=quantity) for size, quantity in rows])


def material(consumption='2', unit='m', max_plies=100, code='R1'):
    return PlanMaterial(material_code=code, consumption=Decimal(consumption), unit=unit, max_plies=max_plies)


def request(orders, materials, length='8', min_plies=10, seconds=60):
    return PlanRequest(orders=orders, materials=materials, table_length_m=Decimal(length),
                       min_plies=min_plies, time_limit_seconds=seconds)


def lays_from(result):
    """Rebuild solver lays from the JSON the UI receives, so the validator checks what is displayed."""
    return [Lay(tuple(lay['counts']), lay['plies']) for lay in result['lays']]


# ---- Input mapping -------------------------------------------------------------------------------

def test_orders_are_combined_by_size_in_first_printed_order():
    demand = order_demand([order('100', ('C48', '84'), ('C50', '42'), ('c48', '16')),
                           order('101', (' C52 ', '1 002'), ('C50', 8))])
    assert demand.sizes == ('C48', 'C50', 'C52')
    assert demand.quantities == (100, 50, 1002)
    assert demand.warnings == ['Contract 100 lists size C48 in 2 rows; their quantities were added together.']


def test_zero_quantity_sizes_are_kept_as_columns():
    demand = order_demand([order('1', ('S', '0'), ('M', '20'))])
    assert demand.sizes == ('S', 'M') and demand.quantities == (0, 20)


@pytest.mark.parametrize('value,expected', [('32', 32), ('32.0', 32), ('1 002', 1002), (7, 7), ('0', 0),
                                            ('1.5', None), ('-3', None), (-3, None), ('1,234.50', None),
                                            ('', None), (None, None), ('abc', None)])
def test_whole_quantity(value, expected):
    assert whole_quantity(value) == expected


def test_every_unreadable_row_is_reported_at_once():
    with pytest.raises(PlanInputError) as caught:
        order_demand([order('100', ('S', '1.5'), (None, '4'), ('M', None)), PlanOrder(label=None, size_rows=[])])
    assert caught.value.problems == [
        'Contract 100, size row 1 (S): quantity "1.5" is not a whole number of garments.',
        'Contract 100, size row 2 has no size.',
        'Contract 100, size row 3 (M) has no quantity.',
        'Purchase order 2 has no size rows.']


def test_an_order_with_no_garments_is_rejected():
    with pytest.raises(PlanInputError, match='no garments'):
        order_demand([order('1', ('S', '0'))])


@pytest.mark.parametrize('length,consumption,unit,expected', [
    ('8', '0.15', 'm', 53), ('8', '1.65', 'm', 4), ('0.3', '0.1', 'm', 3),
    ('8', '165', 'cm', 4), ('8', '1500', 'mm', 5), ('8', '0.6', 'yd', 14), ('1', '2', 'm', 0)])
def test_capacity_is_table_length_over_consumption_rounded_down(length, consumption, unit, expected):
    assert material_capacity(Decimal(length), material(consumption, unit)) == expected


def test_planner_input_uses_each_materials_capacity_and_ply_limit():
    plan = request([order('1', ('S', '100'), ('M', '200'))], [material('2', max_plies=120), material('0.1', max_plies=80)])
    demand = order_demand(plan.orders)
    first, second = (planner_input(demand, item, plan) for item in plan.materials)
    assert first == PlannerInput(('S', 'M'), (100, 200), 4, 120, 10, 60.0)
    assert (second.capacity, second.max_plies) == (80, 80)


@pytest.mark.parametrize('item,message', [(material('9'), 'capacity is below 1'),
                                          (material('2', max_plies=5), 'above this material')])
def test_impossible_material_settings_are_refused_before_solving(item, message):
    plan = request([order('1', ('S', '10'))], [item])
    with pytest.raises(ValueError, match=message):
        planner_input(order_demand(plan.orders), item, plan)


# ---- Solver invocation and output handling -----------------------------------------------------------

def test_simple_ratio_order_uses_one_marker_with_proven_markers_and_lays():
    data = PlannerInput(('S', 'M', 'L'), (140, 280, 140), 4, 100, 10, 10.0)
    result = run_material(data, prefix='B01-')
    assert result['status'] == 'OPTIMAL' and result['validated']
    assert result['marker_minimum_proven'] and result['lay_minimum_proven'] and result['secondary_optimal']
    assert result['marker_count'] == 1 and result['marker_lower_bound'] == 1
    assert result['one_marker_shortcut']
    assert [event['phase'] for event in result['progress']] == ['building', 'complete']  # no search ran
    assert result['markers'] == [{'id': 'B01-M01', 'counts': [1, 2, 1], 'sets_per_marker': 4, 'lay_numbers': [1, 2],
                                  'lay_count': 2, 'total_plies': 140, 'sets_cut': 560}]
    assert [lay['plies'] for lay in result['lays']] == [100, 40]
    assert all(row['difference'] == 0 for row in result['production'])
    validate_plan(data, lays_from(result))


def test_order_needing_several_markers_is_exact_and_valid():
    data = PlannerInput(('S', 'M', 'L'), (100, 200, 300), 4, 100, 10, 10.0)
    result = run_material(data, prefix='B02-')
    assert result['status'] == 'OPTIMAL' and result['marker_count'] == 2
    assert not result['one_marker_shortcut']
    assert [marker['id'] for marker in result['markers']] == ['B02-M01', 'B02-M02']
    assert {lay['marker_id'] for lay in result['lays']} == {'B02-M01', 'B02-M02'}
    assert [(row['required'], row['produced']) for row in result['production']] == [(100, 100), (200, 200), (300, 300)]
    assert sum(marker['lay_count'] for marker in result['markers']) == result['lay_count'] == len(result['lays'])
    validate_plan(data, lays_from(result))


def test_solve_plan_is_the_entry_point_and_progress_is_forwarded(monkeypatch):
    calls, events = [], []
    real = marker_plan.solve_plan

    def spy(data, on_progress=None):
        calls.append(data)
        return real(data, on_progress)

    monkeypatch.setattr(marker_plan, 'solve_plan', spy)
    data = PlannerInput(('S', 'M', 'L'), (100, 200, 300), 4, 100, 10, 10.0)
    result = run_material(data, events.append)
    assert calls == [data]
    assert events and events[-1].phase == 'complete' and events[-1].status == result['status']
    assert [event['phase'] for event in result['progress']] == [event.phase for event in events]


def test_restricted_search_result_is_valid_but_not_called_optimal():
    data = PlannerInput(tuple(f'S{i}' for i in range(8)), tuple(range(1001, 1009)), 30, 100, 10, 5.0)
    result = run_material(data)
    assert result['status'] == 'FEASIBLE' and result['validated'] and not result['one_marker_shortcut']
    assert not result['marker_minimum_proven'] and not result['lay_minimum_proven'] and not result['secondary_optimal']
    validate_plan(data, lays_from(result))


def test_time_limited_result_never_claims_proof():
    data = PlannerInput(tuple(f'S{i}' for i in range(9)), (8, 16, 40, 54, 64, 24, 8, 8, 8), 9, 70, 10, 0.001)
    result = run_material(data)
    assert result['status'] in ('FEASIBLE', 'UNKNOWN')
    assert not result['marker_minimum_proven'] and not result['lay_minimum_proven']
    if result['status'] == 'FEASIBLE':
        validate_plan(data, lays_from(result))


def test_infeasible_order_has_no_plan():
    result = run_material(PlannerInput(('S', 'M', 'L'), (1, 1, 200), 1, 100, 10, 10.0))
    assert result['status'] == 'INFEASIBLE'
    assert result['lays'] == [] and result['markers'] == [] and not result['validated']


def test_resource_limit_is_reported_not_infeasible():
    result = run_material(PlannerInput(('S',), (10**12,), 1, 100, 10, 10.0))
    assert result['status'] == 'MODEL_TOO_LARGE' and result['lays'] == []


def test_a_plan_that_fails_independent_validation_is_never_shown(monkeypatch):
    bad = PlanResult('OPTIMAL', [Lay((1, 0), 50)], 1, True)  # leaves size M uncut
    monkeypatch.setattr(marker_plan, 'solve_plan', lambda data, on_progress=None: bad)
    result = run_material(PlannerInput(('S', 'M'), (50, 50), 2, 100, 10, 10.0))
    assert result['status'] == 'ERROR' and result['lays'] == [] and 'independent validation' in result['message']


def test_a_solver_crash_becomes_an_error_result(monkeypatch):
    def crash(data, on_progress=None):
        raise RuntimeError('native failure')
    monkeypatch.setattr(marker_plan, 'solve_plan', crash)
    result = run_material(PlannerInput(('S',), (50,), 2, 100, 10, 10.0))
    assert result['status'] == 'ERROR' and 'native failure' in result['message']


# ---- API ---------------------------------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    MarkerPlanRecord.__table__.create(engine)
    AuditLog.__table__.create(engine)
    monkeypatch.setattr(marker_plan_store, 'SessionLocal', sessionmaker(bind=engine, expire_on_commit=False))
    monkeypatch.setattr(marker_plan_routes, '_jobs', {})
    monkeypatch.setattr(marker_plan_routes, '_inputs', {})
    # Run jobs immediately instead of in the background thread.
    monkeypatch.setattr(marker_plan_routes, 'submit', lambda function, *args: function(*args))
    app = FastAPI()
    app.include_router(marker_plan_routes.router)
    app.dependency_overrides[require_user] = lambda: SimpleNamespace(id=uuid4(), email='ann@example.com', full_name='Ann Planner')
    yield TestClient(app)
    engine.dispose()


def logged(client):
    """Every activity-log entry written so far, oldest first, as plain tuples (action, who, document, details)."""
    with marker_plan_store.SessionLocal() as session:
        rows = session.scalars(select(AuditLog).order_by(AuditLog.created_at, AuditLog.action)).all()
        return [(row.action, row.user_email, row.target_type, row.target_name, row.target_id, row.details) for row in rows]


def body(**changes):
    value = {'orders': [{'label': '355800', 'size_rows': [{'size': 'S', 'quantity': '400'}, {'size': 'M', 'quantity': '200'},
                                                           {'size': 'L', 'quantity': '200'}]}],
             'materials': [{'material_code': 'R1845', 'description': 'Main', 'consumption': '2', 'unit': 'm', 'max_plies': 120}],
             'table_length_m': '8', 'min_plies': 10, 'time_limit_seconds': 60}
    value.update(changes)
    return value


def test_delete_finished_plan_removes_durable_and_cached_results(client):
    job_id = client.post('/api/marker-plans', json=body()).json()['id']
    assert client.delete(f'/api/marker-plans/{job_id}').status_code == 200
    assert client.get(f'/api/marker-plans/{job_id}').status_code == 404
    assert client.get(f'/api/marker-plans/{job_id}/excel').status_code == 404
    assert all(row['id'] != job_id for row in client.get('/api/marker-plans').json())
    assert client.delete(f'/api/marker-plans/{job_id}').status_code == 404


def test_generating_a_plan_is_logged_with_its_inputs(client):
    data = body(tech_pack_filename='tp-1459.pdf', style_number='1459')
    job_id = client.post('/api/marker-plans', json=data).json()['id']
    (action, who, target_type, name, target_id, details), = logged(client)
    assert (action, who, target_type, name, target_id) == ('marker_plan.create', 'ann@example.com', 'marker_plan', 'tp-1459.pdf', job_id)
    assert details['orders'] == ['355800'] and details['total_quantity'] == 800 and details['style_number'] == '1459'
    assert (details['table_length_m'], details['min_plies'], details['time_limit_seconds']) == ('8', 10, 60.0)
    assert details['materials'] == [{'material_code': 'R1845', 'consumption': '2', 'unit': 'm', 'max_plies': 120}]


def test_a_plan_without_a_file_name_is_named_after_its_purchase_orders(client):
    client.post('/api/marker-plans', json=body())
    assert logged(client)[0][3] == '355800'


def test_deleting_a_plan_logs_what_was_deleted(client):
    job_id = client.post('/api/marker-plans', json=body(tech_pack_filename='tp.pdf')).json()['id']
    assert client.delete(f'/api/marker-plans/{job_id}').status_code == 200
    created, deleted = sorted(logged(client), key=lambda entry: entry[0])
    assert (created[0], deleted[0]) == ('marker_plan.create', 'marker_plan.delete')
    assert (deleted[1], deleted[3], deleted[4]) == ('ann@example.com', 'tp.pdf', job_id)
    assert deleted[5]['status'] == 'complete' and deleted[5]['summary']['complete'] is True
    assert deleted[5]['materials'][0]['material_code'] == 'R1845'


def test_a_rejected_delete_is_not_logged(client, monkeypatch):
    monkeypatch.setattr(marker_plan_routes, 'submit', lambda *args: None)
    job_id = client.post('/api/marker-plans', json=body()).json()['id']
    assert client.delete(f'/api/marker-plans/{job_id}').status_code == 409
    assert client.delete('/api/marker-plans/00000000-0000-0000-0000-000000000000').status_code == 404
    assert [entry[0] for entry in logged(client)] == ['marker_plan.create']


def test_excel_download_is_logged_and_refused_when_it_cannot_be_logged(client, monkeypatch):
    job_id = client.post('/api/marker-plans', json=body(tech_pack_filename='tp.pdf')).json()['id']
    assert client.get(f'/api/marker-plans/{job_id}/excel').status_code == 200
    assert [entry[0] for entry in logged(client)] == ['marker_plan.create', 'marker_plan.download']
    def unavailable(*args):
        raise RuntimeError('database offline')
    monkeypatch.setattr(marker_plan_store, 'log_event', unavailable)
    assert client.get(f'/api/marker-plans/{job_id}/excel').status_code == 503
    assert len(logged(client)) == 2


def test_delete_active_plan_is_rejected(client, monkeypatch):
    monkeypatch.setattr(marker_plan_routes, 'submit', lambda *args: None)
    job_id = client.post('/api/marker-plans', json=body()).json()['id']
    assert client.delete(f'/api/marker-plans/{job_id}').status_code == 409
    assert client.get(f'/api/marker-plans/{job_id}').status_code == 200


def test_delete_database_failure_keeps_cached_plan(client, monkeypatch):
    job_id = client.post('/api/marker-plans', json=body()).json()['id']
    def fail(*args):
        raise RuntimeError('Database unavailable')
    monkeypatch.setattr(marker_plan_routes.store, 'delete_record', fail)
    assert client.delete(f'/api/marker-plans/{job_id}').status_code == 503
    assert client.get(f'/api/marker-plans/{job_id}').status_code == 200


def test_rerun_fails_when_current_ply_lookup_is_unavailable(client):
    # This fixture has the marker-plan table, but deliberately no plies table.
    job_id = client.post('/api/marker-plans', json=body()).json()['id']
    assert client.get(f'/api/marker-plans/{job_id}/rerun-settings').status_code == 503


def test_plan_actions_have_unique_route_registrations():
    keys = [(route.path, method) for route in marker_plan_routes.router.routes for method in route.methods]
    assert len(keys) == len(set(keys))


def test_rerun_retains_durable_incumbent_even_if_solver_fails(client, monkeypatch):
    from app import marker_plan
    data = body(orders=[{'label':'Test','size_rows':[{'size':'S','quantity':'100'}, {'size':'M','quantity':'200'}, {'size':'L','quantity':'300'}]}],
        materials=[{'material_code':'R1','consumption':'2','max_plies':100}])
    original_id = client.post('/api/marker-plans', json=data).json()['id']
    original = client.get('/api/marker-plans/' + original_id).json()
    assert original['summary']['complete']
    def fail(*args):
        raise RuntimeError('Simulated search interruption')
    monkeypatch.setattr(marker_plan, 'solve_plan', fail)
    data['time_limit_seconds'] = 90
    data['table_length_m'] = '8.00'
    data['materials'][0]['consumption'] = '2.00'
    new_id = client.post('/api/marker-plans', json=data).json()['id']
    new = client.get('/api/marker-plans/' + new_id).json()
    assert new_id != original_id
    assert new['summary']['complete']
    assert new['materials'][0]['result']['marker_count'] <= original['materials'][0]['result']['marker_count']
    assert client.get('/api/marker-plans/' + original_id).json() == original


def test_rerun_settings_use_current_plies_without_changing_saved_plan(client, monkeypatch):
    job_id = client.post('/api/marker-plans', json=body()).json()['id']
    original = client.get(f'/api/marker-plans/{job_id}').json()
    monkeypatch.setattr(marker_plan_routes.store, 'current_ply_info', lambda materials: {
        'R1845': {'max_ply': 60, 'matches': [{'col_d': '60'}]}})
    response = client.get(f'/api/marker-plans/{job_id}/rerun-settings')
    assert response.status_code == 200
    assert response.json()['request']['materials'][0]['max_plies'] == 60
    assert response.json()['request']['orders'] == original['request']['orders']
    assert client.get(f'/api/marker-plans/{job_id}').json() == original
    monkeypatch.setattr(marker_plan_routes.store, 'current_ply_info', lambda materials: {})
    fallback = client.get(f'/api/marker-plans/{job_id}/rerun-settings').json()
    assert fallback['request']['materials'][0]['max_plies'] == 120
    assert fallback['notes']


def test_plan_is_queued_then_completed_with_full_results(client):
    created = client.post('/api/marker-plans', json=body())
    assert created.status_code == 202
    job = created.json()
    assert job['status'] == 'queued' and job['summary'] is None
    assert job['sizes'] == ['S', 'M', 'L'] and job['quantities'] == [400, 200, 200] and job['total_quantity'] == 800
    assert job['materials'][0]['capacity'] == 4
    done = client.get(f"/api/marker-plans/{job['id']}").json()
    assert done['status'] == 'complete'
    entry = done['materials'][0]
    assert entry['state'] == 'done' and entry['live']['phase'] == 'complete'
    result = entry['result']
    for key in ('status', 'lays', 'marker_count', 'secondary_optimal', 'marker_lower_bound', 'message',
                'elapsed_seconds', 'progress'):
        assert key in result
    assert result['status'] == 'OPTIMAL' and result['marker_count'] == 1
    validate_plan(PlannerInput(('S', 'M', 'L'), (400, 200, 200), 4, 120, 10, 5.0), lays_from(result))
    assert done['summary'] == {'complete': True, 'marker_count': 1, 'lay_count': len(result['lays']), 'failed': 0}


def test_each_material_is_solved_separately_and_one_bad_material_does_not_block_others(client):
    materials = [{'material_code': 'MAIN', 'consumption': '2', 'max_plies': 120},
                 {'material_code': 'LINING', 'consumption': '10', 'unit': 'cm', 'max_plies': 80},
                 {'material_code': 'TOO-LONG', 'consumption': '9', 'max_plies': 120}]
    job = client.post('/api/marker-plans', json=body(materials=materials)).json()
    assert [entry['capacity'] for entry in job['materials']] == [4, 80, 0]
    assert job['materials'][2]['result']['status'] == 'INVALID_INPUT'
    done = client.get(f"/api/marker-plans/{job['id']}").json()
    first, second, third = (entry['result'] for entry in done['materials'])
    assert first['status'] == second['status'] == 'OPTIMAL'
    assert first['markers'][0]['id'] == 'B01-M01' and second['markers'][0]['id'] == 'B02-M01'
    assert all(lay['plies'] <= 80 for lay in second['lays'])
    assert all(sum(lay['counts']) <= 80 for lay in second['lays'])
    assert third['lays'] == [] and 'capacity is below 1' in third['message']
    assert done['summary'] == {'complete': False, 'marker_count': None, 'lay_count': None, 'failed': 1}


def test_unreadable_po_quantities_are_a_clear_400(client):
    response = client.post('/api/marker-plans', json=body(orders=[{'label': '9', 'size_rows': [{'size': 'S', 'quantity': '12.5'}]}]))
    assert response.status_code == 400
    assert 'Contract 9, size row 1 (S)' in response.json()['detail']


@pytest.mark.parametrize('changes', [
    {'table_length_m': '0'}, {'min_plies': 0}, {'time_limit_seconds': 0}, {'time_limit_seconds': 59}, {'time_limit_seconds': 301},
    {'materials': []}, {'orders': []},
    {'materials': [{'consumption': '0', 'max_plies': 10}]},
    {'materials': [{'consumption': '2', 'unit': 'kg', 'max_plies': 10}]},
    {'materials': [{'consumption': '2', 'max_plies': 0}]},
    {'materials': [{'consumption': 'Infinity', 'max_plies': 10}]},
    {'orders': [{'label': '1', 'size_rows': [{'size': 'S', 'quantity': True}]}]},
])
def test_invalid_requests_are_rejected(client, changes):
    assert client.post('/api/marker-plans', json=body(**changes)).status_code == 422


def test_timeout_and_unknown_status_are_reported_without_a_plan(client, monkeypatch):
    monkeypatch.setattr(marker_plan, 'solve_plan', lambda data, on_progress=None: PlanResult(
        'UNKNOWN', message='No plan found within the time budget. Try a larger budget.'))
    job = client.post('/api/marker-plans', json=body()).json()
    result = client.get(f"/api/marker-plans/{job['id']}").json()['materials'][0]['result']
    assert result['status'] == 'UNKNOWN' and result['lays'] == [] and not result['validated']
    assert 'time budget' in result['message']


def test_unexpected_job_failure_finishes_the_job(client, monkeypatch):
    def broken(*args, **kwargs):
        raise MemoryError('out of memory')
    monkeypatch.setattr(marker_plan_routes, 'run_material', broken)
    job = client.post('/api/marker-plans', json=body()).json()
    done = client.get(f"/api/marker-plans/{job['id']}").json()
    assert done['status'] == 'complete'
    assert done['materials'][0]['result']['status'] == 'ERROR'
    assert done['summary']['complete'] is False


def test_unknown_job_is_404(client):
    assert client.get('/api/marker-plans/00000000-0000-0000-0000-000000000000').status_code == 404


def test_the_router_is_registered_in_the_app(client):
    from app.auth import require_user
    from app.main import app
    # No context manager: start-up (database and MinIO) is not needed for this route.
    app.dependency_overrides[require_user] = lambda: SimpleNamespace(is_admin=True, permissions={})
    try:
        response = TestClient(app).get('/api/marker-plans/00000000-0000-0000-0000-000000000000')
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 404 and 'Cutting plan not found' in response.json()['detail']


def test_completed_plan_survives_cache_loss_and_lists_its_saved_inputs(client):
    created = client.post('/api/marker-plans', json=body()).json()
    before = client.get(f"/api/marker-plans/{created['id']}").json()
    marker_plan_routes._jobs.clear()
    marker_plan_routes._inputs.clear()
    restored = client.get(f"/api/marker-plans/{created['id']}").json()
    assert restored == before
    assert restored['saved'] is True
    assert restored['request']['orders'][0]['label'] == '355800'
    assert restored['request']['materials'][0]['consumption'] == '2'
    history = client.get('/api/marker-plans').json()
    assert len(history) == 1 and history[0]['id'] == before['id']
    assert history[0]['summary']['complete'] is True
    assert history[0]['total_quantity'] == 800


def test_generating_again_keeps_both_saved_versions(client):
    first = client.post('/api/marker-plans', json=body()).json()
    second = client.post('/api/marker-plans', json=body()).json()
    history = client.get('/api/marker-plans').json()
    assert [row['id'] for row in history] == [second['id'], first['id']]


def test_restart_finishes_interrupted_jobs_without_discarding_completed_materials(client, monkeypatch):
    done_id = client.post('/api/marker-plans', json=body()).json()['id']
    complete = client.get(f'/api/marker-plans/{done_id}').json()
    monkeypatch.setattr(marker_plan_routes, 'submit', lambda *args: None)
    queued = client.post('/api/marker-plans', json=body(materials=[
        {'material_code': 'A', 'consumption': '2', 'max_plies': 120},
        {'material_code': 'B', 'consumption': '2', 'max_plies': 120},
    ])).json()
    interrupted = deepcopy(queued)
    interrupted['materials'][0] = deepcopy(complete['materials'][0])
    marker_plan_store.update_snapshot(interrupted)
    marker_plan_routes._jobs.clear()
    marker_plan_routes.recover_interrupted_plans()
    restored = client.get(f"/api/marker-plans/{queued['id']}").json()
    assert restored['status'] == 'complete'
    assert restored['materials'][0]['result']['validated'] is True
    assert restored['materials'][1]['result']['status'] == 'ERROR'
    assert 'restart' in restored['materials'][1]['result']['message'].lower()
    assert restored['summary']['complete'] is False
    assert client.get(f'/api/marker-plans/{done_id}').json() == complete


def test_database_failure_does_not_start_an_unsaved_plan(client, monkeypatch):
    calls = []
    def unavailable(*args):
        raise RuntimeError('database offline')
    monkeypatch.setattr(marker_plan_store, 'create_record', unavailable)
    monkeypatch.setattr(marker_plan_routes, 'submit', lambda *args: calls.append(args))
    response = client.post('/api/marker-plans', json=body())
    assert response.status_code == 503
    assert calls == [] and marker_plan_routes._jobs == {}


def test_final_save_failure_is_visible_and_cannot_export_a_stale_plan(client, monkeypatch):
    def unavailable(*args):
        raise RuntimeError('database offline')
    monkeypatch.setattr(marker_plan_store, 'update_snapshot', unavailable)
    queued = client.post('/api/marker-plans', json=body()).json()
    done = client.get(f"/api/marker-plans/{queued['id']}").json()
    assert done['status'] == 'complete' and done['saved'] is False
    assert done['persistence_error']
    assert client.get(f"/api/marker-plans/{queued['id']}/excel").status_code == 409
