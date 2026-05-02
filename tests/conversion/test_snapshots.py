from __future__ import annotations

from pathlib import Path

import pytest

from arxiv_md import convert_path


FIXTURES = (
    "simple-paper",
    "macro-paper",
    "table-paper",
    "rich-table-paper",
    "include-paper",
)


@pytest.mark.parametrize("name", FIXTURES)
def test_fixture_markdown_matches_snapshot(
    name: str, fixtures_root: Path, assert_snapshot
) -> None:
    src = fixtures_root / name
    if not src.exists():
        pytest.skip(f"fixture missing: {src}")
    md = convert_path(src).markdown
    assert_snapshot(f"{name}.md", md)
