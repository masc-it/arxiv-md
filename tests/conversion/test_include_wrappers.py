"""Tests for include-wrapper macro detection and resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from arxiv_md import convert_path, convert_text
from arxiv_md.tex.macros import find_include_wrapper_macros
from arxiv_md.tex.source import SourceReader


# --- Unit tests for find_include_wrapper_macros ---


def test_detect_newcommand_input_wrapper():
    text = r"\newcommand{\myinput}[1]{\input{#1}}"
    assert find_include_wrapper_macros(text) == {"myinput": "input"}


def test_detect_newcommand_include_wrapper():
    text = r"\newcommand{\myinclude}[1]{\include{#1}}"
    assert find_include_wrapper_macros(text) == {"myinclude": "include"}


def test_detect_def_wrapper():
    text = r"\def\loadchapter#1{\input{#1}}"
    assert find_include_wrapper_macros(text) == {"loadchapter": "input"}


def test_non_wrapper_rejected():
    text = r"\newcommand{\safemacro}[1]{\textbf{#1}}"
    assert find_include_wrapper_macros(text) == {}


def test_complex_body_not_wrapper():
    text = r"\newcommand{\myinclude}[1]{\clearpage\input{#1}}"
    assert find_include_wrapper_macros(text) == {}


def test_no_args_not_wrapper():
    text = r"\newcommand{\loadstuff}{\input{fixed-file}}"
    assert find_include_wrapper_macros(text) == {}


# --- Source reader skips #N param refs ---


def test_source_reader_skips_param_refs(tmp_path: Path):
    """INCLUDE_RE should not match \\input{#1} inside macro bodies."""
    main = tmp_path / "main.tex"
    main.write_text(
        r"\newcommand{\myinc}[1]{\input{#1}}" "\n"
        r"\begin{document}Hello\end{document}" "\n"
    )
    reader = SourceReader(tmp_path)
    expanded = reader.expand(main)
    # No missing_include warnings for #1
    codes = [w.code for w in expanded.warnings]
    assert "missing_include" not in codes


# --- Integration: include-wrapper resolves files ---


def test_include_wrapper_resolves_files(tmp_path: Path):
    """Custom include-wrapper macro should resolve included files."""
    macros = tmp_path / "macros.tex"
    macros.write_text(r"\newcommand{\myinput}[1]{\input{#1}}")

    chapter = tmp_path / "ch1.tex"
    chapter.write_text(r"\section{Chapter One}" "\nContent of chapter one.\n")

    main = tmp_path / "main.tex"
    main.write_text(
        r"\documentclass{article}" "\n"
        r"\input{macros}" "\n"
        r"\begin{document}" "\n"
        r"\myinput{ch1}" "\n"
        r"\end{document}" "\n"
    )

    result = convert_path(main)
    assert "Chapter One" in result.markdown
    assert "Content of chapter one" in result.markdown
    missing = [w for w in result.warnings if w.code == "missing_include"]
    assert len(missing) == 0


# --- Fixture test ---


def test_include_wrapper_paper_fixture(fixtures_root: Path):
    src = fixtures_root / "include-wrapper-paper"
    if not src.exists():
        pytest.skip("fixture missing")
    result = convert_path(src)
    assert "Introduction" in result.markdown
    assert "Methods" in result.markdown
    assert "include-wrapper macro" in result.markdown
    # No warnings expected
    warn_codes = [w.code for w in result.warnings]
    assert "missing_include" not in warn_codes
    assert "macro_expansion_skipped" not in warn_codes
