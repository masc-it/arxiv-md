from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from types import MappingProxyType

from typing import Callable, ClassVar, Mapping

from arxiv_md.tex._common import SourceSpan, TexWarning, warning


class TokKind(str, Enum):
    TEXT = "TEXT"
    COMMAND = "COMMAND"
    BEGIN_GROUP = "BEGIN_GROUP"
    END_GROUP = "END_GROUP"
    LBRACK = "LBRACK"
    RBRACK = "RBRACK"
    INLINE_MATH_OPEN = "INLINE_MATH_OPEN"
    INLINE_MATH_CLOSE = "INLINE_MATH_CLOSE"
    DISPLAY_MATH_OPEN = "DISPLAY_MATH_OPEN"
    DISPLAY_MATH_CLOSE = "DISPLAY_MATH_CLOSE"
    ALIGN_TAB = "ALIGN_TAB"
    PARAMETER = "PARAMETER"
    PARAGRAPH_BREAK = "PARAGRAPH_BREAK"
    BEGIN_ENV = "BEGIN_ENV"
    END_ENV = "END_ENV"
    VERB_INLINE = "VERB_INLINE"
    VERBATIM_BLOCK = "VERBATIM_BLOCK"
    EOF = "EOF"


@dataclass(slots=True, frozen=True)
class Token:
    kind: TokKind
    value: str
    pos: int

    meta: str = ""


@dataclass(slots=True)
class Diagnostics:
    warnings: list[TexWarning] = field(default_factory=list)
    unknown_command_counts: dict[str, int] = field(default_factory=dict)
    unknown_env_counts: dict[str, int] = field(default_factory=dict)
    raw_fallback_command_counts: dict[str, int] = field(default_factory=dict)

    mapper: Callable[[int, int | None], SourceSpan | None] | None = None

    def warn(self, code: str, message: str, path: Path | None = None) -> None:
        self.warnings.append(warning(code, message, path))

    def warn_at(
        self,
        code: str,
        message: str,
        start: int,
        end: int | None = None,
    ) -> None:
        span: SourceSpan | None = None
        if self.mapper is not None:
            span = self.mapper(start, end)
        self.warnings.append(warning(code, message, span=span))


VERBATIM_ENVS: frozenset[str] = frozenset(
    {
        "verbatim",
        "Verbatim",
        "verbatim*",
        "lstlisting",
        "minted",
        "comment",
        "alltt",
    }
)


VERB_INLINE_CMDS: frozenset[str] = frozenset({"verb", "lstinline", "mintinline"})


_TEXT_STOP_CHARS: frozenset[str] = frozenset("\\$%{}[]&#\n")


def _is_verb_delim(c: str) -> bool:
    return bool(c) and not c.isspace() and not c.isalpha() and c != "*"


def _read_digits(text: str, pos: int, n: int) -> tuple[int, bool]:
    j = pos
    while j < n and text[j].isdigit():
        j += 1
    return j, j > pos


def _read_number(text: str, pos: int, n: int) -> tuple[int, bool]:
    j = pos
    if j < n and text[j] in "+-":
        j += 1
    j, saw_digit = _read_digits(text, j, n)
    if j < n and text[j] == ".":
        j += 1
        j, saw_frac = _read_digits(text, j, n)
        saw_digit = saw_digit or saw_frac
    return j, saw_digit


def _read_dimen_tail(text: str, pos: int, n: int) -> int:
    j = pos
    while j < n and text[j].isalpha():
        j += 1
    if j < n and text[j] == "\\":
        j += 1
        while j < n and (text[j].isalpha() or text[j] == "@"):
            j += 1
    return j


def _skip_ws(text: str, pos: int, n: int) -> int:
    while pos < n and text[pos] in " \t":
        pos += 1
    return pos


def _match_glue_kw(text: str, pos: int, n: int, kw: str) -> int:
    if not text.startswith(kw, pos):
        return -1
    end = pos + len(kw)
    if end < n and (text[end].isalpha() or text[end] == "@"):
        return -1
    return end


def _skip_glue_tail(text: str, pos: int, n: int) -> int:
    j = pos
    for kw in ("plus", "minus"):
        kw_start = _skip_ws(text, j, n)
        kw_end = _match_glue_kw(text, kw_start, n, kw)
        if kw_end < 0:
            continue
        k = _skip_ws(text, kw_end, n)
        k, kw_saw_digit = _read_number(text, k, n)
        if not kw_saw_digit:
            break
        j = _read_dimen_tail(text, k, n)
    return j


