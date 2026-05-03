from __future__ import annotations

from dataclasses import dataclass

import re

from arxiv_md.tex.ast import Command, Env, Group, Math, Text
from arxiv_md.tex.handler_types import TransformContextProtocol
from arxiv_md.tex.model import AlgorithmBlock, Block, CodeBlock, InlineNode, MathSpan, Paragraph, QuoteBlock, TextSpan

__all__ = [
    "ALGORITHM_ENVS",
    "ALGORITHMIC_ENVS",
    "algorithm_env",
    "algorithmic_env",
]


ALGORITHM_ENVS: frozenset[str] = frozenset(
    {
        "algorithm",
        "algorithm*",
    }
)
ALGORITHMIC_ENVS: frozenset[str] = frozenset(
    {
        "algorithmic",
        "algorithmicx",
        "algpseudocode",
    }
)


_BLOCK_OPEN: dict[str, str] = {
    "While": "while",
    "WHILE": "while",
    "For": "for",
    "FOR": "for",
    "ForAll": "for all",
    "FORALL": "for all",
    "ForEach": "for each",
    "FOREACH": "for each",
    "If": "if",
    "IF": "if",
    "Loop": "loop",
    "LOOP": "loop",
    "Repeat": "repeat",
    "REPEAT": "repeat",
    "Function": "function",
    "FUNCTION": "function",
    "Procedure": "procedure",
    "PROCEDURE": "procedure",
}


_BLOCK_CLOSE: dict[str, str] = {
    "EndWhile": "end while",
    "ENDWHILE": "end while",
    "EndFor": "end for",
    "ENDFOR": "end for",
    "EndIf": "end if",
    "ENDIF": "end if",
    "EndLoop": "end loop",
    "ENDLOOP": "end loop",
    "Until": "until",
    "UNTIL": "until",
    "EndFunction": "end function",
    "ENDFUNCTION": "end function",
    "EndProcedure": "end procedure",
    "ENDPROCEDURE": "end procedure",
}


_BLOCK_MID: dict[str, str] = {
    "Else": "else",
    "ELSE": "else",
    "ElsIf": "else if",
    "ELSIF": "else if",
    "ElseIf": "else if",
    "ELSEIF": "else if",
}


_KEYWORD_PREFIX: dict[str, str] = {
    "State": "",
    "STATE": "",
    "Require": "Require: ",
    "REQUIRE": "Require: ",
    "Ensure": "Ensure: ",
    "ENSURE": "Ensure: ",
    "Return": "return ",
    "RETURN": "return ",
    "KwIn": "Input: ",
    "KwOut": "Output: ",
    "KwData": "Data: ",
    "KwResult": "Result: ",
    "KwRet": "return ",
}

_DO_BLOCKS = frozenset(
    {
        "While",
        "WHILE",
        "For",
        "FOR",
        "ForAll",
        "FORALL",
        "ForEach",
        "FOREACH",
        "Loop",
        "LOOP",
    }
)
_IF_BLOCKS = frozenset({"If", "IF"})
_PSEUDOCODE_COMMANDS = (
    frozenset(_KEYWORD_PREFIX)
    | frozenset(_BLOCK_OPEN)
    | frozenset(_BLOCK_CLOSE)
    | frozenset(_BLOCK_MID)
)
_COMMANDS_TO_SKIP = frozenset({"caption", "label", "dontprintsemicolon", "DontPrintSemicolon", "SetAlgoLined", "SetAlgoNoLine", "SetAlgoNoEnd", "SetKwInOut", "SetKwInput", "SetKwComment"})
_NEWLINE_COMMANDS = frozenset({"\\\\"})
_COMMENT_COMMANDS = frozenset({"Comment", "COMMENT"})

_INDENT = "  "


def _nodes_to_plain(nodes: list, ctx=None) -> str:
    if ctx is not None:
        return ctx.inline_markdown(nodes).strip()
    return "".join(_node_to_plain_part(node, ctx) for node in nodes)


def _node_to_plain_part(node, ctx=None) -> str:
    if isinstance(node, Text):
        return node.value
    if isinstance(node, Math):
        return _nodes_to_plain(list(node.body), ctx)
    if isinstance(node, Command):
        return _command_to_plain(node, ctx)
    if isinstance(node, Group):
        return _nodes_to_plain(list(node.children), ctx)
    if isinstance(node, Env):
        return _nodes_to_plain(list(node.body), ctx)
    return ""


def _command_to_plain(cmd: Command, ctx=None) -> str:
    parts = [_command_plain_name(cmd.name)]
    for arg in cmd.args:
        parts.append(_nodes_to_plain(list(arg.children), ctx))
    return "".join(parts)


def _command_plain_name(name: str) -> str:
    if name in _KEYWORD_PREFIX:
        return _KEYWORD_PREFIX[name]
    if name in _BLOCK_OPEN:
        return _BLOCK_OPEN[name]
    if name in _NEWLINE_COMMANDS:
        return " "
    return name


