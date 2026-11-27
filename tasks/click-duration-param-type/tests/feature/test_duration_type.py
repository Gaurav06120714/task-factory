from datetime import timedelta

import pytest

import click
from click.testing import CliRunner


def make_cli(param_type):
    @click.command()
    @click.option("--wait", type=param_type)
    def cli(wait):
        click.echo(repr(wait))

    return cli


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("90", timedelta(seconds=90)),
        ("0", timedelta(0)),
        ("5m", timedelta(minutes=5)),
        ("45s", timedelta(seconds=45)),
        ("1h30m", timedelta(hours=1, minutes=30)),
        ("2d4h", timedelta(days=2, hours=4)),
        ("1D2H3M4S", timedelta(days=1, hours=2, minutes=3, seconds=4)),
        ("  10m  ", timedelta(minutes=10)),
    ],
)
def test_valid_values(raw, expected):
    assert click.Duration().convert(raw, None, None) == expected


@pytest.mark.parametrize(
    "raw", ["", "abc", "1.5h", "-5", "30m1h", "1h1h", "1w", "1h 30m", "h"]
)
def test_invalid_values(raw):
    result = CliRunner().invoke(make_cli(click.Duration()), ["--wait", raw])
    assert result.exit_code == 2
    assert f"{raw!r} is not a valid duration." in result.output


def test_timedelta_passthrough():
    value = timedelta(minutes=3)
    assert click.Duration().convert(value, None, None) is value


def test_cli_converts_to_timedelta():
    result = CliRunner().invoke(make_cli(click.Duration()), ["--wait", "1h30m"])
    assert result.exit_code == 0, result.output
    assert result.output.strip() == repr(timedelta(hours=1, minutes=30))


def test_max_bound_inclusive_and_message():
    cli = make_cli(click.Duration(max=timedelta(hours=1)))
    ok = CliRunner().invoke(cli, ["--wait", "1h"])
    assert ok.exit_code == 0, ok.output
    bad = CliRunner().invoke(cli, ["--wait", "2h"])
    assert bad.exit_code == 2
    assert "'2h' is not in the range - to 1:00:00." in bad.output


def test_min_bound_message():
    cli = make_cli(click.Duration(min=timedelta(seconds=10)))
    bad = CliRunner().invoke(cli, ["--wait", "5s"])
    assert bad.exit_code == 2
    assert "'5s' is not in the range 0:00:10 to -." in bad.output


def test_both_bounds_message():
    t = click.Duration(min=timedelta(minutes=1), max=timedelta(minutes=2))
    bad = CliRunner().invoke(make_cli(t), ["--wait", "3m"])
    assert "'3m' is not in the range 0:01:00 to 0:02:00." in bad.output


def test_help_metavar():
    result = CliRunner().invoke(make_cli(click.Duration()), ["--help"])
    assert "--wait DURATION" in result.output


def test_repr_and_info_dict():
    t = click.Duration(min=timedelta(seconds=1), max=timedelta(minutes=1))
    assert repr(t) == "Duration"
    info = t.to_info_dict()
    assert info["name"] == "duration"
    assert info["param_type"] == "Duration"
    assert info["min"] == 1.0 and info["max"] == 60.0
    assert click.Duration().to_info_dict()["min"] is None


def test_exported_from_types():
    from click.types import Duration

    assert click.Duration is Duration


def test_min_bound_inclusive():
    # Added after mutation testing: `<` -> `<=` on the lower bound survived.
    assert click.Duration(min=timedelta(minutes=5)).convert("5m", None, None) == timedelta(minutes=5)
