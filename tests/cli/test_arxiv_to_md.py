from __future__ import annotations

from pathlib import Path


def test_help_exits_zero(run_cli) -> None:
    out = run_cli("arxiv-to-md", ["--help"])
    assert out.exit_code == 0
    assert "arxiv" in out.stdout.lower()


def test_missing_outdir_rejected(run_cli) -> None:
    out = run_cli("arxiv-to-md", ["2601.07892"])
    assert out.exit_code != 0


def test_unknown_flag_rejected(run_cli, tmp_path: Path) -> None:
    out = run_cli(
        "arxiv-to-md",
        ["2601.07892", "--outdir", str(tmp_path), "--definitely-not-a-flag"],
    )
    assert out.exit_code != 0
