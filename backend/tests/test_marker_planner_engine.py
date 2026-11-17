import itertools

import pytest

# Engine regression tests carried over from the original Marker cutting project.
from app.marker_planner import planner


@pytest.mark.parametrize('capacity,maximum,manual_markers', [
    (6, 120, 7), (23, 120, 5), (200, 120, 3), (21, 120, 4), (50, 120, 3),
    (6, 80, 7), (23, 50, 5), (200, 35, 3), (21, 40, 4), (50, 35, 3),
])
def test_800_garment_order_combines_sizes_below_normal_gcd(capacity, maximum, manual_markers):
    quantities = (40, 80, 112, 112, 96, 80, 48, 48, 32, 32,
                  16, 16, 16, 16, 16, 16, 16, 8)
    data = planner.PlannerInput(tuple(f'Size{i}' for i in range(18)), quantities,
                                capacity, maximum, 10, 2.0)
    result = planner.solve_plan(data)
    assert result.status in ('OPTIMAL', 'FEASIBLE')
    planner.validate_plan(data, result.lays)
    assert result.marker_count <= manual_markers


def inputs(q=(100, 200, 300), capacity=4, maximum=100, minimum=10):
    return planner.PlannerInput(tuple(f"Size{i}" for i in range(len(q))), q,
                                capacity, maximum, minimum, 12.0)


def test_original_po_has_two_unique_markers():
    assert hasattr(planner, "solve_plan"), "Planning engine is not implemented"
    data = inputs()
    result = planner.solve_plan(data)
    assert result.status == "OPTIMAL"
    assert result.marker_count == 2
    planner.validate_plan(data, result.lays)


def test_reused_marker_counts_once():
    data = inputs((140, 280, 140))
    result = planner.solve_plan(data)
    assert result.status == "OPTIMAL"
    assert result.marker_count == 1
    assert len(result.lays) == 2
    assert sum(lay.plies for lay in result.lays) == 140
    assert {lay.marker for lay in result.lays} == {(1, 2, 1)}
    planner.validate_plan(data, result.lays)


def test_final_remainder_exception_and_equal_plies():
    planner.validate_plan(inputs((105,), 1), [planner.Lay((1,), 100), planner.Lay((1,), 5)])
    planner.validate_plan(inputs((200,), 1), [planner.Lay((1,), 100), planner.Lay((1,), 100)])
    planner.validate_plan(inputs(), [planner.Lay((1, 2, 1), 100), planner.Lay((0, 0, 4), 50)])
    result = planner.solve_plan(inputs((105,), 1))
    assert result.marker_count == 1
    planner.validate_plan(inputs((105,), 1), result.lays)


@pytest.mark.parametrize("q,cap,lays", [
    ((105,), 1, [((1,), 5), ((1,), 100)]),
    ((105,), 1, [((1,), 100), ((1,), 6)]),
    ((100, 200), 4, [((1, 0), 100), ((1, 2), 100)]),
    ((100,), 4, [((5,), 20)]),
    ((100,), 4, [((1,), 0)]),
    ((100,), 4, [((1,), -1)]),
    ((15,), 1, [((1,), 8), ((1,), 7)]),
])
def test_invalid_cutting_plans_are_rejected(q, cap, lays):
    with pytest.raises(ValueError):
        planner.validate_plan(inputs(q, cap), [planner.Lay(m, p) for m, p in lays])


@pytest.mark.parametrize("changes", [
    {"sizes": ("", "M", "L")}, {"sizes": ("S", "S", "L")},
    {"quantities": (1.5, 2, 3)}, {"quantities": (-1, 2, 3)},
    {"max_plies": 0}, {"min_plies": 101}, {"capacity": 0},
    {"time_limit_seconds": float("nan")}, {"time_limit_seconds": 0},
])
def test_invalid_inputs_are_rejected(changes):
    from dataclasses import replace
    with pytest.raises(ValueError):
        planner.solve_plan(replace(inputs(), **changes))


def test_capacity_and_zero_demand():
    assert planner.capacity_from_length(8, 2) == 4
    assert planner.capacity_from_length(0.3, 0.1) == 3
    for length, consumption in [(0, 2), (8, 0), (float("inf"), 2)]:
        with pytest.raises(ValueError):
            planner.capacity_from_length(length, consumption)
    result = planner.solve_plan(inputs((0, 20), 2))
    assert result.status == "OPTIMAL"
    assert all(lay.marker[0] == 0 for lay in result.lays)
    empty = planner.solve_plan(inputs((0, 0)))
    assert empty.marker_count == 0 and empty.lays == []


