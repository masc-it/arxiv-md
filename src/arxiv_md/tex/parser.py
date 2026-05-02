from __future__ import annotations

from arxiv_md.tex.ast import (
    Command,
    Env,
    Group,
    Math,
    Node,
    ParagraphBreak,
    Parameter,
    Text,
    Verbatim,
)
from arxiv_md.tex.lexer import Diagnostics, TokKind, Token, tokenize
from arxiv_md.tex.signatures import COMMAND_SIGNATURES, ENV_SIGNATURES


_GREEDY_CAP = 5


_SECTION_LIKE = frozenset(
    {
        "section",
        "subsection",
        "subsubsection",
        "chapter",
        "part",
        "paragraph",
        "subparagraph",
    }
)


class Parser:
    __slots__ = ("text", "tokens", "pos", "diag", "extra_signatures")

    def __init__(
        self,
        text: str,
        tokens: list[Token],
        diag: Diagnostics,
        *,
        extra_signatures: dict[str, str] | None = None,
    ) -> None:
        self.text = text
        self.tokens = tokens
        self.pos = 0
        self.diag = diag
        self.extra_signatures = extra_signatures or {}

    def parse(self) -> list[Node]:
        nodes: list[Node] = []
        while self._peek().kind is not TokKind.EOF:
            save_pos = self.pos
            save_warn = len(self.diag.warnings)

            def _end(tok: Token, anchor: int = save_pos) -> bool:
                if tok.kind is TokKind.EOF:
                    return True
                if tok.kind is TokKind.COMMAND and self.pos != anchor:
                    if tok.value.rstrip("*") in _SECTION_LIKE:
                        return True
                return False

            try:
                chunk = self._read_nodes(end_predicate=_end)
                nodes.extend(chunk)
            except RecursionError:
                self.diag.warnings = self.diag.warnings[:save_warn]
                err_pos = (
                    self.tokens[save_pos].pos if save_pos < len(self.tokens) else 0
                )
                self.diag.warn_at(
                    "parse_recovery",
                    "Recovery overflow; skipping to next section",
                    err_pos,
                )
                if self.pos == save_pos:
                    self._advance()
        if self._peek().kind is TokKind.EOF:
            self._advance()
        return nodes

    def _peek(self, offset: int = 0) -> Token:
        idx = self.pos + offset
        if idx >= len(self.tokens):
            return self.tokens[-1]
        return self.tokens[idx]

    def _advance(self) -> Token:
        tok = self.tokens[self.pos]
        if tok.kind is not TokKind.EOF:
            self.pos += 1
        return tok

    def _skip_ws(self) -> None:
        while True:
            tok = self._peek()
            if tok.kind is TokKind.TEXT and tok.value.strip() == "":
                self._advance()
                continue
            return

    def _read_nodes(self, *, end_predicate) -> list[Node]:
        out: list[Node] = []
        while True:
            tok = self._peek()
            if tok.kind is TokKind.EOF:
                return out
            if end_predicate(tok):
                return out
            node = self._read_node()
            if node is not None:
                out.append(node)

    def _read_node(self) -> Node | None:
        tok = self._peek()
        kind = tok.kind

        if kind is TokKind.TEXT:
            self._advance()
            return Text(pos=tok.pos, value=tok.value)
        if kind is TokKind.PARAGRAPH_BREAK:
            self._advance()
            return ParagraphBreak(pos=tok.pos)
        if kind is TokKind.PARAMETER:
            self._advance()
            try:
                idx = int(tok.value)
            except ValueError:
                idx = 0
            return Parameter(pos=tok.pos, index=idx)
        if kind is TokKind.ALIGN_TAB:
            self._advance()
            return Text(pos=tok.pos, value="&")
        if kind is TokKind.LBRACK:
            self._advance()
            return Text(pos=tok.pos, value="[")
        if kind is TokKind.RBRACK:
            self._advance()
            return Text(pos=tok.pos, value="]")
        if kind is TokKind.BEGIN_GROUP:
            return self._read_group()
        if kind is TokKind.END_GROUP:
            self._advance()
            self.diag.warn_at(
                "parse_recovery",
                "Unmatched '}'",
                tok.pos,
                tok.pos + 1,
            )
            return None
        if kind is TokKind.INLINE_MATH_OPEN or kind is TokKind.DISPLAY_MATH_OPEN:
            return self._read_math(self._advance())
        if kind is TokKind.INLINE_MATH_CLOSE or kind is TokKind.DISPLAY_MATH_CLOSE:
            self._advance()
            self.diag.warn_at(
                "parse_recovery",
                f"Unmatched math close '{tok.value}'",
                tok.pos,
                tok.pos + len(tok.value),
            )
            return None
        if kind is TokKind.BEGIN_ENV:
            return self._read_env(self._advance())
        if kind is TokKind.END_ENV:
            self._advance()
            self.diag.warn_at(
                "parse_recovery",
                f"Unmatched \\end{{{tok.meta}}}",
                tok.pos,
                tok.pos + 6 + len(tok.meta),
            )
            return None
        if kind is TokKind.VERB_INLINE:
            self._advance()
            return Verbatim(pos=tok.pos, text=tok.value, language=tok.meta, inline=True)
        if kind is TokKind.VERBATIM_BLOCK:
            self._advance()
            language = (
                ""
                if tok.meta in {"verbatim", "Verbatim", "verbatim*", "comment", "alltt"}
                else tok.meta
            )
            return Verbatim(
                pos=tok.pos, text=tok.value, language=language, inline=False
            )
        if kind is TokKind.COMMAND:
            return self._read_command(self._advance())

        self._advance()
        self.diag.warn_at("parse_recovery", f"Unexpected token {kind}", tok.pos)
        return None

    def _read_group(self) -> Group:
        opener = self._advance()
        children: list[Node] = []
        while True:
            tok = self._peek()
            if tok.kind is TokKind.EOF:
                self.diag.warn_at(
                    "parse_recovery",
                    "EOF inside '{...}'",
                    opener.pos,
                    opener.pos + 1,
                )
                break
            if tok.kind is TokKind.END_GROUP:
                self._advance()
                break
            node = self._read_node()
            if node is not None:
                children.append(node)
        return Group(pos=opener.pos, children=children)

    def _read_optional_arg_after_lbrack(self, opener: Token) -> Group:
        children: list[Node] = []
        depth = 0
        while True:
            tok = self._peek()
            if tok.kind is TokKind.EOF:
                self.diag.warn_at(
                    "parse_recovery",
                    "EOF inside '[...]'",
                    opener.pos,
                    opener.pos + 1,
                )
                break
            if tok.kind is TokKind.RBRACK and depth == 0:
                self._advance()
                break
            if tok.kind is TokKind.LBRACK:
                depth += 1
                self._advance()
                children.append(Text(pos=tok.pos, value="["))
                continue
            if tok.kind is TokKind.RBRACK:
                depth -= 1
                self._advance()
                children.append(Text(pos=tok.pos, value="]"))
                continue
            node = self._read_node()
            if node is not None:
                children.append(node)
        return Group(pos=opener.pos, children=children)

    def _read_math(self, opener: Token) -> Math:
        display = opener.kind is TokKind.DISPLAY_MATH_OPEN

        if opener.value == "$":

            def is_end(t: Token) -> bool:
                return t.kind is TokKind.INLINE_MATH_OPEN and t.value == "$"
        elif opener.value == "$$":

            def is_end(t: Token) -> bool:
                return t.kind is TokKind.DISPLAY_MATH_OPEN and t.value == "$$"
        elif opener.value == "\\(":

            def is_end(t: Token) -> bool:
                return t.kind is TokKind.INLINE_MATH_CLOSE
        elif opener.value == "\\[":

            def is_end(t: Token) -> bool:
                return t.kind is TokKind.DISPLAY_MATH_CLOSE
        else:

            def is_end(t: Token) -> bool:
                return False

        body_start = opener.pos + len(opener.value)
        close_pos: int | None = None
        while True:
            tok = self._peek()
            if tok.kind is TokKind.EOF:
                self.diag.warn_at(
                    "parse_recovery",
                    "Unterminated math",
                    opener.pos,
                    opener.pos + len(opener.value),
                )
                close_pos = tok.pos
                break
            if is_end(tok):
                close_pos = tok.pos
                self._advance()
                break
            self._advance()
        body_text = self.text[body_start:close_pos] if close_pos is not None else ""
        body_text = body_text.strip()
        body: list[Node] = [Text(pos=body_start, value=body_text)] if body_text else []
        return Math(pos=opener.pos, display=display, body=body)

    def _read_env(self, begin_tok: Token) -> Env | Verbatim:
        name = begin_tok.meta or ""
        sig = ENV_SIGNATURES.get(name, "")
        opt_args, args = self._read_signature_args(sig)

        body: list[Node] = []
        depth = 1
        end_pos = begin_tok.pos
        while True:
            tok = self._peek()
            if tok.kind is TokKind.EOF:
                self.diag.warn_at(
                    "parse_recovery",
                    f"Unterminated environment {name}",
                    begin_tok.pos,
                    begin_tok.pos + 8 + len(name),
                )
                end_pos = tok.pos
                break
            if tok.kind is TokKind.BEGIN_ENV and tok.meta == name:
                self._advance()
                child = self._read_env(tok)
                body.append(child)
                continue
            if tok.kind is TokKind.END_ENV:
                if tok.meta == name:
                    self._advance()
                    depth -= 1
                    if depth == 0:
                        end_pos = tok.pos + 6 + len(name)
                        break

                    continue

                self._advance()
                self.diag.warn_at(
                    "parse_recovery",
                    f"Mismatched \\end{{{tok.meta}}} inside env {name}",
                    tok.pos,
                    tok.pos + 6 + len(tok.meta),
                )
                continue
            node = self._read_node()
            if node is not None:
                body.append(node)
        raw = self.text[begin_tok.pos : end_pos] if self.text else ""
        return Env(
            pos=begin_tok.pos,
            name=name,
            opt_args=opt_args,
            args=args,
            body=body,
            end_pos=end_pos,
            raw=raw,
        )

    def _read_command(self, cmd_tok: Token) -> Command:
        raw_name = cmd_tok.value
        star = raw_name.endswith("*")
        base_name = raw_name[:-1] if star else raw_name
        cmd = Command(
            pos=cmd_tok.pos,
            name=base_name,
            star=star,
            trailing_ws=(cmd_tok.meta == "ws"),
        )

        sig = COMMAND_SIGNATURES.get(base_name)
        if sig is None:
            sig = self.extra_signatures.get(base_name)
        if sig is None:
            self._read_args_greedy(cmd)
        else:
            opt_args, args = self._read_signature_args(sig)
            cmd.opt_args = opt_args
            cmd.args = args
        return cmd

    def _read_signature_args(
        self,
        sig: str,
    ) -> tuple[list[Group], list[Group]]:
        opt_args: list[Group] = []
        args: list[Group] = []
        for char in sig:
            if char == "s":
                continue
            if char == "o":
                save = self.pos
                self._skip_ws()
                tok = self._peek()
                if tok.kind is TokKind.LBRACK:
                    self._advance()
                    opt_args.append(self._read_optional_arg_after_lbrack(tok))
                else:
                    self.pos = save
                continue
            if char == "m":
                save = self.pos
                self._skip_ws()
                tok = self._peek()
                if tok.kind is TokKind.BEGIN_GROUP:
                    args.append(self._read_group())
                else:
                    self.pos = save

                continue
            if char == "v":
                continue

        return opt_args, args

    def _read_args_greedy(self, cmd: Command) -> None:
        captured = 0
        while captured < _GREEDY_CAP:
            save = self.pos
            self._skip_ws()
            tok = self._peek()
            if tok.kind is TokKind.LBRACK:
                self._advance()
                opt = self._read_optional_arg_after_lbrack(tok)
                self._skip_ws()
                if self._peek().kind is TokKind.BEGIN_GROUP:
                    cmd.opt_args.append(opt)
                    cmd.args.append(self._read_group())
                    captured += 1
                    continue

                self.pos = save
                return
            if tok.kind is TokKind.BEGIN_GROUP:
                cmd.args.append(self._read_group())
                captured += 1
                continue
            self.pos = save
            return


def parse(
    tokens: list[Token],
    diag: Diagnostics | None = None,
    *,
    source_text: str = "",
    extra_signatures: dict[str, str] | None = None,
) -> list[Node]:

    diag = diag if diag is not None else Diagnostics()
    return Parser(source_text, tokens, diag, extra_signatures=extra_signatures).parse()


def parse_text(text: str, diag: Diagnostics | None = None) -> list[Node]:

    diag = diag if diag is not None else Diagnostics()
    toks = tokenize(text, diag)
    return Parser(text, toks, diag).parse()
