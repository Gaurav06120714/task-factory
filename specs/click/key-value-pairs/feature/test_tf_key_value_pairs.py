"""Tests for click.KeyValuePairs. Inputs chosen by the generator; expected values recorded
from the reference implementation."""
import re

import pytest

import click


def test_normal_use():
    assert repr(click.KeyValuePairs().convert('key1=value1,key2=value2', None, None)) == "[('key1', 'value1'), ('key2', 'value2')]"

def test_empty_string():
    with pytest.raises(click.BadParameter, match=re.escape("'' is not a valid KEY=VALUE pair.")):
        click.KeyValuePairs().convert('', None, None)

def test_single_pair():
    assert repr(click.KeyValuePairs().convert('key=value', None, None)) == "[('key', 'value')]"

def test_multiple_pairs():
    assert repr(click.KeyValuePairs().convert('key1=value1,key2=value2,key3=value3', None, None)) == "[('key1', 'value1'), ('key2', 'value2'), ('key3', 'value3')]"

def test_trailing_comma():
    with pytest.raises(click.BadParameter, match=re.escape("'key1=value1,' is not a valid KEY=VALUE pair.")):
        click.KeyValuePairs().convert('key1=value1,', None, None)

def test_leading_comma():
    with pytest.raises(click.BadParameter, match=re.escape("',key1=value1' is not a valid KEY=VALUE pair.")):
        click.KeyValuePairs().convert(',key1=value1', None, None)

def test_multiple_delimiters():
    assert repr(click.KeyValuePairs(delimiter=':').convert('key1:value1,key2:value2', None, None)) == "[('key1', 'value1'), ('key2', 'value2')]"

def test_whitespace_around_delimiter():
    assert repr(click.KeyValuePairs().convert('key1 = value1, key2 = value2', None, None)) == "[('key1', 'value1'), ('key2', 'value2')]"

def test_missing_value():
    with pytest.raises(click.BadParameter, match=re.escape("'key1,key2=value2' is not a valid KEY=VALUE pair.")):
        click.KeyValuePairs().convert('key1,key2=value2', None, None)

def test_extra_value():
    with pytest.raises(click.BadParameter, match=re.escape("'key1=value1,key2=value2=value3' is not a valid KEY=VALUE pair.")):
        click.KeyValuePairs().convert('key1=value1,key2=value2=value3', None, None)

def test_non_string_input():
    with pytest.raises(click.BadParameter, match=re.escape('123 is not a valid string of KEY=VALUE pairs.')):
        click.KeyValuePairs().convert(123, None, None)

def test_invalid_delimiter():
    with pytest.raises(ValueError, match=re.escape('empty separator')):
        click.KeyValuePairs(delimiter='').convert('key1=value1', None, None)

def test_unicode_key():
    assert repr(click.KeyValuePairs().convert('keyé=value1', None, None)) == "[('keyé', 'value1')]"

def test_unicode_value():
    assert repr(click.KeyValuePairs().convert('key1=évalue', None, None)) == "[('key1', 'évalue')]"

def test_non_ascii_delimiter():
    with pytest.raises(click.BadParameter, match=re.escape("'key1=value1' is not a valid KEY=VALUE pair.")):
        click.KeyValuePairs(delimiter='é').convert('key1=value1', None, None)
