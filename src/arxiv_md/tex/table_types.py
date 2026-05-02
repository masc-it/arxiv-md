from __future__ import annotations

from typing import Literal, TypeAlias

ColumnAlign: TypeAlias = Literal[
    "left",
    "center",
    "right",
    "justify",
    "decimal",
    "unknown",
]
"""Horizontal alignment hint for columns or cells."""

ColumnVAlign: TypeAlias = Literal[
    "top",
    "middle",
    "bottom",
    "baseline",
    "unknown",
]
"""Vertical alignment hint for cells."""

TableAlign: TypeAlias = ColumnAlign
"""Public table horizontal alignment vocabulary."""

TableVAlign: TypeAlias = ColumnVAlign
"""Public table vertical alignment vocabulary."""

TableSectionKind: TypeAlias = Literal["head", "body", "foot"]
"""Longtable section kind used by `TableSection`."""

TableRuleKind: TypeAlias = Literal[
    "toprule",
    "midrule",
    "bottomrule",
    "hline",
    "xhline",
    "cline",
    "cmidrule",
    "specialrule",
]
"""Supported horizontal rule commands preserved in table IR."""

CaptionPosition: TypeAlias = Literal["top", "bottom", "unknown"]
"""Relative caption position recovered from table/figure wrappers."""

ALIGN_VALUES: set[ColumnAlign] = {
    "left",
    "center",
    "right",
    "justify",
    "decimal",
    "unknown",
}
VALIGN_VALUES: set[ColumnVAlign] = {
    "top",
    "middle",
    "bottom",
    "baseline",
    "unknown",
}
SECTION_KIND_VALUES: set[TableSectionKind] = {"head", "body", "foot"}
RULE_KIND_VALUES: set[TableRuleKind] = {
    "toprule",
    "midrule",
    "bottomrule",
    "hline",
    "xhline",
    "cline",
    "cmidrule",
    "specialrule",
}
CAPTION_POSITION_VALUES: set[CaptionPosition] = {"top", "bottom", "unknown"}


def parse_align(value: str | None) -> ColumnAlign:
    if value is None:
        return "unknown"
    if value in ALIGN_VALUES:
        return value
    return "unknown"


def parse_align_optional(value: str | None) -> ColumnAlign | None:
    if value is None:
        return None
    if value in ALIGN_VALUES:
        return value
    return "unknown"


def parse_valign(value: str | None) -> ColumnVAlign:
    if value is None:
        return "unknown"
    if value in VALIGN_VALUES:
        return value
    return "unknown"


def parse_valign_optional(value: str | None) -> ColumnVAlign | None:
    if value is None:
        return None
    if value in VALIGN_VALUES:
        return value
    return "unknown"


def parse_section_kind(value: str | None) -> TableSectionKind:
    if value is None:
        return "body"
    if value in SECTION_KIND_VALUES:
        return value
    return "body"


def parse_rule_kind(value: str | None) -> TableRuleKind:
    if value is None:
        return "hline"
    if value in RULE_KIND_VALUES:
        return value
    return "hline"


def parse_caption_position(value: str | None) -> CaptionPosition:
    if value is None:
        return "unknown"
    if value in CAPTION_POSITION_VALUES:
        return value
    return "unknown"
