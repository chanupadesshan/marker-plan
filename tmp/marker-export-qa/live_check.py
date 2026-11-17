"""Exercise real PostgreSQL persistence and an authenticated workbook download."""
import http.client
import json
import sys
import time
from pathlib import Path
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/marker-plan-test'
settings = dotenv_values(ROOT / '.env')

def api(method, path, body=None, binary=False):
    connection = http.client.HTTPConnection('127.0.0.1', 8000, timeout=30)
    headers = {'Content-Type': 'application/json'}
    if globals().get('token'):
        headers['Authorization'] = 'Bearer ' + token
    connection.request(method, path, json.dumps(body) if body is not None else None, headers)
    response = connection.getresponse()
    data = response.read()
    connection.close()
    if response.status >= 300:
        raise RuntimeError(f'{response.status}: {data.decode()[:500]}')
    return data if binary else json.loads(data)

token = api('POST', '/api/auth/login', {
    'email': settings.get('ADMIN_EMAIL') or settings.get('admin_email'),
    'password': settings.get('ADMIN_PASSWORD') or settings.get('admin_password'),
})['token']
if len(sys.argv) > 1 and sys.argv[1] == 'verify':
    original = json.loads((OUT / 'saved-live-plan.json').read_text())
    restored = api('GET', '/api/marker-plans/' + original['id'])
    assert restored == original, 'Restart changed the saved plan'
    assert any(row['id'] == restored['id'] for row in api('GET', '/api/marker-plans'))
    data = api('GET', '/api/marker-plans/' + restored['id'] + '/excel', binary=True)
    (OUT / '361061-marker-plan.xlsx').write_bytes(data)
    print('PASS: same saved plan, all results and Excel download survive a backend restart.')
    sys.exit()

packs = api('GET', '/api/documents')
pack = next(item for item in packs if item['filename'] == 'tech-pack-two-boms.pdf')
document = api('GET', '/api/documents/' + pack['id'])
po_docs = api('GET', '/api/purchase-orders')
po_doc = next(item for item in po_docs if item['filename'] == 'purchase-orders-two-pos.pdf')
po = next(order for order in api('GET', '/api/purchase-orders/' + po_doc['id'])['extraction']['orders']
          if order['contract_number'] == '361061')
materials = document['extraction']['page_tables'][0]['materials']
payload = {
    'tech_pack_id': pack['id'], 'tech_pack_filename': pack['filename'],
    'style_number': document['extraction'].get('style_number'),
    'orders': [{
        'label': po['contract_number'], 'tech_pack_reference': po['tech_pack_reference'],
        'model_id': po['model_id'], 'quality_id': po['quality_id'], 'color_id': po['color_id'],
        'source_filename': po_doc['filename'],
        'size_rows': [{'size': row['size'], 'quantity': row['quantity']} for row in po['size_rows']],
    }],
    'materials': [{
        **{key: material.get(key) for key in ['material_code', 'description', 'composition', 'placement', 'placement_type', 'colorways']},
        'page_number': 1, 'consumption': material['quantity'], 'unit': material['unit'], 'max_plies': maximum,
    } for material, maximum in zip(materials, [70, 30, 30, 30])],
    'table_length_m': '8', 'min_plies': 10, 'time_limit_seconds': 20,
}
job = api('POST', '/api/marker-plans', payload)
print('Saved job:', job['id'], flush=True)
for _ in range(100):
    job = api('GET', '/api/marker-plans/' + job['id'])
    if job['status'] == 'complete':
        break
    time.sleep(2)
assert job['summary']['complete'] and job['saved']
assert job['total_quantity'] == 504
for material in job['materials']:
    assert all(row['difference'] == 0 for row in material['result']['production'])
    print(material['marker_prefix'], material['material_code'], material['result']['marker_count'],
          'markers;', [lay['plies'] for lay in material['result']['lays']], 'plies')
OUT.mkdir(parents=True, exist_ok=True)
(OUT / 'saved-live-plan.json').write_text(json.dumps(job, indent=2))
(OUT / '361061-marker-plan.xlsx').write_bytes(api('GET', '/api/marker-plans/' + job['id'] + '/excel', binary=True))
print('PASS: generated, saved and downloaded the four-material plan; 504 garments per material.')