def test_more_sizes_than_capacity_can_use_subsets():
    result = planner.solve_plan(inputs((10, 10, 10, 10, 10), 4))
    assert result.status == "OPTIMAL"
    assert result.marker_count == 2
    planner.validate_plan(inputs((10,) * 5, 4), result.lays)


def test_subset_plan_can_defer_an_outstanding_size():
    planner.validate_plan(inputs((100, 200), 4),
                          [planner.Lay((1, 0), 100), planner.Lay((0, 2), 100)])


def test_real_twenty_size_order_accepts_mixed_subset_lays():
    quantities = (270, 1020, 1890, 930, 1410, 1680, 870, 300, 120, 30,
                  30, 120, 330, 300, 360, 150, 60, 60, 60, 30)
    data = inputs(quantities, 6)
    # Construct an independent feasibility witness, not an optimality claim.
    remaining = [q // 30 for q in quantities]
    lays = []
    while any(remaining):
        marker = [0] * len(remaining)
        for _ in range(6):
            if not any(remaining):
                break
            size = min((i for i, q in enumerate(remaining) if q), key=lambda i: (marker[i], i))
            marker[size] += 1
            remaining[size] -= 1
        lays.append(planner.Lay(tuple(marker), 30))
    assert len(quantities) == 20 and sum(quantities) == 10020
    assert sum(c > 0 for c in lays[0].marker) == 6
    planner.validate_plan(data, lays)
    # This rule fix must not label the order infeasible merely for having 20 sizes.
    result = planner.solve_plan(data)
    assert result.status in ("FEASIBLE", "OPTIMAL")
    planner.validate_plan(data, result.lays)


@pytest.mark.parametrize("capacity", [19, 21, 40, 200])
def test_real_order_large_materials_produce_valid_plans(capacity):
    q = (270, 1020, 1890, 930, 1410, 1680, 870, 300, 120, 30,
         30, 120, 330, 300, 360, 150, 60, 60, 60, 30)
    from dataclasses import replace
    data = replace(inputs(q, capacity), time_limit_seconds=1)
    result = planner.solve_plan(data)
    assert result.status in ("FEASIBLE", "OPTIMAL")
    planner.validate_plan(data, result.lays)
    assert result.marker_lower_bound <= result.marker_count


def test_lay_bound_covers_sizes_that_are_cut_separately():
    data = inputs((1, 1, 1), 1, 1, 1)
    result = planner.solve_plan(data)
    assert result.status == "OPTIMAL"
    assert len(result.lays) == 3
    assert result.marker_count == 3
    planner.validate_plan(data, result.lays)


def test_minimum_rule_can_make_a_po_infeasible():
    result = planner.solve_plan(inputs((1, 1, 200), 1))
    assert result.status == "INFEASIBLE"


def test_small_size_can_be_deferred_to_final_remainder():
    data = inputs((1, 200), 2)
    result = planner.solve_plan(data)
    assert result.status == "OPTIMAL"
    assert result.marker_count == 2
    planner.validate_plan(data, result.lays)


def test_large_model_is_not_reported_as_infeasible():
    data = inputs(tuple(range(1001, 1009)), 30)
    result = planner.solve_plan(data)
    assert result.status == "FEASIBLE"
    planner.validate_plan(data, result.lays)
    assert not result.secondary_optimal


def test_huge_single_size_does_not_allocate_unbounded_lays():
    result = planner.solve_plan(inputs((10**12,), 1))
    assert result.status == "MODEL_TOO_LARGE"


def test_tiny_budget_does_not_claim_optimality():
    from dataclasses import replace
    data = replace(inputs(), time_limit_seconds=0.000001)
    result = planner.solve_plan(data)
    assert result.status in ("UNKNOWN", "FEASIBLE")
    if result.status == "FEASIBLE":
        planner.validate_plan(data, result.lays)


def test_progress_reports_actual_marker_search_and_completion():
    events = []
    data = inputs()
    result = planner.solve_plan(data, on_progress=events.append)
    assert events == result.progress
    search = [e for e in events if e.phase == "markers"]
    assert search
    counts = [e.marker_count for e in search]
    assert counts == sorted(set(counts), reverse=True)
    assert all(not e.marker_minimum_proven for e in search)
    final = events[-1]
    assert final.phase == "complete"
    assert final.status == result.status
    assert final.marker_count == result.marker_count
    assert final.lay_count == len(result.lays)
    assert final.marker_minimum_proven == (result.status == "OPTIMAL")
    assert all(0 <= e.elapsed_seconds <= result.elapsed_seconds for e in events)


def test_direct_solution_and_failure_have_honest_progress():
    events = []
    result = planner.solve_plan(inputs((140, 280, 140)), on_progress=events.append)
    assert events[-1].marker_count == 1
    assert events[-1].marker_minimum_proven
    assert result.progress == events
    failed = planner.solve_plan(inputs((1, 1, 200), 1))
    assert failed.progress[-1].status == "INFEASIBLE"
    assert failed.progress[-1].marker_count is None
    assert not failed.progress[-1].marker_minimum_proven


def test_timeout_progress_does_not_claim_proof():
    from dataclasses import replace
    result = planner.solve_plan(replace(inputs(), time_limit_seconds=0.000001))
    assert not result.progress[-1].marker_minimum_proven


def brute_minimum(q, capacity, maximum, minimum):
    """Small independent exhaustive oracle; no CP-SAT implementation details."""
    best = sum(q) + 1

    def search(remaining, previous, used):
        nonlocal best
        if not any(remaining):
            best = min(best, len(used))
            return
        if len(used) >= best:
            return
        ranges = [range(0, min(v, capacity) + 1) for v in remaining]
        for marker in itertools.product(*ranges):
            if not 1 <= sum(marker) <= capacity:
                continue
            for plies in range(1, min(previous, maximum) + 1):
                after = tuple(v - c * plies for v, c in zip(remaining, marker))
                if min(after) < 0 or (plies < minimum and any(after)):
                    continue
                search(after, plies, used | {marker})

    search(q, maximum, set())
    return None if best > sum(q) else best


@pytest.mark.parametrize("q", [(1, 2), (2, 3), (3, 5), (4, 4), (1, 1, 2), (3, 4, 5)])
def test_solver_matches_small_exhaustive_oracle(q):
    data = inputs(q, 3, 3, 2)
    expected = brute_minimum(q, 3, 3, 2)
    result = planner.solve_plan(data)
    if expected is None:
        assert result.status == "INFEASIBLE"
    else:
        assert result.status == "OPTIMAL"
        assert result.marker_count == expected
        planner.validate_plan(data, result.lays)


@pytest.mark.parametrize('capacity', [9, 34, 66])
def test_po_357705_small_gcd_keeps_normal_minimum(capacity):
    data = planner.PlannerInput(tuple(f'S{i}' for i in range(9)),
        (8,16,40,54,64,24,8,8,8), capacity, 70, 10, 10)
    result = planner.solve_plan(data)
    assert result.status in ('FEASIBLE', 'OPTIMAL')
    planner.validate_plan(data, result.lays)
    assert all(l.plies >= 10 for l in result.lays[:-1])


def test_flexible_search_returns_valid_seed_when_budget_is_exhausted():
    data=planner.PlannerInput(tuple(f'S{i}' for i in range(9)),
        (8,16,40,54,64,24,8,8,8),9,70,10,.001)
    result=planner.solve_plan(data)
    assert result.status=='FEASIBLE'
    planner.validate_plan(data,result.lays)
    assert not result.secondary_optimal


@pytest.mark.parametrize('capacity', [3, 27])
def test_combined_po_358449_359259_large_lay_bound_returns_valid_plan(capacity):
    data = planner.PlannerInput(
        ('C44','C46','C48','C50','C52','C54','C56','C58','C148','C154','D92','D100','D104','D108','D112'),
        (90,288,576,618,504,252,126,27,27,27,9,27,27,18,9),
        capacity,70,10,.001)
    result = planner.solve_plan(data)
    assert result.status == 'FEASIBLE'
    planner.validate_plan(data,result.lays)
    assert not result.secondary_optimal
    assert not result.progress[-1].marker_minimum_proven
    assert all(sum(l.marker)<=capacity and l.plies<=70 for l in result.lays)
