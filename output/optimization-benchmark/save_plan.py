import json
import runpy
import sys
from pathlib import Path

sys.argv = ['workflow', 'read-only']
api = runpy.run_path('output/marker-plan-03/workflow.py')['api']
out = Path('output/optimization-benchmark')
state = out / 'documents.json'
if not state.exists():
    request = json.loads(Path('output/marker-plan-multiple-po/request.json').read_text())
    request['time_limit_seconds'] = 20
    job = api('POST', '/api/marker-plans', json=request).json()
    state.write_text(json.dumps({'id': job['id']}, indent=2))
job_id = json.loads(state.read_text())['id']
job = api('GET', f'/api/marker-plans/{job_id}').json()
print('Plan:', job_id, job['status'])
if job['status'] == 'complete':
    assert job['saved'] and job['summary']['complete']
    (out / 'saved-plan.json').write_text(json.dumps(job, indent=2))
    (out / '358449-359259-improved-marker-plan.xlsx').write_bytes(api('GET', f'/api/marker-plans/{job_id}/excel').content)
    for material in job['materials']:
        result = material['result']
        assert result['validated'] and all(row['difference'] == 0 for row in result['production'])
        print(material['material_code'], result['marker_count'], 'markers', result['lay_count'], 'lays', result['status'])
