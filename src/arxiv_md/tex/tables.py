from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from arxiv_md.tex.reader import find_environment_end, read_braced_group as _read_group
from arxiv_md.tex.table_types import (
    TableAlign,
    TableSectionKind,
    TableVAlign,
    parse_align,
    parse_section_kind,
    parse_valign,
)


CellProcessor = Callable[[str], tuple[str, int, int] | None]
"""Legacy combined cell processor kept for backward compat in handler bridge.
raw cell text → (rendered_html, colspan, rowspan) or None to trigger fallback.
"""
MathToText = Callable[[str], str | None]
"""Map math body (no ``$``) to unicode glyph, or None for ``$body$`` fallback."""


@dataclass(slots=True)
class ParsedColumn:
    align: TableAlign = "left"
    width: str | None = None
    valign: TableVAlign | None = None
    separator_left: str = ""
    separator_right: str = ""
    raw_spec: str = ""


@dataclass(slots=True)
class ParsedRule:
    kind: str = "hline"
    col_start: int | None = None
    col_end: int | None = None
    trim_left: bool = False
    trim_right: bool = False
    thickness: str | None = None
    color: str | None = None


@dataclass(slots=True)
class CellStyle:
    background: str | None = None
    font_size: str | None = None
    bold: bool = False
    italic: bool = False


@dataclass(slots=True)
class RowStyle:
    background: str | None = None
    font_size: str | None = None


@dataclass(slots=True)
class ParsedCell:
    raw_text: str = ""
    original_text: str = ""
    colspan: int = 1
    rowspan: int = 1
    is_header: bool = False
    align: str | None = None
    style: CellStyle | None = None


@dataclass(slots=True)
class ParsedRow:
    cells: list[ParsedCell] = field(default_factory=list)
    is_header: bool = False
    style: RowStyle | None = None
    rules_before: list[ParsedRule] = field(default_factory=list)


@dataclass(slots=True)
class ParsedSection:
    kind: TableSectionKind = "body"
    rows: list[ParsedRow] = field(default_factory=list)


@dataclass(slots=True)
class ParsedTable:
    columns: list[ParsedColumn] = field(default_factory=list)
    sections: list[ParsedSection] = field(default_factory=list)
    rules_after: list[ParsedRule] = field(default_factory=list)
    source_env: str | None = None
    parse_warnings: list[str] = field(default_factory=list)
    failure_reason: str | None = None


_COLSPEC_TOKEN = re.compile(
    r"""
    @\{[^{}]*\}         # @{...} inter-column material
    | !\{[^{}]*\}       # !{...} inter-column material
    | [>]\{[^{}]*\}     # >{...} before-column decl
    | [<]\{[^{}]*\}     # <{...} after-column decl
    | [pmb]\{[^{}]*\}   # p{width}, m{width}, b{width}
    | \|                 # vertical rule
    | \|\|              # double vertical rule
    | [lcrXS]           # simple alignment
    | \*\{(\d+)\}\{([^{}]*)\}  # *{n}{spec} repeat
    """,
    re.VERBOSE,
)


def parse_colspec(spec: str) -> list[ParsedColumn]:

    expanded = _expand_star_repeats(spec)
    return _parse_colspec_tokens(expanded)


def _expand_star_repeats(spec: str) -> str:
    star_re = re.compile(r"\*\{(\d+)\}\{([^{}]*)\}")
    while star_re.search(spec):
        spec = star_re.sub(lambda m: m.group(2) * int(m.group(1)), spec)
    return spec


_VALIGN_BY_SPEC = {"p": "top", "m": "middle", "b": "bottom"}
_ALIGN_BY_SPEC = {
    "l": "left",
    "c": "center",
    "r": "right",
    "X": "unknown",
    "S": "decimal",
}


@dataclass(slots=True)
class _ColspecParseState:
    columns: list[ParsedColumn] = field(default_factory=list)
    pending_sep_left: str = ""

    def add_vertical_rule(self) -> None:
        if self.columns:
            self.columns[-1].separator_right += "|"
        else:
            self.pending_sep_left += "|"

    def add_column(self, column: ParsedColumn) -> None:
        column.separator_left = self.pending_sep_left
        self.pending_sep_left = ""
        self.columns.append(column)

    def apply_trailing_separator(self) -> None:
        if self.pending_sep_left and self.columns:
            self.columns[-1].separator_right += self.pending_sep_left


