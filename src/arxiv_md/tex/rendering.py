from __future__ import annotations

import re
from typing import Any, Callable

from arxiv_md.tex._common import BibEntry, TexDocument

from arxiv_md.tex.model import (
    AlgorithmBlock,
    Block,
    CodeBlock,
    Figure,
    Heading,
    InlineNode,
    ListBlock,
    MathBlock,
    Paragraph,
    QuoteBlock,
    RawLatex,
    Table,
    TableCell,
    TableColumn,
    TableRow,
    TableSection,
)
from arxiv_md.tex.transform.inline_render import InlineSerializer
from arxiv_md.tex.transform.math_text import katex_normalize as _katex_normalize

_RENDER_SERIALIZER = InlineSerializer(ref_style="bracket")


_MATH_ENV_WRAPPER: dict[str, str] = {
    "align": "align",
    "align*": "align*",
    "alignat": "aligned",
    "alignat*": "aligned",
    "eqnarray": "eqnarray",
    "eqnarray*": "eqnarray*",
    "split": "aligned",
    "gather": "gather",
    "gather*": "gather*",
    "multline": "multline",
    "multline*": "multline*",
}

# Inner-math environments that always need wrapping when at top level
_MATH_ENV_SELF_WRAP: frozenset[str] = frozenset(
    {
        "matrix", "matrix*",
        "pmatrix", "pmatrix*",
        "bmatrix", "bmatrix*",
        "Bmatrix", "Bmatrix*",
        "vmatrix", "vmatrix*",
        "Vmatrix", "Vmatrix*",
        "smallmatrix",
        "cases", "cases*",
        "dcases", "dcases*",
    }
)


def render_document_markdown(document: TexDocument) -> str:
    parts: list[str] = []
    if document.title:
        parts.append(f"# {document.title}")
    if document.authors:
        parts.append("*" + "; ".join(document.authors) + "*")
    if document.abstract:
        parts.append("## Abstract")
        parts.extend(_render_block(block) for block in document.abstract)
    parts.extend(_render_block(block) for block in document.blocks)
    if document.bibliography:
        parts.append("## References")
        parts.extend(_render_bib(entry) for entry in document.bibliography)
    markdown = "\n\n".join(part.strip() for part in parts if part and part.strip())
    return markdown.rstrip() + "\n"


def _render_inline(nodes: list[InlineNode]) -> str:
    return _RENDER_SERIALIZER.serialize(nodes, target="markdown")


def _render_heading(block: Heading) -> str:
    level = max(1, min(6, block.level or 2))
    return f"{'#' * level} {_render_inline(block.children)}"


def _render_paragraph(block: Paragraph) -> str:
    return _render_inline(block.children)


def _render_math(block: MathBlock) -> str:
    body = _katex_normalize(block.text.strip())
    env = block.env or ""
    # Inner-math envs (matrix, cases) always need their own begin/end wrapper
    if env in _MATH_ENV_SELF_WRAP:
        body = f"\\begin{{{env}}}\n{body}\n\\end{{{env}}}"
    else:
        wrapper = _MATH_ENV_WRAPPER.get(env)
        if wrapper is not None and ("&" in body or "\\\\" in body):
            body = f"\\begin{{{wrapper}}}\n{body}\n\\end{{{wrapper}}}"
    return f"$$\n{body}\n$$"


def _render_list(block: ListBlock) -> str:
    lines: list[str] = []
    for idx, item in enumerate(block.items, start=1):
        marker = f"{idx}." if block.ordered else "-"
        indent = " " * (len(marker) + 1)
        rendered: list[tuple[Block, str]] = [
            (child, _render_block(child)) for child in item
        ]
        rendered = [(c, r) for (c, r) in rendered if r and r.strip()]
        if not rendered:
            lines.append(marker)
            continue

        body = rendered[0][1]
        for child, text in rendered[1:]:
            sep = "\n" if isinstance(child, ListBlock) else "\n\n"
            body = f"{body}{sep}{text}"

        item_lines = body.split("\n")
        out_lines = [f"{marker} {item_lines[0]}"]
        for ln in item_lines[1:]:
            out_lines.append(f"{indent}{ln}" if ln else "")
        lines.append("\n".join(out_lines))
    return "\n".join(lines)


def _render_quote(block: QuoteBlock) -> str:
    child_parts = [_render_block(child) for child in block.blocks]
    body = "\n\n".join(part for part in child_parts if part.strip())
    if block.title:
        body = f"**{block.title}** {body}" if body else f"**{block.title}**"
    return "\n".join(f"> {line}" if line else ">" for line in body.splitlines())


