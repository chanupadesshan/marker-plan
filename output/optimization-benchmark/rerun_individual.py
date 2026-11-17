import json
import runpy
import sys
from pathlib import Path

sys.argv = ['workflow', 'read-only']
api = runpy.run_path('output/marker-plan-03/workflow.py')['api']
out = Path('output/optimization-benchmark/individual')
out.mkdir(parents=True, exist_ok=True)
state_path = out / 'reruns.json'
state = json.loads(state_path.read_text()) if state_path.exists() else {}
history = api('GET', '/api/marker-plans?limit=100').json()
for contract in ['361061','355800','362097']:
    if contract not in state:
        source = next(row for row in history if row['order_labels'] == [contract])
        original = api('GET', '/api/marker-plans/' + source['id']).json()
        settings = api('GET', '/api/marker-plans/' + source['id'] + '/rerun-settings').json()
        request = settings['request']
        request['time_limit_seconds'] = 20
        assert [order['label'] for order in request['orders']] == [contract]
        job = api('POST', '/api/marker-plans', json=request).json()
        state[contract] = {'id':job['id'],'previous_id':source['id'],'previous_summary':source['summary'],
                           'notes':settings.get('notes',[])}
        state_path.write_text(json.dumps(state, indent=2))
        (out / f'{contract}-previous.json').write_text(json.dumps(original, indent=2))
    job = api('GET', '/api/marker-plans/' + state[contract]['id']).json()
    print(contract,job['id'],job['status'],flush=True)
    if job['status'] == 'complete':
        assert job['saved'] and job['summary']['complete']
        for material in job['materials']:
            result = material['result']
            assert result['validated'] and all(row['difference'] == 0 for row in result['production'])
        (out / f'{contract}-saved-plan.json').write_text(json.dumps(job, indent=2))
        (out / f'{contract}-improved-marker-plan.xlsx').write_bytes(api('GET', '/api/marker-plans/'+job['id']+'/excel').content)
        print(json.dumps({'contract':contract,'quantity':job['total_quantity'],'summary':job['summary'],
            'table_length_m':job['request']['table_length_m'],'notes':state[contract]['notes'],
            'materials':[{ 'code':m['material_code'],'max_plies':m['max_plies'],
               'markers':m['result']['marker_count'],'lays':m['result']['lay_count']} for m in job['materials']]}),flush=True)
