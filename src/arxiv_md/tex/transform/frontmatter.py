from __future__ import annotations

import re

from arxiv_md.tex.ast import Command, Env, Node
from arxiv_md.tex.handler_types import TransformContextProtocol
from arxiv_md.tex.model import Block


def find_document_body(nodes: list[Node]) -> list[Node]:
    for n in nodes:
        if isinstance(n, Env) and n.name == "document":
            return n.body
    return nodes


def extract_title(ctx: TransformContextProtocol, all_nodes: list[Node]) -> str:
    from arxiv_md.tex.transform.blocks import walk_all

    for n in walk_all(all_nodes):
        if isinstance(n, Command) and n.name == "title" and n.args:
            return ctx.inline_markdown(n.args[0].children)
    for n in walk_all(all_nodes):
        if isinstance(n, Command) and n.name.endswith("title") and n.args:
            return ctx.inline_markdown(n.args[0].children)
    return ""


def extract_authors(ctx: TransformContextProtocol, all_nodes: list[Node]) -> list[str]:
    from arxiv_md.tex.transform.blocks import walk_all, walk_inside

    for n in walk_all(all_nodes):
        if isinstance(n, Command) and n.name == "author" and n.args:
            raw = ctx.inline_markdown(n.args[0].children)
            authors = split_authors(raw)
            if authors:
                return authors

    for n in walk_all(all_nodes):
        if isinstance(n, Env) and n.name.endswith("authorlist"):
            names: list[str] = []
            for sub in walk_inside(n):
                if (
                    isinstance(sub, Command)
                    and sub.name.endswith("author")
                    and sub.args
                ):
                    names.append(ctx.inline_markdown(sub.args[0].children))
            if names:
                return [name for name in names if name.strip()]
    return []


def extract_abstract(
    ctx: TransformContextProtocol,
    all_nodes: list[Node],
    body: list[Node],
) -> list[Block]:
    from arxiv_md.tex.transform.blocks import walk_blocks

    from arxiv_md.tex.transform.blocks import walk_all

    for scope in (body, all_nodes):
        for n in walk_all(scope):
            if isinstance(n, Env) and n.name == "abstract":
                blocks = walk_blocks(ctx, n.body)
                return blocks if blocks else []
    for n in walk_all(all_nodes):
        if isinstance(n, Command) and n.name == "abstract" and n.args:
            blocks = walk_blocks(ctx, n.args[0].children)
            return blocks if blocks else []
    return []


_AUTHOR_AND_RE = re.compile(r"\\and\b")
_AUTHOR_SPLIT_RE = re.compile(r"\s+(?:and|AND)\s+|\s*,\s*")


def split_authors(text: str) -> list[str]:
    text = _AUTHOR_AND_RE.sub(" and ", text)
    parts = _AUTHOR_SPLIT_RE.split(text)
    return [part.strip() for part in parts if part.strip()]


__all__ = [
    "extract_abstract",
    "extract_authors",
    "extract_title",
    "find_document_body",
    "split_authors",
]
