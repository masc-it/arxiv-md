from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol, cast, runtime_checkable

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
from arxiv_md.tex.commands import (
    ACCENT_COMMANDS,
    IGNORED_INLINE_COMMANDS,
    KNOWN_INLINE_COMMANDS,
)
from arxiv_md.tex.handler_types import TransformContextProtocol
from arxiv_md.tex.lexer import Diagnostics
from arxiv_md.tex.macro_engine import TRAILING_WS_SENTINEL
from arxiv_md.tex.model import (
    CitationSpan,
    CodeSpan,
    EmphasisSpan,
    InlineNode,
    LinkSpan,
    MathSpan,
    RawLatexSpan,
    ReferenceSpan,
    StrongSpan,
    SubscriptSpan,
    SuperscriptSpan,
    TextSpan,
)
from arxiv_md.tex.transform.math_text import KNOWN_MATH_COMMANDS, _math_to_text


__all__ = [
    "InlineEngine",
    "transform_inline",
    "INLINE_WRAPPERS",
    "INLINE_PASSTHROUGH",
    "INLINE_DROPPED",
    "INLINE_NOOP",
    "CITE_COMMANDS",
    "CITE_PLURAL_COMMANDS",
    "REF_COMMANDS",
    "TEXT_MACROS",
    "MATH_GLYPHS",
    "MATH_COMPLEX",
    "XSPACE_COMMANDS",
    "BUILTIN_COMMAND_SPECS",
    "InlineCommandHandler",
    "InlineCommandSpec",
]


INLINE_WRAPPERS: frozenset[str] = frozenset({"textbf", "emph", "textit", "texttt"})


DECL_FONT_MAP: dict[str, str] = {
    "em": "emphasis",
    "it": "emphasis",
    "itshape": "emphasis",
    "sl": "emphasis",
    "slshape": "emphasis",
    "bf": "strong",
    "bfseries": "strong",
    "tt": "code",
    "ttfamily": "code",
    "rm": "passthrough",
    "rmfamily": "passthrough",
    "sf": "passthrough",
    "sffamily": "passthrough",
    "sc": "passthrough",
    "scshape": "passthrough",
    "mdseries": "passthrough",
    "upshape": "passthrough",
    "normalfont": "passthrough",
}


INLINE_PASSTHROUGH: frozenset[str] = (
    frozenset(
        {
            "textsc",
            "textnormal",
            "textmd",
            "textrm",
            "textsf",
            "underline",
            "uline",
            "uuline",
            "uwave",
            "sout",
            "mbox",
            "fbox",
            "framebox",
            "makebox",
            "detokenize",
            "text",
            "v",
            "ensuremath",
            "centerline",
            "leftline",
            "rightline",
            "mathrm",
            "mathbf",
            "mathcal",
            "mathbb",
            "mathit",
            "mathsf",
            "mathtt",
            "boldsymbol",
            "bm",
            "operatorname",
        }
    )
    | ACCENT_COMMANDS
)


INLINE_DROPPED: frozenset[str] = frozenset(
    {
        "footnote",
        "footnotemark",
        "footnotetext",
        "thanks",
        "label",
        "bibliography",
        "bibliographystyle",
        "addbibresource",
        "printbibliography",
        "captionsetup",
        "ignorespaces",
        "ignorespacesafterend",
        "phantomsection",
        "bibitem",
        "index",
    }
)


INLINE_NOOP: frozenset[str] = frozenset(IGNORED_INLINE_COMMANDS) | frozenset(
    {
        "vspace",
        "hspace",
        "hskip",
        "vskip",
        "rule",
        "raisebox",
        "rotatebox",
        "scalebox",
        "newblock",
        "fontsize",
        "fontencoding",
        "looseness",
        "itemsep",
        "tabcolsep",
        "baselineskip",
        "sisetup",
    }
)

INLINE_LIST_ENVS: frozenset[str] = frozenset({"itemize", "enumerate", "description"})


