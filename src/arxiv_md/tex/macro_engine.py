from __future__ import annotations

from dataclasses import dataclass, field

from arxiv_md.tex._common import ResourceLimits
from arxiv_md.tex.ast import (
    Command,
    Comment,
    Env,
    Group,
    Math,
    Node,
    ParagraphBreak,
    Parameter,
    Text,
    Verbatim,
)
from arxiv_md.tex.lexer import Diagnostics, tokenize
from arxiv_md.tex.macros import Macro
from arxiv_md.tex.parser import parse as ast_parse


MAX_DEPTH: int = 10
MAX_EXPANDED_NODES: int = 50_000


_LEAF_TYPES = (Text, ParagraphBreak, Parameter, Comment, Verbatim)


def _clone_node(n: Node) -> Node:
    if isinstance(n, _LEAF_TYPES):
        return n
    if isinstance(n, Group):
        return Group(pos=n.pos, children=_clone_list(n.children))
    if isinstance(n, Command):
        return Command(
            pos=n.pos,
            name=n.name,
            star=n.star,
            opt_args=[
                Group(pos=g.pos, children=_clone_list(g.children)) for g in n.opt_args
            ],
            args=[Group(pos=g.pos, children=_clone_list(g.children)) for g in n.args],
            trailing_ws=n.trailing_ws,
        )
    if isinstance(n, Env):
        return Env(
            pos=n.pos,
            end_pos=n.end_pos,
            raw=n.raw,
            name=n.name,
            opt_args=[
                Group(pos=g.pos, children=_clone_list(g.children)) for g in n.opt_args
            ],
            args=[Group(pos=g.pos, children=_clone_list(g.children)) for g in n.args],
            body=_clone_list(n.body),
        )
    if isinstance(n, Math):
        return Math(pos=n.pos, display=n.display, body=_clone_list(n.body))

    return n


def _clone_list(nodes: list[Node]) -> list[Node]:
    return [_clone_node(c) for c in nodes]


TRAILING_WS_SENTINEL: str = "\x00WS\x00"


MATH_ACCENT_COMMANDS: frozenset[str] = frozenset(
    {
        "acute",
        "bar",
        "breve",
        "check",
        "ddot",
        "dot",
        "grave",
        "hat",
        "overline",
        "tilde",
        "underline",
        "vec",
        "widehat",
        "widetilde",
    }
)
MATH_ARG_WRAPPER_COMMANDS: frozenset[str] = frozenset(
    {
        "boldsymbol",
        "mathbb",
        "mathbf",
        "mathcal",
        "mathfrak",
        "mathit",
        "mathrm",
        "mathsf",
        "mathtt",
        "operatorname",
        "text",
    }
)
MATH_LAYOUT_WRAPPER_COMMANDS: frozenset[str] = frozenset({"resizebox", "scalebox"})


@dataclass(slots=True)
class CompiledMacro:
    name: str
    argc: int
    body_nodes: list[Node] = field(default_factory=list)

    body_text: str = ""
    default: str | None = None
    default_nodes: list[Node] = field(default_factory=list)


def compile_macros(
    macros: dict[str, Macro],
    diag: Diagnostics | None = None,
) -> dict[str, CompiledMacro]:
    diag = diag if diag is not None else Diagnostics()
    out: dict[str, CompiledMacro] = {}
    for name, m in macros.items():
        toks = tokenize(m.body, diag)
        body_nodes = ast_parse(toks, diag, source_text=m.body)
        default_nodes: list[Node] = []
        if m.default is not None:
            d_toks = tokenize(m.default, diag)
            default_nodes = ast_parse(d_toks, diag, source_text=m.default)
        out[name] = CompiledMacro(
            name=name,
            argc=m.argc,
            body_nodes=body_nodes,
            body_text=m.body,
            default=m.default,
            default_nodes=default_nodes,
        )
    return out


def expand(
    nodes: list[Node],
    macros: dict[str, CompiledMacro],
    diag: Diagnostics,
    limits: ResourceLimits | None = None,
) -> list[Node]:
    if limits is None:
        limits = ResourceLimits()
    counter = [0]
    return _expand_list(
        nodes,
        macros,
        diag,
        depth=0,
        counter=counter,
        max_depth=limits.max_macro_expansion_depth,
        max_nodes=limits.max_macro_expanded_nodes,
    )


