"""Bounded aggregate search for orders too large to enumerate marker patterns.

Ply totals are restricted to multiples of the demand GCD. Failure in this
restricted search is never a proof of infeasibility or minimum marker count.
"""
from functools import reduce
from math import gcd
from time import monotonic

from ortools.sat.python import cp_model


def compact_plan(inputs, quantities, capacity, expand, emit, deadline):
    # Import locally to avoid a module cycle with the public planner interface.
    from .planner import Lay, validate_plan

    unit = reduce(gcd, quantities)
    if unit < inputs.min_plies or len(quantities) > 100:
        return None

    def split(patterns):
        merged = {}
        for marker, total in patterns:
            marker = expand(marker)
            merged[marker] = merged.get(marker, 0) + total
        lays = []
        for marker, total in merged.items():
            n = (total + inputs.max_plies - 1) // inputs.max_plies
            if n > 10000 or len(lays) + n > 10000:
                return None
            base, extra = divmod(total, n)
            lays.extend(Lay(marker, base + (i < extra)) for i in range(n))
        lays.sort(key=lambda lay: -lay.plies)
        try:
            validate_plan(inputs, lays)
        except ValueError:
            return None
        return lays

    # A guaranteed initial candidate for this supported domain, then greedily
    # merge sizes when their exact common ratio fits in one marker.
    groups = []
    for i in sorted(range(len(quantities)), key=lambda i: -quantities[i]):
        for group in groups:
            new = group + [i]
            common = reduce(gcd, (quantities[j] for j in new))
            if sum(quantities[j] // common for j in new) <= capacity:
                group.append(i)
                break
        else:
            groups.append([i])
    patterns = []
    for group in groups:
        common = reduce(gcd, (quantities[i] for i in group))
        marker = tuple(quantities[i] // common if i in group else 0
                       for i in range(len(quantities)))
        # Fill more of the table without changing the exact size ratio.
        # Keep aggregate plies above the normal minimum where possible.
        multiplier = max(k for k in range(1, capacity // sum(marker) + 1)
                         if common % k == 0 and common // k >= inputs.min_plies)
        marker = tuple(c * multiplier for c in marker)
        common //= multiplier
        patterns.append((marker, common))
    best = split(patterns)
    if best is None:
        return None
    lower = max(2, (len(quantities) + capacity - 1) // capacity)
    count = len({lay.marker for lay in best})
    emit("markers", count, len(best))
    demand = tuple(q // unit for q in quantities)
    for k in range(lower, count):
        budget = deadline - monotonic()
        if budget <= 0.02:
            break
        model = cp_model.CpModel()
        weights = [model.new_int_var(1, max(demand), f"w{j}") for j in range(k)]
        counts = [[model.new_int_var(0, min(capacity, q), f"c{j}_{i}")
                   for i, q in enumerate(demand)] for j in range(k)]
        for j in range(k):
            model.add(sum(counts[j]) >= 1)
            model.add(sum(counts[j]) <= capacity)
            if j:
                model.add(weights[j - 1] >= weights[j])
        for i, q in enumerate(demand):
            produced = []
            for j in range(k):
                v = model.new_int_var(0, q, f"p{j}_{i}")
                model.add_multiplication_equality(v, [weights[j], counts[j][i]])
                produced.append(v)
            model.add(sum(produced) == q)
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = min(4.0, max(0.001, deadline - monotonic()))
        solver.parameters.num_search_workers = 8
        status = solver.solve(model)
        if status in (cp_model.FEASIBLE, cp_model.OPTIMAL):
            candidate = split([(tuple(solver.value(c) for c in row),
                                solver.value(weights[j]) * unit)
                               for j, row in enumerate(counts)])
            if candidate is not None and len({lay.marker for lay in candidate}) < count:
                best = candidate
                count = len({lay.marker for lay in best})
                emit("markers", count, len(best))
                break
    return best, lower
