"""Create this requested document set and persist its cutting plan through the application API."""
import json
import sys
import time
from pathlib import Path
import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
STATE = OUT / 'documents.json'
env = dotenv_values(ROOT / '.env')
client = httpx.Client(base_url='http://127.0.0.1:8000', timeout=90)
response = client.post('/api/auth/login', json={'email': env.get('ADMIN_EMAIL') or env.get('admin_email'),
    'password': env.get('ADMIN_PASSWORD') or env.get('admin_password')})
response.raise_for_status()
client.headers['Authorization'] = 'Bearer ' + response.json()['token']

def api(method, path, **kwargs):
    result = client.request(method, path, **kwargs)
    if result.status_code >= 300:
        raise RuntimeError(f'{result.status_code}: {result.text[:800]}')
    return result

state = json.loads(STATE.read_text()) if STATE.exists() else {}
mode = sys.argv[1]
if mode == 'plies':
    for row in api('GET', '/api/plies').json():
        if str(row.get('col_c') or '').split('-')[0].strip().upper().lstrip('R') in ['1847', '1645', '1845', '2020']:
            print({key: row.get(key) for key in ['id', 'col_c', 'col_d']}, flush=True)
elif mode == 'upload':
    for kind, filename, endpoint in [('tech_pack', 'tech-pack-362097-bom.pdf', '/api/documents/upload'),
                                     ('purchase_order', 'purchase-order-362097.pdf', '/api/purchase-orders/upload')]:
        if kind not in state:
            with (ROOT / 'output/pdf' / filename).open('rb') as stream:
                fields = {'tech_pack_id': state['tech_pack']['id']} if kind == 'purchase_order' else {}
                state[kind] = api('POST', endpoint, files={'file': (filename, stream, 'application/pdf')}, data=fields).json()
            STATE.write_text(json.dumps(state, indent=2))
        print(kind, state[kind]['id'], state[kind]['status'], flush=True)
elif mode == 'status':
    for kind, endpoint in [('tech_pack', '/api/documents/'), ('purchase_order', '/api/purchase-orders/')]:
        row = api('GET', endpoint + state[kind]['id']).json()
        (OUT / (kind + '-extraction.json')).write_text(json.dumps(row, indent=2))
        print(kind, row['status'], 'error:', row.get('error'), flush=True)
        if kind == 'tech_pack':
            print('ply_info:', json.dumps(row.get('ply_info')), flush=True)
            extraction = row.get('extraction') or {}
            print('BOM rows:', json.dumps(extraction.get('materials')), flush=True)
        else:
            print('PO:', json.dumps((row.get('extraction') or {}).get('orders')), flush=True)
elif mode == 'correct':
    document = api('GET', '/api/documents/' + state['tech_pack']['id']).json()
    assert document['status'] not in ['queued', 'processing']
    payload = document['extraction']
    payload.pop('materials', None)
    for table in payload['page_tables']:
        unique, seen = [], set()
        for row in table['materials']:
            fingerprint = json.dumps(row, sort_keys=True)
            if fingerprint not in seen:
                unique.append(row)
                seen.add(fingerprint)
        table['materials'] = unique
    assert [row['material_code'] for row in payload['page_tables'][0]['materials']] == ['R1847', 'R1645', 'R1845', 'R2020']
    (OUT / 'corrected-bom.json').write_text(json.dumps(payload, indent=2))
    print(api('PUT', '/api/documents/' + document['id'] + '/extraction', json=payload).json(), flush=True)
    print('Exact repeated extraction rows removed; four physical Wovens rows preserved; approval remains required.', flush=True)
