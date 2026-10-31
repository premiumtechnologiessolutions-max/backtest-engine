"""Frozen research API request parsing must be unambiguous and finite."""
import pytest

from scripts.quantlab_desktop import decode_request_json


@pytest.mark.parametrize("payload", [
    b'{"year":2012,"year":2013}',
    b'{"year":2012,"grid":{"fast":[8],"fast":[9]}}',
    b'{"grid":{"fast":[1e999]}}',
    b'{"grid":{"fast":[-1e999]}}',
    b'{"grid":{"fast":[NaN]}}',
    b'{"grid":{"fast":[Infinity]}}',
    b'\xff',
    b'{"year":2012',
])
def test_rejects_ambiguous_invalid_or_nonfinite_json(payload):
    with pytest.raises(ValueError):
        decode_request_json(payload)


def test_accepts_valid_nested_finite_request():
    obj = decode_request_json(b'{"year":2012,"grid":{"fast":[8,9],"rr":[1.5]}}')
    assert obj == {"year": 2012, "grid": {"fast": [8, 9], "rr": [1.5]}}
