import pytest

from core import version


@pytest.mark.parametrize("v,expected", [
    ("1.2.3", (1, 2, 3)),
    ("v1.2.3", (1, 2, 3)),
    ("0.1.0", (0, 1, 0)),
    ("2.0.0-rc1", (2, 0, 0)),
])
def test_parse(v, expected):
    assert version.parse(v) == expected


def test_parse_invalid():
    with pytest.raises(ValueError):
        version.parse("not-a-version")


@pytest.mark.parametrize("a,b,expected", [
    ("1.0.0", "1.0.0", 0),
    ("1.0.1", "1.0.0", 1),
    ("1.0.0", "1.0.1", -1),
    ("2.0.0", "1.9.9", 1),
])
def test_compare(a, b, expected):
    assert version.compare(a, b) == expected
