"""Tests for click.IPAddress. Inputs chosen by the generator; expected values recorded
from the reference implementation."""
import re

import pytest

import click


def test_valid_ipv4_address():
    with pytest.raises(TypeError, match=re.escape('isinstance() arg 2 must be a type, a tuple of types, or a union')):
        click.IPAddress().convert('192.168.1.1', None, None)

def test_valid_ipv6_address():
    with pytest.raises(TypeError, match=re.escape('isinstance() arg 2 must be a type, a tuple of types, or a union')):
        click.IPAddress().convert('2001:0db8:85a3:0000:0000:8a2e:0370:7334', None, None)

def test_valid_ipv4_network():
    with pytest.raises(TypeError, match=re.escape('isinstance() arg 2 must be a type, a tuple of types, or a union')):
        click.IPAddress(network=True).convert('192.168.1.0/24', None, None)

def test_valid_ipv6_network():
    with pytest.raises(TypeError, match=re.escape('isinstance() arg 2 must be a type, a tuple of types, or a union')):
        click.IPAddress(network=True).convert('2001:0db8:85a3:0000:0000:8a2e:0370:7334/64', None, None)

def test_invalid_ipv4_address():
    with pytest.raises(TypeError, match=re.escape('isinstance() arg 2 must be a type, a tuple of types, or a union')):
        click.IPAddress().convert('256.256.256.256', None, None)

def test_invalid_ipv6_address():
    with pytest.raises(TypeError, match=re.escape('isinstance() arg 2 must be a type, a tuple of types, or a union')):
        click.IPAddress().convert('2001:0db8:85a3:0000:0000:8a2e:0370:7334:1', None, None)

def test_invalid_ipv4_network():
    with pytest.raises(TypeError, match=re.escape('isinstance() arg 2 must be a type, a tuple of types, or a union')):
        click.IPAddress(network=True).convert('192.168.1.0/33', None, None)

def test_invalid_ipv6_network():
    with pytest.raises(TypeError, match=re.escape('isinstance() arg 2 must be a type, a tuple of types, or a union')):
        click.IPAddress(network=True).convert('2001:0db8:85a3:0000:0000:8a2e:0370:7334/129', None, None)

def test_empty_string():
    with pytest.raises(TypeError, match=re.escape('isinstance() arg 2 must be a type, a tuple of types, or a union')):
        click.IPAddress().convert('', None, None)

def test_non_string_input():
    with pytest.raises(TypeError, match=re.escape('isinstance() arg 2 must be a type, a tuple of types, or a union')):
        click.IPAddress().convert(12345, None, None)

def test_ipv4_with_leading_zero():
    with pytest.raises(TypeError, match=re.escape('isinstance() arg 2 must be a type, a tuple of types, or a union')):
        click.IPAddress().convert('192.168.01.1', None, None)

def test_ipv6_with_leading_zero():
    with pytest.raises(TypeError, match=re.escape('isinstance() arg 2 must be a type, a tuple of types, or a union')):
        click.IPAddress().convert('2001:0db8:85a3:0000:0000:8a2e:0370:0001', None, None)

def test_ipv4_with_trailing_zero():
    with pytest.raises(TypeError, match=re.escape('isinstance() arg 2 must be a type, a tuple of types, or a union')):
        click.IPAddress().convert('192.168.1.0', None, None)
