from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from arxiv_md.tex._common import TexWarning, warning

MAX_ARGS = 9
COMMAND_RE = re.compile(r"\\([A-Za-z@]+|.)")


@dataclass(slots=True)
class Macro:
    name: str
    argc: int
    body: str
    default: str | None = None


@dataclass(slots=True)
class MacroCollectResult:
    macros: dict[str, Macro]
    stripped: str
    remove_ranges: list[tuple[int, int]] = field(default_factory=list)


_MacroParseResult = tuple[Macro | None, int]
_MacroDefParser = Callable[..., _MacroParseResult | None]


@dataclass(slots=True, frozen=True)
class _MacroDefPattern:
    prefix: str
    parser: _MacroDefParser
    skip_len: int
    warning_message: str | None = None
    needs_macros: bool = False
    word_boundary: bool = False


def collect_macros(
    text: str, warnings: list[TexWarning] | None = None
) -> tuple[dict[str, Macro], str]:
    result = collect_macros_full(text, warnings)
    return result.macros, result.stripped


def collect_macros_full(
    text: str,
    warnings: list[TexWarning] | None = None,
) -> MacroCollectResult:
    warnings = warnings if warnings is not None else []
    macros: dict[str, Macro] = {}
    remove_ranges: list[tuple[int, int]] = []
    i = 0
    while i < len(text):
        comment_end = _skip_comment_line(text, i)
        if comment_end is not None:
            i = comment_end
            continue
        match = _try_match_definition(text, i, macros, warnings)
        if match is None:
            i += 1
            continue
        i = _record_definition_match(remove_ranges, match)
    return MacroCollectResult(
        macros=macros,
        stripped=_remove_ranges(text, remove_ranges),
        remove_ranges=remove_ranges,
    )


@dataclass(slots=True, frozen=True)
class StripOffsetMap:
    ranges: tuple[tuple[int, int], ...]
    inserted_positions: tuple[int, ...]
    deltas: tuple[int, ...]

    def translate(self, offset: int) -> int:
        if not self.ranges:
            return offset
        idx = _bisect_right(self.inserted_positions, offset) - 1
        if idx < 0:
            return offset
        if offset == self.inserted_positions[idx]:
            return self.ranges[idx][0]
        return offset + self.deltas[idx]


def build_strip_offset_map(remove_ranges: list[tuple[int, int]]) -> StripOffsetMap:
    if not remove_ranges:
        return StripOffsetMap(ranges=(), inserted_positions=(), deltas=())
    ordered = sorted(remove_ranges)
    inserted_positions: list[int] = []
    deltas: list[int] = []
    prior = 0
    for start, end in ordered:
        inserted_positions.append(start - prior)
        prior += (end - start) - 1
        deltas.append(prior)
    return StripOffsetMap(
        ranges=tuple(ordered),
        inserted_positions=tuple(inserted_positions),
        deltas=tuple(deltas),
    )


def _bisect_right(seq: tuple[int, ...], x: int) -> int:

    lo, hi = 0, len(seq)
    while lo < hi:
        mid = (lo + hi) // 2
        if x < seq[mid]:
            hi = mid
        else:
            lo = mid + 1
    return lo


def _maybe_store_macro(
    macros: dict[str, Macro], macro: Macro, warnings: list[TexWarning]
) -> None:
    if macro.argc > MAX_ARGS:
        warnings.append(
            warning(
                "macro_expansion_skipped", f"Macro \\{macro.name} has too many args"
            )
        )
        return
    if _unsafe_macro_body(macro.body):
        if _xspace_like_pattern(macro.body) and _xspace_like_inert(macro.body):
            collapse = "." if _DOTLIKE_NAMES.search(macro.name) else " "
            macros[macro.name] = Macro(name=macro.name, argc=0, body=collapse)
            return
        warnings.append(
            warning(
                "macro_expansion_skipped", f"Unsafe macro preserved: \\{macro.name}"
            )
        )
        return
    macros[macro.name] = macro


_XSPACE_LIKE_RE = re.compile(
    r"^\s*(?:\\(?:relax|protect|empty)\s*)*"
    r"\\if(?:x|cat|dim|num|odd|hmode|vmode|mmode|inner|true|false)?"
    r"[A-Za-z@]*\b.*?\\fi\b\s*$",
    flags=re.S,
)
_XSPACE_INNER_RE = re.compile(r"\\if[A-Za-z@]*\b.*?\\fi\b", flags=re.S)
_DOTLIKE_NAMES = re.compile(r"(?:onedot|fullstop|period|punct)$", re.I)


