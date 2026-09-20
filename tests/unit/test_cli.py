"""Unit tests for Typer/Rich CLI interface."""

from pathlib import Path

from typer.testing import CliRunner

from deep_research.cli import app

runner = CliRunner()


def test_cli_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Execute autonomous deep research" in result.output


def test_cli_invalid_mode() -> None:
    result = runner.invoke(app, ["Test query", "--mode", "non_existent"])
    assert result.exit_code == 1
    assert "Invalid research mode" in result.output


def test_cli_mock_run_with_output(tmp_path: Path) -> None:
    out_file = tmp_path / "cli_report.md"
    result = runner.invoke(
        app,
        [
            "Quantum error correction",
            "--mode",
            "quick",
            "--llm",
            "mock",
            "--search",
            "mock",
            "--output",
            str(out_file),
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "Synthesized Investigation Report" in content
