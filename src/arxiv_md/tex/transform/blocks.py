from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterator, Protocol, runtime_checkable

from arxiv_md.tex.ast import (
    Command,
    Env,
    Group,
    Math,
    Node,
    ParagraphBreak,
    Text,
    Verbatim,
)
from arxiv_md.tex.handler_types import TransformContextProtocol
from arxiv_md.tex.model import (
    Block,
    CodeBlock,
    Figure,
    Heading,
    InlineNode,
    MathBlock,
    Paragraph,
    TextSpan,
)
from arxiv_md.tex.transform.handlers.env_dispatch import (
    CONTAINER_ENVS as CONTAINER_ENVS,
    FIGURE_ENVS as FIGURE_ENVS,
    LIST_ENVS as LIST_ENVS,
    MATH_ENVS as MATH_ENVS,
    QUOTE_ENVS as QUOTE_ENVS,
    SKIP_BODY_ENVS,
    TABLE_WRAPPER_ENVS as TABLE_WRAPPER_ENVS,
    TABULAR_ENVS as TABULAR_ENVS,
    dispatch_env,
)


HEADING_LEVELS: dict[str, int] = {
    "section": 2,
    "subsection": 3,
    "subsubsection": 4,
    "paragraph": 5,
    "subparagraph": 6,
}

SKIP_BODY_COMMANDS: frozenset[str] = frozenset(
    {
        "title",
        "subtitle",
        "shorttitle",
        "icmltitlerunning",
        "author",
        "authors",
        "shortauthor",
        "shortauthors",
        "date",
        "thanks",
        "maketitle",
        "documentclass",
        "usepackage",
        "RequirePackage",
        "PassOptionsToPackage",
        "newcommand",
        "renewcommand",
        "providecommand",
        "DeclareRobustCommand",
        "newenvironment",
        "renewenvironment",
        "let",
        "def",
        "newif",
        "newcounter",
        "newlength",
        "setcounter",
        "setlength",
        "addtocounter",
        "addtolength",
        "newcolumntype",
        "captionsetup",
        "icmlsetsymbol",
        "icmlkeywords",
        "icmlauthor",
        "icmlaffiliation",
        "icmlcorrespondingauthor",
        "icmlEqualContribution",
        "printAffiliationsAndNotice",
        "abstract",
        "graphicspath",
        "affiliation",
        "institution",
        "email",
        "country",
        "city",
        "state",
        "postcode",
        "streetaddress",
        "orcid",
        "inst",
        "institute",
        "IEEEmembership",
        "ccsdesc",
        "keywords",
    }
)


SKIP_LOOSE_COMMANDS: frozenset[str] = frozenset({"label", "phantomsection"})


_SECTION_ENVS: dict[str, str] = {
    "acks": "Acknowledgments",
    "acknowledgments": "Acknowledgments",
    "acknowledgements": "Acknowledgments",
}


_LABEL_RE = re.compile(r"\\label\*?\{([^{}]+)\}")
_LABEL_RE_ALL = re.compile(r"\\label\*?\{([^{}]+)\}")


_ABSORBABLE_HEADING_FILLER = frozenset(
    {
        "index",
        "phantomsection",
        "noindent",
        "makeatletter",
        "makeatother",
        "ignorespaces",
        "ignorespacesafterend",
        "protect",
    }
)


@dataclass(slots=True)
class NodeStream:
    nodes: list[Node]
    index: int = 0

    def current(self) -> Node | None:
        if self.index < len(self.nodes):
            return self.nodes[self.index]
        return None

    def peek(self, offset: int = 0) -> Node | None:
        j = self.index + offset
        if 0 <= j < len(self.nodes):
            return self.nodes[j]
        return None

    def advance(self, count: int = 1) -> None:
        self.index += count

    def skip_absorbable_filler(self) -> int:
        start = self.index
        while self.index < len(self.nodes) and is_absorbable_filler(
            self.nodes[self.index]
        ):
            self.index += 1
        return self.index - start

    @property
    def exhausted(self) -> bool:
        return self.index >= len(self.nodes)


