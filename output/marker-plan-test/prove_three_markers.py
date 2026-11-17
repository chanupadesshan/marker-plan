"""Check the three-marker question without the production compact search's GCD restriction.

The aggregate model relaxes lay splitting and sequencing. Every valid cutting plan with at
most three unique markers maps to a solution here by summing each marker's lay plies.
Therefore INFEASIBLE proves three markers impossible under the stricter cutting rules too.
"""
import json
from pathlib import Path
from time import monotonic
from ortools.sat.python import cp_model
from app.marker_plan import PlanRequest, order_demand, planner_input
from app.marker_planner import Lay, validate_plan

root = Path(__file__).resolve().parent
saved = json.loads((root / 'saved-live-plan.json').read_text())
request = PlanRequest.model_validate(saved['request'])
demand = order_demand(request.orders)
inputs = planner_input(demand, request.materials[0], request)
validate_plan(inputs, [Lay(tuple(lay['counts']), lay['plies']) for lay in saved['materials'][0]['result']['lays']])
assert len({tuple(lay['counts']) for lay in saved['materials'][0]['result']['lays']}) == 4

model = cp_model.CpModel()
maximum = max(inputs.quantities)
weights = [model.new_int_var(0, maximum, f'total_plies_{j}') for j in range(3)]
counts = [[model.new_int_var(0, min(inputs.capacity, q), f'ratio_{j}_{i}')
           for i, q in enumerate(inputs.quantities)] for j in range(3)]
for j in range(3):
    model.add(sum(counts[j]) <= inputs.capacity)
    if j:
        model.add(weights[j - 1] >= weights[j])
for i, q in enumerate(inputs.quantities):
    production = []
    for j in range(3):
        value = model.new_int_var(0, q, f'production_{j}_{i}')
        model.add_multiplication_equality(value, [weights[j], counts[j][i]])
        production.append(value)
    model.add(sum(production) == q)

solver = cp_model.CpSolver()
solver.parameters.max_time_in_seconds = 30
solver.parameters.num_search_workers = 8
start = monotonic()
status = solver.solve(model)
report = {
    'contract': '361061', 'material': 'R1514', 'consumption_m': '1.65',
    'table_length_m': str(request.table_length_m), 'capacity': inputs.capacity,
    'max_plies_per_lay': inputs.max_plies, 'min_plies': inputs.min_plies,
    'sizes': list(inputs.sizes), 'quantities': list(inputs.quantities),
    'tested_unique_markers_at_most': 3, 'status': solver.status_name(status),
    'elapsed_seconds': round(monotonic() - start, 3),
    'weight_domain': f'Every integer from 0 to {maximum}; no demand-GCD restriction',
    'model': 'Relaxed aggregate feasibility: each marker capacity at most 4; exact quantity per size. Lay limits relaxed.',
    'four_marker_plan_independently_validated': True,
    'minimum_markers_proven': 4 if status == cp_model.INFEASIBLE else None,
}
if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
    report['candidate'] = [{'counts': [solver.value(c) for c in row], 'total_plies': solver.value(weights[j])}
                           for j, row in enumerate(counts)]
print(json.dumps(report, indent=2))
(root / 'three-marker-proof.json').write_text(json.dumps(report, indent=2))
