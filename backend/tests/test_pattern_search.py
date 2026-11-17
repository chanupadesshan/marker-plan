from time import monotonic
from app.marker_planner.planner import PlannerInput, Lay, validate_plan
from app.marker_planner.pattern_search import optimize_patterns


def test_aggregate_patterns_split_large_totals_into_valid_lays():
    data = PlannerInput(('S','M','L'), (330,330,330), 3, 75, 10, 2)
    lays, proven, _ = optimize_patterns(data, [(1,1,1)], monotonic()+2, complete=True)
    validate_plan(data, lays)
    assert len({lay.marker for lay in lays}) == 1
    assert len(lays) == 5 and sum(lay.plies for lay in lays) == 330
    assert proven


def test_marker_count_has_priority_over_lays_and_mixed_sizes_are_searched():
    data = PlannerInput(('S','M','L'), (100,200,300), 4, 100, 10, 3)
    lays, proven, _ = optimize_patterns(data, [(1,2,0),(0,0,3),(1,0,0),(0,1,0),(0,0,1)], monotonic()+3)
    validate_plan(data, lays)
    assert len({lay.marker for lay in lays}) == 2 and len(lays) == 2
    assert not proven  # A restricted catalogue cannot prove the unrestricted capacity model.


def test_deadline_keeps_valid_incumbent_and_rejects_invalid_hint():
    data = PlannerInput(('S','M','L'), (100,200,300), 4, 100, 10, 1)
    best = [Lay((1,2,0),100),Lay((0,0,3),100)]
    lays, proven, _ = optimize_patterns(data, [(1,0,0)], monotonic(), incumbent=best)
    assert lays == best and not proven
    lays, _, _ = optimize_patterns(data, [(1,0,0)], monotonic(), incumbent=[Lay((1,2,0),101)])
    assert lays is None


def test_multiple_small_balance_groups_are_not_permitted():
    data = PlannerInput(('S','M','L'), (9,9,6), 1, 75, 10, 2)
    lays, _, _ = optimize_patterns(data, [(1,0,0),(0,1,0),(0,0,1)], monotonic()+2, complete=True)
    assert lays is None


def test_resource_lay_cap_never_proves_unrestricted_catalogue_minimum():
    data = PlannerInput(('S','M','L'), (9000,9000,10004), 3, 1, 1, 3)
    catalogue = [(1,1,0),(0,0,1),(1,1,1),(2,1,0),(0,1,2),(1,0,1)]
    lays, proven, _ = optimize_patterns(data, catalogue, monotonic()+3, complete=True)
    if lays is not None:
        validate_plan(data, lays)
    assert not proven  # Two markers are possible outside the 10,000-lay resource cap.


def test_invalid_new_result_keeps_independently_validated_incumbent(monkeypatch):
    from app import marker_plan
    from app.marker_planner.planner import PlanResult
    data = PlannerInput(('S','M'), (50,50), 2, 75, 10, 1,
                        incumbent_lays=(Lay((1,1),50),))
    monkeypatch.setattr(marker_plan, 'solve_plan', lambda *args: PlanResult('FEASIBLE', [Lay((1,1),49)], 1))
    result = marker_plan.run_material(data)
    assert result['validated'] and result['status'] == 'FEASIBLE'
    assert result['lays'][0]['plies'] == 50


def test_resource_lay_cap_cannot_prove_catalogue_infeasible():
    from ortools.sat.python import cp_model
    data = PlannerInput(('S',), (10001,), 1, 1, 1, 1)
    lays, proven, status = optimize_patterns(data, [(1,)], monotonic()+1, complete=True)
    assert lays is None and not proven and status == cp_model.UNKNOWN