def _render_code(block: CodeBlock) -> str:
    return f"```{block.language}\n{block.text}\n```"


def _render_raw(block: RawLatex) -> str:
    return f"```latex\n{block.text}\n```"


def _render_algorithm(block: AlgorithmBlock) -> str:
    return block.text


_BLOCK_RENDERERS: dict[type, Callable[[Any], str]] = {}


def _ensure_dispatch_table() -> dict[type, Callable[[Any], str]]:
    if not _BLOCK_RENDERERS:
        _BLOCK_RENDERERS.update(
            {
                Heading: _render_heading,
                Paragraph: _render_paragraph,
                MathBlock: _render_math,
                Figure: _render_figure,
                Table: _render_table,
                ListBlock: _render_list,
                QuoteBlock: _render_quote,
                CodeBlock: _render_code,
                RawLatex: _render_raw,
                AlgorithmBlock: _render_algorithm,
            }
        )
    return _BLOCK_RENDERERS


def _render_block(block: Block) -> str:
    renderer = _ensure_dispatch_table().get(type(block))
    if renderer is not None:
        return renderer(block)
    return ""


def _html_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _attr_escape(value: str) -> str:
    return _html_escape(value)


_CSS_SAFE_VALUE = re.compile(r"^[a-zA-Z0-9 _.#%,()/-]+$")


def _sanitize_css_value(value: str) -> str | None:
    value = value.strip()
    if not value or not _CSS_SAFE_VALUE.match(value):
        return None
    return value


_SECTION_TAG = {"head": "thead", "foot": "tfoot", "body": "tbody"}


def _render_table(table: Table) -> str:
    if table.parse_status == "raw_fallback" and table.raw_latex is not None:
        return _render_table_fallback(table)
    if table.sections:
        return _render_table_html(table)

    return ""


def _render_table_fallback(table: Table) -> str:
    caption = _render_inline(table.caption)
    raw = f"```latex\n{table.raw_latex}\n```"
    return f"*Table: {caption}*\n\n{raw}" if caption else raw


def _render_table_html(table: Table) -> str:

    table_styles: list[str] = []
    if table.style:
        w = _sanitize_css_value(table.style.width or "")
        if w:
            table_styles.append(f"width:{w}")

    tag_attrs = ""
    if table_styles:
        tag_attrs = f' style="{_attr_escape("; ".join(table_styles))}"'
    out: list[str] = [f"<table{tag_attrs}>"]

    if table.caption:
        caption_html = _RENDER_SERIALIZER.serialize(table.caption, target="html")
        if caption_html:
            out.append(f"<caption>{caption_html}</caption>")

    colgroup = _render_colgroup(table.columns)
    if colgroup:
        out.append(colgroup)

    for section in table.sections:
        out.append(_render_section(section, table.columns))

    out.append("</table>")
    return "\n".join(out)


def _render_colgroup(columns: list[TableColumn]) -> str:
    if not columns or not any(c.width for c in columns):
        return ""
    cols: list[str] = []
    for col in columns:
        styles: list[str] = []
        w = _sanitize_css_value(col.width or "")
        if w:
            styles.append(f"width:{w}")
        if styles:
            cols.append(f'<col style="{_attr_escape("; ".join(styles))}">')
        else:
            cols.append("<col>")
    return "<colgroup>" + "".join(cols) + "</colgroup>"


def _render_section(section: TableSection, columns: list[TableColumn]) -> str:
    tag = _SECTION_TAG.get(section.kind, "tbody")
    parts: list[str] = [f"<{tag}>"]
    for row in section.rows:
        parts.append(_render_row(row, columns))
    parts.append(f"</{tag}>")
    return "\n".join(parts)


def _render_row(row: TableRow, columns: list[TableColumn]) -> str:
    row_styles: list[str] = []
    if row.style and row.style.background:
        bg = _sanitize_css_value(row.style.background)
        if bg:
            row_styles.append(f"background:{bg}")

    row_attr = ""
    if row_styles:
        row_attr = f' style="{_attr_escape("; ".join(row_styles))}"'

    cells: list[str] = []
    col_idx = 0
    for cell in row.cells:
        col = columns[col_idx] if col_idx < len(columns) else None
        cells.append(_render_cell(cell, col))
        col_idx += cell.colspan
    return f"<tr{row_attr}>" + "".join(cells) + "</tr>"


