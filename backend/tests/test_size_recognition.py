import pytest

from app.services.fashion_sizes import normalize_size
from app.services.integrations.import_transforms import size_codes


@pytest.mark.parametrize(('raw', 'expected'), [
    ('1X', 'XL'), ('2X', 'XXL'), ('3x', '3XL'), ('4X', '4XL'),
    ('5 X', '5XL'), ('6X', '6XL'), ('FR', 'FREE'), ('fre', 'FREE'),
])
def test_confirmed_retail_aliases(raw, expected):
    assert normalize_size(raw) == expected


def test_import_recognises_numeric_and_range_meanings_without_letter_guess():
    codes = {c['code']: c for c in size_codes(['32', 'S TO XXL', 'STO2XL', '0M', '00M', '1T4'])}
    assert codes['32']['meaning'] == 'Numeric clothing size: 32'
    assert codes['S TO XXL']['meaning'] == 'Size range: S to XXL'
    assert codes['STO2XL']['meaning'] == 'Size range: S to XXL'
    for code in codes.values():
        assert code['suggestion'] is None
    assert codes['0M']['meaning'] == 'Source-specific code — review required'


def test_apply_uses_aliases_keeps_identity_and_honours_blank_override():
    from types import SimpleNamespace
    from app.services.integrations.smart_import import _apply

    table = SimpleNamespace(exclusions=[], row_numbers=[2, 3], records=[
        {'id': 'A', 'desc': 'BRAND - STYLE - RED - 2X'},
        {'id': 'B', 'desc': 'BRAND - STYLE - BLUE - FR'},
    ])
    decision = {'mapping': {'sku': 'id', 'description': 'desc'},
                'transforms': {'parse_variant': True, 'group_pieces': False}, 'size_map': {'FR': ''}}
    records, *_ = _apply(table, decision, ['id'])
    assert records[0]['x_size'] == 'XXL'
    assert records[0]['x_size_code'] == '2X'
    assert records[1]['x_size'] is None
    assert records[1]['x_size_code'] == 'FR'