def strip_math_comments(text: str) -> str:
    if "%" not in text:
        return text
    out: list[str] = []
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        if ch == "\\" and i + 1 < n:
            out.append(text[i : i + 2])
            i += 2
            continue
        if ch == "%":
            nl = text.find("\n", i)
            if nl < 0:
                break
            i = nl + 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def brace_math_accent_arguments(text: str) -> str:
    if "\\" not in text:
        return text
    out: list[str] = []
    i = 0
    n = len(text)
    changed = False
    while i < n:
        command = _read_control_word(text, i)
        if command is None:
            out.append(text[i])
            i += 1
            continue
        name, command_end = command
        if name not in MATH_ACCENT_COMMANDS:
            out.append(text[i:command_end])
            i = command_end
            continue
        ws_end = _skip_math_space(text, command_end)
        wrapper = _read_control_word(text, ws_end)
        if wrapper is None:
            out.append(text[i:command_end])
            i = command_end
            continue
        wrapper_name, wrapper_command_end = wrapper
        if wrapper_name not in MATH_ARG_WRAPPER_COMMANDS:
            out.append(text[i:command_end])
            i = command_end
            continue
        group_start = _skip_math_space(text, wrapper_command_end)
        if group_start >= n or text[group_start] != "{":
            out.append(text[i:command_end])
            i = command_end
            continue
        group_end = _balanced_group_end(text, group_start)
        if group_end is None:
            out.append(text[i:command_end])
            i = command_end
            continue
        out.append(text[i:command_end])
        out.append("{")
        out.append(text[ws_end:group_end])
        out.append("}")
        i = group_end
        changed = True
    return "".join(out) if changed else text


def unwrap_math_layout_wrappers(text: str) -> str:
    if "\\" not in text:
        return text
    current = text
    for _ in range(MAX_DEPTH):
        normalized, changed = _unwrap_one_math_layout_pass(current)
        current = normalized
        if not changed:
            break
    return current


def _unwrap_one_math_layout_pass(text: str) -> tuple[str, bool]:
    out: list[str] = []
    i = 0
    n = len(text)
    changed = False
    while i < n:
        command = _read_control_word(text, i)
        if command is None:
            out.append(text[i])
            i += 1
            continue
        name, command_end = command
        if name not in MATH_LAYOUT_WRAPPER_COMMANDS:
            out.append(text[i:command_end])
            i = command_end
            continue
        body_span = _math_layout_wrapper_body_span(text, name, command_end)
        if body_span is None:
            out.append(text[i:command_end])
            i = command_end
            continue
        body_start, body_end = body_span
        out.append(_strip_outer_math_delimiters(text[body_start + 1 : body_end - 1]))
        i = body_end
        changed = True
    return ("".join(out), changed)


def _math_layout_wrapper_body_span(
    text: str,
    name: str,
    command_end: int,
) -> tuple[int, int] | None:
    i = command_end
    if i < len(text) and text[i] == "*":
        i += 1
    if name == "resizebox":
        for _ in range(2):
            span = _read_required_group_span(text, i)
            if span is None:
                return None
            _, i = span
        return _read_required_group_span(text, i)
    if name == "scalebox":
        span = _read_required_group_span(text, i)
        if span is None:
            return None
        _, i = span
        optional = _read_optional_bracket_span(text, i)
        if optional is not None:
            _, i = optional
        return _read_required_group_span(text, i)
    return None


def _read_required_group_span(text: str, start: int) -> tuple[int, int] | None:
    group_start = _skip_math_space(text, start)
    if group_start >= len(text) or text[group_start] != "{":
        return None
    group_end = _balanced_group_end(text, group_start)
    if group_end is None:
        return None
    return group_start, group_end


def _read_optional_bracket_span(text: str, start: int) -> tuple[int, int] | None:
    bracket_start = _skip_math_space(text, start)
    if bracket_start >= len(text) or text[bracket_start] != "[":
        return None
    depth = 0
    escaped = False
    i = bracket_start
    while i < len(text):
        ch = text[i]
        if escaped:
            escaped = False
            i += 1
            continue
        if ch == "\\":
            escaped = True
            i += 1
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return bracket_start, i + 1
        i += 1
    return None


def _strip_outer_math_delimiters(text: str) -> str:
    stripped = text.strip()
    if len(stripped) >= 4 and stripped.startswith("$$") and stripped.endswith("$$"):
        return stripped[2:-2].strip()
    if len(stripped) >= 2 and stripped.startswith("$") and stripped.endswith("$"):
        return stripped[1:-1].strip()
    if len(stripped) >= 4 and stripped.startswith(r"\(") and stripped.endswith(r"\)"):
        return stripped[2:-2].strip()
    if len(stripped) >= 4 and stripped.startswith(r"\[") and stripped.endswith(r"\]"):
        return stripped[2:-2].strip()
    return text