def _parse_colspec_tokens(spec: str) -> list[ParsedColumn]:
    state = _ColspecParseState()
    i = 0

    while i < len(spec):
        c = spec[i]
        if c in " \t\n":
            i += 1
            continue
        i = _consume_colspec_token(spec, i, state)

    state.apply_trailing_separator()
    return state.columns


def _consume_colspec_token(
    spec: str,
    pos: int,
    state: _ColspecParseState,
) -> int:
    c = spec[pos]
    if c == "|":
        state.add_vertical_rule()
        return pos + 1
    if _is_braced_declaration(spec, pos):
        return _skip_braced_declaration(spec, pos)
    if _is_width_column(spec, pos):
        return _consume_width_column(spec, pos, state)
    if c in _ALIGN_BY_SPEC:
        state.add_column(ParsedColumn(align=parse_align(_ALIGN_BY_SPEC[c]), raw_spec=c))
    return pos + 1


def _is_braced_declaration(spec: str, pos: int) -> bool:
    return spec[pos] in "@!><" and pos + 1 < len(spec) and spec[pos + 1] == "{"


def _skip_braced_declaration(spec: str, pos: int) -> int:
    end = _find_matching_brace(spec, pos + 1)
    return end + 1 if end is not None else pos + 1


def _is_width_column(spec: str, pos: int) -> bool:
    return spec[pos] in _VALIGN_BY_SPEC and pos + 1 < len(spec) and spec[pos + 1] == "{"


def _consume_width_column(
    spec: str,
    pos: int,
    state: _ColspecParseState,
) -> int:
    end = _find_matching_brace(spec, pos + 1)
    c = spec[pos]
    width = spec[pos + 2 : end] if end is not None else None
    raw_spec = spec[pos : end + 1] if end is not None else c
    state.add_column(
        ParsedColumn(
            align="left",
            width=width,
            valign=parse_valign(_VALIGN_BY_SPEC.get(c)),
            raw_spec=raw_spec,
        )
    )
    return end + 1 if end is not None else pos + 1


def _find_matching_brace(text: str, pos: int) -> int | None:
    if pos >= len(text) or text[pos] != "{":
        return None
    depth = 1
    i = pos + 1
    while i < len(text) and depth > 0:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    return i - 1 if depth == 0 else None


_RULE_CMD_RE = re.compile(
    r"\\(toprule|midrule|bottomrule|hline|Xhline|cmidrule|cline|specialrule|addlinespace)"
    r"(?:\[([^\]]*)\])?"
    r"(?:\(([^)]*)\))?"
    r"(?:\{([^{}]*)\})?"
    r"(?:\{([^{}]*)\})?"
    r"(?:\{([^{}]*)\})?"
)


def _parse_rule_command(
    match: re.Match, current_color: str | None = None
) -> ParsedRule | None:
    kind = match.group(1)
    opt_bracket = match.group(2)
    trim_paren = match.group(3)
    first_brace = match.group(4)

    if kind == "addlinespace":
        return None

    rule = ParsedRule(kind=kind.lower() if kind != "Xhline" else "xhline")

    if kind in ("cline", "cmidrule") and first_brace:
        range_match = re.match(r"(\d+)-(\d+)", first_brace)
        if range_match:
            rule.col_start = int(range_match.group(1))
            rule.col_end = int(range_match.group(2))

    if kind == "cmidrule" and trim_paren:
        rule.trim_left = "l" in trim_paren
        rule.trim_right = "r" in trim_paren

    if kind == "specialrule" and first_brace:
        rule.thickness = first_brace
    elif kind == "Xhline" and first_brace:
        rule.thickness = first_brace
    elif opt_bracket:
        rule.thickness = opt_bracket

    if current_color:
        rule.color = current_color

    return rule


_RULE_FULL_RE = re.compile(
    r"\\(toprule|midrule|bottomrule|hline|Xhline|cmidrule|cline|specialrule|addlinespace)"
    r"(?:\[[^\]]*\])?"
    r"(?:\([^)]*\))?"
    r"(?:\{[^{}]*\})*"
    r"\s*"
)


