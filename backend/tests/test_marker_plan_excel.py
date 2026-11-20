"""Inspect real XLSX cells, cached formulas and the requested single-sheet material groups."""
from io import BytesIO
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from test_marker_plan import client, body
from copy import deepcopy


def test_repeated_marker_lays_export_one_grouped_row_without_changing_snapshot(client):
    from app.marker_plan_excel import build_marker_plan_excel
    payload = body(orders=[{'label': 'A', 'size_rows': [{'size': 'S', 'quantity': '330'}]}],
                   materials=[{'material_code': 'R1', 'consumption': '2', 'max_plies': 75}])
    job, _ = export(client, payload)
    # A known valid plan: one ratio, five lays, and total plies above the per-lay limit.
    job['materials'][0]['result']['lays'] = [
        {'number': i + 1, 'marker_id': 'B01-M01', 'counts': [1], 'plies': plies, 'sets': plies}
        for i, plies in enumerate([75, 75, 75, 75, 30])]
    before = deepcopy(job)
    cells, _ = sheet_cells(build_marker_plan_excel(job))
    rows = [(address, value) for address, (value, _) in cells.items()
            if address.startswith('A') and address[1:].isdigit() and isinstance(value, str) and 'B01-M01' in value]
    assert len(rows) == 1
    row = int(rows[0][0][1:])
    assert int(cells[f'S{row}'][0]) == 330
    assert int(cells[f'T{row}'][0]) == 330
    assert int(cells[f'W{row}'][0]) == 5
    assert cells[f'X{row}'][0] == 'L1: 75; L2: 75; L3: 75; L4: 75; L5: 30'
    assert job == before

NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def sheet_cells(payload):
    with ZipFile(BytesIO(payload)) as archive:
        strings = [''.join(node.itertext()) for node in ET.fromstring(archive.read('xl/sharedStrings.xml'))]
        sheet = ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
        cells = {}
        for cell in sheet.findall('.//s:sheetData/s:row/s:c', NS):
            value = cell.find('s:v', NS)
            text = value.text if value is not None else None
            if cell.attrib.get('t') == 's' and text is not None:
                text = strings[int(text)]
            cells[cell.attrib['r']] = (text, cell.findtext('s:f', default=None, namespaces=NS))
        return cells, sheet


def export(client, payload=None):
    created = client.post('/api/marker-plans', json=payload or body()).json()
    job = client.get(f"/api/marker-plans/{created['id']}").json()
    response = client.get(f"/api/marker-plans/{created['id']}/excel")
    assert response.status_code == 200, response.text
    return job, response


def marker_rows(cells, markers):
    return sorted(int(address[1:]) for address, (value, _) in cells.items()
                  if address.startswith('A') and address[1:].isdigit() and isinstance(value, str)
                  and any(value.endswith("-" + marker["marker_id"]) for marker in markers))


