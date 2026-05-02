from __future__ import annotations

from collections.abc import Callable, MutableMapping
from typing import Any, Protocol, TypeAlias

from arxiv_md.tex._common import TexWarning
from arxiv_md.tex.ast import Command, Env, Node
from arxiv_md.tex.model import Block, InlineNode


class DiagnosticsProtocol(Protocol):
    """Warning/counter subset exposed to custom handlers."""

    @property
    def warnings(self) -> list[TexWarning]: ...

    @property
    def unknown_env_counts(self) -> MutableMapping[str, int]: ...

    @property
    def unknown_command_counts(self) -> MutableMapping[str, int]: ...


class TransformContextProtocol(Protocol):
    """Stable handler context for lowering AST nodes into public IR.

    Helper methods preserve converter normalization rules; handlers should call
    them instead of rendering child nodes by hand.
    """

    @property
    def diag(self) -> DiagnosticsProtocol: ...

    source_text: str
    macros: Any
    limits: Any
    inline: Any
    theorem_env_titles: dict[str, str]

    def block_ir(self, nodes: list[Node]) -> list[Block]: ...
    def inline_ir(self, nodes: list[Node]) -> list[InlineNode]: ...
    def inline_markdown(self, nodes: list[Node]) -> str: ...
    def inline_html(self, nodes: list[Node]) -> str: ...
    def inline_plain(self, nodes: list[Node]) -> str: ...
    def env_full_raw(self, env: Env) -> str: ...
    def env_inner_raw(self, env: Env) -> str: ...
    def next_theorem_number(self) -> int: ...


CommandHandler: TypeAlias = Callable[
    [Command, TransformContextProtocol],
    list[InlineNode],
]
EnvHandler: TypeAlias = Callable[
    [Env, TransformContextProtocol],
    list[Block],
]