_ROWCOLOR_RE = re.compile(r"\\rowcolor(?:\[([^\]]*)\])?\{([^{}]*)\}\s*")
_CELLCOLOR_RE = re.compile(r"\\cellcolor(?:\[([^\]]*)\])?\{([^{}]*)\}\s*")
_FONT_SIZE_RE = re.compile(
    r"\\(tiny|scriptsize|footnotesize|small|normalsize"
    r"|large|Large|LARGE|huge|Huge)\b\s*"
)
_ARRAYRULECOLOR_RE = re.compile(r"\\arrayrulecolor(?:\[([^\]]*)\])?\{([^{}]*)\}\s*")
_NOALIGN_RE = re.compile(r"\\noalign\s*\{[^{}]*\}\s*")
_SPACING_COMMANDS_RE = re.compile(
    r"\\(?:vspace|hspace)\*?(?:\[[^\]]*\])?\s*\{[^{}]*\}\s*"
    r"|\\(?:smallskip|medskip|bigskip)\b\s*"
)


_NESTED_BLOCK_ENVS_RE = re.compile(
    r"\\begin\{(?:tabular\*?|tabularx|longtable|table\*?|figure\*?|"
    r"verbatim|lstlisting|minted)\}"
)


def _extract_rowcolor(text: str) -> tuple[str, str | None]:
    m = _ROWCOLOR_RE.search(text)
    if m:
        color = m.group(2)
        return _ROWCOLOR_RE.sub("", text), color
    return text, None


def _extract_cellcolor(text: str) -> tuple[str, str | None]:
    m = _CELLCOLOR_RE.search(text)
    if m:
        color = m.group(2)
        return _CELLCOLOR_RE.sub("", text), color
    return text, None


def _extract_font_size(text: str) -> tuple[str, str | None]:
    m = _FONT_SIZE_RE.search(text)
    if m:
        return _FONT_SIZE_RE.sub("", text), m.group(1)
    return text, None


@dataclass
class _DepthTracker:
    brace: int = 0
    env: int = 0
    dollar: bool = False
    ddollar: bool = False

    @property
    def _in_math(self) -> bool:
        return self.dollar or self.ddollar

    @property
    def at_top_level(self) -> bool:
        return self.brace == 0 and self.env == 0 and not self._in_math

    def _update_env(self, text: str, pos: int) -> int:
        if text[pos] != "\\":
            return 0
        if text[pos:].startswith("\\begin{"):
            self.env += 1
            end_brace = text.find("}", pos + 7)
            if end_brace >= 0:
                return end_brace + 1 - pos
        if text[pos:].startswith("\\end{"):
            self.env = max(0, self.env - 1)
            end_brace = text.find("}", pos + 5)
            if end_brace >= 0:
                return end_brace + 1 - pos
        return 0

    def update(self, text: str, pos: int) -> int:

        env_consumed = self._update_env(text, pos)
        if env_consumed:
            return env_consumed

        ch = text[pos]

        if ch == "{" and not self._in_math:
            self.brace += 1
        elif ch == "}" and not self._in_math:
            self.brace = max(0, self.brace - 1)

        if ch == "$":
            if pos + 1 < len(text) and text[pos + 1] == "$":
                self.ddollar = not self.ddollar
                return 2
            self.dollar = not self.dollar

        return 1


def _skip_row_break_tail(text: str, pos: int) -> int:
    i = pos
    n = len(text)
    while i < n and text[i] in " \t":
        i += 1
    if i < n and text[i] == "[":
        end = text.find("]", i + 1)
        if end >= 0:
            i = end + 1
    return i


def _split_rows_aware(body: str) -> list[str]:
    rows: list[str] = []
    current: list[str] = []
    tracker = _DepthTracker()
    i = 0
    n = len(body)

    while i < n:
        if (
            body[i] == "\\"
            and i + 1 < n
            and body[i + 1] == "\\"
            and tracker.at_top_level
        ):
            rows.append("".join(current))
            current = []
            i = _skip_row_break_tail(body, i + 2)
            continue

        consumed = tracker.update(body, i)
        current.append(body[i : i + consumed])
        i += consumed

    if current:
        trailing = "".join(current).strip()
        if trailing:
            rows.append("".join(current))
    return rows


