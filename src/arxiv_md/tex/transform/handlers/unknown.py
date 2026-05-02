from __future__ import annotations

from arxiv_md.tex._common import warning
from arxiv_md.tex.ast import Env
from arxiv_md.tex.handler_types import TransformContextProtocol
from arxiv_md.tex.model import Block, RawLatex


def unknown_env(env: Env, ctx: TransformContextProtocol) -> list[Block]:
    raw = ctx.env_full_raw(env).strip()
    if not raw:
        return []
    msg = f"Unknown environment preserved: {env.name}"
    ctx.diag.warnings.append(warning("unknown_env", msg))
    ctx.diag.unknown_env_counts[env.name] = (
        ctx.diag.unknown_env_counts.get(env.name, 0) + 1
    )
    return [RawLatex(text=raw, env=env.name)]
