from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from arxiv_md import ConvertResult, TexConvertError, TexWarning, convert_text


def _convert(body: str) -> ConvertResult | None:
    try:
        return convert_text(rf"\begin{{document}}{body}\end{{document}}")
    except TexConvertError:
        return None


_TEX_NOISE = st.text(
    alphabet=st.characters(
        blacklist_categories=("Cs",),
        min_codepoint=0x20,
        max_codepoint=0x2FFF,
    ),
    max_size=200,
)


@given(body=_TEX_NOISE)
@settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_convert_text_never_raises_untyped(body: str) -> None:
    r = _convert(body)
    if r is not None:
        assert isinstance(r, ConvertResult)
        assert isinstance(r.markdown, str)


@given(body=_TEX_NOISE)
@settings(max_examples=50, deadline=None)
def test_warnings_are_always_typed(body: str) -> None:
    r = _convert(body)
    if r is None:
        return
    for w in r.warnings:
        assert isinstance(w, TexWarning)
        assert isinstance(w.code, str) and w.code
        assert isinstance(w.message, str)


@given(body=_TEX_NOISE)
@settings(max_examples=50, deadline=None)
def test_unknown_counts_are_nonneg_ints(body: str) -> None:
    r = _convert(body)
    if r is None:
        return
    for name, count in r.stats.unknown_command_counts.items():
        assert isinstance(name, str)
        assert isinstance(count, int) and count >= 0
