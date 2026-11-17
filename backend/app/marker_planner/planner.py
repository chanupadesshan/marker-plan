"""Exact unique-marker optimization for the simplified garment capacity model."""

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_FLOOR
from functools import reduce
from math import comb, gcd, isfinite
from numbers import Integral
from time import monotonic
from typing import Callable

from ortools.sat.python import cp_model


@dataclass(frozen=True)
class PlannerInput:
    sizes: tuple[str, ...]
    quantities: tuple[int, ...]
    capacity: int = 4
    max_plies: int = 100
    min_plies: int = 10
    time_limit_seconds: float = 20.0
    incumbent_lays: tuple['Lay', ...] = ()
    allowed_markers: tuple[tuple[int, ...], ...] | None = None


@dataclass(frozen=True)
class Lay:
    marker: tuple[int, ...]
    plies: int


@dataclass
class ProgressEvent:
    phase: str
    elapsed_seconds: float
    marker_count: int | None = None
    lay_count: int | None = None
    marker_minimum_proven: bool = False
    status: str = "SEARCHING"


@dataclass
class PlanResult:
    status: str
    lays: list[Lay] = field(default_factory=list)
    marker_count: int = 0
    secondary_optimal: bool = False
    elapsed_seconds: float = 0.0
    message: str = ""
    marker_lower_bound: int | None = None
    progress: list[ProgressEvent] = field(default_factory=list)


class _SearchProgress(cp_model.CpSolverSolutionCallback):
    """Only send improved incumbents; native callbacks never call the UI."""

    def __init__(self, used, active, phase, emit):
        super().__init__()
        self.used, self.active, self.phase, self.emit = used, active, phase, emit
        self.best = float("inf")

    def on_solution_callback(self):
        markers = sum(self.value(v) for v in self.used)
        lays = sum(self.value(v) for v in self.active)
        objective = markers if self.phase == "markers" else lays
        if objective < self.best:
            self.best = objective
            self.emit(self.phase, markers, lays, self.phase == "lays")


def _integer(value):
    return isinstance(value, Integral) and not isinstance(value, bool)


def _validate_inputs(data):
    if not data.sizes or len(data.sizes) != len(data.quantities):
        raise ValueError("Provide matching size names and quantities.")
    if any(not isinstance(s, str) or not s.strip() for s in data.sizes):
        raise ValueError("Size names must be nonempty.")
    if len({s.strip().casefold() for s in data.sizes}) != len(data.sizes):
        raise ValueError("Size names must be unique.")
    if any(not _integer(q) or q < 0 for q in data.quantities):
        raise ValueError("Quantities must be nonnegative whole numbers.")
    if any(not _integer(v) or v < 1 for v in
           (data.capacity, data.max_plies, data.min_plies)):
        raise ValueError("Capacity and plies limits must be positive whole numbers.")
    if data.min_plies > data.max_plies:
        raise ValueError("Minimum plies cannot exceed maximum plies.")
    if not isfinite(data.time_limit_seconds) or data.time_limit_seconds <= 0:
        raise ValueError("Solver time budget must be finite and positive.")


def capacity_from_length(length: float, consumption: float) -> int:
    if not isfinite(length) or not isfinite(consumption) or length <= 0 or consumption <= 0:
        raise ValueError("Table length and consumption must be finite and positive.")
    return int((Decimal(str(length)) / Decimal(str(consumption))).to_integral_value(
        rounding=ROUND_FLOOR))