def _arg_text(cmd: Command, idx: int, ctx=None) -> str:
    if idx < len(cmd.args):
        return _nodes_to_plain(list(cmd.args[idx].children), ctx)
    return ""


@dataclass
class _AlgoState:
    lines: list[str]
    indent: int = 0
    pending_indent: int | None = None

    def flush_pending(self) -> None:
        if self.pending_indent is not None:
            self.lines.append(_INDENT * self.pending_indent)
            self.pending_indent = None

    def append_text(self, val: str) -> None:
        if self.pending_indent is not None:
            self.lines.append(_INDENT * self.pending_indent + val)
            self.pending_indent = None
        elif self.lines:
            prev = self.lines[-1]
            if prev.endswith(" "):
                self.lines[-1] = prev + val
            else:
                self.lines[-1] = prev + " " + val
        else:
            self.lines.append(_INDENT * self.indent + val)


@dataclass
class _BracketSkipState:
    _active: bool | str = True

    def should_skip(self, val: str) -> bool:
        if self._active is True and val == "[":
            self._active = "open"
            return True
        if self._active == "open":
            if val == "]":
                self._active = False
            return True
        return False

    def disable(self) -> None:
        self._active = False


def _handle_block_close(node: Command, state: _AlgoState) -> None:
    state.indent = max(0, state.indent - 1)
    state.lines.append(_INDENT * state.indent + _BLOCK_CLOSE[node.name])


def _handle_block_mid(
    node: Command,
    state: _AlgoState,
    ctx: TransformContextProtocol | None,
) -> None:
    display = _BLOCK_MID[node.name]
    mid_indent = max(0, state.indent - 1)
    cond = _arg_text(node, 0, ctx)
    if cond:
        state.lines.append(_INDENT * mid_indent + f"{display} {cond} then")
    else:
        state.lines.append(_INDENT * mid_indent + display)


def _handle_block_open(
    node: Command,
    state: _AlgoState,
    ctx: TransformContextProtocol | None,
) -> None:
    display = _BLOCK_OPEN[node.name]
    cond = _arg_text(node, 0, ctx)
    if len(node.args) >= 2:
        _handle_algorithm2e_block(node, state, ctx, display, cond)
        return

    suffix = _block_open_suffix(node.name)
    if cond:
        state.lines.append(_INDENT * state.indent + f"{display} {cond}{suffix}")
    else:
        state.lines.append(_INDENT * state.indent + display)
    state.indent += 1


def _handle_algorithm2e_block(
    node: Command,
    state: _AlgoState,
    ctx: TransformContextProtocol | None,
    display: str,
    cond: str,
) -> None:
    if cond:
        state.lines.append(_INDENT * state.indent + f"{display} {cond} do")
    else:
        state.lines.append(_INDENT * state.indent + display)
    state.indent += 1
    body_lines = _walk_algorithmic_body(list(node.args[1].children), ctx)
    for body_line in body_lines:
        state.lines.append(_INDENT * state.indent + body_line)
    state.indent = max(0, state.indent - 1)
    state.lines.append(_INDENT * state.indent + f"end {display}")


def _block_open_suffix(name: str) -> str:
    if name in _IF_BLOCKS:
        return " then"
    if name in _DO_BLOCKS:
        return " do"
    return ""


def _handle_keyword(
    node: Command,
    state: _AlgoState,
    ctx: TransformContextProtocol | None,
) -> None:
    prefix = _KEYWORD_PREFIX[node.name]
    arg_text_val = _arg_text(node, 0, ctx)
    if prefix == "":
        state.pending_indent = state.indent
    else:
        state.lines.append(_INDENT * state.indent + prefix + arg_text_val)


def _handle_comment(
    node: Command,
    state: _AlgoState,
    ctx: TransformContextProtocol | None,
) -> None:
    comment_text = _arg_text(node, 0, ctx)
    if not comment_text:
        return
    if state.lines:
        state.lines[-1] += f"  // {comment_text}"
    else:
        state.lines.append(_INDENT * state.indent + f"// {comment_text}")


def _handle_unknown_command(
    node: Command,
    state: _AlgoState,
    ctx: TransformContextProtocol | None,
) -> None:
    parts = [node.name]
    for arg in node.args:
        parts.append(_nodes_to_plain(list(arg.children), ctx))
    line_text = " ".join(p for p in parts if p)
    state.lines.append(_INDENT * state.indent + line_text)


def _handle_text_node(
    node: Text,
    state: _AlgoState,
    skip_state: _BracketSkipState,
) -> None:
    val = node.value.strip()
    if not val:
        return
    if skip_state.should_skip(val):
        return
    skip_state.disable()
    state.append_text(val)


