from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from arxiv_md.tex._common import warning
from arxiv_md.tex.ast import Command, Env, Group, Math, Node, Verbatim
from arxiv_md.tex.handler_types import TransformContextProtocol
from arxiv_md.tex.model import (
    Block,
    Paragraph,
    RawLatex,
    Table,
    TableCell,
    TableCellStyle,
    TableColumn,
    TableRow,
    TableRowStyle,
    TableRule,
    TableSection,
    TableStyle,
)
from arxiv_md.tex.table_types import (
    CaptionPosition,
    parse_align_optional,
    parse_rule_kind,
    parse_section_kind,
)
from arxiv_md.tex.tables import (
    ARRAYRULECOLOR_RE,
    FONT_SIZE_COMMANDS,
    SPACING_COMMANDS,
    ParsedCell,
    ParsedColumn,
    ParsedRow,
    ParsedRule,
    ParsedTable,
    _drop_rowcolor,
    _flatten_makecell,
    parse_tabular,
)

_TABLE_WRAPPER_COMMANDS = frozenset({"resizebox", "scalebox", "adjustbox"})
_TABLE_WRAPPER_ENVS = frozenset({"adjustbox"})


_MAX_TABLE_DEPTH = 4


_table_depth = 0

_MULTIROW_FULL = re.compile(
    r"\s*\\multirow\*?\{(\d+|\*)\}\{[^{}]*\}\{(.*)\}\s*",
    re.S,
)
_MULTICOL_FULL = re.compile(
    r"\s*\\multicolumn\{(\d+)\}\{([^{}]*)\}\{(.*)\}\s*",
    re.S,
)


@dataclass(frozen=True)
class _TableMeta:
    caption_node: Group | None
    label: str
    tabular_env: Env | None


def _caption_arg(command: Command) -> Group | None:
    if command.name == "caption" and command.args:
        return command.args[0]
    return None


def _label_text(command: Command, ctx: TransformContextProtocol) -> str:
    if command.name == "label" and command.args:
        return ctx.inline_markdown(command.args[0].children).strip()
    return ""


def _tabular_env_or_none(node: Node, tabular_envs: frozenset[str]) -> Env | None:
    if isinstance(node, Env) and node.name in tabular_envs:
        return node
    return None


def _scan_table_metadata(
    env: Env,
    ctx: TransformContextProtocol,
    tabular_envs: frozenset[str],
) -> _TableMeta:
    from arxiv_md.tex.transform.blocks import walk_inside

    caption_node: Group | None = None
    label = ""
    tabular_env: Env | None = None
    for node in walk_inside(env):
        if isinstance(node, Command):
            caption_node = caption_node or _caption_arg(node)
            label = label or _label_text(node, ctx)
        elif tabular_env is None:
            tabular_env = _tabular_env_or_none(node, tabular_envs)
    return _TableMeta(caption_node, label, tabular_env)


def _find_wrapped_tabular_env(
    nodes: list[Node], tabular_envs: frozenset[str]
) -> Env | None:
    for node in nodes:
        if isinstance(node, Command) and node.name in _TABLE_WRAPPER_COMMANDS:
            for group in _wrapper_body_groups(node):
                found = _find_first_tabular_env(group.children, tabular_envs)
                if found is not None:
                    return found
        if isinstance(node, Env) and node.name in _TABLE_WRAPPER_ENVS:
            found = _find_first_tabular_env(node.body, tabular_envs)
            if found is not None:
                return found
        child_nodes = _node_children(node)
        if child_nodes:
            found = _find_wrapped_tabular_env(child_nodes, tabular_envs)
            if found is not None:
                return found
    return None


def _wrapper_body_groups(cmd: Command) -> list[Group]:
    if cmd.name == "resizebox" and len(cmd.args) >= 3:
        return [cmd.args[2]]
    if cmd.name == "scalebox" and len(cmd.args) >= 2:
        return [cmd.args[-1]]
    if cmd.name == "adjustbox" and len(cmd.args) >= 2:
        return [cmd.args[1]]
    return []


