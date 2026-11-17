from test_marker_plan import client, body


def nesting(**changes):
    value = {'label': 'Verified four-set marker', 'length_m': '7.30', 'verified': True,
             'width_cm': '148', 'efficiency_percent': '91.35',
             'size_rows': [{'size': 'S', 'quantity': 2}, {'size': 'M', 'quantity': 2}]}
    value.update(changes)
    return value


def payload():
    return body(orders=[{'label': 'Test', 'size_rows': [{'size': 'S', 'quantity': '40'}, {'size': 'M', 'quantity': '40'}]}],
                materials=[{'material_code': 'R1310', 'consumption': '2.09', 'max_plies': 75,
                            'nesting_markers': [nesting()]}])


def test_verified_pattern_uses_actual_length_instead_of_bom_capacity(client):
    response = client.post('/api/marker-plans', json=payload())
    assert response.status_code == 202
    job = client.get('/api/marker-plans/' + response.json()['id']).json()
    material = job['materials'][0]
    assert material['capacity'] == 4 and material['capacity_basis'] == 'verified_nesting'
    result = material['result']
    assert result['validated'] and result['marker_count'] == 1
    assert all(lay['counts'] == [2,2] for lay in result['lays'])
    assert result['markers'][0]['length_m'] == '7.30'
    assert not result['one_marker_shortcut']
    assert result['optimization_scope'] == 'verified_nesting_catalogue'
    from test_marker_plan_excel import sheet_cells
    excel = client.get('/api/marker-plans/' + job['id'] + '/excel')
    assert excel.status_code == 200
    cells, _ = sheet_cells(excel.content)
    assert float(cells['C12'][0]) == 730
    assert float(cells['B12'][0]) == 148
    assert float(cells['E12'][0]) == 91.35
    assert float(cells['U12'][0]) == 146


def test_unverified_overlength_unknown_size_or_fractional_ratio_is_rejected(client):
    for changes in [{'verified': False}, {'length_m': '8.01'},
                    {'size_rows': [{'size': 'Unknown', 'quantity': 1}]},
                    {'size_rows': [{'size': 'S', 'quantity': '1.5'}]}]:
        data = payload()
        data['materials'][0]['nesting_markers'] = [nesting(**changes)]
        assert client.post('/api/marker-plans', json=data).status_code == 422


def test_catalogue_is_a_whitelist_and_does_not_enable_other_four_set_ratios(client):
    data = payload()
    data['orders'][0]['size_rows'][0]['quantity'] = '42'
    response = client.post('/api/marker-plans', json=data)
    job = client.get('/api/marker-plans/' + response.json()['id']).json()
    assert not job['summary']['complete']
    assert job['materials'][0]['result']['status'] == 'INFEASIBLE'


def test_legacy_capacity_stays_consumption_based(client):
    data = payload(); del data['materials'][0]['nesting_markers']
    response = client.post('/api/marker-plans', json=data)
    job = client.get('/api/marker-plans/' + response.json()['id']).json()
    assert job['materials'][0]['capacity'] == 3