CITE_COMMANDS: frozenset[str] = frozenset(
    {
        "cite",
        "citep",
        "citet",
        "citealt",
        "citealp",
        "citeauthor",
        "citeyear",
        "parencite",
        "textcite",
        "autocite",
        "footcite",
        "shortcite",
        "citeyearpar",
    }
)


CITE_PLURAL_COMMANDS: frozenset[str] = frozenset({"parencites", "textcites"})
REF_COMMANDS: frozenset[str] = frozenset(
    {"ref", "cref", "Cref", "eqref", "autoref", "pageref", "nameref"}
)


TEXT_MACROS: dict[str, str] = {
    "ldots": "...",
    "dots": "...",
    "textellipsis": "...",
    "textbackslash": "\\\\",
    "textasciitilde": "~",
    "textasciicircum": "^",
    "newline": " ",
    "\\\\": " ",
    "quad": " ",
    "qquad": " ",
    "hfill": " ",
    "vfill": " ",
    "smallskip": "",
    "medskip": "",
    "bigskip": "",
    "and": " and ",
    "AND": " and ",
    "And": " and ",
    "eg": "e.g.",
    "ie": "i.e.",
    "vs": "vs.",
    "onedot": ".",
    "@onedot": ".",
    "fullstop": ".",
    "LaTeX": "LaTeX",
    "TeX": "TeX",
    "etal": "et al.",
    "etc": "etc.",
    "textbar": "|",
    "textemdash": "\u2014",
    "textendash": "\u2013",
    "textless": "<",
    "textgreater": ">",
}


_TEXT_MACRO_WORDLIKE: frozenset[str] = frozenset(
    {"LaTeX", "TeX", "etal", "etc", "eg", "ie", "vs"}
)


MATH_GLYPHS: frozenset[str] = frozenset(
    {
        "alpha",
        "beta",
        "gamma",
        "delta",
        "epsilon",
        "varepsilon",
        "zeta",
        "eta",
        "theta",
        "vartheta",
        "iota",
        "kappa",
        "lambda",
        "mu",
        "nu",
        "xi",
        "pi",
        "varpi",
        "rho",
        "varrho",
        "sigma",
        "varsigma",
        "tau",
        "upsilon",
        "phi",
        "varphi",
        "chi",
        "psi",
        "omega",
        "Alpha",
        "Beta",
        "Gamma",
        "Delta",
        "Epsilon",
        "Zeta",
        "Eta",
        "Theta",
        "Iota",
        "Kappa",
        "Lambda",
        "Mu",
        "Nu",
        "Xi",
        "Pi",
        "Rho",
        "Sigma",
        "Tau",
        "Upsilon",
        "Phi",
        "Chi",
        "Psi",
        "Omega",
        "infty",
        "leq",
        "geq",
        "neq",
        "approx",
        "sim",
        "propto",
        "triangleq",
        "subset",
        "subseteq",
        "supset",
        "supseteq",
        "cup",
        "cap",
        "rightarrow",
        "leftarrow",
        "Leftrightarrow",
        "Rightarrow",
        "Leftarrow",
        "to",
        "mapsto",
        "implies",
        "iff",
        "sum",
        "prod",
        "int",
        "oint",
        "partial",
        "nabla",
        "pm",
        "mp",
        "times",
        "div",
        "cdot",
        "ast",
        "forall",
        "exists",
        "neg",
        "wedge",
        "vee",
        "dagger",
        "ddagger",
        "le",
        "ge",
        "ne",
        "equiv",
        "in",
        "notin",
        "emptyset",
        "varnothing",
        "leftrightarrow",
        "longrightarrow",
        "longleftarrow",
        "longleftrightarrow",
        "Longrightarrow",
        "Longleftarrow",
        "Longleftrightarrow",
        "hookrightarrow",
        "hookleftarrow",
        "nearrow",
        "searrow",
        "swarrow",
        "nwarrow",
        "gets",
        "uparrow",
        "downarrow",
        "updownarrow",
        "Uparrow",
        "Downarrow",
        "Updownarrow",
        "star",
        "bullet",
        "circ",
        "oplus",
        "ominus",
        "otimes",
        "odot",
        "setminus",
        "ll",
        "gg",
        "prec",
        "succ",
        "preceq",
        "succeq",
        "sqcap",
        "sqcup",
        "models",
        "vdash",
        "dashv",
        "aleph",
        "beth",
        "ell",
        "hbar",
        "Re",
        "Im",
        "top",
        "bot",
        "perp",
        "angle",
        "triangle",
        "square",
        "Box",
        "Diamond",
        "langle",
        "rangle",
        "lceil",
        "rceil",
        "lfloor",
        "rfloor",
        "vert",
        "Vert",
        "ldots",
        "cdots",
        "vdots",
        "ddots",
        "prime",
        "checkmark",
        "Checkmark",
        "copyright",
        "degree",
        "ldotp",
        "cdotp",
        "colon",
        "semicolon",
        "land",
        "lor",
        "lnot",
    }
)