def _xspace_like_pattern(body: str) -> bool:
    return bool(_XSPACE_LIKE_RE.match(body))


def _xspace_like_inert(body: str) -> bool:
    residue = _XSPACE_INNER_RE.sub("", body).strip()
    return all(ch.isspace() or ch in ".,;: " or ch == "\\" for ch in residue)


def _unsafe_macro_body(body: str) -> bool:
    return bool(
        re.search(
            r"\\(?:if[A-Za-z@]*|fi|else|csname|catcode|write\d*|input|include)\b", body
        )
    )


def _is_escaped(text: str, pos: int) -> bool:
    n = 0
    j = pos - 1
    while j >= 0 and text[j] == "\\":
        n += 1
        j -= 1
    return (n % 2) == 1


def _skip_optional_bracket(text: str, i: int) -> int | None:
    if i >= len(text) or text[i] != "[":
        return i
    end = text.find("]", i + 1)
    return None if end < 0 else _skip_ws(text, end + 1)


def _skip_newenvironment(text: str, pos: int) -> int | None:
    m = re.match(r"\\(?:re)?newenvironment\*?", text[pos:])
    if not m:
        return None
    i = _skip_ws(text, pos + m.end())

    name_group = _read_group(text, i)
    if name_group is None:
        return None
    _, i = name_group
    i = _skip_ws(text, i)

    i_after = _skip_optional_bracket(text, i)
    if i_after is None:
        return None

    i_after = _skip_optional_bracket(text, i_after)
    if i_after is None:
        return None

    begin_group = _read_group(text, i_after)
    if begin_group is None:
        return None
    _, i = begin_group
    i = _skip_ws(text, i)

    end_group = _read_group(text, i)
    if end_group is None:
        return None
    _, i = end_group
    return i


_NEWCOMMAND_RE = re.compile(
    r"\\(?:(?:re)?newcommand|providecommand|DeclareRobustCommand)\*?"
)


def _parse_command_name(text: str, i: int) -> tuple[str, int] | None:
    if i < len(text) and text[i] == "{":
        group = _read_group(text, i)
        if group is None:
            return None
        raw_name, i = group
        name = raw_name.strip()
        if name.startswith("\\"):
            name = name[1:]
        return name, i
    if i < len(text) and text[i] == "\\":
        cmd = COMMAND_RE.match(text, i)
        if not cmd:
            return None
        return cmd.group(1), cmd.end()
    return None


def _parse_argc_and_defaults(text: str, i: int) -> tuple[int, str | None, int] | None:
    argc = 0
    default: str | None = None
    if i >= len(text) or text[i] != "[":
        return argc, default, i
    end = text.find("]", i + 1)
    if end < 0:
        return None
    try:
        argc = int(text[i + 1 : end].strip() or "0")
    except ValueError:
        return None
    i = _skip_ws(text, end + 1)

    if i < len(text) and text[i] == "[":
        end2 = text.find("]", i + 1)
        if end2 < 0:
            return None
        default = text[i + 1 : end2]
        i = _skip_ws(text, end2 + 1)
    return argc, default, i


def _parse_newcommand(text: str, pos: int) -> tuple[Macro, int] | None:
    m = _NEWCOMMAND_RE.match(text, pos)
    if not m:
        return None
    i = _skip_ws(text, m.end())
    result = _parse_command_name(text, i)
    if result is None:
        return None
    name, i = result
    i = _skip_ws(text, i)
    argc_result = _parse_argc_and_defaults(text, i)
    if argc_result is None:
        return None
    argc, default, i = argc_result
    body = _read_group(text, i)
    if body is None:
        return None
    return Macro(name=name, argc=argc, body=body[0], default=default), body[1]


def _handle_hash_in_def(text: str, i: int, argc: int) -> tuple[int, int]:
    if i + 1 >= len(text):
        return argc, i + 1
    next_ch = text[i + 1]
    if next_ch.isdigit():
        return max(argc, int(next_ch)), i + 2
    if next_ch == "#":
        return argc, i + 2
    return argc, i + 1


