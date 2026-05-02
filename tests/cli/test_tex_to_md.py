from __future__ import annotations

import json
from pathlib import Path


def test_converts_simple_paper(run_cli, simple_paper, tmp_path: Path) -> None:
    out = run_cli("tex-to-md", [str(simple_paper), "--outdir", str(tmp_path)])
    assert out.exit_code == 0, out.stderr
    md = (tmp_path / "document.md").read_text(encoding="utf-8")
    assert md.startswith("# Simple Paper")


def test_writes_sidecar(run_cli, simple_paper, tmp_path: Path) -> None:
    out = run_cli("tex-to-md", [str(simple_paper), "--outdir", str(tmp_path)])
    assert out.exit_code == 0
    sidecar = json.loads((tmp_path / "conversion.json").read_text(encoding="utf-8"))
    assert sidecar["config"]["raster_dpi"] == 120


def test_missing_outdir_exits_nonzero(run_cli, simple_paper) -> None:
    out = run_cli("tex-to-md", [str(simple_paper)])
    assert out.exit_code != 0


def test_unknown_source_exits_nonzero(run_cli, tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.tex"
    out = run_cli("tex-to-md", [str(missing), "--outdir", str(tmp_path / "out")])
    assert out.exit_code != 0


def test_outdir_inside_source_tree_rejected(
    run_cli, simple_paper, tmp_path: Path
) -> None:
    nested = simple_paper / "out"
    out = run_cli("tex-to-md", [str(simple_paper), "--outdir", str(nested)])
    assert out.exit_code != 0
