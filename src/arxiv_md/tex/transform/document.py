from __future__ import annotations

from pathlib import Path

from arxiv_md.tex._common import ResourceLimits, TexDocument
from arxiv_md.tex.ast import Node
from arxiv_md.tex.handler_types import TransformContextProtocol
from arxiv_md.tex.transform.frontmatter import (
    extract_abstract,
    extract_authors,
    extract_title,
    find_document_body,
)
from arxiv_md.tex.transform.blocks import walk_blocks
from arxiv_md.tex.transform.refs import resolve_references


__all__ = ["build_document"]


def build_document(
    ctx: TransformContextProtocol,
    nodes: list[Node],
    *,
    root_dir: Path,
    main_tex: Path,
    limits: ResourceLimits | None = None,
) -> TexDocument:

    from arxiv_md.tex.bibliography import parse_bibliography

    doc = TexDocument(root_dir=root_dir, main_tex=main_tex)
    body = find_document_body(nodes)
    doc.title = extract_title(ctx, nodes)
    doc.authors = extract_authors(ctx, nodes)
    doc.abstract = extract_abstract(ctx, nodes, body)
    doc.blocks = walk_blocks(ctx, body)
    doc.bibliography = parse_bibliography(
        root_dir,
        ctx.source_text,
        ctx.diag.warnings,
        limits=limits if limits is not None else ctx.limits,
    )

    doc.warnings = list(ctx.diag.warnings)
    doc.unknown_command_counts = dict(ctx.diag.unknown_command_counts)
    resolve_references(doc)
    return doc
