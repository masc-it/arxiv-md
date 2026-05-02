from __future__ import annotations

import inspect

import pytest

from arxiv_md import (
    ConvertOptions,
    Heading,
    Paragraph,
    QuoteBlock,
    RawLatex,
    StrongSpan,
    convert_text,
)
from arxiv_md.tex.transform.context import TransformContext
from arxiv_md.tex.transform.inline import InlineEngine


def _wrap(body: str) -> str:
    return r"\begin{document}" + body + r"\end{document}"


def test_returns_markdown() -> None:
    r = convert_text(_wrap(r"Hello \textbf{world}"))
    assert "Hello **world**" in r.markdown


def test_returns_typed_document() -> None:
    r = convert_text(_wrap(r"\section{Intro} Body."))
    headings = [b for b in r.document.blocks if isinstance(b, Heading)]
    assert headings and headings[0].level >= 1


def test_inline_strong_span_in_paragraph() -> None:
    r = convert_text(_wrap(r"Hi \textbf{there}"))
    paras = [b for b in r.document.blocks if isinstance(b, Paragraph)]
    assert paras
    assert any(isinstance(c, StrongSpan) for c in paras[0].children)


def test_unknown_command_counted() -> None:
    r = convert_text(_wrap(r"\zzznope{x}"))
    assert "\\zzznope" in r.stats.unknown_command_counts


def test_options_round_trip() -> None:
    opts = ConvertOptions(strict=False)
    r = convert_text(_wrap("Plain."), opts)
    assert r.options is opts


def test_newtheorem_discovered_env_uses_static_dispatch() -> None:
    source = _wrap(
        r"\newtheorem{claimbox}{Claim}"
        r"\begin{claimbox}[Tight]Body.\end{claimbox}"
    )

    r = convert_text(source)

    quotes = [b for b in r.document.blocks if isinstance(b, QuoteBlock)]
    assert quotes
    assert quotes[0].title == "Claim 1 (Tight)."
    assert "claimbox" not in r.stats.unknown_env_counts
    assert r.stats.unknown_env_counts == {}


def test_siunitx_uses_static_inline_dispatch() -> None:
    source = _wrap(
        r"Values: \SI{10}{\meter\per\second}, \si{\kilo\gram}, "
        r"\ang{1;2;3}, \num{1e-3}, \SIrange{1}{2}{\meter}, \numrange{3}{4}."
    )

    r = convert_text(source)

    assert r.markdown == "Values: 10 m/s, kg, 1°2′3″, 1 × 10⁻³, 1 m to 2 m, 3 to 4.\n"
    assert r.stats.unknown_command_counts == {}


def test_unknown_environment_non_strict_preserves_raw_latex_and_counts() -> None:
    source = _wrap(
        r"Before."
        r"\begin{mysteryenv}[x]Raw \textbf{body}.\end{mysteryenv}"
        r"After."
    )

    r = convert_text(source)

    raw_blocks = [b for b in r.document.blocks if isinstance(b, RawLatex)]
    assert len(raw_blocks) == 1
    assert raw_blocks[0].env == "mysteryenv"
    assert raw_blocks[0].text == (
        r"\begin{mysteryenv}[x]Raw \textbf{body}.\end{mysteryenv}"
    )
    assert r.stats.unknown_env_counts == {"mysteryenv": 1}
    assert "```latex" in r.markdown
    assert r.warnings[-1].code == "unknown_env"
    assert r.warnings[-1].message == "Unknown environment preserved: mysteryenv"


def test_registry_api_removed_from_public_options_and_transform_context() -> None:
    assert "registry" not in inspect.signature(ConvertOptions).parameters
    with pytest.raises(TypeError):
        ConvertOptions(registry=object())  # type: ignore[call-arg]
    assert "registry" not in inspect.signature(TransformContext).parameters
    assert "registry" not in inspect.signature(InlineEngine).parameters