def _find_first_tabular_env(
    nodes: list[Node], tabular_envs: frozenset[str]
) -> Env | None:
    for node in nodes:
        if isinstance(node, Env) and node.name in tabular_envs:
            return node
        child_nodes = _node_children(node)
        if child_nodes:
            found = _find_first_tabular_env(child_nodes, tabular_envs)
            if found is not None:
                return found
    return None


def _node_children(node: Node) -> list[Node]:
    if isinstance(node, Env):
        out: list[Node] = list(node.body)
        for group in (*node.args, *node.opt_args):
            out.extend(group.children)
        return out
    if isinstance(node, Command):
        out = []
        for group in (*node.args, *node.opt_args):
            out.extend(group.children)
        return out
    if isinstance(node, Group):
        return list(node.children)
    return []


def _map_column(pc: ParsedColumn) -> TableColumn:
    return TableColumn(
        align=pc.align if pc.align in ("left", "center", "right") else "left",
        width=pc.width,
        separator_left=pc.separator_left,
        separator_right=pc.separator_right,
    )


def _map_rule(pr: ParsedRule) -> TableRule:
    return TableRule(
        kind=parse_rule_kind(pr.kind),
        col_start=pr.col_start,
        col_end=pr.col_end,
        trim_left=pr.trim_left,
        trim_right=pr.trim_right,
    )


@dataclass(slots=True)
class _MultiSpanResult:
    nodes: list[Node]
    colspan: int
    rowspan: int
    align: str | None


def _preprocess_cell_text(raw: str) -> str:

    text = _flatten_makecell(raw)
    text = FONT_SIZE_COMMANDS.sub("", text)
    text = ARRAYRULECOLOR_RE.sub("", text)
    text = _drop_rowcolor(text)
    return SPACING_COMMANDS.sub("", text)


def _parse_and_expand(
    text: str,
    extra_signatures: dict[str, str],
    macros: Any,
    has_macros: bool,
) -> list[Node]:
    from arxiv_md.tex.lexer import Diagnostics, tokenize
    from arxiv_md.tex.macro_engine import expand as macro_expand_ast
    from arxiv_md.tex.parser import parse as ast_parse

    diag = Diagnostics()
    tokens = tokenize(text, diag)
    nodes = ast_parse(
        tokens,
        diag,
        source_text=text,
        extra_signatures=extra_signatures,
    )
    if has_macros:
        nodes = macro_expand_ast(nodes, macros, diag)
    return nodes


def _align_from_colspec(colspec: str) -> str | None:
    if "c" in colspec:
        return "center"
    if "r" in colspec:
        return "right"
    if "l" in colspec:
        return "left"
    return None


def _reparse_multispan(
    flattened: str,
    nodes: list[Node],
    colspan: int,
    rowspan: int,
    align: str | None,
    macros: Any,
    extra_signatures: dict[str, str],
    has_macros: bool,
) -> _MultiSpanResult:
    multirow_m = _MULTIROW_FULL.fullmatch(flattened)
    if multirow_m:
        if multirow_m.group(1).isdigit():
            rowspan = int(multirow_m.group(1))
        inner = multirow_m.group(2)
        nodes = _parse_and_expand(inner, extra_signatures, macros, has_macros)
        flattened = inner

    multicol_m = _MULTICOL_FULL.fullmatch(flattened)
    if multicol_m:
        colspan = int(multicol_m.group(1))
        colspec_align = _align_from_colspec(multicol_m.group(2))
        if colspec_align is not None:
            align = colspec_align
        inner = multicol_m.group(3)
        nodes = _parse_and_expand(inner, extra_signatures, macros, has_macros)

    return _MultiSpanResult(nodes, colspan, rowspan, align)


def _route_cell_content(
    nodes: list[Node], ctx: TransformContextProtocol
) -> list[Block]:
    from arxiv_md.tex.transform.blocks import walk_blocks

    has_block_nodes = any(
        isinstance(n, Env)
        or (isinstance(n, Verbatim) and not n.inline)
        or (isinstance(n, Math) and n.display)
        for n in nodes
    )
    if has_block_nodes:
        blocks = walk_blocks(ctx, nodes)
        if blocks:
            return blocks

    ir = ctx.inline_ir(nodes)
    if ir:
        return [Paragraph(children=ir)]
    return []