MATH_COMPLEX: frozenset[str] = frozenset(
    {"frac", "dfrac", "tfrac", "cfrac", "sqrt", "binom", "tbinom", "dbinom"}
)

XSPACE_COMMANDS: frozenset[str] = frozenset({"xspace", "@xspace"})


_XSPACE_EXCEPTIONS: frozenset[str] = frozenset(".,;:!?'`)]}/-~")


@runtime_checkable
class InlineCommandHandler(Protocol):
    name: str

    def emit(
        self,
        cmd: Command,
        next_node: Node | None,
        engine: "InlineEngine",
        ctx: TransformContextProtocol | None,
    ) -> list[InlineNode]: ...


@dataclass(frozen=True, slots=True)
class InlineCommandSpec:
    names: frozenset[str]
    handler: InlineCommandHandler


class XSpaceHandler:
    name = "xspace"

    def emit(
        self,
        cmd: Command,
        next_node: Node | None,
        engine: "InlineEngine",
        ctx: TransformContextProtocol | None,
    ) -> list[InlineNode]:
        glue = _xspace_glue(next_node)
        return [TextSpan(text=glue)] if glue else []


class TextMacroHandler:
    name = "text_macro"

    def emit(
        self,
        cmd: Command,
        next_node: Node | None,
        engine: "InlineEngine",
        ctx: TransformContextProtocol | None,
    ) -> list[InlineNode]:
        mapped = TEXT_MACROS[cmd.name]
        if not mapped:
            return []
        if cmd.trailing_ws and cmd.name in _TEXT_MACRO_WORDLIKE:
            mapped += " "
        return [TextSpan(text=mapped)]


class MathGlyphHandler:
    name = "math_glyph"

    def emit(
        self,
        cmd: Command,
        next_node: Node | None,
        engine: "InlineEngine",
        ctx: TransformContextProtocol | None,
    ) -> list[InlineNode]:
        return [MathSpan(tex=f"\\{cmd.name}", rendered_text=None)]


class MathComplexHandler:
    name = "math_complex"

    def emit(
        self,
        cmd: Command,
        next_node: Node | None,
        engine: "InlineEngine",
        ctx: TransformContextProtocol | None,
    ) -> list[InlineNode]:
        tex = _cmd_to_tex(cmd)
        return [MathSpan(tex=tex, rendered_text=None)]


class WrapperHandler:
    name = "wrapper"

    def emit(
        self,
        cmd: Command,
        next_node: Node | None,
        engine: "InlineEngine",
        ctx: TransformContextProtocol | None,
    ) -> list[InlineNode]:
        inner = engine._arg(cmd, 0, ctx=ctx)
        n = cmd.name
        if n == "textbf":
            return [StrongSpan(children=inner)]
        if n in ("emph", "textit"):
            return [EmphasisSpan(children=inner)]
        if n == "texttt":
            return [CodeSpan(text=_inline_to_plain(inner))]
        return inner


class PassthroughHandler:
    name = "passthrough"

    def emit(
        self,
        cmd: Command,
        next_node: Node | None,
        engine: "InlineEngine",
        ctx: TransformContextProtocol | None,
    ) -> list[InlineNode]:
        return engine._arg(cmd, 0, ctx=ctx)


