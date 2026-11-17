"""Bounded search for a validated starting plan with shared-size lays.

Ply candidates use the demand GCD, but only the final lay may be below
the normal minimum. This is a heuristic, never an optimality proof.
"""
from functools import reduce
from math import gcd, ceil
from time import monotonic


def shared_seed(inputs, quantities, capacity, expand, deadline):
    from .planner import Lay, validate_plan

    unit = reduce(gcd, quantities)
    if len(quantities) > 100 or inputs.max_plies // unit > 1000:
        return None
    # A small beam keeps this independent of the expensive CP-SAT model.
    frontier = [(quantities, inputs.max_plies, ())]
    seen = set()
    for _ in range(min(80, sum(quantities))):
        candidates = {}
        for remaining, previous, path in frontier:
            if monotonic() >= deadline:
                return None
            for plies in range(min(previous, max(remaining)) // unit * unit, 0, -unit):
                available = tuple(q // plies for q in remaining)
                if not any(available):
                    continue
                if plies < inputs.min_plies:
                    if any(q % plies for q in remaining) or sum(available) > capacity:
                        continue
                    orders = [range(len(remaining))]
                else:
                    orders = [
                        sorted(range(len(remaining)), key=lambda i: -remaining[i]),
                        sorted(range(len(remaining)), key=lambda i: (remaining[i] % plies != 0, -remaining[i])),
                        sorted(range(len(remaining)), key=lambda i: (available[i] == 0, available[i], -remaining[i])),
                        sorted(range(len(remaining)), key=lambda i: (remaining[i] % plies, -remaining[i])),
                    ]
                patterns = set()
                for order in orders:
                    marker = [0] * len(remaining)
                    room = capacity
                    for i in order:
                        marker[i] = min(available[i], room)
                        room -= marker[i]
                    patterns.add(tuple(marker))
                for marker in sorted(patterns):
                    left = tuple(q - c * plies for q, c in zip(remaining, marker))
                    new_path = path + ((marker, plies),)
                    if not any(left):
                        lays = [Lay(expand(m), p) for m, p in new_path]
                        try:
                            validate_plan(inputs, lays)
                        except ValueError:
                            continue
                        return lays
                    state = (left, plies)
                    if state not in seen:
                        candidates.setdefault(state, new_path)
        if not candidates:
            return None
        def rank(item):
            (left, plies), path = item
            lower = max(ceil(sum(left) / (capacity * plies)),
                        ceil(sum(q > 0 for q in left) / capacity))
            return lower, sum(left), sum(q > 0 for q in left), sum(p for _, p in path), left, plies
        chosen = sorted(candidates.items(), key=rank)[:64]
        seen.update(candidates)
        frontier = [(left, plies, path) for (left, plies), path in chosen]
    return None
