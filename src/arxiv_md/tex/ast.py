from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Node:
    """Base parsed node; `pos` indexes the expanded TeX source string."""

    pos: int = 0


@dataclass(slots=True)
class Text(Node):
    """Text node content follows TeX comment and whitespace rules."""

    value: str = ""


@dataclass(slots=True)
class Group(Node):
    """Balanced `{...}` or `[...]` argument contents without delimiters."""

    children: list[Node] = field(default_factory=list)


@dataclass(slots=True)
class Command(Node):
    """Parsed control sequence with signature-driven optional/required args."""

    name: str = ""
    star: bool = False
    opt_args: list[Group] = field(default_factory=list)
    args: list[Group] = field(default_factory=list)

    trailing_ws: bool = False


@dataclass(slots=True)
class Env(Node):
    """Parsed `\\begin`/`\\end` environment preserving raw source slice."""

    name: str = ""
    opt_args: list[Group] = field(default_factory=list)
    args: list[Group] = field(default_factory=list)
    body: list[Node] = field(default_factory=list)
    end_pos: int = 0
    raw: str = ""


@dataclass(slots=True)
class Math(Node):
    """Math delimiter body; transformer decides inline vs display IR."""

    display: bool = False
    body: list[Node] = field(default_factory=list)


@dataclass(slots=True)
class Verbatim(Node):
    """Opaque verbatim body; parser never interprets nested TeX inside it."""

    text: str = ""
    language: str = ""
    inline: bool = False


@dataclass(slots=True)
class Parameter(Node):
    """Macro parameter marker such as `#1` retained inside macro bodies."""

    index: int = 0


@dataclass(slots=True)
class ParagraphBreak(Node):
    """Structural blank-line marker produced before block transformation."""

    pass


@dataclass(slots=True)
class Comment(Node):
    """Retained TeX comment when lexer is explicitly configured to keep comments."""

    value: str = ""


@dataclass(slots=True)
class RefMarker(Node):
    key: str = ""
    style: str = ""
    display: str = ""