@dataclass(slots=True)
class ParagraphBuffer:
    nodes: list[Node] = field(default_factory=list)

    def append(self, node: Node) -> None:
        self.nodes.append(node)

    def flush(self, ctx: TransformContextProtocol) -> list[Block]:
        if not self.nodes:
            return []
        ir = ctx.inline_ir(self.nodes)
        self.nodes.clear()
        if not ir:
            return []

        if all(isinstance(n, TextSpan) and not n.text.strip() for n in ir):
            return []

        if isinstance(ir[0], TextSpan):
            lstripped = ir[0].text.lstrip()
            if lstripped:
                ir[0] = TextSpan(text=lstripped)
            else:
                ir.pop(0)
        if ir and isinstance(ir[-1], TextSpan):
            rstripped = ir[-1].text.rstrip()
            if rstripped:
                ir[-1] = TextSpan(text=rstripped)
            else:
                ir.pop()
        if not ir:
            return []
        return [Paragraph(children=ir)]


@runtime_checkable
class BlockRule(Protocol):
    name: str

    def matches(
        self, node: Node, stream: NodeStream, ctx: TransformContextProtocol
    ) -> bool: ...

    def emit(
        self,
        node: Node,
        stream: NodeStream,
        ctx: TransformContextProtocol,
        paragraph: ParagraphBuffer,
    ) -> list[Block]: ...


class ParagraphBreakRule:
    name = "paragraph_break"

    def matches(
        self, node: Node, stream: NodeStream, ctx: TransformContextProtocol
    ) -> bool:
        return isinstance(node, ParagraphBreak)

    def emit(
        self,
        node: Node,
        stream: NodeStream,
        ctx: TransformContextProtocol,
        paragraph: ParagraphBuffer,
    ) -> list[Block]:
        blocks = paragraph.flush(ctx)
        stream.advance()
        return blocks


class DisplayMathRule:
    name = "display_math"

    def matches(
        self, node: Node, stream: NodeStream, ctx: TransformContextProtocol
    ) -> bool:
        return isinstance(node, Math) and node.display

    def emit(
        self,
        node: Node,
        stream: NodeStream,
        ctx: TransformContextProtocol,
        paragraph: ParagraphBuffer,
    ) -> list[Block]:
        blocks = paragraph.flush(ctx)
        body = math_body_text(node).strip()  # type: ignore[arg-type]
        if body:
            blocks.append(MathBlock(text=body, raw_latex=body))
        stream.advance()
        return blocks


class VerbatimBlockRule:
    name = "verbatim_block"

    def matches(
        self, node: Node, stream: NodeStream, ctx: TransformContextProtocol
    ) -> bool:
        return isinstance(node, Verbatim) and not node.inline

    def emit(
        self,
        node: Node,
        stream: NodeStream,
        ctx: TransformContextProtocol,
        paragraph: ParagraphBuffer,
    ) -> list[Block]:
        assert isinstance(node, Verbatim)
        blocks = paragraph.flush(ctx)
        blocks.append(CodeBlock(text=node.text, language=node.language or ""))
        stream.advance()
        return blocks


class ScaleBoxUnwrapRule:
    name = "scalebox_unwrap"

    def matches(
        self, node: Node, stream: NodeStream, ctx: TransformContextProtocol
    ) -> bool:
        if not isinstance(node, Command):
            return False
        if node.name == "resizebox" and len(node.args) >= 3:
            return True
        if node.name == "scalebox" and len(node.args) >= 2:
            return True
        return False

    def emit(
        self,
        node: Node,
        stream: NodeStream,
        ctx: TransformContextProtocol,
        paragraph: ParagraphBuffer,
    ) -> list[Block]:
        assert isinstance(node, Command)
        blocks = paragraph.flush(ctx)
        if node.name == "resizebox":
            blocks.extend(walk_blocks(ctx, node.args[2].children))
        else:
            blocks.extend(walk_blocks(ctx, node.args[1].children))
        stream.advance()
        return blocks


