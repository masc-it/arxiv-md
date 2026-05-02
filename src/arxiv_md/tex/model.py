from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, TypeAlias

from arxiv_md.tex.table_types import (
    CaptionPosition,
    TableAlign,
    TableRuleKind,
    TableSectionKind,
    TableVAlign,
)


@dataclass(slots=True)
class TextSpan:
    """Inline text that renderers must escape as content, not markup.

    Whitespace already follows converter normalization rules.
    """

    text: str


@dataclass(slots=True)
class StrongSpan:
    """Strong emphasis with nested spans preserved for renderer-specific escaping."""

    children: list[InlineNode]


@dataclass(slots=True)
class EmphasisSpan:
    """Emphasis with nested spans preserved for renderer-specific escaping."""

    children: list[InlineNode]


@dataclass(slots=True)
class CodeSpan:
    """Inline code where contents are already plain text, not child spans."""

    text: str


@dataclass(slots=True)
class LinkSpan:
    """Inline link; `url` is source data and must be escaped by renderers."""

    children: list[InlineNode]
    url: str


@dataclass(slots=True)
class ReferenceSpan:
    """Unresolved or resolved cross-reference preserving original command kind."""

    key: str
    kind: str = "ref"


@dataclass(slots=True)
class CitationSpan:
    """Citation reference list; `kind` preserves author-year/numeric intent."""

    keys: list[str]
    kind: str = "cite"


@dataclass(slots=True)
class MathSpan:
    """Inline math; `tex` excludes delimiters and `rendered_text` is optional."""

    tex: str
    rendered_text: str | None = None


@dataclass(slots=True)
class SuperscriptSpan:
    """Superscript text lowered from explicit text-mode superscript commands."""

    children: list[InlineNode]


@dataclass(slots=True)
class SubscriptSpan:
    """Subscript text lowered from explicit text-mode subscript commands."""

    children: list[InlineNode]


@dataclass(slots=True)
class RawLatexSpan:
    """Unsupported inline LaTeX preserved verbatim for lossless fallback."""

    tex: str


InlineNode: TypeAlias = (
    TextSpan
    | StrongSpan
    | EmphasisSpan
    | CodeSpan
    | LinkSpan
    | ReferenceSpan
    | CitationSpan
    | MathSpan
    | SuperscriptSpan
    | SubscriptSpan
    | RawLatexSpan
)
"""Discriminated union of every inline span the IR exposes publicly."""

INLINE_TYPES: tuple[type, ...] = (
    TextSpan,
    StrongSpan,
    EmphasisSpan,
    CodeSpan,
    LinkSpan,
    ReferenceSpan,
    CitationSpan,
    MathSpan,
    SuperscriptSpan,
    SubscriptSpan,
    RawLatexSpan,
)
"""Runtime variant tuple for consumers that need `isinstance` checks."""


@dataclass(slots=True)
class Paragraph:
    """Paragraph block; `label` carries nearby TeX labels for ref resolution."""

    children: list[InlineNode]
    label: str | None = None


@dataclass(slots=True)
class Heading:
    """Section heading; `level` is clamped to Markdown-compatible range 1..6."""

    level: int
    children: list[InlineNode]
    label: str | None = None


@dataclass(slots=True)
class Figure:
    """Figure block with source graphic refs and optional materialized images.

    `graphics` preserves TeX paths; `images` contains output-relative paths only
    after asset rendering/copying succeeds.
    """

    caption: list[InlineNode] = field(default_factory=list)
    graphics: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    label: str | None = None
    raw_latex: str | None = None


TableParseStatus: TypeAlias = Literal["structured", "raw_fallback"]
"""Whether the table was successfully parsed into cells."""


@dataclass(slots=True)
class TableStyle:
    """Table-level presentation hints; renderers may ignore unsupported hints."""

    width: str | None = None
    align: TableAlign = "center"
    border_collapse: bool = True
    wrapper: str | None = None


@dataclass(slots=True)
class TableColumn:
    """Column spec from LaTeX preamble; separators map to rendered borders."""

    align: TableAlign = "left"
    width: str | None = None
    separator_left: str = ""
    separator_right: str = ""


@dataclass(slots=True)
class TableRule:
    """Horizontal rule metadata; column range is one-based when present."""

    kind: TableRuleKind = "hline"
    col_start: int | None = None
    col_end: int | None = None
    trim_left: bool = False
    trim_right: bool = False


