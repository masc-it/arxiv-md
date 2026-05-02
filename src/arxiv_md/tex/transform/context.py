from __future__ import annotations

from dataclasses import dataclass, field

from arxiv_md.tex._common import ResourceLimits
from arxiv_md.tex.ast import Env, Node
from arxiv_md.tex.lexer import Diagnostics
from arxiv_md.tex.macro_engine import CompiledMacro
from arxiv_md.tex.model import Block, InlineNode
from arxiv_md.tex.transform.inline import InlineEngine, transform_inline
from arxiv_md.tex.transform.inline_render import InlineSerializer


__all__ = ["TransformContext"]


@dataclass(slots=True)
class TransformContext:
    diag: Diagnostics
    source_text: str
    macros: dict[str, CompiledMacro]
    limits: ResourceLimits = field(default_factory=ResourceLimits)
    inline: InlineEngine | None = None
    inline_serializer: InlineSerializer = field(default_factory=InlineSerializer)
    theorem_env_titles: dict[str, str] = field(default_factory=dict)
    theorem_counter: int = 0

    def __post_init__(self) -> None:
        if self.inline is None:
            self.inline = InlineEngine(self.diag)

    def block_ir(self, nodes: list[Node]) -> list[Block]:
        from arxiv_md.tex.transform.blocks import walk_blocks

        return walk_blocks(self, nodes)

    def inline_ir(self, nodes: list[Node]) -> list[InlineNode]:
        return transform_inline(self, nodes)

    def next_theorem_number(self) -> int:
        self.theorem_counter += 1
        return self.theorem_counter

    def inline_markdown(self, nodes: list[Node]) -> str:
        return self.inline_serializer.serialize(
            self.inline_ir(nodes), target="markdown"
        )

    def inline_html(self, nodes: list[Node]) -> str:
        return self.inline_serializer.serialize(self.inline_ir(nodes), target="html")

    def inline_plain(self, nodes: list[Node]) -> str:
        return self.inline_serializer.serialize(self.inline_ir(nodes), target="plain")

    def env_full_raw(self, env: Env) -> str:
        if env.raw:
            return env.raw
        if not self.source_text or env.end_pos <= env.pos:
            return ""
        return self.source_text[env.pos : env.end_pos]

    def env_inner_raw(self, env: Env) -> str:
        raw = self.env_full_raw(env)
        if not raw:
            return ""
        begin_marker = f"\\begin{{{env.name}}}"
        end_marker = f"\\end{{{env.name}}}"
        if raw.startswith(begin_marker):
            raw = raw[len(begin_marker) :]
        if raw.endswith(end_marker):
            raw = raw[: -len(end_marker)]
        return raw
