from __future__ import annotations

from arxiv_md.tex._common import warning
from arxiv_md.tex.ast import Command, Env, Group
from arxiv_md.tex.handler_types import TransformContextProtocol
from arxiv_md.tex.model import Block, Figure


TIKZ_FALLBACK_ENVS = frozenset(
    {
        "tikzpicture",
        "pgfpicture",
        "pgfplots",
        "axis",
        "semilogxaxis",
        "semilogyaxis",
        "loglogaxis",
    }
)


def figure_env(env: Env, ctx: TransformContextProtocol) -> list[Block]:
    caption_node, label, graphics, has_tikz = _scan_figure_descendants(env, ctx)

    if not graphics and has_tikz:
        _warn_tikz_fallback(ctx)
        caption_ir = ctx.inline_ir(caption_node.children) if caption_node else []
        return [
            Figure(
                caption=caption_ir,
                graphics=[],
                images=[],
                label=label or None,
                raw_latex=ctx.env_full_raw(env).strip(),
            )
        ]

    caption_ir = ctx.inline_ir(caption_node.children) if caption_node else []
    return [
        Figure(
            caption=caption_ir,
            graphics=list(graphics),
            images=[],
            label=label or None,
            raw_latex=None,
        )
    ]


def _scan_figure_descendants(
    env: Env,
    ctx: TransformContextProtocol,
) -> tuple[Group | None, str, list[str], bool]:
    from arxiv_md.tex.transform.blocks import walk_inside

    caption_node: Group | None = None
    label = ""
    graphics: list[str] = []
    has_tikz = False
    for n in walk_inside(env):
        if isinstance(n, Command):
            if n.name == "caption" and n.args and caption_node is None:
                caption_node = n.args[0]
            elif n.name == "label" and n.args and not label:
                label = ctx.inline_markdown(n.args[0].children).strip()
            elif n.name == "includegraphics" and n.args:
                graphics.append(ctx.inline_markdown(n.args[0].children).strip())
        elif isinstance(n, Env) and n.name in TIKZ_FALLBACK_ENVS:
            has_tikz = True
    return caption_node, label, graphics, has_tikz


def tikz_env(env: Env, ctx: TransformContextProtocol) -> list[Block]:
    from arxiv_md.tex.transform.blocks import walk_inside

    _warn_tikz_fallback(ctx)
    label = ""
    for n in walk_inside(env):
        if isinstance(n, Command) and n.name == "label" and n.args and not label:
            label = ctx.inline_markdown(n.args[0].children).strip()
            break
    return [
        Figure(
            caption=[],
            graphics=[],
            images=[],
            label=label or None,
            raw_latex=ctx.env_full_raw(env).strip(),
        )
    ]


def _warn_tikz_fallback(ctx: TransformContextProtocol) -> None:
    ctx.diag.warnings.append(
        warning("unsupported_asset", "TikZ/PGF figure rendered as placeholder")
    )
