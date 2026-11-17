"""Generate contract 355800 from the already-uploaded, approved page-2 document data."""
import json
import runpy
import sys
from pathlib import Path

mode = sys.argv[1] if len(sys.argv) > 1 else 'start'
sys.argv = ['workflow', 'reuse-api']
api = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'marker-plan-03/workflow.py'))['api']
out = Path(__file__).resolve().parent
state_file = out / 'plan.json'
if mode == 'start':
    doc = api('GET', '/api/documents/f89c4d32-129d-47ce-8253-22047652689b').json()
    po_doc = api('GET', '/api/purchase-orders/61d90941-59bd-4af7-a765-7c5d7a56a561').json()
    table = next(table for table in doc['extraction']['page_tables'] if table['page_number'] == 2)
    materials = table['materials']
    order = next(order for order in po_doc['extraction']['orders'] if order['contract_number'] == '355800')
    assert [row['material_code'] for row in materials] == ['R1845', 'R1645', 'R1845', 'R2020']
    assert [row['quantity'] for row in materials] == ['0.89', '0.26', '0.04', '0.37']
    assert [row['size'] for row in order['size_rows']] == ['-C44','-C46','-C48','-C50','-C52','-C54','-C56','-C58','-C60','-C62']
    assert [int(row['quantity']) for row in order['size_rows']] == [30,90,210,240,330,270,150,30,30,30]
    assert sum(int(row['quantity']) for row in order['size_rows']) == 1410
    assert order['model_id'] == '1449' and order['quality_id'] == '1845' and order['color_id'] == '8699'
    assert doc['status'] == po_doc['status'] == 'approved'
    payload = {'tech_pack_id': doc['id'], 'tech_pack_filename': doc['filename'], 'style_number': '1449',
        'tech_pack_number': order['tech_pack_reference'], 'table_length_m': '8', 'min_plies': 10, 'time_limit_seconds': 20,
        'orders': [{'label': order['contract_number'], **{key: order.get(key) for key in ['tech_pack_reference','model_id','quality_id','color_id']},
            'source_filename': po_doc['filename'], 'size_rows': [{'size': row['size'], 'quantity': row['quantity']} for row in order['size_rows']]}],
        'materials': [{**{key: row.get(key) for key in ['material_code','description','composition','placement','placement_type','colorways']},
            'page_number': 2, 'consumption': row['quantity'], 'unit': row['unit'],
            'max_plies': doc['ply_info'][row['material_code']]['max_ply']} for row in materials]}
    (out / 'request.json').write_text(json.dumps(payload, indent=2))
    if not state_file.exists():
        state_file.write_text(json.dumps(api('POST', '/api/marker-plans', json=payload).json(), indent=2))
    print('Saved job', json.loads(state_file.read_text())['id'], '8 m table; four materials; 1410 garments; max plies',
        [row['max_plies'] for row in payload['materials']], flush=True)
else:
    job = api('GET', '/api/marker-plans/' + json.loads(state_file.read_text())['id']).json()
    (out / 'saved-plan.json').write_text(json.dumps(job, indent=2))
    print(job['id'], job['status'], job.get('summary'), flush=True)
    for entry in job['materials']:
        result = entry.get('result')
        print(entry['material_code'], entry.get('placement'), entry['state'],
            result and {key: result.get(key) for key in ['status','validated','marker_count','lay_count']}, flush=True)
    if job['status'] == 'complete':
        assert job['saved'] and job['summary']['complete'] and job['total_quantity'] == 1410
        assert len(job['materials']) == 4
        assert all(entry['result']['validated'] and all(row['difference'] == 0 for row in entry['result']['production']) for entry in job['materials'])
        (out / '355800-marker-plan-8m.xlsx').write_bytes(api('GET', '/api/marker-plans/' + job['id'] + '/excel').content)
        assert any(row['id'] == job['id'] for row in api('GET', '/api/marker-plans').json())
        print('PASS: four validated material groups; exact 1410 garments each; saved in history and Excel downloaded.', flush=True)