def _split_cells_aware(row: str) -> list[str]:
    cells: list[str] = []
    current: list[str] = []
    tracker = _DepthTracker()
    i = 0

    while i < len(row):
        if row[i] == "&" and tracker.at_top_level:
            cells.append("".join(current))
            current = []
            i += 1
            continue

        consumed = tracker.update(row, i)
        current.append(row[i : i + consumed])
        i += consumed

    cells.append("".join(current))
    return cells


_TABINCELL_RE = re.compile(r"\\tabincell\{[^{}]*\}\{(.*?)\}", re.S)

_MAKECELL_RE = re.compile(r"\\makecell(?:\[[^\]]*\])?\{(.*?)\}", re.S)


def _flatten_nested_tabular(cell: str) -> str:
    _BEGIN = re.compile(r"\\begin\{(tabular\*?)\}")
    result: list[str] = []
    pos = 0
    while pos < len(cell):
        m = _BEGIN.search(cell, pos)
        if m is None:
            result.append(cell[pos:])
            break
        result.append(cell[pos : m.start()])
        env_name = m.group(1)
        end_tag = f"\\end{{{env_name}}}"
        cursor = m.end()

        while cursor < len(cell) and cell[cursor].isspace():
            cursor += 1
        if cursor < len(cell) and cell[cursor] == "[":
            close = cell.find("]", cursor + 1)
            if close >= 0:
                cursor = close + 1

        while cursor < len(cell) and cell[cursor].isspace():
            cursor += 1
        if cursor < len(cell) and cell[cursor] == "{":
            bdepth = 1
            cursor += 1
            while cursor < len(cell) and bdepth > 0:
                if cell[cursor] == "{":
                    bdepth += 1
                elif cell[cursor] == "}":
                    bdepth -= 1
                cursor += 1
        end_pos = cell.find(end_tag, cursor)
        if end_pos < 0:
            result.append(cell[m.start() :])
            break
        inner_body = cell[cursor:end_pos]
        inner_body = re.sub(r"\\\\\s*(?:\[[^\]]*\])?\s*", " ", inner_body)
        result.append(inner_body.strip())
        pos = end_pos + len(end_tag)
    return "".join(result)


def _flatten_cell_structures(cell: str) -> str:

    def _join_lines(m: re.Match) -> str:
        inner = m.group(1)
        inner = re.sub(r"\\\\\s*(?:\[[^\]]*\])?\s*", " ", inner)
        return inner.strip()

    cell = _flatten_nested_tabular(cell)
    cell = _TABINCELL_RE.sub(_join_lines, cell)
    cell = _MAKECELL_RE.sub(_join_lines, cell)
    return cell


def _flatten_makecell(cell: str) -> str:

    def _join_lines(m: re.Match) -> str:
        inner = m.group(1)
        inner = re.sub(r"\\\\\s*(?:\[[^\]]*\])?\s*", " ", inner)
        return inner.strip()

    cell = _TABINCELL_RE.sub(_join_lines, cell)
    cell = _MAKECELL_RE.sub(_join_lines, cell)
    return cell


_MULTIROW_FULL = re.compile(r"\s*\\multirow\*?\{(\d+|\*)\}\{[^{}]*\}\{(.*)\}\s*", re.S)
_MULTIROW_SUB = re.compile(r"\\multirow\*?\{[^{}]*\}\{[^{}]*\}\{([^{}]*)\}")
_MULTICOL_FULL = re.compile(r"\s*\\multicolumn\{(\d+)\}\{([^{}]*)\}\{(.*)\}\s*", re.S)