class TexOrPdfStringHandler:
    name = "texorpdfstring"

    def emit(
        self,
        cmd: Command,
        next_node: Node | None,
        engine: "InlineEngine",
        ctx: TransformContextProtocol | None,
    ) -> list[InlineNode]:
        # \texorpdfstring{tex}{pdf}: outside math we are emitting plain text
        # (PDF-bookmark variant). Inside math, this command is preserved
        # verbatim as part of the surrounding MathSpan, so this branch only
        # runs in text/heading context.
        return engine._arg(cmd, 1, ctx=ctx)


class DropNoopHandler:
    name = "drop_noop"

    def emit(
        self,
        cmd: Command,
        next_node: Node | None,
        engine: "InlineEngine",
        ctx: TransformContextProtocol | None,
    ) -> list[InlineNode]:
        return []


class HrefUrlHandler:
    name = "href_url"

    def emit(
        self,
        cmd: Command,
        next_node: Node | None,
        engine: "InlineEngine",
        ctx: TransformContextProtocol | None,
    ) -> list[InlineNode]:
        n = cmd.name
        if n == "href":
            url = _inline_to_plain(engine._arg(cmd, 0, ctx=ctx)).strip()
            if len(cmd.args) >= 2:
                children = engine._arg(cmd, 1, ctx=ctx)
            else:
                children = [TextSpan(text=url)] if url else []
            return [LinkSpan(children=children, url=url)]
        if n == "url":
            url = _inline_to_plain(engine._arg(cmd, 0, ctx=ctx)).strip()
            if not url:
                return []
            return [LinkSpan(children=[], url=url)]

        return list(engine._arg(cmd, 0, ctx=ctx))


class ColorPassthroughHandler:
    name = "color_passthrough"

    def emit(
        self,
        cmd: Command,
        next_node: Node | None,
        engine: "InlineEngine",
        ctx: TransformContextProtocol | None,
    ) -> list[InlineNode]:
        n = cmd.name
        if n == "fcolorbox":
            idx = 2 if len(cmd.args) >= 3 else 0
        else:
            idx = 1 if len(cmd.args) >= 2 else 0
        return list(engine._arg(cmd, idx, ctx=ctx))


class ScriptHandler:
    name = "script"

    def emit(
        self,
        cmd: Command,
        next_node: Node | None,
        engine: "InlineEngine",
        ctx: TransformContextProtocol | None,
    ) -> list[InlineNode]:
        inner = engine._arg(cmd, 0, ctx=ctx)
        if cmd.name == "textsuperscript":
            return [SuperscriptSpan(children=inner)]
        return [SubscriptSpan(children=inner)]


class CitationHandler:
    name = "citation"

    def emit(
        self,
        cmd: Command,
        next_node: Node | None,
        engine: "InlineEngine",
        ctx: TransformContextProtocol | None,
    ) -> list[InlineNode]:
        n = cmd.name
        if n in CITE_COMMANDS:
            keys_text = _inline_to_plain(engine._arg(cmd, 0, ctx=ctx))
            keys = [k.strip() for k in keys_text.split(",") if k.strip()]
            return [CitationSpan(keys=keys, kind=n)] if keys else []

        plural_keys: list[str] = []
        for i in range(len(cmd.args)):
            k = _inline_to_plain(engine._arg(cmd, i, ctx=ctx)).strip()
            if k:
                plural_keys.append(k)
        if plural_keys:
            return [CitationSpan(keys=plural_keys, kind=n.rstrip("s"))]
        return []


class ReferenceHandler:
    name = "reference"

    def emit(
        self,
        cmd: Command,
        next_node: Node | None,
        engine: "InlineEngine",
        ctx: TransformContextProtocol | None,
    ) -> list[InlineNode]:
        key = _inline_to_plain(engine._arg(cmd, 0, ctx=ctx)).strip()
        return [ReferenceSpan(key=key, kind=cmd.name)] if key else []


