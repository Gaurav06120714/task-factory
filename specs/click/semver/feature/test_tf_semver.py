"""Tests for click.SemVer. Inputs chosen by the generator; expected values recorded
from the reference implementation."""
import re

import pytest

import click


def test_valid_version():
    assert repr(click.SemVer().convert('1.2.3', None, None)) == "'1.2.3'"

def test_valid_version_with_pre_release():
    assert repr(click.SemVer().convert('1.2.3-rc.1', None, None)) == "'1.2.3-rc.1'"

def test_valid_version_with_build():
    assert repr(click.SemVer().convert('1.2.3+build.1', None, None)) == "'1.2.3+build.1'"

def test_valid_version_with_pre_release_and_build():
    assert repr(click.SemVer().convert('1.2.3-rc.1+build.1', None, None)) == "'1.2.3-rc.1+build.1'"

def test_invalid_version_format():
    with pytest.raises(click.BadParameter, match=re.escape("'1.2' is not a valid semantic version.")):
        click.SemVer().convert('1.2', None, None)

def test_invalid_pre_release_format():
    assert repr(click.SemVer().convert('1.2.3-invalid', None, None)) == "'1.2.3-invalid'"

def test_invalid_build_format():
    assert repr(click.SemVer().convert('1.2.3+invalid', None, None)) == "'1.2.3+invalid'"

def test_version_outside_min_range():
    with pytest.raises(click.BadParameter, match=re.escape("'1.2.3' is not in the range 1.2.4 to -.")):
        click.SemVer(min='1.2.4').convert('1.2.3', None, None)

def test_version_outside_max_range():
    with pytest.raises(click.BadParameter, match=re.escape("'1.2.3' is not in the range - to 1.2.2.")):
        click.SemVer(max='1.2.2').convert('1.2.3', None, None)

def test_version_at_min_range():
    assert repr(click.SemVer(min='1.2.3').convert('1.2.3', None, None)) == "'1.2.3'"

def test_version_at_max_range():
    assert repr(click.SemVer(max='1.2.3').convert('1.2.3', None, None)) == "'1.2.3'"

def test_empty_string():
    with pytest.raises(click.BadParameter, match=re.escape("'' is not a valid semantic version.")):
        click.SemVer().convert('', None, None)

def test_none_value():
    with pytest.raises(click.BadParameter, match=re.escape('None is not a valid semantic version.')):
        click.SemVer().convert(None, None, None)

def test_non_string_value():
    with pytest.raises(click.BadParameter, match=re.escape('123 is not a valid semantic version.')):
        click.SemVer().convert(123, None, None)