class Lexer:
    __slots__ = ("text", "pos", "diag", "_dollar_open", "_paren_depth", "_brack_depth")

    _SIMPLE_TOKENS: ClassVar[Mapping[str, TokKind]] = MappingProxyType(
        {
            "{": TokKind.BEGIN_GROUP,
            "}": TokKind.END_GROUP,
            "[": TokKind.LBRACK,
            "]": TokKind.RBRACK,
            "&": TokKind.ALIGN_TAB,
        }
    )

    def __init__(self, text: str, diag: Diagnostics | None = None) -> None:
        self.text = text
        self.pos = 0
        self.diag = diag if diag is not None else Diagnostics()

        self._dollar_open = False
        self._paren_depth = 0
        self._brack_depth = 0

    @property
    def _in_math(self) -> bool:
        return self._dollar_open or self._paren_depth > 0 or self._brack_depth > 0

    def tokens(self) -> list[Token]:
        out: list[Token] = []
        while self.pos < len(self.text):
            tok = self._next()
            if tok is None:
                continue
            out.append(tok)
        out.append(Token(TokKind.EOF, "", len(self.text)))
        return out

    def _next(self) -> Token | None:
        c = self.text[self.pos]

        if c == "%":
            return self._consume_comment()

        if c == "\\":
            return self._consume_backslash()

        if c == "$":
            return self._consume_dollar()
        if c == "#":
            return self._consume_hash()
        if c == "\n":
            return self._consume_newlines()

        kind = self._SIMPLE_TOKENS.get(c)
        if kind is not None:
            start = self.pos
            self.pos += 1
            return Token(kind, c, start)

        return self._consume_text()

    def _consume_comment(self) -> Token | None:

        end = self.text.find("\n", self.pos)
        self.pos = len(self.text) if end < 0 else end + 1
        return None

    def _consume_backslash(self) -> Token | None:
        start = self.pos
        nxt = self.text[self.pos + 1 : self.pos + 2]

        math = self._consume_math_escape(start, nxt)
        if math is not None:
            return math

        special = self._consume_special_escape(start, nxt)
        if special is not None:
            return special

        return self._consume_named_command(start)

    def _consume_math_escape(self, start: int, nxt: str) -> Token | None:
        if nxt == "(":
            self.pos += 2
            self._paren_depth += 1
            return Token(TokKind.INLINE_MATH_OPEN, "\\(", start)
        if nxt == ")":
            self.pos += 2
            if self._paren_depth > 0:
                self._paren_depth -= 1
            return Token(TokKind.INLINE_MATH_CLOSE, "\\)", start)
        if nxt == "[":
            self.pos += 2
            self._brack_depth += 1
            return Token(TokKind.DISPLAY_MATH_OPEN, "\\[", start)
        if nxt == "]":
            self.pos += 2
            if self._brack_depth > 0:
                self._brack_depth -= 1
            return Token(TokKind.DISPLAY_MATH_CLOSE, "\\]", start)
        return None

    def _consume_special_escape(self, start: int, nxt: str) -> Token | None:
        if nxt == "\\":
            self.pos += 2
            return Token(TokKind.TEXT, " ", start)

        if nxt in (" ", "\t", "\n"):
            self.pos += 2
            return Token(TokKind.TEXT, " ", start)

        if nxt and not nxt.isalpha() and nxt != "@":
            self.pos += 2
            if nxt in {"%", "&", "_", "#", "{", "}", "$"}:
                return Token(TokKind.TEXT, nxt, start)
            return Token(TokKind.COMMAND, nxt, start)
        return None

    def _consume_named_command(self, start: int) -> Token:
        name, name_end, had_ws = self._read_command_name(self.pos + 1)
        if not name:
            self.pos += 1
            return Token(TokKind.TEXT, "\\", start)
        self.pos = name_end

        if not self._in_math:
            self._skip_optional_assignment()

        had_ws = had_ws and name not in VERB_INLINE_CMDS

        if name == "par":
            return Token(TokKind.PARAGRAPH_BREAK, "\\par", start)

        if name in ("begin", "end"):
            return self._consume_begin_end(start, name)

        if name in VERB_INLINE_CMDS:
            verb = self._consume_verb_inline(start, name)
            if verb is not None:
                return verb

        return Token(TokKind.COMMAND, name, start, "ws" if had_ws else "")

    def _consume_begin_end(self, start: int, name: str) -> Token:
        env_name = self._read_required_brace_name()
        kind = TokKind.BEGIN_ENV if name == "begin" else TokKind.END_ENV
        if env_name is None:
            self.diag.warn_at("parse_recovery", f"Malformed \\{name}{{...}}", start)
            return Token(kind, name, start, "")
        if kind is TokKind.BEGIN_ENV and env_name in VERBATIM_ENVS:
            return self._consume_verbatim_env(start, env_name)
        return Token(kind, name, start, env_name)

    def _consume_dollar(self) -> Token:
        start = self.pos
        if self.text.startswith("$$", self.pos):
            self.pos += 2
            self._dollar_open = not self._dollar_open
            return Token(TokKind.DISPLAY_MATH_OPEN, "$$", start)
        self.pos += 1
        self._dollar_open = not self._dollar_open
        return Token(TokKind.INLINE_MATH_OPEN, "$", start)

    def _consume_hash(self) -> Token:
        start = self.pos

        if self.text.startswith("##", self.pos):
            self.pos += 2
            return Token(TokKind.TEXT, "#", start)

        if self.pos + 1 < len(self.text) and self.text[self.pos + 1].isdigit():
            idx = self.text[self.pos + 1]
            self.pos += 2
            return Token(TokKind.PARAMETER, idx, start)

        self.pos += 1
        return Token(TokKind.TEXT, "#", start)

    def _consume_newlines(self) -> Token | None:
        start = self.pos

        nl_count = 0
        i = self.pos
        while i < len(self.text):
            ch = self.text[i]
            if ch == "\n":
                nl_count += 1
                i += 1
                continue
            if ch in " \t\r":
                i += 1
                continue
            break
        self.pos = i
        if nl_count >= 2:
            return Token(TokKind.PARAGRAPH_BREAK, "\n\n", start)

        return Token(TokKind.TEXT, " ", start)

    def _consume_text(self) -> Token:
        start = self.pos
        i = self.pos
        stop = _TEXT_STOP_CHARS
        while i < len(self.text) and self.text[i] not in stop:
            i += 1

        if i == start:
            i += 1
        self.pos = i
        return Token(TokKind.TEXT, self.text[start:i], start)

    def _read_command_name(self, pos: int) -> tuple[str, int, bool]:
        i = pos
        while i < len(self.text) and (self.text[i].isalpha() or self.text[i] == "@"):
            i += 1
        if i == pos:
            return "", pos, False
        name = self.text[pos:i]

        if i < len(self.text) and self.text[i] == "*":
            name += "*"
            i += 1

        had_ws = False
        while i < len(self.text) and self.text[i] in " \t":
            i += 1
            had_ws = True
        return name, i, had_ws

    def _skip_optional_assignment(self) -> None:
        text = self.text
        n = len(text)
        i = self.pos

        i = _skip_ws(text, i, n)
        if i >= n or text[i] != "=":
            return

        j = _skip_ws(text, i + 1, n)

        j, saw_digit = _read_number(text, j, n)
        if not saw_digit:
            return
        j = _read_dimen_tail(text, j, n)

        self.pos = _skip_glue_tail(text, j, n)

    def _read_required_brace_name(self) -> str | None:

        i = self.pos
        while i < len(self.text) and self.text[i] in " \t\n":
            i += 1
        if i >= len(self.text) or self.text[i] != "{":
            return None
        end = self.text.find("}", i + 1)
        if end < 0:
            return None
        name = self.text[i + 1 : end].strip()
        self.pos = end + 1
        return name

    def _consume_verb_inline(self, start: int, name: str) -> Token | None:

        i = self._skip_verb_options(self.pos)
        if i is None:
            return None
        i, language = self._read_verb_language(i, name)
        if i is None:
            return None
        if i >= len(self.text):
            return None
        delim = self.text[i]
        if not _is_verb_delim(delim):
            return None
        body_start = i + 1
        body_end = self.text.find(delim, body_start)
        if body_end < 0:
            self.diag.warn_at("parse_recovery", f"Unterminated \\{name}", start)
            return None
        self.pos = body_end + 1
        return Token(
            TokKind.VERB_INLINE,
            self.text[body_start:body_end],
            start,
            language or name,
        )

    def _skip_verb_options(self, i: int) -> int | None:
        if i >= len(self.text) or self.text[i] != "[":
            return i
        close = self.text.find("]", i + 1)
        if close < 0:
            return None
        return close + 1

    def _read_verb_language(self, i: int, name: str) -> tuple[int | None, str]:
        if name != "mintinline" or i >= len(self.text) or self.text[i] != "{":
            return i, ""
        close = self.text.find("}", i + 1)
        if close < 0:
            return None, ""
        return close + 1, self.text[i + 1 : close].strip()

    def _consume_verbatim_env(self, start: int, env_name: str) -> Token:

        marker = "\\end{" + env_name + "}"
        end = self.text.find(marker, self.pos)
        if end < 0:
            self.diag.warn_at(
                "parse_recovery", f"Unterminated verbatim env {env_name}", start
            )
            body = self.text[self.pos :]
            self.pos = len(self.text)
            return Token(TokKind.VERBATIM_BLOCK, body, start, env_name)
        body = self.text[self.pos : end]
        self.pos = end + len(marker)
        return Token(TokKind.VERBATIM_BLOCK, body, start, env_name)


def tokenize(text: str, diag: Diagnostics | None = None) -> list[Token]:
    return Lexer(text, diag).tokens()