def _handle_math_node(
    node: Math,
    state: _AlgoState,
    ctx: TransformContextProtocol | None,
) -> None:
    math_text = _nodes_to_plain(list(node.body), ctx)
    if math_text:
        state.append_text(f"${math_text}$")


def _handle_group_or_env_node(
    node: Group | Env,
    state: _AlgoState,
    ctx: TransformContextProtocol | None,
) -> None:
    body_nodes = list(node.body) if isinstance(node, Env) else list(node.children)
    text = _nodes_to_plain(body_nodes, ctx)
    if text.strip():
        state.append_text(text.strip())


def _dispatch_command(
    node: Command,
    state: _AlgoState,
    ctx: TransformContextProtocol | None,
) -> None:
    name = node.name
    if name in _PSEUDOCODE_COMMANDS:
        state.pending_indent = None
    elif state.pending_indent is not None:
        text = _nodes_to_plain([node], ctx).strip()
        if text:
            state.append_text(text)
            return
        state.flush_pending()
    else:
        state.flush_pending()

    if name in _BLOCK_CLOSE:
        _handle_block_close(node, state)
    elif name in _BLOCK_MID:
        _handle_block_mid(node, state, ctx)
    elif name in _BLOCK_OPEN:
        _handle_block_open(node, state, ctx)
    elif name in _KEYWORD_PREFIX:
        _handle_keyword(node, state, ctx)
    elif name in _COMMENT_COMMANDS:
        _handle_comment(node, state, ctx)
    elif name in _COMMANDS_TO_SKIP:
        return
    elif name in _NEWLINE_COMMANDS:
        # \\ acts as statement separator in algorithm2e-style blocks
        state.pending_indent = state.indent
    else:
        _handle_unknown_command(node, state, ctx)


def _walk_algorithmic_body(
    body: list,
    ctx: TransformContextProtocol | None = None,
) -> list[str]:
    state = _AlgoState(lines=[])
    skip_state = _BracketSkipState()
    for node in body:
        if isinstance(node, Text):
            _handle_text_node(node, state, skip_state)
            continue
        if isinstance(node, Math):
            _handle_math_node(node, state, ctx)
            continue
        if not isinstance(node, Command):
            if isinstance(node, (Group, Env)):
                _handle_group_or_env_node(node, state, ctx)
            continue

        skip_state.disable()
        _dispatch_command(node, state, ctx)

    state.flush_pending()
    return state.lines


def _extract_caption(env: Env, ctx) -> str | None:
    for node in env.body:
        if isinstance(node, Command) and node.name == "caption" and node.args:
            return _nodes_to_plain(list(node.args[0].children), ctx)
    return None


def _extract_label(env: Env, ctx) -> str | None:
    for node in env.body:
        if isinstance(node, Command) and node.name == "label" and node.args:
            return ctx.inline_markdown(node.args[0].children).strip() or None
    return None


def _algo_lines_to_markdown(lines: list[str]) -> str:
    """Render algorithm lines as nested blockquotes with inline math.

    Indentation is expressed via nested ``>`` markers (one per indent
    level).  ``$...$`` segments are preserved so math renders inline.
    """
    rendered: list[str] = []
    for line in lines:
        stripped = line.lstrip(" ")
        indent_level = (len(line) - len(stripped)) // len(_INDENT)
        prefix = "> " * (indent_level + 1)
        rendered.append(f"{prefix}{stripped}")
    return "\n" + "\n".join(rendered)


def _find_algorithmic_env(body: list) -> Env | None:
    for node in body:
        if isinstance(node, Env) and node.name in ALGORITHMIC_ENVS:
            return node
    return None


def algorithm_env(env: Env, ctx: TransformContextProtocol) -> list[Block]:
    caption = _extract_caption(env, ctx)
    label = _extract_label(env, ctx)

    inner = _find_algorithmic_env(env.body)
    if inner is not None:
        lines = _walk_algorithmic_body(list(inner.body), ctx)
    else:
        filtered = [
            n
            for n in env.body
            if not (isinstance(n, Command) and n.name in ("caption", "label"))
        ]
        lines = _walk_algorithmic_body(filtered, ctx)

    code_text = "\n".join(lines)

    blocks: list[Block] = []

    if caption:
        cap_text = f"**Algorithm: {caption}**"
        cap_para = Paragraph(children=[TextSpan(text=cap_text)])
        if label:
            cap_para.label = label
        blocks.append(cap_para)
    elif label:
        cap_para = Paragraph(children=[TextSpan(text="**Algorithm**")])
        cap_para.label = label
        blocks.append(cap_para)

    blocks.append(AlgorithmBlock(text=_algo_lines_to_markdown(lines)))
    return blocks


def algorithmic_env(env: Env, ctx: TransformContextProtocol) -> list[Block]:
    lines = _walk_algorithmic_body(list(env.body), ctx)
    return [AlgorithmBlock(text=_algo_lines_to_markdown(lines))]
