from __future__ import annotations

import re
from dataclasses import dataclass

from arxiv_md.tex._common import TexDocument
from arxiv_md.tex.model import (
    Block,
    CitationSpan,
    CodeBlock,
    CodeSpan,
    EmphasisSpan,
    Figure,
    Heading,
    InlineNode,
    LinkSpan,
    ListBlock,
    MathBlock,
    MathSpan,
    Paragraph,
    QuoteBlock,
    RawLatex,
    RawLatexSpan,
    ReferenceSpan,
    StrongSpan,
    SubscriptSpan,
    SuperscriptSpan,
    Table,
    TextSpan,
)

__all__ = [
    "LabelInfo",
    "resolve_references",
    "replace_block_refs",
    "replace_ref_markers",
]

_REF_MARKER_RE = re.compile(r"@@REF:([^@]+?)@@")
_NUMBERED_THEOREM_TITLE_RE = re.compile(
    r"^(?P<type>.+?)\s+(?P<number>\d+[A-Za-z]*)(?:\s*\(|$)"
)

_REF_PREFIX_TRAILER = re.compile(
    r"(?ix)\b(?:"
    r"figs?|figures?|tab|tabs|tables?|eq|eqn|eqns|equations?|sec|sect|sects|sections?"
    r"|thm|thms|theorems?|lem|lemmas?|prop|propositions?|cor|corollar(?:y|ies)"
    r"|def|definitions?|remarks?"
    r"|alg|algs|algorithms?"
    r")\.?\s*\(?$"
)
_LABEL_PREFIX_WORDS: tuple[str, ...] = (
    "Figure ",
    "Figures ",
    "Table ",
    "Tables ",
    "Equation ",
    "Equations ",
    "Section ",
    "Sections ",
    "Theorem ",
    "Theorems ",
    "Lemma ",
    "Lemmas ",
    "Proposition ",
    "Corollary ",
    "Definition ",
    "Remark ",
    "Algorithm ",
    "Algorithms ",
)


@dataclass(slots=True)
class LabelInfo:
    category: str
    number: str
    text: str


_CREF_ABBREV: dict[str, str] = {
    "figure": "fig.",
    "table": "tab.",
    "equation": "eq.",
    "section": "section",
    "theorem": "thm.",
}


_CREF_PLURAL: dict[str, str] = {
    "figure": "figs.",
    "table": "tabs.",
    "equation": "eqs.",
    "section": "sections",
    "theorem": "thms.",
}


_AUTOREF_PREFIX: dict[str, str] = {
    "figure": "Figure",
    "table": "Table",
    "equation": "Equation",
    "section": "Section",
    "theorem": "Theorem",
}


_AUTOREF_PLURAL: dict[str, str] = {
    "figure": "Figures",
    "table": "Tables",
    "equation": "Equations",
    "section": "Sections",
    "theorem": "Theorems",
}


def _format_ref(kind: str, info: LabelInfo) -> str:
    if kind in ("ref", "nameref", "pageref"):
        return info.number
    if kind == "eqref":
        return f"({info.number})"
    if kind in ("autoref", "Cref"):
        prefix = _AUTOREF_PREFIX.get(info.category)
        if prefix:
            return f"{prefix} {info.number}"
        return info.text
    if kind == "cref":
        abbrev = _CREF_ABBREV.get(info.category)
        if abbrev:
            return f"{abbrev} {info.number}"
        return info.text

    return info.text


def _missing_label_text(key: str, kind: str) -> str:
    if kind == "eqref":
        return f"([{key}])"
    return f"[{key}]"


def _join_and(parts: list[str]) -> str:
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def _format_cref_keys(
    kind: str, keys: list[str], label_index: dict[str, LabelInfo]
) -> str:
    keys = [k.strip() for k in keys if k.strip()]
    if not keys:
        return ""
    if len(keys) == 1:
        info = label_index.get(keys[0])
        if info is None:
            return _missing_label_text(keys[0], kind)
        return _format_ref(kind, info)
    infos: list[LabelInfo | None] = [label_index.get(k) for k in keys]
    all_resolved = all(i is not None for i in infos)
    same_category = (
        all_resolved and len({i.category for i in infos if i is not None}) == 1  # type: ignore[union-attr]
    )
    if all_resolved and same_category and len(keys) >= 3:
        category = infos[0].category  # type: ignore[union-attr]
        if kind == "Cref":
            prefix = _AUTOREF_PLURAL.get(category) or _AUTOREF_PREFIX.get(category)
        else:
            prefix = _CREF_PLURAL.get(category) or _CREF_ABBREV.get(category)
        if prefix:
            nums = [i.number for i in infos if i is not None]
            return f"{prefix} " + _join_and(nums)
    parts: list[str] = []
    for k, info in zip(keys, infos):
        if info is None:
            parts.append(_missing_label_text(k, kind))
        else:
            parts.append(_format_ref(kind, info))
    return _join_and(parts)


