import json
from pathlib import Path
from app.marker_plan import PlanRequest, order_demand, planner_input
from app.marker_planner import Lay, validate_plan

out = Path(__file__).resolve().parent
for path in sorted(out.glob('*-saved-plan.json')):
    job = json.loads(path.read_text())
    request = PlanRequest.model_validate(job['request'])
    demand = order_demand(request.orders)
    assert len(request.orders) == 1 and len(job['materials']) == 4
    for source, material in zip(request.materials,job['materials']):
        result = material['result']
        lays = [Lay(tuple(row['counts']),row['plies']) for row in result['lays']]
        validate_plan(planner_input(demand,source,request),lays)
        assert len({lay.marker for lay in lays}) == result['marker_count']
    print(job['order_labels'][0], 'PASS: every material independently validated, quantities exact, limits respected.')
