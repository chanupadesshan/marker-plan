"""Cutting-plan optimizer: marker size combinations and lay plies for exact size demand.

The four modules are kept together, unchanged, so their relative imports work:
planner.py (public entry point and validator), compact_search.py, flexible_search.py
and shared_seed.py. They optimize integer size counts and plies only; they do not nest
pattern pieces or measure fabric use.
"""
from .planner import (Lay, PlanResult, PlannerInput, ProgressEvent, capacity_from_length,
                      solve_plan, validate_plan)

__all__ = ['Lay', 'PlanResult', 'PlannerInput', 'ProgressEvent', 'capacity_from_length',
           'solve_plan', 'validate_plan']