def _build_cell(
    parsed_cell: ParsedCell,
    ctx: TransformContextProtocol,
    *,
    expand_macros: bool = True,
) -> TableCell:
    from arxiv_md.tex.macro_engine import TRAILING_WS_SENTINEL, _flatten_node

    colspan = parsed_cell.colspan
    rowspan = parsed_cell.rowspan
    align = parsed_cell.align

    raw = parsed_cell.original_text
    if not raw.strip():
        return _make_cell([], colspan, rowspan, align, parsed_cell)

    preprocessed = _preprocess_cell_text(raw)
    if not preprocessed.strip():
        return _make_cell([], colspan, rowspan, align, parsed_cell)

    macros = ctx.macros
    extra_signatures: dict[str, str] = {}
    for name, m in macros.items():
        if m.argc <= 0:
            continue
        if m.default is not None:
            extra_signatures[name] = "o" + "m" * (m.argc - 1)
        else:
            extra_signatures[name] = "m" * m.argc
    has_macros = bool(macros) and expand_macros

    try:
        nodes = _parse_and_expand(preprocessed, extra_signatures, macros, has_macros)
        flattened = "".join(_flatten_node(n) for n in nodes)
        flattened = flattened.replace(TRAILING_WS_SENTINEL, " ")
        span_result = _reparse_multispan(
            flattened,
            nodes,
            colspan,
            rowspan,
            align,
            macros,
            extra_signatures,
            has_macros,
        )
        blocks = _route_cell_content(span_result.nodes, ctx)
        return _make_cell(
            blocks,
            span_result.colspan,
            span_result.rowspan,
            span_result.align,
            parsed_cell,
        )
    except Exception:
        blocks = [RawLatex(text=raw.strip(), env=None)]
        return _make_cell(blocks, colspan, rowspan, align, parsed_cell)


def _make_cell(
    blocks: list[Block],
    colspan: int,
    rowspan: int,
    align: str | None,
    parsed_cell: ParsedCell,
) -> TableCell:
    style: TableCellStyle | None = None
    if parsed_cell.style or align:
        align_map = {"left": "left", "center": "center", "right": "right"}
        style = TableCellStyle(
            align=parse_align_optional(align_map.get(align or "")),
            bold=parsed_cell.style.bold if parsed_cell.style else False,
            italic=parsed_cell.style.italic if parsed_cell.style else False,
        )

    return TableCell(
        blocks=blocks,
        colspan=colspan,
        rowspan=rowspan,
        is_header=parsed_cell.is_header,
        style=style,
    )


def _build_row(
    parsed_row: ParsedRow,
    ctx: TransformContextProtocol,
    *,
    expand_macros: bool = True,
) -> TableRow:
    cells = [
        _build_cell(pc, ctx, expand_macros=expand_macros) for pc in parsed_row.cells
    ]

    row_style: TableRowStyle | None = None
    if parsed_row.style and parsed_row.style.background:
        row_style = TableRowStyle(background=parsed_row.style.background)

    return TableRow(
        cells=cells,
        is_header=parsed_row.is_header,
        style=row_style,
    )


def _build_table_from_parsed(
    parsed: ParsedTable,
    ctx: TransformContextProtocol,
    *,
    caption_ir: list | None = None,
    label: str | None = None,
    source_env: str | None = None,
    caption_position: CaptionPosition = "unknown",
    style: TableStyle | None = None,
    expand_macros: bool = True,
) -> Table:
    columns = [_map_column(c) for c in parsed.columns]

    sections: list[TableSection] = []
    for ps in parsed.sections:
        rows = [_build_row(pr, ctx, expand_macros=expand_macros) for pr in ps.rows]
        sections.append(
            TableSection(
                kind=parse_section_kind(ps.kind),
                rows=rows,
            )
        )

    return Table(
        parse_status="structured",
        sections=sections,
        columns=columns,
        caption=caption_ir or [],
        label=label,
        source_env=source_env or parsed.source_env,
        caption_position=caption_position,
        parse_warnings=list(parsed.parse_warnings),
        style=style,
    )