class HeadingRule:
    name = "heading"

    def matches(
        self, node: Node, stream: NodeStream, ctx: TransformContextProtocol
    ) -> bool:
        return isinstance(node, Command) and node.name in HEADING_LEVELS

    def emit(
        self,
        node: Node,
        stream: NodeStream,
        ctx: TransformContextProtocol,
        paragraph: ParagraphBuffer,
    ) -> list[Block]:
        assert isinstance(node, Command)
        blocks = paragraph.flush(ctx)
        heading = make_heading(ctx, node)

        saved = stream.index
        stream.advance()
        stream.skip_absorbable_filler()
        label_node = stream.current()
        if isinstance(label_node, Command) and label_node.name == "label":
            if label_node.args and not heading.label:
                heading.label = (
                    ctx.inline_markdown(label_node.args[0].children).strip() or None
                )
            stream.advance()
        else:
            stream.index = saved + 1
        blocks.append(heading)
        return blocks


class SkipBodyCommandRule:
    name = "skip_body_command"

    def matches(
        self, node: Node, stream: NodeStream, ctx: TransformContextProtocol
    ) -> bool:
        if not isinstance(node, Command):
            return False
        if node.name in SKIP_BODY_COMMANDS or node.name.endswith("title"):
            return True
        if node.name in SKIP_LOOSE_COMMANDS:
            return True
        return False

    def emit(
        self,
        node: Node,
        stream: NodeStream,
        ctx: TransformContextProtocol,
        paragraph: ParagraphBuffer,
    ) -> list[Block]:
        stream.advance()
        return []


class StandaloneFigureRule:
    name = "standalone_figure"

    def matches(
        self, node: Node, stream: NodeStream, ctx: TransformContextProtocol
    ) -> bool:
        return (
            isinstance(node, Command)
            and node.name == "includegraphics"
            and bool(node.args)
        )

    def emit(
        self,
        node: Node,
        stream: NodeStream,
        ctx: TransformContextProtocol,
        paragraph: ParagraphBuffer,
    ) -> list[Block]:
        assert isinstance(node, Command)
        blocks = paragraph.flush(ctx)
        gfx_path = ctx.inline_markdown(node.args[0].children).strip()

        label: str | None = None
        saved = stream.index
        stream.advance()
        stream.skip_absorbable_filler()
        label_node = stream.current()
        if (
            isinstance(label_node, Command)
            and label_node.name == "label"
            and label_node.args
        ):
            label = ctx.inline_markdown(label_node.args[0].children).strip() or None
            stream.advance()
        else:
            stream.index = saved + 1
        blocks.append(
            Figure(
                caption=[],
                graphics=[gfx_path] if gfx_path else [],
                images=[],
                label=label,
            )
        )
        return blocks


class CaptionRule:
    name = "caption"

    def matches(
        self, node: Node, stream: NodeStream, ctx: TransformContextProtocol
    ) -> bool:
        return isinstance(node, Command) and node.name == "caption" and bool(node.args)

    def emit(
        self,
        node: Node,
        stream: NodeStream,
        ctx: TransformContextProtocol,
        paragraph: ParagraphBuffer,
    ) -> list[Block]:
        assert isinstance(node, Command)
        blocks = paragraph.flush(ctx)
        cap_ir = ctx.inline_ir(node.args[0].children)
        if cap_ir:
            blocks.append(Paragraph(children=cap_ir))
        stream.advance()
        return blocks


class SkipBodyEnvRule:
    name = "skip_body_env"

    def matches(
        self, node: Node, stream: NodeStream, ctx: TransformContextProtocol
    ) -> bool:
        if not isinstance(node, Env):
            return False
        if node.name in SKIP_BODY_ENVS:
            return True
        if node.name.endswith("authorlist"):
            return True
        return False

    def emit(
        self,
        node: Node,
        stream: NodeStream,
        ctx: TransformContextProtocol,
        paragraph: ParagraphBuffer,
    ) -> list[Block]:
        stream.advance()
        return []


class SectionEnvRule:
    name = "section_env"

    def matches(
        self, node: Node, stream: NodeStream, ctx: TransformContextProtocol
    ) -> bool:
        return isinstance(node, Env) and node.name in _SECTION_ENVS

    def emit(
        self,
        node: Node,
        stream: NodeStream,
        ctx: TransformContextProtocol,
        paragraph: ParagraphBuffer,
    ) -> list[Block]:
        assert isinstance(node, Env)
        blocks = paragraph.flush(ctx)
        section_title = _SECTION_ENVS[node.name]
        body_blocks = walk_blocks(ctx, node.body)
        if body_blocks:
            blocks.append(
                Heading(
                    level=2,
                    children=[TextSpan(text=section_title)],
                    label=None,
                )
            )
            blocks.extend(body_blocks)
        stream.advance()
        return blocks


