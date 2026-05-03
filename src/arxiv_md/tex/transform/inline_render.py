from __future__ import annotations

import html
from types import MappingProxyType
from typing import ClassVar, Iterable, Literal, Mapping

from arxiv_md.tex.model import (
    CitationSpan,
    CodeSpan,
    EmphasisSpan,
    InlineNode,
    LinkSpan,
    MathSpan,
    RawLatexSpan,
    ReferenceSpan,
    StrongSpan,
    SubscriptSpan,
    SuperscriptSpan,
    TextSpan,
)
from arxiv_md.tex.transform.math_text import _MATH_UNICODE, katex_normalize as _katex_normalize

import re as _re


_BARE_GLYPH_RE = _re.compile(r"^\\([A-Za-z@]+)$")


def _bare_glyph_to_unicode(tex: str) -> str | None:
    m = _BARE_GLYPH_RE.match(tex)
    if m is None:
        return None
    return _MATH_UNICODE.get(m.group(1))


__all__ = ["InlineSerializer", "InlineTarget", "RefStyle"]


InlineTarget = Literal["markdown", "html", "plain"]
RefStyle = Literal["marker", "bracket"]


def _normalize_ws(text: str) -> str:
    return " ".join(text.split())


class InlineSerializer:
    __slots__ = ("ref_style",)

    _SPAN_RENDERERS: ClassVar[Mapping[type[InlineNode], str]] = MappingProxyType(
        {
            TextSpan: "_text_span",
            StrongSpan: "_strong",
            EmphasisSpan: "_emphasis",
            CodeSpan: "_code",
            LinkSpan: "_link",
            ReferenceSpan: "_ref",
            CitationSpan: "_cite",
            MathSpan: "_math",
            SuperscriptSpan: "_superscript",
            SubscriptSpan: "_subscript",
            RawLatexSpan: "_raw_latex",
        }
    )

    def __init__(self, ref_style: RefStyle = "marker") -> None:
        self.ref_style = ref_style

    def serialize(
        self,
        nodes: list[InlineNode] | Iterable[InlineNode],
        target: InlineTarget = "markdown",
    ) -> str:
        return _normalize_ws(self._render(list(nodes), target))

    def _render(self, nodes: list[InlineNode], target: InlineTarget) -> str:
        return "".join(self._one(n, target) for n in nodes)

    def _one(self, node: InlineNode, target: InlineTarget) -> str:
        renderer_name = self._SPAN_RENDERERS.get(type(node))
        if renderer_name is None:
            return ""
        return getattr(self, renderer_name)(node, target)

    def _text_span(self, node: TextSpan, target: InlineTarget) -> str:
        return self._text(node.text, target)

    def _strong(self, node: StrongSpan, target: InlineTarget) -> str:
        inner = self._render(node.children, target)
        if target == "html":
            return f"<strong>{inner}</strong>"
        if target == "plain":
            return inner
        return f"**{inner}**"

    def _emphasis(self, node: EmphasisSpan, target: InlineTarget) -> str:
        inner = self._render(node.children, target)
        if target == "html":
            return f"<em>{inner}</em>"
        if target == "plain":
            return inner
        return f"*{inner}*"

    def _code(self, node: CodeSpan, target: InlineTarget) -> str:
        if target == "html":
            return f"<code>{html.escape(node.text)}</code>"
        if target == "plain":
            return node.text
        return f"`{node.text}`"

    def _superscript(self, node: SuperscriptSpan, target: InlineTarget) -> str:
        inner = self._render(node.children, target)
        if target == "html":
            return f"<sup>{inner}</sup>"
        if target == "plain":
            return inner
        return f"^{inner}^"

    def _subscript(self, node: SubscriptSpan, target: InlineTarget) -> str:
        inner = self._render(node.children, target)
        if target == "html":
            return f"<sub>{inner}</sub>"
        if target == "plain":
            return inner
        return f"~{inner}~"

    def _raw_latex(self, node: RawLatexSpan, _target: InlineTarget) -> str:

        return node.tex

    def _text(self, text: str, target: InlineTarget) -> str:
        if target == "html":
            return html.escape(text)
        return text

    def _link(self, node: LinkSpan, target: InlineTarget) -> str:
        url = node.url
        if not node.children:
            if target == "html":
                return (
                    f'<a href="{html.escape(url, quote=True)}">{html.escape(url)}</a>'
                )
            if target == "plain":
                return url
            return f"<{url}>"
        display = self._render(node.children, target)
        if target == "html":
            return f'<a href="{html.escape(url, quote=True)}">{display}</a>'
        if target == "plain":
            return display
        return f"[{display}]({url})"

    def _ref(self, node: ReferenceSpan, target: InlineTarget) -> str:
        key = node.key
        if not key:
            return ""
        if self.ref_style == "marker":
            return f"@@REF:{key}@@"
        return f"[{key}]"

    # Pandoc citation conventions:
    #   parenthetical (\cite, \citep, \parencite, \autocite) -> [@k1; @k2]
    #   narrative/textual (\citet, \textcite, \citeauthor)   -> @k1; @k2
    # Other biblatex variants fall back to parenthetical for now.
    _NARRATIVE_CITE_KINDS: frozenset[str] = frozenset(
        {"citet", "textcite", "citeauthor"}
    )

    def _cite(self, node: CitationSpan, target: InlineTarget) -> str:
        if not node.keys:
            return ""
        body = "; ".join(f"@{k}" for k in node.keys)
        if node.kind in self._NARRATIVE_CITE_KINDS:
            return body
        return f"[{body}]"

    def _math(self, node: MathSpan, target: InlineTarget) -> str:

        if target == "html":
            if node.rendered_text is not None:
                return node.rendered_text
            glyph = _bare_glyph_to_unicode(node.tex)
            if glyph is not None:
                return glyph
            return self._math_md(node)
        if target == "plain":
            if node.rendered_text is not None:
                return node.rendered_text
            return node.tex
        return self._math_md(node)

    def _math_md(self, node: MathSpan) -> str:

        if node.rendered_text is not None:
            return node.rendered_text
        body = _katex_normalize(node.tex)

        return f"\\({body}\\)" if "$" in body else f"${body}$"