def _try_build_table(
    raw: str,
    ctx: TransformContextProtocol,
    *,
    caption_ir: list | None = None,
    label: str | None = None,
    source_env: str | None = None,
    caption_position: CaptionPosition = "unknown",
    style: TableStyle | None = None,
    expand_macros: bool = True,
) -> Table | None:
    global _table_depth

    depth_limit = getattr(ctx.limits, "max_table_nesting_depth", _MAX_TABLE_DEPTH)
    if _table_depth >= depth_limit:
        return None

    parsed = parse_tabular(raw)
    if parsed.failure_reason:
        return None

    _table_depth += 1
    try:
        return _build_table_from_parsed(
            parsed,
            ctx,
            caption_ir=caption_ir,
            label=label,
            source_env=source_env,
            caption_position=caption_position,
            style=style,
            expand_macros=expand_macros,
        )
    finally:
        _table_depth -= 1


def _try_build_from_candidates(
    raw_candidates: list[tuple[str, bool]],
    ctx: TransformContextProtocol,
    *,
    caption_ir: list | None,
    label: str | None,
    source_env: str,
    caption_position: CaptionPosition,
    style: TableStyle | None,
) -> Table | None:
    for raw, wrapped in raw_candidates:
        table = _try_build_table(
            raw,
            ctx,
            caption_ir=caption_ir,
            label=label,
            source_env=source_env,
            caption_position=caption_position,
            style=style,
        )
        if table is None and wrapped:
            table = _try_build_table(
                raw,
                ctx,
                caption_ir=caption_ir,
                label=label,
                source_env=source_env,
                caption_position=caption_position,
                style=style,
                expand_macros=False,
            )
        if table is not None:
            return table
    return None


def _append_raw_candidate(
    raw_candidates: list[tuple[str, bool]],
    ctx: TransformContextProtocol,
    env: Env,
    *,
    wrapped: bool,
) -> None:
    raw = ctx.env_full_raw(env)
    if raw:
        raw_candidates.append((raw, wrapped))


def _raw_table_candidates(
    ctx: TransformContextProtocol,
    wrapped_tabular_env: Env | None,
    tabular_env: Env | None,
) -> list[tuple[str, bool]]:
    raw_candidates: list[tuple[str, bool]] = []
    if wrapped_tabular_env is not None:
        _append_raw_candidate(raw_candidates, ctx, wrapped_tabular_env, wrapped=True)
    if tabular_env is not None and tabular_env is not wrapped_tabular_env:
        _append_raw_candidate(raw_candidates, ctx, tabular_env, wrapped=False)
    return raw_candidates


def _longtable_caption_position(body: list[Node]) -> CaptionPosition:
    from arxiv_md.tex.ast import Text

    caption_idx: int | None = None
    content_idx: int | None = None
    for i, node in enumerate(body):
        if isinstance(node, Command) and node.name == "caption":
            if caption_idx is None:
                caption_idx = i
        elif isinstance(node, Text) and not node.value.strip():
            continue
        elif isinstance(node, Command) and node.name in (
            "label",
            "hline",
            "toprule",
            "midrule",
            "bottomrule",
            "endhead",
            "endfirsthead",
            "endfoot",
            "endlastfoot",
        ):
            continue
        else:
            if content_idx is None:
                content_idx = i
    if caption_idx is None:
        return "unknown"
    if content_idx is None:
        return "top"
    return "top" if caption_idx < content_idx else "bottom"


def _detect_wrapper(nodes: list[Node]) -> str | None:
    for node in nodes:
        if isinstance(node, Command) and node.name in _TABLE_WRAPPER_COMMANDS:
            return node.name
        if isinstance(node, Env) and node.name in _TABLE_WRAPPER_ENVS:
            return node.name
    return None