@dataclass(slots=True)
class TableCellStyle:
    """Cell-level presentation hints; `None` means inherit table/column default."""

    align: TableAlign | None = None
    valign: TableVAlign | None = None
    bold: bool = False
    italic: bool = False


@dataclass(slots=True)
class TableCell:
    """Structured table cell; nested blocks allow paragraphs, lists, and tables."""

    blocks: list[Block] = field(default_factory=list)
    colspan: int = 1
    rowspan: int = 1
    is_header: bool = False
    style: TableCellStyle | None = None


@dataclass(slots=True)
class TableRowStyle:
    """Row-level presentation hints; renderers may ignore unsupported hints."""

    background: str | None = None


@dataclass(slots=True)
class TableRow:
    """Structured table row; `is_header` lets renderers choose `<th>` cells."""

    cells: list[TableCell] = field(default_factory=list)
    is_header: bool = False
    style: TableRowStyle | None = None


@dataclass(slots=True)
class TableSection:
    """Longtable-aware row group corresponding to table head/body/foot."""

    kind: TableSectionKind = "body"
    rows: list[TableRow] = field(default_factory=list)
    rules_before: list[TableRule] = field(default_factory=list)
    rules_after: list[TableRule] = field(default_factory=list)


@dataclass(slots=True)
class Table:
    """Table IR, preserving raw LaTeX when structural parsing fails.

    `parse_status="raw_fallback"` means consumers should prefer `raw_latex` over
    empty/partial structural fields.
    """

    parse_status: TableParseStatus = "structured"
    sections: list[TableSection] = field(default_factory=list)
    columns: list[TableColumn] = field(default_factory=list)
    caption: list[InlineNode] = field(default_factory=list)
    label: str | None = None
    raw_latex: str | None = None
    source_env: str | None = None
    caption_position: CaptionPosition = "unknown"
    parse_warnings: list[str] = field(default_factory=list)
    style: TableStyle | None = None


@dataclass(slots=True)
class MathBlock:
    """Display math; `text` is renderable body and `raw_latex` keeps source."""

    text: str
    raw_latex: str
    env: str | None = None
    label: str | None = None
    sublabels: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ListBlock:
    """List block; each item is a block list so nested paragraphs stay intact."""

    ordered: bool
    items: list[list[Block]]
    label: str | None = None


@dataclass(slots=True)
class QuoteBlock:
    """Quote/admonition block; `title` differentiates theorem/proof wrappers."""

    blocks: list[Block] = field(default_factory=list)
    title: str = ""
    label: str | None = None


@dataclass(slots=True)
class CodeBlock:
    """Fenced code content; `language` is empty when source gives no safe tag."""

    text: str
    language: str = ""


@dataclass(slots=True)
class RawLatex:
    """Unsupported block LaTeX preserved verbatim for review or custom handling."""

    text: str
    env: str | None = None


Block: TypeAlias = (
    Paragraph
    | Heading
    | Figure
    | Table
    | MathBlock
    | ListBlock
    | QuoteBlock
    | CodeBlock
    | RawLatex
)
"""Discriminated union of every block the IR exposes publicly."""

BLOCK_TYPES: tuple[type, ...] = (
    Paragraph,
    Heading,
    Figure,
    Table,
    MathBlock,
    ListBlock,
    QuoteBlock,
    CodeBlock,
    RawLatex,
)
"""Runtime variant tuple for consumers that need `isinstance` checks."""


__all__ = [
    "TextSpan",
    "StrongSpan",
    "EmphasisSpan",
    "CodeSpan",
    "LinkSpan",
    "ReferenceSpan",
    "CitationSpan",
    "MathSpan",
    "SuperscriptSpan",
    "SubscriptSpan",
    "RawLatexSpan",
    "InlineNode",
    "INLINE_TYPES",
    "TableAlign",
    "TableVAlign",
    "TableSectionKind",
    "TableRuleKind",
    "CaptionPosition",
    "TableParseStatus",
    "TableStyle",
    "TableColumn",
    "TableRule",
    "TableCellStyle",
    "TableCell",
    "TableRowStyle",
    "TableRow",
    "TableSection",
    "Paragraph",
    "Heading",
    "Figure",
    "Table",
    "MathBlock",
    "ListBlock",
    "QuoteBlock",
    "CodeBlock",
    "RawLatex",
    "Block",
    "BLOCK_TYPES",
]