def _parse_numbered_theorem_title(title: str) -> tuple[str, str] | None:
    clean = title.rstrip(".").strip()
    match = _NUMBERED_THEOREM_TITLE_RE.match(clean)
    if not match:
        return None
    return match.group("type").strip(), match.group("number")


def _build_label_index(doc: TexDocument) -> dict[str, LabelInfo]:
    labels: dict[str, LabelInfo] = {}
    figure_no = 0
    table_no = 0
    equation_no = 0
    theorem_no = 0
    algorithm_no = 0
    for block in doc.blocks:
        if isinstance(block, Heading):
            if block.label:
                heading_text = _serialize_inline(block.children)
                labels[block.label] = LabelInfo(
                    category="section",
                    number=heading_text,
                    text=heading_text,
                )
        elif isinstance(block, Figure):
            figure_no += 1
            if block.label:
                labels[block.label] = LabelInfo(
                    category="figure",
                    number=str(figure_no),
                    text=f"Figure {figure_no}",
                )
        elif isinstance(block, Table):
            table_no += 1
            if block.label:
                labels[block.label] = LabelInfo(
                    category="table",
                    number=str(table_no),
                    text=f"Table {table_no}",
                )
        elif isinstance(block, MathBlock) and block.label:
            equation_no += 1
            labels[block.label] = LabelInfo(
                category="equation",
                number=str(equation_no),
                text=f"Equation {equation_no}",
            )
            for idx, sub_key in enumerate(block.sublabels):
                if not sub_key:
                    continue
                suffix = chr(ord("a") + idx + 1)
                sub_num = f"{equation_no}{suffix}"
                labels[sub_key] = LabelInfo(
                    category="equation",
                    number=sub_num,
                    text=f"Equation {sub_num}",
                )
        elif isinstance(block, QuoteBlock) and block.label:
            parsed = _parse_numbered_theorem_title(block.title)
            if parsed is not None:
                type_word, number = parsed
                labels[block.label] = LabelInfo(
                    category="theorem",
                    number=number,
                    text=f"{type_word} {number}",
                )
            else:
                theorem_no += 1

                title = block.title.rstrip(".") if block.title else "Theorem"
                type_word = title.split("(")[0].strip() if "(" in title else title
                labels[block.label] = LabelInfo(
                    category="theorem",
                    number=str(theorem_no),
                    text=f"{type_word} {theorem_no}",
                )
        elif isinstance(block, Paragraph) and block.label:
            inline_text = _serialize_inline(block.children)
            if "Algorithm" in inline_text:
                algorithm_no += 1
                labels[block.label] = LabelInfo(
                    category="algorithm",
                    number=str(algorithm_no),
                    text=f"Algorithm {algorithm_no}",
                )
    return labels


def _flat_labels(label_index: dict[str, LabelInfo]) -> dict[str, str]:
    return {k: v.text for k, v in label_index.items()}


def resolve_references(doc: TexDocument) -> None:
    label_index = _build_label_index(doc)
    flat = _flat_labels(label_index)
    for block in doc.abstract:
        _replace_block_refs_typed(block, label_index, flat)
    for block in doc.blocks:
        _replace_block_refs_typed(block, label_index, flat)