def _handle_bracket_in_def(text: str, i: int, argc: int) -> tuple[int, int] | None:
    end = text.find("]", i + 1)
    if end < 0:
        return None
    for digit in re.findall(r"#(\d)", text[i:end]):
        argc = max(argc, int(digit))
    return argc, end + 1


def _scan_def_param_token(text: str, i: int, argc: int) -> tuple[int, int, bool] | None:
    i = _skip_ws(text, i)
    if i >= len(text) or text[i] == "{":
        return argc, i, True
    ch = text[i]
    if ch == "#":
        argc, i = _handle_hash_in_def(text, i, argc)
        return argc, i, False
    if ch == "[":
        result = _handle_bracket_in_def(text, i, argc)
        if result is None:
            return None
        return result[0], result[1], False
    return argc, i + 1, False


def _parse_def(text: str, pos: int) -> tuple[Macro, int] | None:
    i = _skip_ws(text, pos + len("\\def"))
    cmd = COMMAND_RE.match(text, i)
    if not cmd:
        return None
    name = cmd.group(1)
    i = cmd.end()
    argc = 0
    while True:
        step = _scan_def_param_token(text, i, argc)
        if step is None:
            return None
        argc, i, done = step
        if done:
            break
    body = _read_group(text, i)
    if body is None:
        return None
    return Macro(name=name, argc=argc, body=body[0]), body[1]


def _read_group(text: str, pos: int) -> tuple[str, int] | None:
    pos = _skip_ws(text, pos)
    if pos >= len(text) or text[pos] != "{":
        return None
    depth = 0
    escaped = False
    start = pos + 1
    for i in range(pos, len(text)):
        char = text[i]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:i], i + 1
    return None


def _parse_declare_math_operator(text: str, pos: int) -> tuple[Macro, int] | None:
    m = re.match(r"\\DeclareMathOperator(\*?)", text[pos:])
    if not m:
        return None
    starred = m.group(1) == "*"
    i = _skip_ws(text, pos + m.end())

    grp = _read_group(text, i)
    if grp is None:
        return None
    raw_name, i = grp
    name = raw_name.strip().lstrip("\\")
    if not name:
        return None
    i = _skip_ws(text, i)

    body_grp = _read_group(text, i)
    if body_grp is None:
        return None
    body, end = body_grp
    op = "\\operatorname*" if starred else "\\operatorname"
    wrapped = f"{op}{{{body.strip()}}}"
    return Macro(name=name, argc=0, body=wrapped), end


def _parse_let(
    text: str, pos: int, macros: dict[str, Macro]
) -> tuple[Macro, int] | None:
    from arxiv_md.tex.signatures import COMMAND_SIGNATURES

    i = pos + len("\\let")
    i = _skip_ws(text, i)
    lhs = COMMAND_RE.match(text, i)
    if not lhs:
        return None
    lhs_name = lhs.group(1)
    i = _skip_ws(text, lhs.end())

    if i < len(text) and text[i] == "=":
        i = _skip_ws(text, i + 1)
    rhs = COMMAND_RE.match(text, i)
    if not rhs:
        return None
    rhs_name = rhs.group(1)
    end = rhs.end()

    if rhs_name in macros:
        src = macros[rhs_name]
        return Macro(name=lhs_name, argc=src.argc, body=src.body), end

    sig = COMMAND_SIGNATURES.get(rhs_name, "")
    argc = sig.count("m")
    if argc > 0:
        args = "".join("{#" + str(j + 1) + "}" for j in range(argc))
        body = f"\\{rhs_name}{args}"
    else:
        body = f"\\{rhs_name}"
    return Macro(name=lhs_name, argc=argc, body=body), end


def _skip_newenvironment_as_range(text: str, pos: int) -> _MacroParseResult | None:
    env_end = _skip_newenvironment(text, pos)
    if env_end is None:
        return None
    return None, env_end