def _caption_position_from_body(
    env_body: list[Node],
    tabular_envs: frozenset[str],
) -> CaptionPosition:
    caption_pos: int | None = None
    tabular_pos: int | None = None
    for i, node in enumerate(env_body):
        if isinstance(node, Command) and node.name == "caption" and caption_pos is None:
            caption_pos = i
        elif (
            isinstance(node, Env) and node.name in tabular_envs and tabular_pos is None
        ):
            tabular_pos = i

        elif isinstance(node, Command) and node.name in _TABLE_WRAPPER_COMMANDS:
            if tabular_pos is None:
                tabular_pos = i

    if caption_pos is None or tabular_pos is None:
        return "unknown"
    return "top" if caption_pos < tabular_pos else "bottom"


def table_wrapper_env(env: Env, ctx: TransformContextProtocol) -> list[Block]:
    from arxiv_md.tex.transform.blocks import TABULAR_ENVS

    meta = _scan_table_metadata(env, ctx, TABULAR_ENVS)
    wrapped_tabular_env = _find_wrapped_tabular_env(env.body, TABULAR_ENVS)
    caption_ir = ctx.inline_ir(meta.caption_node.children) if meta.caption_node else []

    cap_pos = _caption_position_from_body(env.body, TABULAR_ENVS)
    wrapper_name = _detect_wrapper(env.body)
    style = TableStyle(wrapper=wrapper_name) if wrapper_name else None

    raw_candidates = _raw_table_candidates(ctx, wrapped_tabular_env, meta.tabular_env)

    table = _try_build_from_candidates(
        raw_candidates,
        ctx,
        caption_ir=caption_ir,
        label=meta.label or None,
        source_env=env.name,
        caption_position=cap_pos,
        style=style,
    )
    if table is not None:
        return [table]

    ctx.diag.warnings.append(
        warning("table_raw_fallback", "Table preserved as raw LaTeX")
    )
    return [
        Table(
            parse_status="raw_fallback",
            raw_latex=ctx.env_full_raw(env).strip(),
            caption=caption_ir,
            label=meta.label or None,
            source_env=env.name,
            caption_position=cap_pos,
            style=style,
        )
    ]


def longtable_env(env: Env, ctx: TransformContextProtocol) -> list[Block]:
    from arxiv_md.tex.transform.blocks import walk_inside

    caption_node: Group | None = None
    label = ""

    cap_pos = _longtable_caption_position(env.body)
    for n in walk_inside(env):
        if isinstance(n, Command):
            if n.name == "caption" and n.args and caption_node is None:
                caption_node = n.args[0]
            elif n.name == "label" and n.args and not label:
                label = ctx.inline_markdown(n.args[0].children).strip()
    caption_ir = ctx.inline_ir(caption_node.children) if caption_node else []

    raw = ctx.env_full_raw(env)
    table = (
        _try_build_table(
            raw,
            ctx,
            caption_ir=caption_ir,
            label=label or None,
            source_env=env.name,
            caption_position=cap_pos,
        )
        if raw
        else None
    )

    if table is not None:
        return [table]

    ctx.diag.warnings.append(
        warning("table_raw_fallback", "Table preserved as raw LaTeX")
    )
    return [
        Table(
            parse_status="raw_fallback",
            raw_latex=raw.strip() if raw else "",
            caption=caption_ir,
            label=label or None,
            source_env=env.name,
            caption_position=cap_pos,
        )
    ]


def tabular_standalone(env: Env, ctx: TransformContextProtocol) -> list[Block]:
    from arxiv_md.tex.transform.blocks import walk_inside

    raw = ctx.env_full_raw(env)
    if not raw:
        return []
    label = ""
    for n in walk_inside(env):
        if isinstance(n, Command) and n.name == "label" and n.args and not label:
            label = ctx.inline_markdown(n.args[0].children).strip()

    table = _try_build_table(
        raw,
        ctx,
        caption_ir=[],
        label=label or None,
        source_env=env.name,
    )
    if table is not None:
        return [table]

    ctx.diag.warnings.append(
        warning("table_raw_fallback", "Table preserved as raw LaTeX")
    )
    return [
        Table(
            parse_status="raw_fallback",
            raw_latex=raw.strip(),
            caption=[],
            label=label or None,
            source_env=env.name,
        )
    ]