elif mode == 'generate':
    document = api('GET', '/api/documents/' + state['tech_pack']['id']).json()
    po_doc = api('GET', '/api/purchase-orders/' + state['purchase_order']['id']).json()
    assert document['status'] in ['needs_review', 'approved'], document['status']
    assert po_doc['status'] in ['needs_review', 'approved'], po_doc['status']
    materials = document['extraction']['page_tables'][0]['materials']
    assert [row['material_code'] for row in materials] == ['R1847', 'R1645', 'R1845', 'R2020']
    assert [row['quantity'] for row in materials] == ['1.22', '0.34', '0.04', '0.37']
    assert all(row['unit'] == 'm' for row in materials)
    orders = po_doc['extraction']['orders']
    assert len(orders) == 1
    po = orders[0]
    expected_sizes = ['-C32', '-C34', '-C36', '-C38', '-C40', '-C42', '-C44', '-C46', '-C48', '-C50', '-D18', '-D19', '-D20', '-D21', '-D22', '-D23', '-D24', '-D25']
    expected_qty = [40,80,112,112,96,80,48,48,32,32,16,16,16,16,16,16,16,8]
    assert po['contract_number'] == '362097'
    assert [row['size'] for row in po['size_rows']] == expected_sizes
    assert [int(row['quantity']) for row in po['size_rows']] == expected_qty
    assert int(po['total_quantity']) == sum(expected_qty) == 800
    assert po['model_id'] == '7053' and po['quality_id'] == '1847' and po['color_id'] == '9900'
    assert not po.get('tech_pack_reference'), 'The source tech pack reference is blank'
    choices = {}
    # Explicitly supplied by the user for this plan; the master plies table is unchanged.
    overrides = {'R1847': 80}
    for row in materials:
        if row['material_code'] in overrides:
            choices[row['material_code']] = overrides[row['material_code']]
            continue
        info = document.get('ply_info', {}).get(row['material_code'])
        assert info and info.get('max_ply'), f'Missing ply setting for {row["material_code"]}'
        choices[row['material_code']] = info['max_ply']
    payload = {'tech_pack_id': document['id'], 'tech_pack_filename': document['filename'],
        'style_number': document['extraction'].get('style_number'), 'tech_pack_number': document['extraction'].get('tech_pack_number'),
        'table_length_m': '8', 'min_plies': 10, 'time_limit_seconds': 20,
        'orders': [{'label': po['contract_number'], **{key: po.get(key) for key in ['tech_pack_reference','model_id','quality_id','color_id']},
            'source_filename': po_doc['filename'], 'size_rows': [{'size': row['size'], 'quantity': row['quantity']} for row in po['size_rows']]}],
        'materials': [{**{key: row.get(key) for key in ['material_code','description','composition','placement','placement_type','colorways']},
            'page_number': 1, 'consumption': row['quantity'], 'unit': row['unit'], 'max_plies': choices[row['material_code']]} for row in materials]}
    (OUT / 'request.json').write_text(json.dumps(payload, indent=2))
    if 'plan' not in state:
        state['plan'] = api('POST', '/api/marker-plans', json=payload).json()
        STATE.write_text(json.dumps(state, indent=2))
    print('Plan', state['plan']['id'], 'table 8 m, quantities 800, max plies', choices, flush=True)
elif mode == 'finish':
    job = api('GET', '/api/marker-plans/' + state['plan']['id']).json()
    (OUT / 'saved-plan.json').write_text(json.dumps(job, indent=2))
    print('Plan', job['id'], job['status'], job.get('summary'), flush=True)
    for material in job['materials']:
        result = material.get('result')
        print(material['material_code'], material['state'], result and {key: result.get(key) for key in ['status','validated','marker_count','lay_count','message']}, flush=True)
    if job['status'] == 'complete':
        assert job['saved'] and job['summary']['complete']
        assert job['total_quantity'] == 800 and len(job['materials']) == 4
        assert all(entry['result']['validated'] and all(row['difference'] == 0 for row in entry['result']['production']) for entry in job['materials'])
        path = OUT / '362097-marker-plan-8m.xlsx'
        path.write_bytes(api('GET', '/api/marker-plans/' + job['id'] + '/excel').content)
        assert any(row['id'] == job['id'] for row in api('GET', '/api/marker-plans').json())
        print('PASS: four validated materials, exact 800 garments each; saved in history; Excel downloaded.', flush=True)