def _replace_block_refs_typed(
    block: Block,
    label_index: dict[str, LabelInfo],
    flat: dict[str, str],
) -> None:
    if isinstance(block, (Paragraph, Heading)):
        _rewrite_inline_list(block.children, label_index, flat)
        return
    if isinstance(block, Figure):
        _rewrite_inline_list(block.caption, label_index, flat)
        if block.raw_latex is not None:
            block.raw_latex = replace_ref_markers(block.raw_latex, flat)
        return
    if isinstance(block, Table):
        _rewrite_inline_list(block.caption, label_index, flat)
        if block.raw_latex is not None:
            block.raw_latex = replace_ref_markers(block.raw_latex, flat)

        for section in block.sections:
            for row in section.rows:
                for cell in row.cells:
                    for child in cell.blocks:
                        _replace_block_refs_typed(child, label_index, flat)
        return
    if isinstance(block, MathBlock):
        block.text = replace_ref_markers(block.text, flat)
        block.raw_latex = replace_ref_markers(block.raw_latex, flat)
        return
    if isinstance(block, RawLatex):
        block.text = replace_ref_markers(block.text, flat)
        return
    if isinstance(block, ListBlock):
        for item in block.items:
            for child in item:
                _replace_block_refs_typed(child, label_index, flat)
        return
    if isinstance(block, QuoteBlock):
        for child in block.blocks:
            _replace_block_refs_typed(child, label_index, flat)
        return
    if isinstance(block, CodeBlock):
        return


def replace_block_refs(block: Block, labels: dict[str, str]) -> None:
    label_index = _flat_to_label_index(labels)
    _replace_block_refs_typed(block, label_index, labels)


def _flat_to_label_index(labels: dict[str, str]) -> dict[str, LabelInfo]:
    index: dict[str, LabelInfo] = {}
    for key, text in labels.items():
        cat = "unknown"
        number = text
        for prefix_word in ("Figure ", "Table ", "Equation ", "Section "):
            if text.startswith(prefix_word):
                cat = prefix_word.strip().lower()
                number = text[len(prefix_word) :]
                break
        index[key] = LabelInfo(category=cat, number=number, text=text)
    return index


def replace_ref_markers(text: str, labels: dict[str, str]) -> str:

    def repl(m: re.Match[str]) -> str:
        key = m.group(1)
        label = labels.get(key, f"[{key}]")
        prefix_zone = text[: m.start()]
        if _REF_PREFIX_TRAILER.search(prefix_zone):
            for word in _LABEL_PREFIX_WORDS:
                if label.startswith(word):
                    return label[len(word) :]
        return label

    return _REF_MARKER_RE.sub(repl, text)


def _serialize_inline(nodes: list[InlineNode]) -> str:
    parts: list[str] = []
    for node in nodes:
        if isinstance(node, TextSpan):
            parts.append(node.text)
        elif isinstance(node, MathSpan):
            parts.append(node.rendered_text or node.tex)
        elif isinstance(node, CodeSpan):
            parts.append(node.text)
        elif isinstance(node, CitationSpan):
            parts.append("; ".join(f"@{k}" for k in node.keys))
        elif isinstance(node, ReferenceSpan):
            parts.append(node.key)
        elif isinstance(node, RawLatexSpan):
            parts.append(node.tex)
        elif isinstance(
            node,
            (StrongSpan, EmphasisSpan, LinkSpan, SuperscriptSpan, SubscriptSpan),
        ):
            parts.append(_serialize_inline(node.children))
    return "".join(parts)


def _rewrite_inline_list(
    nodes: list[InlineNode],
    label_index: dict[str, LabelInfo],
    flat: dict[str, str],
) -> None:
    i = 0
    while i < len(nodes):
        node = nodes[i]
        if isinstance(node, TextSpan):
            node.text = replace_ref_markers(node.text, flat)
        elif isinstance(node, ReferenceSpan):
            key = node.key
            kind = node.kind or "ref"
            if key:
                if kind in ("cref", "Cref") and "," in key:
                    keys = [k for k in key.split(",") if k.strip()]
                    display = _format_cref_keys(kind, keys, label_index)
                else:
                    info = label_index.get(key)
                    if info is not None:
                        display = _format_ref(kind, info)

                        if i > 0:
                            previous = nodes[i - 1]
                            if isinstance(previous, TextSpan):
                                prefix = previous.text
                                if _REF_PREFIX_TRAILER.search(prefix):
                                    for word in _LABEL_PREFIX_WORDS:
                                        if display.startswith(word):
                                            display = display[len(word) :]
                                            break
                    else:
                        display = _missing_label_text(key, kind)
                nodes[i] = TextSpan(text=display)
            else:
                nodes[i] = TextSpan(text="")
        elif isinstance(node, CodeSpan):
            node.text = replace_ref_markers(node.text, flat)
        elif isinstance(
            node,
            (StrongSpan, EmphasisSpan, LinkSpan, SuperscriptSpan, SubscriptSpan),
        ):
            _rewrite_inline_list(node.children, label_index, flat)
        elif isinstance(node, (CitationSpan, MathSpan, RawLatexSpan)):
            pass
        i += 1