def _parse_cell_content(raw: str) -> ParsedCell:
    original = raw.strip()
    cell = _flatten_cell_structures(original)

    cell, cell_bg = _extract_cellcolor(cell)
    cell, cell_fs = _extract_font_size(cell)
    cell = _SPACING_COMMANDS_RE.sub("", cell)

    style: CellStyle | None = None
    if cell_bg or cell_fs:
        style = CellStyle(background=cell_bg, font_size=cell_fs)

    rowspan = 1
    multirow = _MULTIROW_FULL.fullmatch(cell)
    if multirow:
        if multirow.group(1).isdigit():
            rowspan = int(multirow.group(1))
        cell = multirow.group(2)
    else:
        cell = _MULTIROW_SUB.sub(r"\1", cell)

    colspan = 1
    align: str | None = None
    multicol = _MULTICOL_FULL.fullmatch(cell)
    if multicol:
        colspan = int(multicol.group(1))
        mc_spec = multicol.group(2).strip()

        for ch in mc_spec:
            if ch in "lcr":
                align = {"l": "left", "c": "center", "r": "right"}[ch]
                break
        cell = multicol.group(3)

    return ParsedCell(
        raw_text=cell.strip(),
        original_text=original,
        colspan=colspan,
        rowspan=rowspan,
        align=align,
        style=style,
    )


# Map LaTeX marker -> (section_kind, role).
# role distinguishes which copy wins when a longtable defines both:
#   - "first" (firsthead) takes precedence over "repeat" (head)
#   - "last" (lastfoot) takes precedence over "repeat" (foot)
_LONGTABLE_MARKERS: dict[str, tuple[str, str]] = {
    "endfirsthead": ("head", "first"),
    "endhead": ("head", "repeat"),
    "endfoot": ("foot", "repeat"),
    "endlastfoot": ("foot", "last"),
}

_LONGTABLE_MARKER_RE = re.compile(r"\\(endfirsthead|endhead|endfoot|endlastfoot)\s*")

# Stripped from longtable body before row splitting so caption/label do not
# leak into the first head row as cell text.
_LONGTABLE_STRIP_COMMANDS = ("caption", "label")
_LONGTABLE_CMD_RE = re.compile(
    r"\\(?:" + "|".join(_LONGTABLE_STRIP_COMMANDS) + r")\*?\s*[\[{]"
)


def _strip_longtable_meta_commands(body: str) -> str:
    out: list[str] = []
    i = 0
    n = len(body)
    while i < n:
        m = _LONGTABLE_CMD_RE.search(body, i)
        if m is None:
            out.append(body[i:])
            break
        out.append(body[i : m.start()])
        j = m.end() - 1  # position of the opening bracket/brace
        opener = body[j]
        closer = "]" if opener == "[" else "}"
        depth = 0
        while j < n:
            ch = body[j]
            if ch == "\\" and j + 1 < n:
                j += 2
                continue
            if ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    j += 1
                    break
            j += 1
        # If trailing optional [...] follows a \caption[...]{...}, drop it too.
        if opener == "[" and j < n and body[j] == "{":
            depth = 0
            while j < n:
                ch = body[j]
                if ch == "\\" and j + 1 < n:
                    j += 2
                    continue
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
                j += 1
        i = j
    return "".join(out)


def _extract_tabular(raw: str) -> tuple[str, str, str] | None:
    match = re.search(r"\\begin\{(tabular\*?|tabularx|array|longtable|tabu)\}", raw)
    if not match:
        return None
    env = match.group(1)
    pos = match.end()

    while pos < len(raw) and raw[pos].isspace():
        pos += 1
    while pos < len(raw) and raw[pos] == "[":
        end = raw.find("]", pos + 1)
        if end < 0:
            return None
        pos = end + 1
        while pos < len(raw) and raw[pos].isspace():
            pos += 1

    if env in {"tabular*", "tabularx"}:
        width = _read_group(raw, pos)
        if width is None:
            return None
        pos = width[1]

    spec = _read_group(raw, pos)
    if spec is None:
        return None

    close = find_environment_end(raw, env, spec[1])
    if close is None:
        return None

    return env, spec[0], close[0]


def parse_tabular(raw: str) -> ParsedTable:
    try:
        return _parse_tabular_inner(raw)
    except Exception as exc:
        return ParsedTable(
            failure_reason=f"parse error: {exc}",
            parse_warnings=[f"Unhandled parse error: {exc}"],
        )


