import click
from click.testing import CliRunner
import pytest

def test_progress_bar_disabled():
    @click.command()
    def cli():
        with click.progressbar(length=100, hidden=True) as bar:
            for i in bar:
                pass

    runner = CliRunner()
    result = runner.invoke(cli, catch_exceptions=False)
    assert "100%|██████████| 100/100 [00:00<?, ?it/s]" not in result.output

def test_progress_bar_enabled():
    @click.command()
    def cli():
        with click.progressbar(length=100, hidden=False) as bar:
            for i in bar:
                pass

    runner = CliRunner()
    result = runner.invoke(cli, catch_exceptions=False)
    assert "100%|██████████| 100/100 [00:00<?, ?it/s]" in result.output
```