class SiunitxHandler:
    name = "siunitx"

    def emit(
        self,
        cmd: Command,
        next_node: Node | None,
        engine: "InlineEngine",
        ctx: TransformContextProtocol | None,
    ) -> list[InlineNode]:
        from arxiv_md.tex.transform.handlers.siunitx import SIUNITX_COMMANDS

        handler = SIUNITX_COMMANDS[cmd.name]
        return list(handler(cmd, cast(TransformContextProtocol, ctx)))


class UnknownCommandHandler:
    name = "unknown_command"

    def emit(
        self,
        cmd: Command,
        next_node: Node | None,
        engine: "InlineEngine",
        ctx: TransformContextProtocol | None,
    ) -> list[InlineNode]:
        engine._count_unknown(cmd.name)
        out: list[InlineNode] = []
        if cmd.args:
            for i, arg in enumerate(cmd.args):
                if i:
                    out.append(TextSpan(text=" "))
                out.extend(engine.transform(list(arg.children), ctx=ctx))
        return out


_BUILTIN_HANDLER_MAP: dict[str, InlineCommandHandler] = {}


def _build_specs() -> tuple[InlineCommandSpec, ...]:
    specs = (
        InlineCommandSpec(names=XSPACE_COMMANDS, handler=XSpaceHandler()),
        InlineCommandSpec(names=frozenset(TEXT_MACROS), handler=TextMacroHandler()),
        InlineCommandSpec(names=MATH_GLYPHS, handler=MathGlyphHandler()),
        InlineCommandSpec(names=MATH_COMPLEX, handler=MathComplexHandler()),
        InlineCommandSpec(names=INLINE_WRAPPERS, handler=WrapperHandler()),
        InlineCommandSpec(names=INLINE_PASSTHROUGH, handler=PassthroughHandler()),
        InlineCommandSpec(
            names=frozenset({"texorpdfstring"}),
            handler=TexOrPdfStringHandler(),
        ),
        InlineCommandSpec(
            names=INLINE_DROPPED | INLINE_NOOP, handler=DropNoopHandler()
        ),
        InlineCommandSpec(
            names=frozenset({"href", "url", "hyperref"}), handler=HrefUrlHandler()
        ),
        InlineCommandSpec(
            names=frozenset({"textcolor", "colorbox", "fcolorbox"}),
            handler=ColorPassthroughHandler(),
        ),
        InlineCommandSpec(
            names=frozenset({"textsuperscript", "textsubscript"}),
            handler=ScriptHandler(),
        ),
        InlineCommandSpec(
            names=CITE_COMMANDS | CITE_PLURAL_COMMANDS, handler=CitationHandler()
        ),
        InlineCommandSpec(names=REF_COMMANDS, handler=ReferenceHandler()),
        InlineCommandSpec(
            names=frozenset({"SI", "si", "ang", "num", "SIrange", "numrange"}),
            handler=SiunitxHandler(),
        ),
    )
    for spec in specs:
        for n in spec.names:
            if n not in _BUILTIN_HANDLER_MAP:
                _BUILTIN_HANDLER_MAP[n] = spec.handler
    return specs


BUILTIN_COMMAND_SPECS: tuple[InlineCommandSpec, ...] = _build_specs()


_UNKNOWN_HANDLER = UnknownCommandHandler()


def _apply_smart_quotes(text: str) -> str:
    if not text:
        return text
    if "`" in text:
        text = text.replace("``", "\u201c").replace("`", "\u2018")
    if "''" in text:
        text = text.replace("''", "\u201d")
    if "---" in text:
        text = text.replace("---", "\u2014")
    if "--" in text:
        text = text.replace("--", "\u2013")
    return text


def _xspace_glue(next_node: Node | None) -> str:
    if next_node is None:
        return ""
    if isinstance(next_node, Text):
        if next_node.value == TRAILING_WS_SENTINEL:
            return ""
        head = next_node.value[:1]
        if not head:
            return ""
        if head in " \t\n":
            return ""
        if head in _XSPACE_EXCEPTIONS:
            return ""
        return " "
    if isinstance(next_node, Command):
        return ""
    if isinstance(next_node, ParagraphBreak):
        return ""
    return " "


