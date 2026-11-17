"""Optimize aggregate plies for fixed mixed-size ratios, then validate their actual lays.

All cutting rules remain enforced, including one undersized final lay. Restricted
candidate pools can improve an incumbent but never prove unrestricted optimality.
"""
from collections import defaultdict
from functools import reduce
from itertools import combinations
from math import comb, gcd, ceil
from time import monotonic
from ortools.sat.python import cp_model


def score(lays):
    return len({lay.marker for lay in lays}), len(lays)


def split_totals(data, patterns):
    from .planner import Lay, validate_plan
    lays = []
    for marker, total in patterns:
        if not total:
            continue
        n = (total + data.max_plies - 1) // data.max_plies
        if n > 10000 or len(lays) + n > 10000:
            return None
        if total >= n * data.min_plies:
            base, extra = divmod(total, n)
            lays.extend(Lay(tuple(marker), base + int(i < extra)) for i in range(n))
        else:
            full, tail = divmod(total, data.max_plies)
            lays.extend(Lay(tuple(marker), data.max_plies) for _ in range(full))
            if tail:
                lays.append(Lay(tuple(marker), tail))
    lays.sort(key=lambda lay: -lay.plies)
    try:
        validate_plan(data, lays)
    except ValueError:
        return None
    return lays


def baseline(data):
    """Fast fallback only; mixed-size optimization improves it when time is available."""
    small = [q for q in data.quantities if 0 < q < data.min_plies]
    unit = reduce(gcd, small) if small else 0
    patterns = []
    for i, quantity in enumerate(data.quantities):
        if quantity >= data.min_plies:
            patterns.append((tuple(int(j == i) for j in range(len(data.quantities))), quantity))
    if small:
        tail = tuple(q // unit if 0 < q < data.min_plies else 0 for q in data.quantities)
        patterns.append((tail, unit))
    return split_totals(data, patterns)


def pattern_candidates(data, incumbent=(), limit=5000):
    """Complete small-capacity enumeration, otherwise bounded useful mixed-size ratios."""
    from .planner import _candidates
    positive = [i for i, q in enumerate(data.quantities) if q > 0]
    q = tuple(data.quantities[i] for i in positive)
    capacity = min(data.capacity, sum(q))
    def expand(pattern):
        full = [0] * len(data.quantities)
        for i, count in zip(positive, pattern):
            full[i] = count
        return tuple(full)
    if comb(capacity + len(q), len(q)) - 1 <= limit:
        return [expand(pattern) for pattern in _candidates(q, capacity)], True
    found = {lay.marker for lay in incumbent}
    for i in positive:
        for count in range(1, min(capacity, data.quantities[i]) + 1):
            found.add(tuple(count if j == i else 0 for j in range(len(data.quantities))))
            if len(found) >= limit:
                return sorted(found), False
    # Primitive ratios of small size subsets are good shared-marker candidates;
    # scaled copies also use otherwise empty table capacity.
    operations = 0
    for width in range(2, min(4, len(positive)) + 1):
        for subset in combinations(positive, width):
            operations += 1
            if operations > 20000:
                return sorted(found), False
            divisor = reduce(gcd, (data.quantities[i] for i in subset))
            pattern = tuple(data.quantities[i] // divisor if i in subset else 0 for i in range(len(data.quantities)))
            if sum(pattern) > capacity:
                continue
            for multiplier in range(1, capacity // sum(pattern) + 1):
                found.add(tuple(c * multiplier for c in pattern))
                if len(found) >= limit:
                    return sorted(found), False
    return sorted(found), False


def optimize_patterns(data, candidates, deadline, incumbent=None, complete=False, emit=None):
    from .planner import Lay, validate_plan
    best = None
    if incumbent:
        try:
            validate_plan(data, list(incumbent))
            best = list(incumbent)
        except ValueError:
            pass
    if monotonic() >= deadline:
        return best, False, None
    patterns = sorted(set(tuple(pattern) for pattern in candidates))
    patterns = [p for p in patterns if len(p) == len(data.quantities) and 0 < sum(p) <= data.capacity
                and all(isinstance(c, int) and c >= 0 for c in p)
                and all(c <= q for c, q in zip(p, data.quantities))]
    if not patterns or len(patterns) * len(data.quantities) > 250000:
        return best, False, None
    model = cp_model.CpModel()
    totals, used, lays, small = [], [], [], []
    sound_lay_bound = (sum(data.quantities) - 1) // data.min_plies + 1
    lay_bound = min(10000, sound_lay_bound)
    for index, pattern in enumerate(patterns):
        upper = min(q // c for q, c in zip(data.quantities, pattern) if c)
        total = model.new_int_var(0, upper, f'total{index}')
        flag = model.new_bool_var(f'used{index}')
        count = model.new_int_var(0, min(lay_bound, (upper + data.max_plies - 1) // data.max_plies), f'lays{index}')
        exception = model.new_bool_var(f'small{index}')
        model.add(total >= flag)
        model.add(total <= upper * flag)
        model.add_division_equality(count, total + data.max_plies - 1, data.max_plies)
        model.add(exception <= flag)
        model.add(total >= data.min_plies * count).only_enforce_if(exception.Not())
        model.add(total >= data.min_plies * (count - 1) + 1).only_enforce_if(exception)
        model.add(total < data.min_plies * count).only_enforce_if(exception)
        totals.append(total); used.append(flag); lays.append(count); small.append(exception)
    model.add(sum(small) <= 1)
    model.add(sum(lays) <= lay_bound)
    for i, quantity in enumerate(data.quantities):
        model.add(sum(p[i] * total for p, total in zip(patterns, totals) if p[i]) == quantity)
    weight = lay_bound + 1
    objective = sum(used) * weight + sum(lays)
    model.minimize(objective)
    if best is not None:
        by_pattern = defaultdict(int)
        for lay in best:
            by_pattern[lay.marker] += lay.plies
        if set(by_pattern) <= set(patterns):
            normalized = split_totals(data, by_pattern.items())
            if normalized is not None and score(normalized) < score(best):
                best = normalized
            model.add(objective <= score(best)[0] * weight + len(best))
            for p, total, flag, count, exception in zip(patterns, totals, used, lays, small):
                t = by_pattern[p]
                n = (t + data.max_plies - 1) // data.max_plies
                for variable, value in [(total,t),(flag,int(t>0)),(count,n),(exception,int(0<t<n*data.min_plies))]:
                    model.add_hint(variable,value)
    if monotonic() >= deadline:
        return best, False, None
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(.001, deadline-monotonic())
    solver.parameters.num_search_workers = 8
    class Progress(cp_model.CpSolverSolutionCallback):
        def on_solution_callback(self):
            if emit:
                emit('markers', sum(self.value(v) for v in used), sum(self.value(v) for v in lays))
    status = solver.solve(model, Progress())
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        if status == cp_model.INFEASIBLE and sound_lay_bound > 10000:
            status = cp_model.UNKNOWN  # The resource-limited model cannot prove impossibility.
        return best, False, status
    candidate = split_totals(data, [(p, solver.value(total)) for p, total in zip(patterns, totals)])
    if candidate is not None and (best is None or score(candidate) < score(best)):
        best = candidate
    proven = complete and sound_lay_bound <= 10000 and status == cp_model.OPTIMAL and best is not None
    return best, proven, status
