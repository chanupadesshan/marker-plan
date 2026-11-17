"""Create separate source records and one combined plan for contracts 358449 and 359259."""
import json
import runpy
import sys
from pathlib import Path

mode = sys.argv[1]
sys.argv = ['workflow', 'reuse-api']
ROOT = Path(__file__).resolve().parents[2]
api = runpy.run_path(str(ROOT / 'output/marker-plan-03/workflow.py'))['api']
OUT = Path(__file__).resolve().parent
state_path = OUT / 'documents.json'
state = json.loads(state_path.read_text()) if state_path.exists() else {}

if mode == 'upload':
    for key, filename, url in [('tech_pack', 'tech-pack-1530-1310.pdf', '/api/documents/upload'),
        ('358449', 'purchase-order-358449.pdf', '/api/purchase-orders/upload'),
        ('359259', 'purchase-order-359259.pdf', '/api/purchase-orders/upload')]:
        if key not in state:
            with (ROOT / 'output/pdf' / filename).open('rb') as stream:
                fields = {'tech_pack_id': state['tech_pack']['id']} if key != 'tech_pack' else {}
                state[key] = api('POST', url, data=fields, files={'file': (filename, stream, 'application/pdf')}).json()
            state_path.write_text(json.dumps(state, indent=2))
        print(key, state[key]['id'], state[key]['status'], flush=True)
    for row in api('GET', '/api/plies').json():
        if str(row.get('col_c') or '').split('-')[0].strip().upper().lstrip('R') in ['1310', '1948']:
            print('Recorded plies:', {key: row.get(key) for key in ['id','col_c','col_d']}, flush=True)
elif mode == 'status':
    for key in ['tech_pack', '358449', '359259']:
        base = '/api/documents/' if key == 'tech_pack' else '/api/purchase-orders/'
        doc = api('GET', base + state[key]['id']).json()
        (OUT / (key + '-extraction.json')).write_text(json.dumps(doc, indent=2))
        print(key, doc['status'], doc.get('error'), flush=True)
        data = doc.get('extraction') or {}
        print(json.dumps(data.get('materials') if key == 'tech_pack' else data.get('orders')), flush=True)
        if key == 'tech_pack': print('Ply info:', json.dumps(doc.get('ply_info')), flush=True)
elif mode == 'start':
    doc = api('GET', '/api/documents/' + state['tech_pack']['id']).json()
    assert doc['status'] in ['approved', 'needs_review'], doc['status']
    materials = doc['extraction']['page_tables'][0]['materials']
    assert [row['material_code'] for row in materials] == ['R1310', 'R1948']
    assert [row['quantity'] for row in materials] == ['2.09', '0.29']
    assert all(row['unit'] == 'm' for row in materials)
    expected = {
        '358449': (['-C44','-C46','-C48','-C50','-C52','-C54','-C56','-C58','-D100','-D104','-D108','-C148','-C154'],
                   [54,198,360,348,378,144,90,27,18,18,9,18,9]),
        '359259': (['-C44','-C46','-C48','-C50','-C52','-C54','-C56','-D92','-D100','-D104','-D108','-D112','-C148','-C154'],
                   [36,90,216,270,126,108,36,9,9,9,9,9,9,18])}
    orders = []
    for key, (sizes, quantities) in expected.items():
        po_doc = api('GET', '/api/purchase-orders/' + state[key]['id']).json()
        assert po_doc['status'] in ['approved', 'needs_review']
        assert len(po_doc['extraction']['orders']) == 1
        po = po_doc['extraction']['orders'][0]
        assert po['contract_number'] == key
        assert [row['size'] for row in po['size_rows']] == sizes
        assert [int(row['quantity']) for row in po['size_rows']] == quantities
        assert int(po['total_quantity'].replace(',', '')) == sum(quantities)
        assert po['tech_pack_reference'] == '18693' and po['model_id'] == '1530' and po['quality_id'] == '1310' and po['color_id'] == '9900'
        orders.append({'label': key, **{field: po.get(field) for field in ['tech_pack_reference','model_id','quality_id','color_id']},
            'source_filename': po_doc['filename'], 'size_rows': [{'size': row['size'], 'quantity': row['quantity']} for row in po['size_rows']]})
    assert sum(int(row['quantity']) for po in orders for row in po['size_rows']) == 2625
    choices = {}
    for material in materials:
        code = material['material_code']
        info = doc.get('ply_info', {}).get(code)
        assert info and info.get('max_ply'), f'Missing maximum plies for {code}'
        choices[code] = info['max_ply']
    payload = {'tech_pack_id': doc['id'], 'tech_pack_filename': doc['filename'], 'style_number': '1530',
        'tech_pack_number': doc['extraction'].get('tech_pack_number'), 'orders': orders,
        'table_length_m': '8', 'min_plies': 10, 'time_limit_seconds': 20,
        'materials': [{**{key: material.get(key) for key in ['material_code','description','composition','placement','placement_type','colorways']},
            'page_number': 1, 'consumption': material['quantity'], 'unit': material['unit'], 'max_plies': choices[material['material_code']]} for material in materials]}
    (OUT / 'request.json').write_text(json.dumps(payload, indent=2))
    if 'plan' not in state:
        state['plan'] = api('POST', '/api/marker-plans', json=payload).json()
        state_path.write_text(json.dumps(state, indent=2))
    print('Saved combined plan', state['plan']['id'], '2625 garments, table 8 m; maximum plies', choices, flush=True)
elif mode == 'finish':
    job = api('GET', '/api/marker-plans/' + state['plan']['id']).json()
    (OUT / 'saved-plan.json').write_text(json.dumps(job, indent=2))
    print(job['id'], job['status'], job.get('summary'), flush=True)
    for material in job['materials']:
        result = material.get('result')
        print(material['material_code'], material['state'], result and {key: result.get(key) for key in ['status','validated','marker_count','lay_count']}, flush=True)
    if job['status'] == 'complete':
        assert job['saved'] and job['summary']['complete'] and job['total_quantity'] == 2625
        assert job['order_labels'] == ['358449', '359259'] and len(job['sizes']) == 15
        assert len(job['materials']) == 2
        assert all(material['result']['validated'] and all(row['difference'] == 0 for row in material['result']['production']) for material in job['materials'])
        (OUT / '358449-359259-marker-plan-8m.xlsx').write_bytes(api('GET', '/api/marker-plans/' + job['id'] + '/excel').content)
        assert any(row['id'] == job['id'] for row in api('GET', '/api/marker-plans').json())
        print('PASS: both POs combined, 15 sizes, 2625 garments per material, saved in history and Excel downloaded.', flush=True)