def validate_plan(inputs: PlannerInput, lays: list[Lay]) -> None:
    """Check actual production independently of the solver's constraints."""
    _validate_inputs(inputs)
    remaining = list(inputs.quantities)
    previous = inputs.max_plies
    for index, lay in enumerate(lays):
        if len(lay.marker) != len(remaining):
            raise ValueError("Marker size columns do not match the PO.")
        if any(not _integer(c) or c < 0 for c in lay.marker):
            raise ValueError("Marker counts must be nonnegative whole numbers.")
        if not 1 <= sum(lay.marker) <= inputs.capacity:
            raise ValueError("Marker exceeds capacity or is empty.")
        if inputs.allowed_markers is not None and lay.marker not in inputs.allowed_markers:
            raise ValueError('Marker ratio is not in the verified nesting catalogue.')
        if not _integer(lay.plies) or not 1 <= lay.plies <= previous:
            raise ValueError("Plies must be positive, within maximum, and non-increasing.")
        if lay.plies < inputs.min_plies and index != len(lays) - 1:
            raise ValueError("Only the final lay may be below minimum plies.")
        for size, count in enumerate(lay.marker):
            if remaining[size] == 0 and count > 0:
                raise ValueError("A lay cannot include a completed size.")
            remaining[size] -= count * lay.plies
            if remaining[size] < 0:
                raise ValueError("Plan overproduces a size.")
        previous = lay.plies
    if any(remaining):
        raise ValueError("Plan does not complete every PO quantity.")


def _candidates(quantities, capacity):
    result = []

    def visit(prefix, position, room):
        if position == len(quantities):
            if any(prefix):
                result.append(tuple(prefix))
            return
        for count in range(min(room, quantities[position]) + 1):
            visit(prefix + [count], position + 1, room - count)

    visit([], 0, capacity)
    return result


