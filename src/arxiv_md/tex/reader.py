from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(slots=True)
class TextNode:
    text: str
    raw: str = ""


@dataclass(slots=True)
class CommandNode:
    name: str
    optional_args: list[str] = field(default_factory=list)
    args: list[str] = field(default_factory=list)
    raw: str = ""


@dataclass(slots=True)
class EnvironmentNode:
    name: str
    optional_args: list[str] = field(default_factory=list)
    body: str = ""
    raw: str = ""


@dataclass(slots=True)
class MathNode:
    display: bool
    text: str
    raw: str = ""


COMMAND_RE = re.compile(r"\\([A-Za-z@]+|.)")


def read_command(text: str, pos: int) -> CommandNode | None:
    match = COMMAND_RE.match(text, pos)
    if not match:
        return None
    return CommandNode(name=match.group(1), raw=match.group(0))


def read_braced_group(text: str, pos: int) -> tuple[str, int] | None:
    pos = skip_ws(text, pos)
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


def read_optional_group(text: str, pos: int) -> tuple[str, int] | None:
    pos = skip_ws(text, pos)
    if pos >= len(text) or text[pos] != "[":
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
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return text[start:i], i + 1
    return None


def read_environment(text: str, pos: int) -> EnvironmentNode | None:
    begin = re.match(r"\\begin\{([^{}]+)\}", text[pos:])
    if not begin:
        return None
    name = begin.group(1)
    body_start = pos + begin.end()
    close = find_environment_end(text, name, body_start)
    if close is None:
        return None
    body, end_pos = close
    return EnvironmentNode(name=name, body=body, raw=text[pos:end_pos])


def read_inline_math(text: str, pos: int) -> MathNode | None:
    if text.startswith(r"\(", pos):
        end = text.find(r"\)", pos + 2)
        if end >= 0:
            return MathNode(
                display=False, text=text[pos + 2 : end], raw=text[pos : end + 2]
            )
    if text[pos : pos + 1] == "$" and text[pos : pos + 2] != "$$":
        end = _find_unescaped(text, "$", pos + 1)
        if end >= 0:
            return MathNode(
                display=False, text=text[pos + 1 : end], raw=text[pos : end + 1]
            )
    return None


def read_display_math(text: str, pos: int) -> MathNode | None:
    if text.startswith(r"\[", pos):
        end = text.find(r"\]", pos + 2)
        if end >= 0:
            return MathNode(
                display=True, text=text[pos + 2 : end], raw=text[pos : end + 2]
            )
    if text.startswith("$$", pos):
        end = text.find("$$", pos + 2)
        if end >= 0:
            return MathNode(
                display=True, text=text[pos + 2 : end], raw=text[pos : end + 2]
            )
    return None


def find_environment_end(
    text: str, name: str, body_start: int
) -> tuple[str, int] | None:
    begin_pat = re.compile(r"\\begin\{" + re.escape(name) + r"\}")
    end_pat = re.compile(r"\\end\{" + re.escape(name) + r"\}")
    depth = 1
    pos = body_start
    while pos < len(text):
        next_begin = begin_pat.search(text, pos)
        next_end = end_pat.search(text, pos)
        if next_end is None:
            return None
        if next_begin is not None and next_begin.start() < next_end.start():
            depth += 1
            pos = next_begin.end()
            continue
        depth -= 1
        if depth == 0:
            return text[body_start : next_end.start()], next_end.end()
        pos = next_end.end()
    return None


def skip_ws(text: str, pos: int) -> int:
    while pos < len(text) and text[pos].isspace():
        pos += 1
    return pos


def _find_unescaped(text: str, needle: str, pos: int) -> int:
    while True:
        found = text.find(needle, pos)
        if found < 0:
            return -1
        backslashes = 0
        i = found - 1
        while i >= 0 and text[i] == "\\":
            backslashes += 1
            i -= 1
        if backslashes % 2 == 0:
            return found
        pos = found + 1