_MACRO_DEF_PATTERNS: tuple[_MacroDefPattern, ...] = (
    _MacroDefPattern(
        "\\newcommand",
        _parse_newcommand,
        1,
        warning_message="Unsupported macro near offset {pos}",
    ),
    _MacroDefPattern(
        "\\renewcommand",
        _parse_newcommand,
        1,
        warning_message="Unsupported macro near offset {pos}",
    ),
    _MacroDefPattern(
        "\\providecommand",
        _parse_newcommand,
        1,
        warning_message="Unsupported macro near offset {pos}",
    ),
    _MacroDefPattern(
        "\\DeclareRobustCommand",
        _parse_newcommand,
        1,
        warning_message="Unsupported macro near offset {pos}",
    ),
    _MacroDefPattern(
        "\\newenvironment",
        _skip_newenvironment_as_range,
        len("\\newenvironment"),
        warning_message="Unsupported \\newenvironment near offset {pos}",
    ),
    _MacroDefPattern(
        "\\renewenvironment",
        _skip_newenvironment_as_range,
        len("\\renewenvironment"),
        warning_message="Unsupported \\newenvironment near offset {pos}",
    ),
    _MacroDefPattern(
        "\\def",
        _parse_def,
        1,
        warning_message="Unsupported \\def near offset {pos}",
        word_boundary=True,
    ),
    _MacroDefPattern("\\DeclareMathOperator", _parse_declare_math_operator, 0),
    _MacroDefPattern("\\let", _parse_let, 0, needs_macros=True, word_boundary=True),
)


def _try_match_definition(
    text: str,
    pos: int,
    macros: dict[str, Macro],
    warnings: list[TexWarning],
) -> tuple[int, tuple[int, int] | None] | None:
    for pattern in _MACRO_DEF_PATTERNS:
        if not text.startswith(pattern.prefix, pos):
            continue
        if pattern.word_boundary and _continues_command_word(text, pos, pattern):
            continue
        parsed = _parse_macro_pattern(pattern, text, pos, macros)
        if parsed is None:
            _warn_macro_parse_failure(pattern, pos, warnings)
            return pos + max(pattern.skip_len, 1), None
        macro, end = parsed
        if macro is not None:
            _maybe_store_macro(macros, macro, warnings)
        return end, (pos, end)
    return None


def _skip_comment_line(text: str, pos: int) -> int | None:
    if text[pos] != "%" or _is_escaped(text, pos):
        return None
    nl = text.find("\n", pos)
    return len(text) if nl < 0 else nl + 1


def _record_definition_match(
    remove_ranges: list[tuple[int, int]],
    match: tuple[int, tuple[int, int] | None],
) -> int:
    new_pos, remove_range = match
    if remove_range is not None:
        remove_ranges.append(remove_range)
    return new_pos


def _continues_command_word(text: str, pos: int, pattern: _MacroDefPattern) -> bool:
    after = pos + len(pattern.prefix)
    return after < len(text) and text[after].isalpha()


def _parse_macro_pattern(
    pattern: _MacroDefPattern,
    text: str,
    pos: int,
    macros: dict[str, Macro],
) -> _MacroParseResult | None:
    if pattern.needs_macros:
        return pattern.parser(text, pos, macros)
    return pattern.parser(text, pos)


def _warn_macro_parse_failure(
    pattern: _MacroDefPattern, pos: int, warnings: list[TexWarning]
) -> None:
    if pattern.warning_message is None:
        return
    warnings.append(
        warning("macro_expansion_skipped", pattern.warning_message.format(pos=pos))
    )


def _skip_ws(text: str, pos: int) -> int:
    n = len(text)
    while pos < n:
        ch = text[pos]
        if ch.isspace():
            pos += 1
            continue
        if ch == "%" and not _is_escaped(text, pos):
            nl = text.find("\n", pos)
            pos = n if nl < 0 else nl + 1
            continue
        break
    return pos


_NEWTHEOREM_RE = re.compile(
    r"\\newtheorem\*?"
    r"\{([A-Za-z]+)\}"
    r"(?:\[[^\]]*\])?"
    r"\{([^}]+)\}"
)


def discover_newtheorem(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("%"):
            continue
        for m in _NEWTHEOREM_RE.finditer(line):
            name = m.group(1)
            title = m.group(2).strip()

            if "\\" in title:
                continue
            result[name] = title
    return result


def _remove_ranges(text: str, ranges: list[tuple[int, int]]) -> str:
    if not ranges:
        return text
    ranges.sort()
    out: list[str] = []
    last = 0
    for start, end in ranges:
        out.append(text[last:start])
        out.append("\n")
        last = end
    out.append(text[last:])
    return "".join(out)
