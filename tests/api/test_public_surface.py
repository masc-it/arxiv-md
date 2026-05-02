from __future__ import annotations

import arxiv_md


REQUIRED = frozenset(
    {
        "convert_path",
        "convert_text",
        "write_result",
        "ConvertOptions",
        "ConvertResult",
        "ConversionStats",
        "ResourceLimits",
        "WrittenResult",
        "TexDocument",
        "BibEntry",
        "TexWarning",
        "SourceSpan",
        "TexConvertError",
        "StrictConversionError",
        "UnsafeArchiveError",
        "UnsupportedArchiveError",
        "UnsafeOutputDirError",
        "SourceReadError",
        "NoMainTexError",
        "NoParseableBodyError",
        "OutputWriteError",
        "ResourceLimitError",
        "Block",
        "InlineNode",
        "Paragraph",
        "Heading",
        "Figure",
        "Table",
        "CodeBlock",
        "MathBlock",
        "ListBlock",
        "QuoteBlock",
        "RawLatex",
        "TextSpan",
        "StrongSpan",
        "EmphasisSpan",
        "CodeSpan",
        "MathSpan",
        "LinkSpan",
        "CitationSpan",
        "ReferenceSpan",
        "RawLatexSpan",
        "SubscriptSpan",
        "SuperscriptSpan",
    }
)


def test_required_names_importable() -> None:
    missing = sorted(name for name in REQUIRED if not hasattr(arxiv_md, name))
    assert not missing, f"public API missing: {missing}"


def test_required_names_in_dunder_all() -> None:
    exported = set(arxiv_md.__all__)
    missing = sorted(REQUIRED - exported)
    assert not missing, f"public names not in __all__: {missing}"