def solve_plan(inputs: PlannerInput,
               on_progress: Callable[[ProgressEvent], None] | None = None) -> PlanResult:
    _validate_inputs(inputs)
    started = monotonic()
    progress = []
    incumbent = None
    if inputs.incumbent_lays:
        try:
            validate_plan(inputs, list(inputs.incumbent_lays))
            incumbent = list(inputs.incumbent_lays)
        except ValueError:
            pass

    def emit(phase, markers=None, lay_count=None, proven=False, status="SEARCHING"):
        event = ProgressEvent(phase, monotonic() - started, markers, lay_count, proven, status)
        progress.append(event)
        if on_progress is not None:
            on_progress(event)

    emit("building")

    def finish(status, lays=None, secondary=False, message="", lower=None):
        lays = lays or []
        if incumbent and (status not in ('OPTIMAL', 'FEASIBLE') or
                          (len({lay.marker for lay in incumbent}), len(incumbent)) <
                          (len({lay.marker for lay in lays}), len(lays))):
            lays, status, secondary = incumbent, 'FEASIBLE', False
            message = 'Kept the best validated earlier plan; no better plan was found within this search.'
            if lower is not None and lower > len({lay.marker for lay in lays}):
                lower = None
        if status in ("OPTIMAL", "FEASIBLE"):
            validate_plan(inputs, lays)
        markers = len({lay.marker for lay in lays})
        emit("complete", markers if status in ("OPTIMAL", "FEASIBLE") else None,
             len(lays) if status in ("OPTIMAL", "FEASIBLE") else None,
             status == "OPTIMAL", status)
        return PlanResult(status, lays, markers, secondary,
                          monotonic() - started, message, lower, progress)

    indices = [i for i, q in enumerate(inputs.quantities) if q > 0]
    if not indices:
        return finish("OPTIMAL", secondary=True, message="No garments are required.", lower=0)
    quantities = tuple(int(inputs.quantities[i]) for i in indices)
    capacity = min(inputs.capacity, sum(quantities))
    if max(quantities) > 10**7 or capacity > 1000 or inputs.max_plies > 10**6:
        return finish("MODEL_TOO_LARGE", message="Quantity, capacity, or plies exceeds the local app resource limit.")

    def expand(marker):
        full = [0] * len(inputs.sizes)
        for i, count in zip(indices, marker):
            full[i] = count
        return tuple(full)

    if inputs.allowed_markers is not None:
        from .pattern_search import optimize_patterns
        lays, proven, status = optimize_patterns(inputs, inputs.allowed_markers,
            started + inputs.time_limit_seconds, incumbent=incumbent, complete=True, emit=emit)
        if lays:
            return finish('OPTIMAL' if proven else 'FEASIBLE', lays, proven,
                'Minimum marker and lay counts proven within the supplied verified nesting catalogue.' if proven else
                'Valid plan using the supplied verified nesting catalogue; minimum is not proven.',
                len({lay.marker for lay in lays}) if proven else None)
        return finish('INFEASIBLE' if status == cp_model.INFEASIBLE else 'UNKNOWN',
            message='No plan satisfies the cutting rules using these verified marker combinations.' if status == cp_model.INFEASIBLE else
            'No verified-marker plan found within the time budget.')

    # Every one-marker solution must be an integer multiple of this primitive ratio.
    divisor = reduce(gcd, quantities)
    primitive = tuple(q // divisor for q in quantities)
    if sum(primitive) <= capacity:
        multiplier = max(k for k in range(1, min(capacity // sum(primitive), divisor) + 1)
                         if divisor % k == 0)
        marker = expand(tuple(c * multiplier for c in primitive))
        total_plies = divisor // multiplier
        if (total_plies + inputs.max_plies - 1) // inputs.max_plies > 10000:
            return finish("MODEL_TOO_LARGE", message="This plan would contain more than 10,000 cutting lays.")
        full, remainder = divmod(total_plies, inputs.max_plies)
        lays = [Lay(marker, inputs.max_plies) for _ in range(full)]
        if remainder:
            lays.append(Lay(marker, remainder))
        return finish("OPTIMAL", lays, True,
                      "One marker is sufficient; marker count and lay count are proven optimal.", 1)

    # Each non-final lay produces at least min_plies garments. With subsets,
    # different sizes may be cut in different lays, so use total demand rather
    # than the largest single-size demand for a sound upper bound.
    slots = (sum(quantities) - 1) // inputs.min_plies + 1
    estimate = comb(capacity + len(indices), len(indices)) - 1
    if slots > 300 or estimate > 2000 or slots * estimate > 50000 or max(quantities) > 10**7:
        from .pattern_search import baseline, pattern_candidates, optimize_patterns, score
        seed = baseline(inputs)
        if incumbent and (seed is None or score(incumbent) < score(seed)):
            seed = incumbent
        if monotonic() < started + inputs.time_limit_seconds:
            from .shared_seed import shared_seed
            shared = shared_seed(inputs, quantities, capacity, expand,
                min(started + inputs.time_limit_seconds, monotonic() + min(.5, inputs.time_limit_seconds * .05)))
            if shared is not None and (seed is None or score(shared) < score(seed)):
                seed = shared
        patterns, complete = pattern_candidates(inputs, seed or ())
        lays, proven, _ = optimize_patterns(inputs, patterns, started + inputs.time_limit_seconds,
                                            incumbent=seed, complete=complete, emit=emit)
        if lays is not None:
            return finish('OPTIMAL' if proven else 'FEASIBLE', lays, proven,
                'Minimum unique marker count and lay count proven by complete mixed-size pattern search.' if proven else
                'Valid mixed-size plan; the best incumbent was retained and minimum counts are not proven.',
                len({lay.marker for lay in lays}) if proven else max(2, (len(indices) + capacity - 1) // capacity))
        from .compact_search import compact_plan
        compact = compact_plan(inputs, quantities, capacity, expand, emit,
                               started + inputs.time_limit_seconds)
        if compact is not None:
            lays, lower = compact
            proven = len({lay.marker for lay in lays}) == lower
            return finish("OPTIMAL" if proven else "FEASIBLE", lays, False,
                          "Minimum unique marker count proven by matching the lower bound."
                          if proven else
                          "Valid plan found by compact search; minimum marker count is not proven.",
                          lower)
        from .flexible_search import flexible_plan
        lays, status, proven = flexible_plan(inputs, quantities, capacity, expand,
                                             started + inputs.time_limit_seconds)
        return finish(status, lays, proven,
                      "Minimum marker and lay counts proven by direct search." if proven else
                      "Valid plan found by direct search; minimum marker count is not proven." if lays else
                      "Direct search reached its resource limit." if status == "MODEL_TOO_LARGE" else
                      "No plan found within the time budget; infeasibility is not proven." if status == "UNKNOWN" else
                      "No plan satisfies the configured cutting constraints.")
    candidates = _candidates(quantities, capacity)
    model = cp_model.CpModel()
    active = [model.new_bool_var(f"active_{t}") for t in range(slots)]
    plies = [model.new_int_var(0, inputs.max_plies, f"plies_{t}") for t in range(slots)]
    selected = [[model.new_bool_var(f"pick_{t}_{k}") for k in range(len(candidates))]
                for t in range(slots)]
    remaining = [[model.new_int_var(0, q, f"left_{t}_{i}")
                  for i, q in enumerate(quantities)] for t in range(slots + 1)]
    for i, q in enumerate(quantities):
        model.add(remaining[0][i] == q)
        model.add(remaining[-1][i] == 0)
    for t in range(slots):
        model.add(sum(selected[t]) == active[t])
        model.add(plies[t] >= active[t])
        model.add(plies[t] <= inputs.max_plies * active[t])
        if t + 1 < slots:
            model.add(active[t] >= active[t + 1])
            model.add(plies[t] >= plies[t + 1])
            model.add(plies[t] >= inputs.min_plies * active[t + 1])
        for i, q in enumerate(quantities):
            count = model.new_int_var(0, min(capacity, q), f"count_{t}_{i}")
            model.add(count == sum(c[i] * selected[t][k] for k, c in enumerate(candidates)))
            outstanding = model.new_bool_var(f"outstanding_{t}_{i}")
            model.add(remaining[t][i] >= 1).only_enforce_if(outstanding)
            model.add(remaining[t][i] == 0).only_enforce_if(outstanding.Not())
            model.add(count == 0).only_enforce_if(outstanding.Not())
            produced = model.new_int_var(0, q, f"produced_{t}_{i}")
            model.add_multiplication_equality(produced, [count, plies[t]])
            model.add(remaining[t + 1][i] == remaining[t][i] - produced)
    used = [model.new_bool_var(f"used_{k}") for k in range(len(candidates))]
    for k, flag in enumerate(used):
        model.add_max_equality(flag, [selected[t][k] for t in range(slots)])
    # The primitive-ratio check above proves a single marker cannot suffice here.
    model.add(sum(used) >= 2)
    model.add(sum(active) >= (sum(quantities) + capacity * inputs.max_plies - 1)
              // (capacity * inputs.max_plies))
    model.minimize(sum(used))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(0.001, inputs.time_limit_seconds - (monotonic() - started))
    solver.parameters.num_search_workers = 8
    status = solver.solve(model, _SearchProgress(used, active, "markers", emit))
    if status == cp_model.INFEASIBLE:
        return finish("INFEASIBLE", message="No plan satisfies all cutting rules.")
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return finish("UNKNOWN", message="No plan found within the time budget. Try a larger budget.")

    def extract():
        return [Lay(expand(candidates[next(k for k, pick in enumerate(selected[t])
                                          if solver.value(pick))]), solver.value(plies[t]))
                for t in range(slots) if solver.value(active[t])]

    lays = extract()
    lower = int(round(solver.best_objective_bound))
    primary_optimal = status == cp_model.OPTIMAL
    if primary_optimal:
        emit("marker_proof", len({lay.marker for lay in lays}), len(lays), True, "OPTIMAL")
    secondary_optimal = False
    budget = inputs.time_limit_seconds - (monotonic() - started)
    if primary_optimal and budget > 0.05:
        model.add(sum(used) == len({lay.marker for lay in lays}))
        # Reuse the primary solution as an incumbent hint for the secondary solve.
        for variable in active + plies + used + [v for row in selected for v in row]:
            model.add_hint(variable, solver.value(variable))
        model.minimize(sum(active))
        solver.parameters.max_time_in_seconds = budget
        secondary_status = solver.solve(model, _SearchProgress(used, active, "lays", emit))
        if secondary_status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            lays = extract()
            secondary_optimal = secondary_status == cp_model.OPTIMAL
    return finish("OPTIMAL" if primary_optimal else "FEASIBLE", lays, secondary_optimal,
                  "Minimum unique marker count proven." if primary_optimal else
                  "Valid plan found; the minimum marker count has not been proven.", lower)
