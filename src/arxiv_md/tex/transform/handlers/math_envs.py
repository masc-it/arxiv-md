from __future__ import annotations

import re

from arxiv_md.tex.ast import Env
from arxiv_md.tex.handler_types import TransformContextProtocol
from arxiv_md.tex.macro_engine import (
    brace_math_accent_arguments,
    expand_math_text,
    strip_math_comments,
    unwrap_math_layout_wrappers,
)
from arxiv_md.tex.model import Block, MathBlock


_LABEL_RE_ALL = re.compile(r"\\label\*?\{([^{}]+)\}")


def math_env(env: Env, ctx: TransformContextProtocol) -> list[Block]:
    raw = ctx.env_inner_raw(env).strip()
    labels = [m.strip() for m in _LABEL_RE_ALL.findall(raw) if m.strip()]
    raw = _LABEL_RE_ALL.sub("", raw).strip()
    if raw:
        raw = strip_math_comments(raw).strip()
    if ctx.macros and raw:
        raw = expand_math_text(raw, ctx.macros)
    if raw:
        raw = unwrap_math_layout_wrappers(raw)
        raw = brace_math_accent_arguments(raw)
    if not raw:
        return []
    primary_label: str | None = None
    sublabels: list[str] = []
    if labels:
        primary_label = labels[0]
        sublabels = list(labels[1:])
    return [
        MathBlock(
            text=raw,
            raw_latex=raw,
            env=env.name,
            label=primary_label,
            sublabels=sublabels,
        )
    ]