def _parse_tabular_inner(raw: str) -> ParsedTable:
    extracted = _extract_tabular(raw)
    if extracted is None:
        return ParsedTable(failure_reason="no tabular environment found")

    env_name, colspec_str, body = extracted
    columns = parse_colspec(colspec_str)
    is_longtable = env_name == "longtable"

    current_color: str | None = None

    body = re.sub(r"\\cr\b", r"\\\\", body)

    if is_longtable:
        body = _strip_longtable_meta_commands(body)

    raw_rows = _split_rows_aware(body)

    all_rows: list[ParsedRow] = []
    pending_rules: list[ParsedRule] = []
    # (section_kind, role, row_idx) — role distinguishes first/repeat/last.
    longtable_sections: list[tuple[str, str, int]] = []

    for raw_row in raw_rows:
        row_text = raw_row.strip()
        if not row_text:
            continue

        for m in _ARRAYRULECOLOR_RE.finditer(row_text):
            current_color = m.group(2)
        row_text = _ARRAYRULECOLOR_RE.sub("", row_text)

        row_text = _NOALIGN_RE.sub("", row_text)

        rules_in_row: list[ParsedRule] = []
        for m in _RULE_CMD_RE.finditer(row_text):
            rule = _parse_rule_command(m, current_color)
            if rule is not None:
                rules_in_row.append(rule)
        row_text = _RULE_FULL_RE.sub("", row_text)

        row_text = _SPACING_COMMANDS_RE.sub("", row_text)

        lt_markers = list(_LONGTABLE_MARKER_RE.finditer(row_text))
        for lt_m in lt_markers:
            marker_kind, marker_role = _LONGTABLE_MARKERS[lt_m.group(1)]
            longtable_sections.append((marker_kind, marker_role, len(all_rows)))
        row_text = _LONGTABLE_MARKER_RE.sub("", row_text)

        row_text = row_text.strip()
        if not row_text:
            pending_rules.extend(rules_in_row)
            continue

        row_text, row_bg = _extract_rowcolor(row_text)
        row_style: RowStyle | None = None
        if row_bg:
            row_style = RowStyle(background=row_bg)

        raw_cells = _split_cells_aware(row_text)
        if all(not c.strip() for c in raw_cells):
            pending_rules.extend(rules_in_row)
            continue

        parsed_cells = [_parse_cell_content(c) for c in raw_cells]

        prow = ParsedRow(
            cells=parsed_cells,
            style=row_style,
            rules_before=pending_rules + rules_in_row,
        )
        pending_rules = []
        all_rows.append(prow)

    trailing_rules = pending_rules

    if is_longtable and longtable_sections:
        sections = _build_longtable_sections(all_rows, longtable_sections)
    else:
        sections = [ParsedSection(kind="body", rows=all_rows)]

    return ParsedTable(
        columns=columns,
        sections=sections,
        rules_after=trailing_rules,
        source_env=env_name,
    )


# Priority for which copy of a section wins when a longtable provides both
# a first/last variant and a repeat variant. Higher number wins.
_LONGTABLE_ROLE_PRIORITY = {"repeat": 0, "first": 1, "last": 1}


def _build_longtable_sections(
    rows: list[ParsedRow],
    markers: list[tuple[str, str, int]],
) -> list[ParsedSection]:
    if not markers:
        return [ParsedSection(kind="body", rows=rows)]

    # First slice rows at every marker boundary so we know which rows belong
    # to which marker. Body rows are everything after the last marker.
    sliced: list[tuple[str, str, list[ParsedRow]]] = []
    last_idx = 0
    for kind, role, row_idx in markers:
        section_rows = rows[last_idx:row_idx]
        sliced.append((kind, role, section_rows))
        last_idx = row_idx
    body_rows = rows[last_idx:]

    # Pick winning section per kind by role priority. Ties keep first occurrence.
    chosen: dict[str, tuple[int, str, list[ParsedRow]]] = {}
    for order, (kind, role, section_rows) in enumerate(sliced):
        prio = _LONGTABLE_ROLE_PRIORITY.get(role, 0)
        prev = chosen.get(kind)
        if prev is None or prio > prev[0]:
            chosen[kind] = (prio, role, section_rows)

    sections: list[ParsedSection] = []
    for kind in ("head", "foot"):
        if kind not in chosen:
            continue
        _prio, _role, section_rows = chosen[kind]
        if section_rows:
            sections.append(
                ParsedSection(kind=parse_section_kind(kind), rows=section_rows)
            )

    # Re-order so head comes before body and foot after; body is appended last
    # head, then body, then foot to match conventional <thead>/<tbody>/<tfoot>.
    head_section = next((s for s in sections if s.kind == "head"), None)
    foot_section = next((s for s in sections if s.kind == "foot"), None)
    ordered: list[ParsedSection] = []
    if head_section is not None:
        ordered.append(head_section)
    if body_rows:
        ordered.append(ParsedSection(kind="body", rows=body_rows))
    if foot_section is not None:
        ordered.append(foot_section)

    return ordered if ordered else [ParsedSection(kind="body", rows=rows)]