def test_single_material_formula_caches_and_unknown_nesting_fields(client):
    job, response = export(client)
    assert response.headers['content-type'].startswith('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    cells, sheet = sheet_cells(response.content)
    from app.marker_plan_excel import grouped_markers
    markers = grouped_markers(job['materials'][0]['result']['lays'])
    rows = marker_rows(cells, markers)
    assert len(rows) == len(markers)
    for row, lay in zip(rows, markers):
        assert [int(cells[f'{column}{row}'][0] or 0) for column in 'FGH'] == lay['counts']
        assert int(cells[f'S{row}'][0]) == lay['plies']
        assert cells[f'T{row}'] == (str(sum(lay['counts']) * lay['plies']), f'R{row}*S{row}')
        assert all(cells.get(f'{col}{row}', (None, None))[0] in (None, '') for col in 'BCDEUV')
    total = next(int(a[1:]) for a, (v, _) in cells.items() if a.startswith('A') and v == 'TOTAL CUT')
    assert int(cells[f'T{total}'][0]) == 800
    assert sheet.find('s:pageSetup', NS).attrib['orientation'] == 'landscape'


def test_one_sheet_has_separate_groups_and_material_plies_columns(client):
    materials = [
        {'material_code': 'R1514', 'description': 'Main', 'placement': 'Body', 'consumption': '2', 'max_plies': 120,
         'colorways': [{'code': '8933', 'material_color_code': '8904', 'material_color_name': 'Navy'}]},
        {'material_code': 'R1514', 'description': 'Contrast', 'placement': 'Visibility', 'consumption': '0.2', 'max_plies': 120,
         'colorways': [{'code': '8933', 'material_color_code': '3300', 'material_color_name': 'HV yellow'}]},
    ]
    job, response = export(client, body(materials=materials))
    with ZipFile(BytesIO(response.content)) as archive:
        names = [n.attrib['name'] for n in ET.fromstring(archive.read('xl/workbook.xml')).find('s:sheets', NS)]
        assert names == ['Marker plan']
    cells, _ = sheet_cells(response.content)
    assert {'1514-8904', '1514-3300'} <= {v for v, _ in cells.values()}
    previous = 0
    for index, entry in enumerate(job['materials']):
        from app.marker_plan_excel import grouped_markers
        markers = grouped_markers(entry['result']['lays']); rows = marker_rows(cells, markers)
        assert len(rows) == len(markers) and min(rows) > previous
        if previous:
            assert min(rows) - previous >= 3
        for row, lay in zip(rows, markers):
            assert int(cells[f'{"ST"[index]}{row}'][0]) == lay['plies']
            assert cells.get(f'{"TS"[index]}{row}', (None, None))[0] is None
            assert int(cells[f'{"UX"[index]}{row}'][0]) == sum(lay['counts']) * lay['plies']
            assert int(cells[f'{"XU"[index]}{row}'][0]) == 0
        previous = max(rows)
    total = next(int(a[1:]) for a, (v, _) in cells.items() if a.startswith('A') and v == 'TOTAL CUT')
    assert int(cells[f'U{total}'][0]) == int(cells[f'X{total}'][0]) == 800
    remaining = [int(a[1:]) for a, (v, _) in cells.items() if a.startswith('E') and v in ('1514-8904', '1514-3300') and int(a[1:]) > total]
    assert len(remaining) == 2
    assert all(int(cells[f'{col}{row}'][0]) == 0 for row in remaining for col in 'FGH')


def test_screenshot_palette_is_present(client):
    _, response = export(client, body(materials=[{'consumption': '2', 'max_plies': 120}] * 4))
    with ZipFile(BytesIO(response.content)) as archive:
        styles = ET.fromstring(archive.read('xl/styles.xml'))
        colors = {n.attrib.get('rgb', '')[-6:] for n in styles.findall('.//s:fills/s:fill/s:patternFill/s:fgColor', NS)}
    assert {'DAEEF3', 'DDD9C4', 'FCD5B4', 'B8CCE4', 'D8E4BC', 'B1A0C7', 'FDE9D9', 'FABF8F', 'FFC000', '92D050'} <= colors


def test_untrusted_order_and_material_text_is_literal(client):
    payload = body(materials=[{'material_code': 'A' * 26 + "'Z", 'description': '=1+1', 'consumption': '2', 'max_plies': 120}])
    payload['orders'][0]['label'] = '=HYPERLINK("https://example.invalid")'
    _, response = export(client, payload); cells, _ = sheet_cells(response.content)
    assert any(v == payload['orders'][0]['label'] and f is None for v, f in cells.values())


def test_multiple_orders_preserve_grouped_and_zero_quantities(client):
    orders = [{'label': 'A', 'size_rows': [{'size': 'S', 'quantity': '1 000'}, {'size': 'M', 'quantity': '0'}]},
              {'label': 'B', 'size_rows': [{'size': ' s ', 'quantity': '20.0'}, {'size': 'M', 'quantity': '20'}]}]
    _, response = export(client, body(orders=orders, materials=[{'material_code': 'R1', 'consumption': '0.1', 'max_plies': 120}]))
    cells, _ = sheet_cells(response.content)
    assert [int(cells[ref][0]) for ref in ['F4', 'G4', 'F5', 'G5']] == [1000, 0, 20, 20]


def test_pending_failed_and_unsaved_plans_cannot_be_exported(client, monkeypatch):
    from app import marker_plan_routes
    monkeypatch.setattr(marker_plan_routes, 'submit', lambda *args: None)
    pending = client.post('/api/marker-plans', json=body()).json()
    assert client.get(f"/api/marker-plans/{pending['id']}/excel").status_code == 409
    bad = client.post('/api/marker-plans', json=body(materials=[{'consumption': '9', 'max_plies': 100}])).json()
    marker_plan_routes.run_job(bad['id'])
    assert client.get(f"/api/marker-plans/{bad['id']}/excel").status_code == 409


def test_excel_survives_cache_loss(client):
    from app import marker_plan_routes
    job, first = export(client); marker_plan_routes._jobs.clear()
    second = client.get(f"/api/marker-plans/{job['id']}/excel")
    assert second.status_code == 200 and sheet_cells(first.content)[0] == sheet_cells(second.content)[0]


def test_export_permissions(client):
    from types import SimpleNamespace
    from app.auth import require_user
    from app.main import app
    from fastapi.testclient import TestClient
    protected = TestClient(app)
    path = '/api/marker-plans/00000000-0000-0000-0000-000000000000/excel'
    assert protected.get(path).status_code == 401
    app.dependency_overrides[require_user] = lambda: SimpleNamespace(is_admin=False, permissions={})
    try:
        assert protected.get(path).status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_summary_by_material_has_totals_and_consumption_formulas(client):
    job, response = export(client)
    cells, _ = sheet_cells(response.content)
    summary = next(int(a[1:]) for a, (v, _) in cells.items() if a.startswith('A') and v == 'SUMMARY BY MATERIAL')
    total = next(int(a[1:]) for a, (v, _) in cells.items() if a.startswith('A') and v == 'TOTAL CUT')
    row = summary + 1
    assert cells[f'F{row}'] == ('800', f'T{total}')
    assert cells[f'H{row}'][1] == f'U{total}'
    assert cells[f'J{row}'][1] == f'V{total}'
    assert cells[f'L{row}'][1] == f'IF(AND(ISNUMBER(U{total}),N(T{total})>0),U{total}/T{total},"")'
    assert cells[f'N{row}'][1] == f'IF(AND(ISNUMBER(V{total}),N(T{total})>0),V{total}/T{total},"")'
    assert any(v and 'PREPARED BY' in v for v, _ in cells.values())
