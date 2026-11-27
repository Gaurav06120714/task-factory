import click
import pytest

def test_custom_color():
    assert click.custom_color("31") == "\033[31m"
    assert click.custom_color("32") == "\033[32m"
    assert click.custom_color("33") == "\033[33m"
    assert click.custom_color("34") == "\033[34m"
    assert click.custom_color("35") == "\033[35m"
    assert click.custom_color("36") == "\033[36m"
    assert click.custom_color("37") == "\033[37m"

def test_custom_color_invalid():
    with pytest.raises(ValueError):
        click.custom_color("invalid")

def test_custom_color_invalid():
    with pytest.raises(ValueError):
        click.custom_color("invalid")
