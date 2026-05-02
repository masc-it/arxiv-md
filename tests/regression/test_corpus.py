from __future__ import annotations

from pathlib import Path

import pytest

from arxiv_md import convert_path

CORPUS = Path(__file__).parent / "corpus"


def _papers() -> list[Path]:
    if not CORPUS.exists():
        return []
    return sorted(
        p for p in CORPUS.iterdir() if p.is_dir() or p.suffix in {".gz", ".zip", ".tar"}
    )


@pytest.mark.slow
@pytest.mark.parametrize(
    "paper",
    _papers() or [pytest.param(None, marks=pytest.mark.skip(reason="no corpus"))],
    ids=lambda p: p.name if p else "empty",
)
def test_paper_converts(paper: Path) -> None:
    r = convert_path(paper)
    assert r.markdown.strip(), "conversion produced no markdown"