def render_tabular_html(
    tabular_raw: str,
    caption: str = "",
    *,
    cell_renderer: Callable[[str], str] | None = None,
    cell_preprocessor: Callable[[str], str] | None = None,
    cell_processor: CellProcessor | None = None,
    math_to_text: MathToText | None = None,
) -> str | None:
    result = parse_tabular(tabular_raw)
    if result.failure_reason:
        return None

    all_rows: list[list[tuple[str, int, int]]] = []
    for section in result.sections:
        for row in section.rows:
            rendered_cells: list[tuple[str, int, int]] = []
            for cell in row.cells:
                if cell_processor is not None:
                    processed = cell_processor(cell.original_text)
                    if processed is None:
                        return None
                    text, colspan, rowspan = processed
                else:
                    raw_text = cell.raw_text
                    if cell_preprocessor is not None:
                        raw_text = cell_preprocessor(raw_text)
                    if cell_renderer is not None:
                        text = cell_renderer(raw_text.strip())
                    else:
                        import html

                        text = html.escape(raw_text.strip())
                    colspan = cell.colspan
                    rowspan = cell.rowspan

                text = _restore_math_in_text(text, math_to_text)
                rendered_cells.append((text, colspan, rowspan))
            if rendered_cells:
                all_rows.append(rendered_cells)

    if not all_rows:
        return None

    out = ["<table>"]
    if caption:
        out.append(f"<caption>{caption}</caption>")
    out.append("<tbody>")
    for row_cells in all_rows:
        parts: list[str] = []
        for text, colspan, rowspan in row_cells:
            attr = f' colspan="{colspan}"' if colspan > 1 else ""
            if rowspan > 1:
                attr += f' rowspan="{rowspan}"'
            parts.append(f"<td{attr}>{text}</td>")
        out.append("<tr>" + "".join(parts) + "</tr>")
    out.append("</tbody>")
    out.append("</table>")
    return "\n".join(out)


_MATH_INLINE_RE = re.compile(r"\$([^$]+)\$")
_MATH_PAREN_RE = re.compile(r"\\\((.+?)\\\)", re.S)
_MATH_BRACKET_RE = re.compile(r"\\\[(.+?)\\\]", re.S)
_MATH_DDOLLAR_RE = re.compile(r"\$\$(.+?)\$\$", re.S)


def _restore_math_in_text(text: str, math_to_text: MathToText | None) -> str:
    if math_to_text is None:
        return text

    def _repl_body(body: str) -> str:
        rendered = math_to_text(body.strip())
        return rendered if rendered is not None else f"${body.strip()}$"

    text = _MATH_PAREN_RE.sub(lambda m: _repl_body(m.group(1)), text)
    text = _MATH_BRACKET_RE.sub(lambda m: _repl_body(m.group(1)), text)
    text = _MATH_DDOLLAR_RE.sub(lambda m: _repl_body(m.group(1)), text)
    text = _MATH_INLINE_RE.sub(lambda m: _repl_body(m.group(1)), text)
    return text


RULE_COMMANDS = _RULE_FULL_RE
NOALIGN_RE = _NOALIGN_RE
SPACING_COMMANDS = _SPACING_COMMANDS_RE
FONT_SIZE_COMMANDS = _FONT_SIZE_RE
ARRAYRULECOLOR_RE = _ARRAYRULECOLOR_RE


def _drop_rowcolor(text: str) -> str:
    text = _ROWCOLOR_RE.sub("", text)
    return _CELLCOLOR_RE.sub("", text)
