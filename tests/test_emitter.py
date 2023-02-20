import pytest

from yace.emitters import camelcase

SNAKECASE = ["foo", "foo_bar", "foo_bar_baz"]
PASCALCASE = ["Foo", "FooBar", "FooBarBaz"]
CAMELCASE = ["foo", "fooBar", "fooBarBaz"]


@pytest.mark.parametrize("symbol,expected", zip(SNAKECASE, PASCALCASE))
def test_camelize_pascalcase(symbol, expected):
    assert camelcase(symbol, True) == expected


@pytest.mark.parametrize("symbol,expected", zip(SNAKECASE, CAMELCASE))
def test_camelize_camelcase(symbol, expected):
    assert camelcase(symbol, False) == expected
