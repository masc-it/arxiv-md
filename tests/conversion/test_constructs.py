from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from arxiv_md import convert_path, convert_text

CONSTRUCTS_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "constructs"


KNOWN_BUGS: dict[str, str] = {}


def _discover_constructs() -> list[Path]:
    if not CONSTRUCTS_ROOT.exists():
        return []
    out: list[Path] = []
    for tex in CONSTRUCTS_ROOT.rglob("input.tex"):
        out.append(tex.parent)
    return sorted(out)


def _construct_id(path: Path) -> str:
    return str(path.relative_to(CONSTRUCTS_ROOT)).replace(os.sep, "/")


def _compose(path: Path) -> str:
    body = (path / "input.tex").read_text(encoding="utf-8")
    if body.lstrip().startswith("\\documentclass"):
        return body
    preamble_file = path / "preamble.tex"
    preamble = (
        preamble_file.read_text(encoding="utf-8") if preamble_file.exists() else ""
    )
    if preamble and not preamble.endswith("\n"):
        preamble += "\n"
    return f"{preamble}\\begin{{document}}\n{body.rstrip()}\n\\end{{document}}\n"


_CONSTRUCTS = _discover_constructs()


def _param_for(p: Path):
    cid = _construct_id(p)
    if cid in KNOWN_BUGS:
        return pytest.param(
            p, marks=pytest.mark.xfail(strict=True, reason=KNOWN_BUGS[cid])
        )
    return pytest.param(p)


_PARAMS = (
    [_param_for(p) for p in _CONSTRUCTS]
    if _CONSTRUCTS
    else [pytest.param(None, marks=pytest.mark.skip(reason="no constructs"))]
)


_CORE_FIXTURE_FILES: frozenset[str] = frozenset(
    {"input.tex", "preamble.tex", "expected.md", "source.txt"}
)


def _aux_files(construct: Path) -> list[Path]:
    return sorted(
        p
        for p in construct.iterdir()
        if p.is_file() and p.name not in _CORE_FIXTURE_FILES
    )


def _render_with_aux(construct: Path, aux: list[Path]) -> str:
    composed = _compose(construct)
    with tempfile.TemporaryDirectory(prefix="arxiv-md-construct-") as tmp:
        root = Path(tmp)
        main_tex = root / "main.tex"
        main_tex.write_text(composed, encoding="utf-8")
        for src in aux:
            shutil.copy2(src, root / src.name)
        return convert_path(main_tex).markdown


@pytest.mark.parametrize(
    "construct",
    _PARAMS,
    ids=lambda p: _construct_id(p) if p else "empty",
)
def test_construct_renders(construct: Path) -> None:
    aux = _aux_files(construct)
    if aux:
        actual = _render_with_aux(construct, aux)
    else:
        actual = convert_text(_compose(construct)).markdown
    expected_file = construct / "expected.md"

    if os.environ.get("UPDATE_SNAPSHOTS") == "1":
        expected_file.write_text(actual, encoding="utf-8")
        return

    if not expected_file.exists():
        pytest.fail(
            f"missing expected.md for {_construct_id(construct)}; "
            "rerun with UPDATE_SNAPSHOTS=1 to bootstrap, then HUMAN-REVIEW the diff"
        )
    expected = expected_file.read_text(encoding="utf-8")
    assert actual == expected, f"render drift: {_construct_id(construct)}"
