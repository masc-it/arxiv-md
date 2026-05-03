"""Tests for TeX conditional stripping (\\ifarxiv, \\iftrue, \\iffalse)."""
from __future__ import annotations

import pytest

from arxiv_md.tex.macros import strip_tex_conditionals


class TestStripTexConditionals:
    def test_ifarxiv_true_branch(self) -> None:
        text = r"\newif\ifarxiv \arxivtrue \ifarxiv ARXIV\else JOURNAL\fi"
        assert "ARXIV" in strip_tex_conditionals(text)
        assert "JOURNAL" not in strip_tex_conditionals(text)

    def test_ifarxiv_default_true(self) -> None:
        """\\ifarxiv defaults to true even without explicit \\arxivtrue."""
        text = r"\newif\ifarxiv \ifarxiv ARXIV\else JOURNAL\fi"
        assert "ARXIV" in strip_tex_conditionals(text)
        assert "JOURNAL" not in strip_tex_conditionals(text)

    def test_ifarxiv_set_false(self) -> None:
        text = r"\newif\ifarxiv \arxivfalse \ifarxiv ARXIV\else JOURNAL\fi"
        result = strip_tex_conditionals(text)
        assert "ARXIV" not in result
        assert "JOURNAL" in result

    def test_ifarxiv_no_else(self) -> None:
        text = r"\newif\ifarxiv \ifarxiv ARXIV\fi rest"
        result = strip_tex_conditionals(text)
        assert "ARXIV" in result
        assert "rest" in result

    def test_iftrue(self) -> None:
        text = r"\iftrue VISIBLE\else HIDDEN\fi"
        result = strip_tex_conditionals(text)
        assert "VISIBLE" in result
        assert "HIDDEN" not in result

    def test_iffalse(self) -> None:
        text = r"\iffalse HIDDEN\else VISIBLE\fi"
        result = strip_tex_conditionals(text)
        assert "HIDDEN" not in result
        assert "VISIBLE" in result

    def test_iffalse_no_else(self) -> None:
        text = r"\iffalse HIDDEN\fi rest"
        result = strip_tex_conditionals(text)
        assert "HIDDEN" not in result
        assert "rest" in result

    def test_nested_conditionals(self) -> None:
        text = r"\newif\ifarxiv \arxivtrue \ifarxiv A \iftrue B\fi C\else D\fi"
        result = strip_tex_conditionals(text)
        assert "A" in result
        assert "B" in result
        assert "C" in result
        assert "D" not in result

    def test_unknown_if_preserved(self) -> None:
        text = r"\ifx something \fi rest"
        result = strip_tex_conditionals(text)
        assert r"\ifx" in result
        assert r"\fi" in result

    def test_newif_stripped(self) -> None:
        text = r"\newif\ifarxiv rest"
        result = strip_tex_conditionals(text)
        assert r"\newif" not in result
        assert "rest" in result

    def test_bool_set_stripped(self) -> None:
        text = r"\newif\ifarxiv \arxivtrue rest"
        result = strip_tex_conditionals(text)
        assert r"\arxivtrue" not in result
        assert "rest" in result

    def test_multiline(self) -> None:
        text = (
            "\\newif\\ifarxiv\n"
            "\\arxivtrue\n"
            "\\ifarxiv\n"
            "arXiv content\n"
            "\\else\n"
            "journal content\n"
            "\\fi\n"
            "common content\n"
        )
        result = strip_tex_conditionals(text)
        assert "arXiv content" in result
        assert "journal content" not in result
        assert "common content" in result

    def test_no_conditionals_passthrough(self) -> None:
        text = r"Just regular \textbf{text} here."
        assert strip_tex_conditionals(text) == text

    def test_comment_in_conditional(self) -> None:
        text = (
            "\\newif\\ifarxiv\n"
            "\\ifarxiv\n"
            "% arxiv comment\n"
            "content\n"
            "\\fi\n"
        )
        result = strip_tex_conditionals(text)
        assert "content" in result
