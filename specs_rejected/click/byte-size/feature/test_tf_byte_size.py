import pytest

import click
from click.testing import CliRunner


def make_cli(param_type):
    @click.command()
    @click.option("--size", type=param_type)
    def cli(size):
        click.echo(repr(size))

    return cli




@pytest.mark.parametrize(
    "raw", ["", "abc", "1.5Kb", "-5", "30K1M", "1K1K", "1W", "1K 30K", "K"]
)
def test_invalid_values(raw):
    result = CliRunner().invoke(make_cli(click.ByteSize()), ["--size", raw])
    assert result.exit_code == 2
    assert f"{raw!r} is not a valid byte size." in result.output


def test_int_passthrough():
    value = 1024
    assert click.ByteSize().convert(value, None, None) is value


def test_cli_converts_to_int():
    result = CliRunner().invoke(make_cli(click.ByteSize()), ["--size", "1K"])
    assert result.exit_code == 0, result.output
    assert result.output.strip() == repr(1024)


def test_max_bound_inclusive_and_message():
    cli = make_cli(click.ByteSize(max=1024))
    ok = CliRunner().invoke(cli, ["--size", "1K"])
    assert ok.exit_code == 0, ok.output
    bad = CliRunner().invoke(cli, ["--size", "2K"])
    assert bad.exit_code == 2
    assert "'2K' is not in the range - to 1024." in bad.output


def test_min_bound_message():
    cli = make_cli(click.ByteSize(min=10))
    bad = CliRunner().invoke(cli, ["--size", "5"])
    assert bad.exit_code == 2
    assert "'5' is not in the range 10 to -." in bad.output


def test_both_bounds_message():
    t = click.ByteSize(min=1024, max=2048)
    bad = CliRunner().invoke(make_cli(t), ["--size", "3K"])
    assert "'3K' is not in the range 1024 to 2048." in bad.output










