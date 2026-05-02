from __future__ import annotations

import io
import os
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pytest

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "fixtures" / "tex"
SNAPSHOTS = ROOT / "conversion" / "snapshots"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--runslow",
        action="store_true",
        default=False,
        help="run tests marked slow (regression corpus, perf smoke)",
    )
    parser.addoption(
        "--runarchitecture",
        action="store_true",
        default=False,
        help="run tests marked architecture (source-scan lint)",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "slow: regression / perf, opt-in")
    config.addinivalue_line("markers", "architecture: source-scan lint, opt-in")


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    skip_slow = pytest.mark.skip(reason="needs --runslow")
    skip_arch = pytest.mark.skip(reason="needs --runarchitecture (opt-in)")
    run_slow = config.getoption("--runslow")
    for item in items:
        if "slow" in item.keywords and not run_slow:
            item.add_marker(skip_slow)
        if "architecture" in item.keywords and not config.getoption(
            "--runarchitecture", default=False
        ):
            item.add_marker(skip_arch)


@dataclass
class CliResult:
    exit_code: int
    stdout: str
    stderr: str


def _run_cli(entry: str, argv: list[str]) -> CliResult:
    if entry == "tex-to-md":
        from arxiv_md.tex.convert import main as cli_main
    elif entry == "arxiv-to-md":
        from arxiv_md.arxiv_to_md import main as cli_main
    else:  # pragma: no cover - misuse
        raise ValueError(f"unknown entry: {entry!r}")

    out, err = io.StringIO(), io.StringIO()
    try:
        with redirect_stdout(out), redirect_stderr(err):
            try:
                code = int(cli_main(argv))
            except SystemExit as exc:
                code = int(exc.code) if exc.code is not None else 0
    except Exception as exc:
        return CliResult(1, out.getvalue(), err.getvalue() + f"\n{exc!r}")
    return CliResult(code, out.getvalue(), err.getvalue())


@pytest.fixture()
def run_cli() -> Callable[[str, list[str]], CliResult]:
    return _run_cli


def _update_snapshots() -> bool:
    return os.environ.get("UPDATE_SNAPSHOTS") == "1"


@pytest.fixture()
def assert_snapshot() -> Callable[[str, str], None]:

    def _check(name: str, actual: str) -> None:
        path = SNAPSHOTS / name
        if _update_snapshots():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(actual, encoding="utf-8")
            return
        if not path.exists():
            pytest.fail(
                f"missing snapshot {path}; rerun with UPDATE_SNAPSHOTS=1 to create"
            )
        expected = path.read_text(encoding="utf-8")
        assert actual == expected, (
            f"snapshot drift for {name!r}; rerun with UPDATE_SNAPSHOTS=1 to update"
        )

    return _check


@pytest.fixture()
def fixtures_root() -> Path:
    return FIXTURES


@pytest.fixture()
def simple_paper() -> Path:
    return FIXTURES / "simple-paper"