class EnvironmentRule:
    name = "environment"

    def matches(
        self, node: Node, stream: NodeStream, ctx: TransformContextProtocol
    ) -> bool:
        return isinstance(node, Env)

    def emit(
        self,
        node: Node,
        stream: NodeStream,
        ctx: TransformContextProtocol,
        paragraph: ParagraphBuffer,
    ) -> list[Block]:
        assert isinstance(node, Env)
        blocks = paragraph.flush(ctx)
        blocks.extend(dispatch_env(ctx, node))
        stream.advance()
        return blocks


DEFAULT_BLOCK_RULES: tuple[BlockRule, ...] = (
    ParagraphBreakRule(),
    DisplayMathRule(),
    VerbatimBlockRule(),
    ScaleBoxUnwrapRule(),
    HeadingRule(),
    SkipBodyCommandRule(),
    StandaloneFigureRule(),
    CaptionRule(),
    SkipBodyEnvRule(),
    SectionEnvRule(),
    EnvironmentRule(),
)


def walk_blocks(ctx: TransformContextProtocol, nodes: list[Node]) -> list[Block]:

    stream = NodeStream(nodes)
    paragraph = ParagraphBuffer()
    out: list[Block] = []
    rules = DEFAULT_BLOCK_RULES

    while not stream.exhausted:
        node = stream.current()
        assert node is not None
        idx_before = stream.index
        matched = False
        for rule in rules:
            if rule.matches(node, stream, ctx):
                out.extend(rule.emit(node, stream, ctx, paragraph))
                assert stream.index > idx_before, (
                    f"BlockRule {rule.name!r} matched but did not advance stream"
                )
                matched = True
                break
        if not matched:
            paragraph.append(node)
            stream.advance()

    out.extend(paragraph.flush(ctx))
    return out


def walk_block(ctx: TransformContextProtocol, node: Node) -> list[Block]:
    return walk_blocks(ctx, [node])


def make_heading(ctx: TransformContextProtocol, cmd: Command) -> Heading:
    level = HEADING_LEVELS[cmd.name]
    children: list[InlineNode] = ctx.inline_ir(cmd.args[0].children) if cmd.args else []
    block = Heading(level=level, children=children)

    if cmd.args:
        for sub in walk_all(cmd.args[0].children):
            if isinstance(sub, Command) and sub.name == "label" and sub.args:
                label = ctx.inline_markdown(sub.args[0].children).strip()
                if label:
                    block.label = label
                break
    return block


def walk_all(nodes: list[Node]) -> Iterator[Node]:
    for n in nodes:
        yield from walk_one(n)


def walk_one(n: Node) -> Iterator[Node]:
    yield n
    for child in children_of(n):
        yield from walk_one(child)


def walk_inside(env: Env) -> Iterator[Node]:
    for n in env.body:
        yield from walk_one(n)
    for g in (*env.args, *env.opt_args):
        for c in g.children:
            yield from walk_one(c)


def math_body_text(node: Math) -> str:
    if not node.body:
        return ""
    head = node.body[0]
    if isinstance(head, Text):
        return head.value
    return ""


def is_blank_text(n: Node) -> bool:
    return isinstance(n, Text) and (not n.value or n.value.isspace())


def is_absorbable_filler(n: Node) -> bool:
    if is_blank_text(n):
        return True
    if isinstance(n, ParagraphBreak):
        return True
    if isinstance(n, Command) and n.name in _ABSORBABLE_HEADING_FILLER:
        return True
    return False


def children_of(n: Node) -> list[Node]:
    if isinstance(n, Env):
        out: list[Node] = list(n.body)
        for g in (*n.args, *n.opt_args):
            out.extend(g.children)
        return out
    if isinstance(n, Command):
        out = []
        for g in (*n.args, *n.opt_args):
            out.extend(g.children)
        return out
    if isinstance(n, Group):
        return list(n.children)
    if isinstance(n, Math):
        return list(n.body)
    return []
