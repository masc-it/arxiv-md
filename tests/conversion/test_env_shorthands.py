"""Tests for environment-shorthand macro expansion (\\be → \\begin{equation}, etc.)."""

from __future__ import annotations

import pytest

from arxiv_md import convert_text
from arxiv_md.tex.macros import (
    Macro,
    expand_env_shorthands,
    find_env_shorthand_macros,
)


# --- Unit tests for find_env_shorthand_macros ---


def test_detect_begin_shorthand():
    macros = {"be": Macro(name="be", argc=0, body=r"\begin{equation}")}
    assert find_env_shorthand_macros(macros) == {"be": r"\begin{equation}"}


def test_detect_end_shorthand():
    macros = {"ee": Macro(name="ee", argc=0, body=r"\end{equation}")}
    assert find_env_shorthand_macros(macros) == {"ee": r"\end{equation}"}


def test_detect_star_env():
    macros = {"ba": Macro(name="ba", argc=0, body=r"\begin{align*}")}
    assert find_env_shorthand_macros(macros) == {"ba": r"\begin{align*}"}


def test_skip_macro_with_args():
    macros = {"myenv": Macro(name="myenv", argc=1, body=r"\begin{#1}")}
    assert find_env_shorthand_macros(macros) == {}


def test_skip_non_env_macro():
    macros = {"bf": Macro(name="bf", argc=0, body=r"\textbf")}
    assert find_env_shorthand_macros(macros) == {}


# --- Unit tests for expand_env_shorthands ---


def test_expand_replaces_commands():
    text = r"before \be x=1 \ee after"
    shorthands = {"be": r"\begin{equation}", "ee": r"\end{equation}"}
    result = expand_env_shorthands(text, shorthands)
    assert result == r"before \begin{equation} x=1 \end{equation} after"


def test_expand_respects_word_boundary():
    text = r"\begin{doc} \bee not-a-shorthand"
    shorthands = {"be": r"\begin{equation}"}
    result = expand_env_shorthands(text, shorthands)
    # \bee should NOT match \be (longer name)
    assert r"\bee" in result
    # \begin should NOT match \be (word boundary)
    assert r"\begin{doc}" in result


def test_expand_empty_shorthands():
    text = r"\be x \ee"
    assert expand_env_shorthands(text, {}) == text


# --- Integration: full convert_text ---


def test_be_ee_equation():
    tex = r"""
\newcommand{\be}{\begin{equation}}
\newcommand{\ee}{\end{equation}}
\begin{document}
\be
V_{\pi}(s) = E[G_t]
\ee
\end{document}
"""
    result = convert_text(tex)
    assert "$$" in result.markdown
    assert r"V_{\pi}(s) = E[G_t]" in result.markdown
    parse_warns = [w for w in result.warnings if w.code == "parse_recovery"]
    assert len(parse_warns) == 0


def test_bea_eea_eqnarray():
    tex = r"""
\newcommand{\bea}{\begin{eqnarray}}
\newcommand{\eea}{\end{eqnarray}}
\begin{document}
\bea
y = 2
\eea
\end{document}
"""
    result = convert_text(tex)
    assert "$$" in result.markdown
    assert "y = 2" in result.markdown


def test_ba_ea_align_star():
    tex = r"""
\newcommand{\ba}{\begin{align*}}
\newcommand{\ea}{\end{align*}}
\begin{document}
\ba
z = 3
\ea
\end{document}
"""
    result = convert_text(tex)
    assert "$$" in result.markdown
    assert "z = 3" in result.markdown


def test_nested_env_inside_shorthand():
    tex = r"""
\newcommand{\be}{\begin{equation}}
\newcommand{\ee}{\end{equation}}
\begin{document}
\be
f(x) = \begin{cases} 1 & x > 0 \\ 0 & x \leq 0 \end{cases}
\ee
\end{document}
"""
    result = convert_text(tex)
    assert "$$" in result.markdown
    assert "cases" in result.markdown
    parse_warns = [w for w in result.warnings if w.code == "parse_recovery"]
    assert len(parse_warns) == 0


def test_multiple_equations():
    tex = r"""
\newcommand{\be}{\begin{equation}}
\newcommand{\ee}{\end{equation}}
\begin{document}
First:
\be x = 1 \ee
Second:
\be y = 2 \ee
\end{document}
"""
    result = convert_text(tex)
    assert result.markdown.count("$$") >= 4  # 2 equations × open+close
    assert "x = 1" in result.markdown
    assert "y = 2" in result.markdown