def _render_cell(cell: TableCell, col: TableColumn | None) -> str:
    tag = "th" if cell.is_header else "td"
    attrs: list[str] = []
    if cell.colspan > 1:
        attrs.append(f'colspan="{cell.colspan}"')
    if cell.rowspan > 1:
        attrs.append(f'rowspan="{cell.rowspan}"')

    styles: list[str] = []

    align = None
    if cell.style and cell.style.align:
        align = cell.style.align
    elif col and col.align and col.align != "left":
        align = col.align
    if align:
        styles.append(f"text-align:{align}")

    if cell.style and cell.style.valign:
        styles.append(f"vertical-align:{cell.style.valign}")

    if col:
        if col.separator_left:
            styles.append("border-left:1px solid")
        if col.separator_right:
            styles.append("border-right:1px solid")

    if styles:
        attrs.append(f'style="{_attr_escape("; ".join(styles))}"')

    attr_str = (" " + " ".join(attrs)) if attrs else ""

    content = _render_cell_blocks(cell.blocks)

    if cell.style:
        if cell.style.bold:
            content = f"<strong>{content}</strong>"
        if cell.style.italic:
            content = f"<em>{content}</em>"

    return f"<{tag}{attr_str}>{content}</{tag}>"


def _render_cell_blocks(blocks: list[Block]) -> str:
    if not blocks:
        return ""
    parts: list[str] = []
    for b in blocks:
        if isinstance(b, Paragraph):
            parts.append(_RENDER_SERIALIZER.serialize(b.children, target="html"))
        elif isinstance(b, Table):
            parts.append(_render_table_html(b))
        elif isinstance(b, ListBlock):
            items: list[str] = []
            tag = "ol" if b.ordered else "ul"
            for item in b.items:
                item_html = _render_cell_blocks(list(item))
                items.append(f"<li>{item_html}</li>")
            parts.append(f"<{tag}>{''.join(items)}</{tag}>")
        elif isinstance(b, MathBlock):
            body = b.text.strip()
            parts.append(f"$${body}$$")
        elif isinstance(b, CodeBlock):
            parts.append(f"<code>{_html_escape(b.text)}</code>")
        elif isinstance(b, RawLatex):
            parts.append(_html_escape(b.text))
        elif isinstance(b, QuoteBlock):
            inner = _render_cell_blocks(list(b.blocks))
            parts.append(f"<blockquote>{inner}</blockquote>")
        elif isinstance(b, Heading):
            level = max(1, min(6, b.level or 2))
            text = _RENDER_SERIALIZER.serialize(b.children, target="html")
            parts.append(f"<h{level}>{text}</h{level}>")
        elif isinstance(b, Figure):
            cap = (
                _RENDER_SERIALIZER.serialize(b.caption, target="html")
                if b.caption
                else ""
            )
            for img in b.images:
                parts.append(
                    f'<img src="{_attr_escape(img)}" alt="{_attr_escape(cap)}">'
                )
        else:
            parts.append(_html_escape(str(b)))
    return "<br>".join(p for p in parts if p)


def _render_figure(block: Figure) -> str:

    if block.raw_latex is not None:
        return _render_raw_figure_placeholder(block)
    caption = _render_inline(block.caption).strip()

    sources = list(block.images) if block.images else list(block.graphics)
    parts: list[str] = []
    for src in sources:
        parts.append(f"![{caption}]({src})")
    if not parts and caption:
        parts.append(caption)
    return "\n\n".join(parts)


def _render_raw_figure_placeholder(block: Figure) -> str:
    caption = _render_inline(block.caption).strip()
    kind = _raw_figure_kind(block.raw_latex or "")
    placeholder = f"[{kind} figure: {caption}]" if caption else f"[{kind} figure]"
    summary = f"Show {kind} source"
    raw = block.raw_latex or ""
    return (
        f"{placeholder}\n\n"
        "<details>\n"
        f"<summary>{summary}</summary>\n\n"
        f"```latex\n{raw}\n```\n\n"
        "</details>"
    )


def _raw_figure_kind(raw: str) -> str:
    pgfplots_envs = ("pgfplots", "axis", "semilogxaxis", "semilogyaxis", "loglogaxis")
    if any(f"\\begin{{{name}}}" in raw for name in pgfplots_envs):
        return "PGFPlots"
    return "TikZ"


def _render_bib(entry: BibEntry) -> str:
    if entry.key:
        return f"- [{entry.key}] {entry.text}".rstrip()
    return f"- {entry.text}".rstrip()