def _math_body_text(node: Math) -> str:
    if not node.body:
        return ""
    head = node.body[0]
    if isinstance(head, Text):
        return head.value
    return ""


def _nodes_to_tex(nodes: Iterable[Node]) -> str:
    parts: list[str] = []
    for n in nodes:
        if isinstance(n, Text):
            parts.append(n.value)
        elif isinstance(n, Command):
            parts.append(_cmd_to_tex(n))
        elif isinstance(n, Group):
            parts.append("{" + _nodes_to_tex(n.children) + "}")
        elif isinstance(n, Math):
            delim = "$$" if n.display else "$"
            parts.append(delim + _nodes_to_tex(n.body) + delim)
    return "".join(parts)


def _cmd_to_tex(cmd: Command) -> str:
    parts = [f"\\{cmd.name}"]
    for opt in cmd.opt_args:
        parts.append("[" + _nodes_to_tex(opt.children) + "]")
    for arg in cmd.args:
        parts.append("{" + _nodes_to_tex(arg.children) + "}")
    return "".join(parts)


class InlineEngine:
    __slots__ = ("diag",)

    def __init__(self, diag: Diagnostics | None = None) -> None:
        self.diag = diag if diag is not None else Diagnostics()

    def transform(
        self,
        nodes: list[Node],
        *,
        ctx: TransformContextProtocol | None = None,
    ) -> list[InlineNode]:
        out: list[InlineNode] = []
        n_total = len(nodes)
        for idx, node in enumerate(nodes):
            nxt = nodes[idx + 1] if idx + 1 < n_total else None
            self._emit(node, nxt, out, ctx=ctx)
        return _coalesce_text(out)

    def transform_source(
        self,
        source: str,
        *,
        ctx: TransformContextProtocol | None = None,
    ) -> list[InlineNode]:
        from arxiv_md.tex.lexer import tokenize
        from arxiv_md.tex.parser import parse as ast_parse

        diag = self.diag
        tokens = tokenize(source, diag)
        nodes = ast_parse(tokens, diag, source_text=source)
        return self.transform(nodes, ctx=ctx)

    def _emit(
        self,
        node: Node,
        next_node: Node | None,
        out: list[InlineNode],
        *,
        ctx: TransformContextProtocol | None,
    ) -> None:
        if isinstance(node, Text):
            if node.value == TRAILING_WS_SENTINEL:
                glue = _xspace_glue(next_node)
                if glue:
                    out.append(TextSpan(text=glue))
                return
            value = node.value.replace("~", " ")
            value = _apply_smart_quotes(value)
            if value:
                out.append(TextSpan(text=value))
            return
        if isinstance(node, ParagraphBreak):
            out.append(TextSpan(text=" "))
            return
        if isinstance(node, Group):
            children = node.children

            if children and isinstance(children[0], Command):
                style = DECL_FONT_MAP.get(children[0].name)
                if style is not None:
                    inner = self.transform(children[1:], ctx=ctx)
                    if style == "emphasis":
                        out.append(EmphasisSpan(children=inner))
                    elif style == "strong":
                        out.append(StrongSpan(children=inner))
                    elif style == "code":
                        out.append(CodeSpan(text=_inline_to_plain(inner)))
                    else:
                        out.extend(inner)
                    return
            out.extend(self.transform(children, ctx=ctx))
            return
        if isinstance(node, Math):
            out.append(self._math(node))
            return
        if isinstance(node, Verbatim):
            out.append(CodeSpan(text=node.text))
            return
        if isinstance(node, Parameter):
            return
        if isinstance(node, Command):
            self._emit_command(node, next_node, out, ctx=ctx)
            return
        if isinstance(node, Env):
            if node.name in INLINE_LIST_ENVS:
                out.extend(self._inline_list(node, ctx=ctx))
                return

            if node.name == "thebibliography":
                return
            out.extend(self.transform(node.body, ctx=ctx))
            return

    def _inline_list(
        self,
        env: Env,
        *,
        ctx: TransformContextProtocol | None,
    ) -> list[InlineNode]:
        ordered = env.name == "enumerate"
        items: list[list[Node]] = []
        current: list[Node] = []

        def has_visible(nodes: list[Node]) -> bool:
            return any(not isinstance(n, Text) or n.value.strip() for n in nodes)

        def flush() -> None:
            nonlocal current
            if has_visible(current):
                items.append(current)
            current = []

        for child in env.body:
            if isinstance(child, Command) and child.name == "item":
                flush()
                if env.name == "description" and child.opt_args:
                    current.extend(child.opt_args[0].children)
                    current.append(Text(pos=child.pos, value=": "))
                continue
            current.append(child)
        flush()
        out: list[InlineNode] = []
        for idx, item in enumerate(items, start=1):
            if out:
                out.append(TextSpan(text="; "))
            marker = f"{idx}. " if ordered else "• "
            out.append(TextSpan(text=marker))
            out.extend(self.transform(item, ctx=ctx))
        return out

    def _math(self, node: Math) -> InlineNode:
        body = _math_body_text(node)
        if node.display:
            return RawLatexSpan(tex=f"$${body}$$")
        rendered = _math_to_text(body)
        return MathSpan(tex=body, rendered_text=rendered)

    def _emit_command(
        self,
        cmd: Command,
        next_node: Node | None,
        out: list[InlineNode],
        *,
        ctx: TransformContextProtocol | None,
    ) -> None:
        handler = _BUILTIN_HANDLER_MAP.get(cmd.name)
        if handler is not None:
            out.extend(handler.emit(cmd, next_node, self, ctx))
            return

        out.extend(_UNKNOWN_HANDLER.emit(cmd, next_node, self, ctx))

    def _arg(
        self,
        cmd: Command,
        idx: int,
        *,
        ctx: TransformContextProtocol | None,
    ) -> list[InlineNode]:
        if idx < len(cmd.args):
            return self.transform(list(cmd.args[idx].children), ctx=ctx)
        return []

    def _count_unknown(self, name: str) -> None:
        if name in IGNORED_INLINE_COMMANDS or name in KNOWN_INLINE_COMMANDS:
            return
        if not name or name.startswith("@"):
            return
        if name in KNOWN_MATH_COMMANDS:
            return
        key = f"\\{name}"
        self.diag.unknown_command_counts[key] = (
            self.diag.unknown_command_counts.get(key, 0) + 1
        )


