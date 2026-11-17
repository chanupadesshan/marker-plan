"""Compare the running marker-plan API against the supplied reference workbook."""
import http.client
import json
import time
from pathlib import Path
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/marker-plan-test'
reference = json.loads((OUT / 'reference.json').read_text())
po = json.loads((ROOT / 'output/pdf/purchase_order-extraction.json').read_text())['extraction']['orders'][0]
bom = json.loads((ROOT / 'output/pdf/tech_pack-extraction.json').read_text())['extraction']['page_tables'][0]['materials']
normalize = lambda size: size.strip().lstrip('-').upper()
assert [normalize(row['size']) for row in po['size_rows']] == reference['sizes']
assert [int(row['quantity']) for row in po['size_rows']] == reference['quantities']
settings = dotenv_values(ROOT / '.env')

def request(method, path, body=None, token=None):
    connection = http.client.HTTPConnection('127.0.0.1', 8000, timeout=30)
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    connection.request(method, path, json.dumps(body) if body is not None else None, headers)
    response = connection.getresponse()
    result = json.loads(response.read())
    connection.close()
    assert response.status < 300, (response.status, result)
    return result

token = request('POST', '/api/auth/login', {
    'email': settings.get('ADMIN_EMAIL') or settings.get('admin_email'),
    'password': settings.get('ADMIN_PASSWORD') or settings.get('admin_password'),
})['token']
payload = {
    'orders': [{'label': po['contract_number'], 'size_rows': [
        {'size': row['size'], 'quantity': row['quantity']} for row in po['size_rows']]}],
    'materials': [{
        'material_code': material['material_code'], 'description': material['description'],
        'placement': material['placement'], 'page_number': 1,
        'consumption': material['quantity'], 'unit': material['unit'],
        'max_plies': expected['max_plies'],
    } for material, expected in zip(bom, reference['materials'])],
    'table_length_m': '8', 'min_plies': 10, 'time_limit_seconds': 20,
}
(OUT / 'request.json').write_text(json.dumps(payload, indent=2))
job = request('POST', '/api/marker-plans', payload, token)
print('Job:', job['id'], flush=True)
for _ in range(120):
    job = request('GET', '/api/marker-plans/' + job['id'], token=token)
    (OUT / 'actual.json').write_text(json.dumps(job, indent=2))
    if job['status'] == 'complete':
        break
    time.sleep(2)
assert job['status'] == 'complete', 'Planner did not complete within 240 seconds'
comparisons = []
for expected, actual in zip(reference['materials'], job['materials']):
    result = actual['result']
    ref_lays = [(tuple(lay['marker']), lay['plies']) for lay in expected['lays']]
    actual_lays = [(tuple(lay['counts']), lay['plies']) for lay in result['lays']]
    reference_production = [sum(marker[i] * plies for marker, plies in ref_lays) for i in range(11)]
    assert reference_production == reference['quantities'], 'Reference does not meet order quantities'
    record = {
        'material': expected['name'], 'capacity_matches': actual['capacity'] == expected['capacity'],
        'status': result['status'], 'validated': result['validated'],
        'expected_markers': len(set(marker for marker, _ in ref_lays)),
        'actual_markers': result['marker_count'],
        'expected_lays': len(ref_lays), 'actual_lays': result['lay_count'],
        'exact_lay_sequence_matches': actual_lays == ref_lays,
        'same_combinations_and_plies': sorted(actual_lays) == sorted(ref_lays),
        'quantities_match': [row['produced'] for row in result['production']] == reference['quantities'],
        'expected_plies': [plies for _, plies in ref_lays],
        'actual_plies': [plies for _, plies in actual_lays],
        'expected_lay_details': expected['lays'], 'actual_lay_details': result['lays'],
    }
    comparisons.append(record)
    print(json.dumps({k: v for k, v in record.items() if not k.endswith('details')}), flush=True)
(OUT / 'comparison.json').write_text(json.dumps(comparisons, indent=2))
print('ALL EXACT:', all(row['exact_lay_sequence_matches'] for row in comparisons), flush=True)