def _read_control_word(text: str, start: int) -> tuple[str, int] | None:
    if start >= len(text) or text[start] != "\\":
        return None
    i = start + 1
    if i >= len(text) or not (text[i].isalpha() or text[i] == "@"):
        return None
    while i < len(text) and (text[i].isalpha() or text[i] == "@"):
        i += 1
    return text[start + 1 : i], i


def _skip_math_space(text: str, start: int) -> int:
    while start < len(text) and text[start] in " \t\n\r":
        start += 1
    return start


def _balanced_group_end(text: str, start: int) -> int | None:
    depth = 0
    escaped = False
    i = start
    while i < len(text):
        ch = text[i]
        if escaped:
            escaped = False
            i += 1
            continue
        if ch == "\\":
            escaped = True
            i += 1
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return None


def _eat_brace_arg(text: str, pos: int) -> tuple[str, int] | None:
    n = len(text)
    if pos >= n or text[pos] != "{":
        return None
    depth = 0
    escaped = False
    k = pos
    while k < n:
        c = text[k]
        if escaped:
            escaped = False
            k += 1
            continue
        if c == "\\":
            escaped = True
            k += 1
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[pos + 1 : k], k + 1
        k += 1
    return None


def _eat_macro_args(text: str, pos: int, argc: int) -> tuple[list[str], int] | None:
    args: list[str] = []
    cursor = pos
    n = len(text)
    for _ in range(argc):
        while cursor < n and text[cursor] in " \t\n":
            cursor += 1
        result = _eat_brace_arg(text, cursor)
        if result is None:
            return None
        arg_text, cursor = result
        args.append(arg_text)
    return args, cursor


def _scan_math_command(text: str, pos: int) -> tuple[str | None, int, str]:
    n = len(text)
    if pos + 1 < n and text[pos + 1] == "\\":
        return None, pos + 2, "\\\\"
    end = pos + 1
    while end < n and (text[end].isalpha() or text[end] == "@"):
        end += 1
    if end == pos + 1:
        literal_end = min(end + 1, n)
        return None, literal_end, text[pos:literal_end]
    return text[pos + 1 : end], end, ""


def expand_math_text(
    text: str,
    macros: dict[str, CompiledMacro],
    *,
    depth: int = 0,
) -> str:
    if depth >= MAX_DEPTH or not macros or "\\" not in text:
        return text
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] != "\\":
            out.append(text[i])
            i += 1
            continue

        name, end, passthrough = _scan_math_command(text, i)
        if name is None:
            out.append(passthrough)
            i = end
            continue

        macro = macros.get(name)
        if macro is None:
            out.append(text[i:end])
            i = end
            continue

        cursor_after_opt = end
        opt_value: str | None = None
        if macro.default is not None:
            cursor_skip = cursor_after_opt
            n2 = len(text)
            while cursor_skip < n2 and text[cursor_skip] in " \t\n":
                cursor_skip += 1
            if cursor_skip < n2 and text[cursor_skip] == "[":
                opt_span = _read_optional_bracket_span(text, cursor_skip)
                if opt_span is not None:
                    opt_start, opt_end = opt_span
                    opt_value = text[opt_start + 1 : opt_end - 1]
                    cursor_after_opt = opt_end
        required = macro.argc - 1 if macro.default is not None else macro.argc
        result = _eat_macro_args(text, cursor_after_opt, required)
        if result is None:
            out.append(text[i:end])
            i = end
            continue

        rest_args, cursor = result
        if macro.default is not None:
            first = opt_value if opt_value is not None else macro.default
            args = [first] + rest_args
        else:
            args = rest_args
        body = _replace_params_in_str(macro.body_text, args)

        body = expand_math_text(body, macros, depth=depth + 1)
        out.append(body)
        i = cursor
    return "".join(out)


def _replace_params_in_str(body: str, args: list[str]) -> str:
    if not body or "#" not in body:
        return body
    out: list[str] = []
    n = len(body)
    i = 0
    while i < n:
        ch = body[i]
        if ch == "#" and i + 1 < n and body[i + 1].isdigit():
            idx = int(body[i + 1]) - 1
            if 0 <= idx < len(args):
                out.append(args[idx])
            i += 2
            continue
        if ch == "#" and i + 1 < n and body[i + 1] == "#":
            out.append("#")
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _expand_list(
    nodes: list[Node],
    macros: dict[str, CompiledMacro],
    diag: Diagnostics,
    *,
    depth: int,
    counter: list[int],
    max_depth: int = MAX_DEPTH,
    max_nodes: int = MAX_EXPANDED_NODES,
) -> list[Node]:
    out: list[Node] = []
    for i, n in enumerate(nodes):
        if counter[0] > max_nodes:
            out.extend(_clone_node(rest) for rest in nodes[i:])
            break
        out.extend(
            _expand_one(
                n,
                macros,
                diag,
                depth=depth,
                counter=counter,
                max_depth=max_depth,
                max_nodes=max_nodes,
            )
        )
    return out