def transform_inline(
    ctx: TransformContextProtocol, nodes: list[Node]
) -> list[InlineNode]:
    engine = ctx.inline
    if engine is None:
        engine = InlineEngine()
        ctx.inline = engine
    return engine.transform(nodes, ctx=ctx)


def _coalesce_text(nodes: list[InlineNode]) -> list[InlineNode]:
    out: list[InlineNode] = []
    for node in nodes:
        if isinstance(node, TextSpan) and out and isinstance(out[-1], TextSpan):
            out[-1] = TextSpan(text=out[-1].text + node.text)
        else:
            out.append(node)
    return out


def _inline_to_plain(nodes: Iterable[InlineNode]) -> str:
    parts: list[str] = []
    for node in nodes:
        if isinstance(node, TextSpan):
            parts.append(node.text)
        elif isinstance(node, CodeSpan):
            parts.append(node.text)
        elif isinstance(node, MathSpan):
            parts.append(node.rendered_text or node.tex)
        elif isinstance(node, RawLatexSpan):
            parts.append(node.tex)
        elif isinstance(node, ReferenceSpan):
            parts.append(node.key)
        elif isinstance(node, CitationSpan):
            parts.append(",".join(node.keys))
        elif isinstance(node, LinkSpan):
            inner = _inline_to_plain(node.children)
            parts.append(inner or node.url)
        elif hasattr(node, "children"):
            parts.append(_inline_to_plain(getattr(node, "children")))
    return "".join(parts)
