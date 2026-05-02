from __future__ import annotations

from arxiv_md.tex.ast import Command, Env, Group, Node, Text
from arxiv_md.tex.handler_types import TransformContextProtocol
from arxiv_md.tex.model import Block, ListBlock


def list_env(env: Env, ctx: TransformContextProtocol) -> Block:
    ordered = env.name == "enumerate"
    is_description = env.name == "description"
    items: list[list[Block]] = []
    current: list[Node] = []

    def flush_item() -> None:
        if not current:
            return
        blocks: list[Block] = ctx.block_ir(current)
        current.clear()
        if blocks:
            items.append(blocks)

    for n in env.body:
        if isinstance(n, Command) and n.name == "item":
            flush_item()
            if is_description and n.opt_args:
                term_children = list(n.opt_args[0].children)
                if term_children:
                    current.append(
                        Command(
                            pos=n.pos,
                            name="textbf",
                            args=[Group(pos=n.pos, children=term_children)],
                        )
                    )
                    current.append(Text(pos=n.pos, value=" "))
            continue
        current.append(n)
    flush_item()
    return ListBlock(ordered=ordered, items=items)