def _expand_one(
    n: Node,
    macros: dict[str, CompiledMacro],
    diag: Diagnostics,
    *,
    depth: int,
    counter: list[int],
    max_depth: int = MAX_DEPTH,
    max_nodes: int = MAX_EXPANDED_NODES,
) -> list[Node]:
    counter[0] += 1
    if isinstance(n, _LEAF_TYPES):
        return [n]
    if isinstance(n, Group):
        return [
            Group(
                pos=n.pos,
                children=_expand_list(
                    n.children,
                    macros,
                    diag,
                    depth=depth,
                    counter=counter,
                    max_depth=max_depth,
                    max_nodes=max_nodes,
                ),
            )
        ]
    if isinstance(n, Env):
        return [
            Env(
                pos=n.pos,
                end_pos=n.end_pos,
                raw=n.raw,
                name=n.name,
                opt_args=_expand_groups(
                    n.opt_args,
                    macros,
                    diag,
                    depth=depth,
                    counter=counter,
                    max_depth=max_depth,
                    max_nodes=max_nodes,
                ),
                args=_expand_groups(
                    n.args,
                    macros,
                    diag,
                    depth=depth,
                    counter=counter,
                    max_depth=max_depth,
                    max_nodes=max_nodes,
                ),
                body=_expand_list(
                    n.body,
                    macros,
                    diag,
                    depth=depth,
                    counter=counter,
                    max_depth=max_depth,
                    max_nodes=max_nodes,
                ),
            )
        ]
    if isinstance(n, Math):
        new_body: list[Node] = []
        for child in n.body:
            if isinstance(child, Text) and child.value:
                value = strip_math_comments(child.value)
                value = expand_math_text(value, macros)
                value = unwrap_math_layout_wrappers(value)
                value = brace_math_accent_arguments(value)
                new_body.append(Text(pos=child.pos, value=value))
            else:
                new_body.append(_clone_node(child))
        return [Math(pos=n.pos, display=n.display, body=new_body)]
    if isinstance(n, Verbatim):
        return [n]
    if isinstance(n, Command):
        new_opt = _expand_groups(
            n.opt_args,
            macros,
            diag,
            depth=depth,
            counter=counter,
            max_depth=max_depth,
            max_nodes=max_nodes,
        )
        new_args = _expand_groups(
            n.args,
            macros,
            diag,
            depth=depth,
            counter=counter,
            max_depth=max_depth,
            max_nodes=max_nodes,
        )
        macro = macros.get(n.name)
        if macro is None:
            return [
                Command(
                    pos=n.pos,
                    name=n.name,
                    star=n.star,
                    opt_args=new_opt,
                    args=new_args,
                    trailing_ws=n.trailing_ws,
                )
            ]
        required = macro.argc - 1 if macro.default is not None else macro.argc
        if len(new_args) < required:
            diag.warn(
                "unknown_macro",
                f"Could not expand \\{n.name}: missing args (got {len(new_args)}, need {required})",
            )
            return [
                Command(
                    pos=n.pos,
                    name=n.name,
                    star=n.star,
                    opt_args=new_opt,
                    args=new_args,
                    trailing_ws=n.trailing_ws,
                )
            ]
        if depth >= max_depth:
            diag.warn(
                "macro_expansion_skipped",
                f"Depth cap reached expanding \\{n.name}",
            )
            return [
                Command(
                    pos=n.pos,
                    name=n.name,
                    star=n.star,
                    opt_args=new_opt,
                    args=new_args,
                    trailing_ws=n.trailing_ws,
                )
            ]
        if macro.default is not None:
            if new_opt:
                first = Group(
                    pos=new_opt[0].pos, children=_clone_list(new_opt[0].children)
                )
            else:
                first = Group(pos=n.pos, children=_clone_list(macro.default_nodes))
            sub_args = [first] + new_args[: macro.argc - 1]
        else:
            sub_args = new_args[: macro.argc]
        substituted = _substitute_params(macro.body_nodes, sub_args)
        expanded = _expand_list(
            substituted,
            macros,
            diag,
            depth=depth + 1,
            counter=counter,
            max_depth=max_depth,
            max_nodes=max_nodes,
        )
        if n.trailing_ws and expanded:
            expanded.append(Text(pos=n.pos, value=TRAILING_WS_SENTINEL))
        return expanded
    return [_clone_node(n)]


