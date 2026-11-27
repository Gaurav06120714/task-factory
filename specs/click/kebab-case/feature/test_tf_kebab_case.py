"""Tests for click.KebabCase. Inputs chosen by the generator; expected values recorded
from the reference implementation."""
import re

import pytest

import click


def test_normal_use():
    assert repr(click.KebabCase().convert('apple,banana,cherry', None, None)) == "'apple-banana-cherry'"

def test_empty_input():
    assert repr(click.KebabCase().convert('', None, None)) == "''"

def test_non_string_input():
    with pytest.raises(click.BadParameter, match=re.escape('123 is not a valid string.')):
        click.KebabCase().convert(123, None, None)

def test_min_boundry():
    assert repr(click.KebabCase(min=3).convert('apple,banana,cherry', None, None)) == "'apple-banana-cherry'"

def test_max_boundry():
    assert repr(click.KebabCase(max=3).convert('apple,banana,cherry', None, None)) == "'apple-banana-cherry'"

def test_min_violation():
    with pytest.raises(click.BadParameter, match=re.escape("'apple,banana,cherry' does not have the correct number of items. Expected 4 to -.")):
        click.KebabCase(min=4).convert('apple,banana,cherry', None, None)

def test_max_violation():
    with pytest.raises(click.BadParameter, match=re.escape("'apple,banana,cherry' does not have the correct number of items. Expected - to 2.")):
        click.KebabCase(max=2).convert('apple,banana,cherry', None, None)

def test_leading_space():
    assert repr(click.KebabCase().convert(' apple,banana,cherry', None, None)) == "'apple-banana-cherry'"

def test_trailing_space():
    assert repr(click.KebabCase().convert('apple,banana,cherry ', None, None)) == "'apple-banana-cherry'"

def test_multiple_spaces():
    assert repr(click.KebabCase().convert('apple,  banana,  cherry', None, None)) == "'apple-banana-cherry'"

def test_empty_item():
    assert repr(click.KebabCase().convert('apple,,banana', None, None)) == "'apple-banana'"

def test_single_item():
    assert repr(click.KebabCase().convert('apple', None, None)) == "'apple'"

def test_all_uppercase():
    assert repr(click.KebabCase().convert('APPLE,BANANA,CHERRY', None, None)) == "'apple-banana-cherry'"

def test_mixed_case():
    assert repr(click.KebabCase().convert('ApPle,BaNaNa,ChErRy', None, None)) == "'apple-banana-cherry'"
