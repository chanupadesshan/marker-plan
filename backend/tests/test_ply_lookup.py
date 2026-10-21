from types import SimpleNamespace
from uuid import uuid4
import pytest
from app import main
from app.models import Ply
from app.ply_lookup import base_code, material_codes, max_ply, ply_info_for


class FakeSession:
    """A stand-in session that returns the given plies rows, or fails like a missing table."""
    def __init__(self, plies=(), fail=False):
        self.plies, self.fail, self.rolled_back = list(plies), fail, False

    def scalars(self, *args, **kwargs):
        if self.fail:
            raise RuntimeError('relation "plies" does not exist')
        return SimpleNamespace(all=lambda: self.plies)

    def rollback(self): self.rolled_back = True


def ply(id, col_c, col_d):
    return Ply(id=id, col_b=1, col_c=col_c, col_d=col_d)


@pytest.mark.parametrize('value,expected', [
    ('R1371', '1371'), ('1371', '1371'), (' r1371 ', '1371'), ('R1936-9800', '1936'), ('1936-9800', '1936'),
    ('F0717', 'F0717'), ('R', 'R'), ('RX12', 'RX12'), ('', ''), (None, '')])
def test_base_code_ignores_a_leading_r_case_and_colour_suffix(value, expected):
    assert base_code(value) == expected


@pytest.mark.parametrize('value,expected', [
    ('80', 80), ('70-75', 75), ('90-100', 100), ('30-35', 35), (' 40 ', 40), ('12.5', 12.5), ('60-12,5', 60),
    ('', None), (None, None), ('n/a', None)])
def test_max_ply_is_the_upper_end_of_a_value_or_range(value, expected):
    assert max_ply(value) == expected


def test_material_codes_come_from_the_combined_list_and_the_page_tables():
    extraction = {'materials': [{'material_code': 'R1'}, {'material_code': None}],
                  'page_tables': [{'materials': [{'material_code': 'R2'}, {'material_code': 'R1'}]}, {'materials': []}]}
    assert material_codes(extraction) == {'R1', 'R2'}
    assert material_codes({}) == set()


def test_a_material_matches_every_related_row_and_takes_the_largest_ply():
    session = FakeSession([ply(1, '1936', '50-60'), ply(2, 'R1936-9800', '80'), ply(3, 'R1936-9800', '60'),
                           ply(4, '1371', '70-75'), ply(5, '2020', '130')])
    info = ply_info_for(session, {'materials': [{'material_code': 'R1936'}, {'material_code': 'R1371'}]})
    assert info['R1936']['max_ply'] == 80
    assert [m['id'] for m in info['R1936']['matches']] == [1, 2, 3]
    assert info['R1371'] == {'max_ply': 75, 'matches': [{'id': 4, 'col_c': '1371', 'col_d': '70-75'}]}


def test_materials_without_a_related_row_are_left_out_so_the_screen_shows_a_dash():
    session = FakeSession([ply(1, '1371', '70-75')])
    assert ply_info_for(session, {'materials': [{'material_code': 'R9999'}]}) == {}


def test_a_related_row_without_a_column_d_value_gives_no_maximum_but_is_still_listed():
    info = ply_info_for(FakeSession([ply(1, '1342', None)]), {'materials': [{'material_code': 'R1342'}]})
    assert info['R1342']['max_ply'] is None and len(info['R1342']['matches']) == 1


def test_an_empty_extraction_does_no_lookup():
    assert ply_info_for(FakeSession(fail=True), {}) == {}
    assert ply_info_for(FakeSession(fail=True), None) == {}


def test_a_failing_plies_lookup_never_breaks_the_tech_pack(monkeypatch):
    session = FakeSession(fail=True)
    assert ply_info_for(session, {'materials': [{'material_code': 'R1371'}]}) == {}
    assert session.rolled_back


def test_the_tech_pack_response_carries_ply_info_outside_the_extraction(monkeypatch):
    doc_id = uuid4()
    extraction = SimpleNamespace(extracted_json={'materials': [{'material_code': 'R1371'}], 'request_usage': []}, model_name='m')
    row = SimpleNamespace(id=doc_id, original_filename='tp.pdf', status='needs_review', error_message=None, page_count=1,
                          selected_pages=[1], created_at=None, extraction=extraction)

    class Session(FakeSession):
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, model, key): return row if key == doc_id else None

    monkeypatch.setattr(main, 'SessionLocal', lambda: Session([ply(4, '1371', '70-75')]))
    result = main.get_document(doc_id)
    assert result['ply_info']['R1371']['max_ply'] == 75
    assert 'ply_info' not in result['extraction'] and 'max_ply' not in str(result['extraction'])