def _expand_groups(
    groups: list[Group],
    macros: dict[str, CompiledMacro],
    diag: Diagnostics,
    *,
    depth: int,
    counter: list[int],
    max_depth: int = MAX_DEPTH,
    max_nodes: int = MAX_EXPANDED_NODES,
) -> list[Group]:
    return [
        Group(
            pos=g.pos,
            children=_expand_list(
                g.children,
                macros,
                diag,
                depth=depth,
                counter=counter,
                max_depth=max_depth,
                max_nodes=max_nodes,
            ),
        )
        for g in groups
    ]


def _substitute_params(body_nodes: list[Node], args: list[Group]) -> list[Node]:
    out: list[Node] = []
    for n in body_nodes:
        out.extend(_substitute_one(n, args))
    return out


def _substitute_one(n: Node, args: list[Group]) -> list[Node]:
    if isinstance(n, Parameter):
        idx = n.index - 1
        if 0 <= idx < len(args):
            return _clone_list(args[idx].children)
        return []
    if isinstance(n, Group):
        return [Group(pos=n.pos, children=_substitute_params(n.children, args))]
    if isinstance(n, Command):
        return [
            Command(
                pos=n.pos,
                name=n.name,
                star=n.star,
                opt_args=_substitute_groups(n.opt_args, args),
                args=_substitute_groups(n.args, args),
                trailing_ws=n.trailing_ws,
            )
        ]
    if isinstance(n, Env):
        return [
            Env(
                pos=n.pos,
                end_pos=n.end_pos,
                raw=n.raw,
                name=n.name,
                opt_args=_substitute_groups(n.opt_args, args),
                args=_substitute_groups(n.args, args),
                body=_substitute_params(n.body, args),
            )
        ]
    if isinstance(n, Math):
        return [
            Math(
                pos=n.pos,
                display=n.display,
                body=[_substitute_in_text_node(c, args) for c in n.body],
            )
        ]
    if isinstance(n, Verbatim):
        return [
            Verbatim(
                pos=n.pos,
                text=_replace_params_in_text(n.text, args),
                language=n.language,
                inline=n.inline,
            )
        ]
    return [_clone_node(n)]


def _substitute_groups(groups: list[Group], args: list[Group]) -> list[Group]:
    return [
        Group(pos=g.pos, children=_substitute_params(g.children, args)) for g in groups
    ]


def _substitute_in_text_node(node: Node, args: list[Group]) -> Node:
    if isinstance(node, Text):
        return Text(pos=node.pos, value=_replace_params_in_text(node.value, args))
    return _clone_node(node)


def _replace_params_in_text(text: str, args: list[Group]) -> str:
    if not text or "#" not in text:
        return text
    out: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "#" and i + 1 < len(text) and text[i + 1].isdigit():
            idx = int(text[i + 1]) - 1
            if 0 <= idx < len(args):
                out.append(_flatten_group(args[idx]))
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _flatten_group(group: Group) -> str:
    return "".join(_flatten_node(c) for c in group.children)


def _flatten_node(n: Node) -> str:
    from arxiv_md.tex.ast import Text

    if isinstance(n, Text):
        return n.value
    if isinstance(n, Group):
        return "{" + _flatten_group(n) + "}"
    if isinstance(n, Math):
        body = "".join(_flatten_node(c) for c in n.body)
        if n.display:
            return f"$${body}$$"
        return f"\\({body}\\)" if "$" in body else f"${body}$"
    if isinstance(n, Verbatim):
        return n.text
    if isinstance(n, Parameter):
        return f"#{n.index}"
    if isinstance(n, Command):
        star = "*" if n.star else ""
        opt = "".join("[" + _flatten_group(g) + "]" for g in n.opt_args)
        args = "".join("{" + _flatten_group(g) + "}" for g in n.args)
        trailing = " " if n.trailing_ws else ""
        return f"\\{n.name}{star}{opt}{args}{trailing}"
    if isinstance(n, Env):
        opt = "".join("[" + _flatten_group(g) + "]" for g in n.opt_args)
        args = "".join("{" + _flatten_group(g) + "}" for g in n.args)
        body = "".join(_flatten_node(c) for c in n.body)
        return f"\\begin{{{n.name}}}{opt}{args}{body}\\end{{{n.name}}}"
    return ""
