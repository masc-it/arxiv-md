from __future__ import annotations

from arxiv_md.tex.ast import Env
from arxiv_md.tex.handler_types import EnvHandler, TransformContextProtocol
from arxiv_md.tex.model import Block, CodeBlock, QuoteBlock


MATH_ENVS: frozenset[str] = frozenset(
    {
        "equation",
        "equation*",
        "align",
        "align*",
        "alignat",
        "alignat*",
        "gather",
        "gather*",
        "multline",
        "multline*",
        "split",
        "displaymath",
        "eqnarray",
        "eqnarray*",
        # amsmath matrix / cases environments (may appear at top level)
        "matrix",
        "matrix*",
        "pmatrix",
        "pmatrix*",
        "bmatrix",
        "bmatrix*",
        "Bmatrix",
        "Bmatrix*",
        "vmatrix",
        "vmatrix*",
        "Vmatrix",
        "Vmatrix*",
        "smallmatrix",
        "cases",
        "cases*",
        "dcases",
        "dcases*",
    }
)

LIST_ENVS: frozenset[str] = frozenset({"itemize", "enumerate", "description"})

CONTAINER_ENVS: frozenset[str] = frozenset(
    {
        "center",
        "flushleft",
        "flushright",
        "minipage",
        "subfigure",
        "subfigure*",
        "subtable",
        "subtable*",
        "adjustbox",
        "small",
        "footnotesize",
        "scriptsize",
        "tiny",
        "tcolorbox",
        "mdframed",
        "adjustwidth",
        "quoting",
        "CJK",
        "CJK*",
    }
)

FIGURE_ENVS: frozenset[str] = frozenset(
    {"figure", "figure*", "wrapfigure", "wrapfigure*", "SCfigure", "subfloat"}
)

TABLE_WRAPPER_ENVS: frozenset[str] = frozenset(
    {"table", "table*", "wraptable", "wraptable*"}
)

TABULAR_ENVS: frozenset[str] = frozenset(
    {"tabular", "tabular*", "tabularx", "array", "longtable", "tabu"}
)

QUOTE_ENVS: frozenset[str] = frozenset({"quote", "quotation", "displayquote"})

SKIP_BODY_ENVS: frozenset[str] = frozenset(
    {
        "abstract",
        "thebibliography",
        "document",
        "CCSXML",
        "IEEEkeywords",
        "keywords",
    }
)


def _list_handler(env: Env, ctx: TransformContextProtocol) -> list[Block]:
    from arxiv_md.tex.transform.handlers.lists import list_env

    return [list_env(env, ctx)]


def _container_handler(env: Env, ctx: TransformContextProtocol) -> list[Block]:
    from arxiv_md.tex.transform.blocks import walk_blocks

    return walk_blocks(ctx, env.body)


def _quote_handler(env: Env, ctx: TransformContextProtocol) -> list[Block]:
    from arxiv_md.tex.transform.blocks import walk_blocks

    return [QuoteBlock(blocks=walk_blocks(ctx, env.body))]


def _tcolorbox_handler(env: Env, ctx: TransformContextProtocol) -> list[Block]:
    from arxiv_md.tex.parser import parse_text
    from arxiv_md.tex.transform.blocks import walk_blocks

    title_raw = _tcolorbox_title_raw(env)
    title = ctx.inline_markdown(parse_text(title_raw)).strip() if title_raw else ""
    return [QuoteBlock(blocks=walk_blocks(ctx, env.body), title=title)]


def _tcblisting_handler(env: Env, ctx: TransformContextProtocol) -> list[Block]:
    raw = _strip_leading_env_options(ctx.env_inner_raw(env)).strip()
    return [CodeBlock(text=raw)]


def _skip_handler(env: Env, ctx: TransformContextProtocol) -> list[Block]:
    return []


def _build_env_handlers() -> dict[str, EnvHandler]:
    from arxiv_md.tex.transform.handlers.algorithms import (
        ALGORITHM_ENVS,
        ALGORITHMIC_ENVS,
        algorithm_env,
        algorithmic_env,
    )
    from arxiv_md.tex.transform.handlers.figures import (
        TIKZ_FALLBACK_ENVS,
        figure_env,
        tikz_env,
    )
    from arxiv_md.tex.transform.handlers.math_envs import math_env
    from arxiv_md.tex.transform.handlers.tables import (
        longtable_env,
        table_wrapper_env,
        tabular_standalone,
    )
    from arxiv_md.tex.transform.handlers.theorems import (
        ALL_BUILTIN_THEOREM_ENVS,
        make_theorem_handler,
    )

    handlers: dict[str, EnvHandler] = {}
    for name in MATH_ENVS:
        handlers[name] = math_env
    for name in LIST_ENVS:
        handlers[name] = _list_handler
    for name in FIGURE_ENVS:
        handlers[name] = figure_env
    for name in TIKZ_FALLBACK_ENVS:
        handlers[name] = tikz_env
    for name in TABLE_WRAPPER_ENVS:
        handlers[name] = table_wrapper_env
    handlers["longtable"] = longtable_env
    for name in TABULAR_ENVS - {"longtable"}:
        handlers[name] = tabular_standalone
    for name in CONTAINER_ENVS:
        handlers[name] = _container_handler
    for name in QUOTE_ENVS:
        handlers[name] = _quote_handler
    for name in SKIP_BODY_ENVS:
        handlers[name] = _skip_handler

    handlers["tcolorbox"] = _tcolorbox_handler
    handlers["tcblisting"] = _tcblisting_handler

    for name in ALGORITHM_ENVS:
        handlers[name] = algorithm_env
    for name in ALGORITHMIC_ENVS:
        handlers[name] = algorithmic_env

    for name, title in ALL_BUILTIN_THEOREM_ENVS.items():
        handlers[name] = make_theorem_handler(title)

    return handlers


ENV_HANDLERS: dict[str, EnvHandler] = _build_env_handlers()


def dispatch_env(ctx: TransformContextProtocol, env: Env) -> list[Block]:
    handler = ENV_HANDLERS.get(env.name)
    if handler is not None:
        return handler(env, ctx)

    theorem_title = ctx.theorem_env_titles.get(env.name)
    if theorem_title is not None:
        from arxiv_md.tex.transform.handlers.theorems import make_theorem_handler

        return make_theorem_handler(theorem_title)(env, ctx)

    from arxiv_md.tex.transform.handlers.unknown import unknown_env

    return unknown_env(env, ctx)


def _tcolorbox_title_raw(env: Env) -> str:
    opt = _first_optional_arg_raw(env)
    if not opt:
        return ""
    for part in _split_top_level_commas(opt):
        key, sep, value = part.partition("=")
        if sep and key.strip() == "title":
            return _strip_outer_braces(value.strip())
    return ""


def _first_optional_arg_raw(env: Env) -> str:
    raw = env.raw
    begin_marker = f"\\begin{{{env.name}}}"
    if not raw.startswith(begin_marker):
        return ""
    i = len(begin_marker)
    while i < len(raw) and raw[i].isspace():
        i += 1
    if i >= len(raw) or raw[i] != "[":
        return ""
    return _read_balanced(raw, i, "[", "]")[0]


def _strip_leading_env_options(raw: str) -> str:
    text = raw.lstrip()
    for opener, closer in (("[", "]"), ("{", "}")):
        if not text.startswith(opener):
            continue
        _body, end = _read_balanced(text, 0, opener, closer)
        if end <= 0:
            break
        text = text[end:].lstrip()
    return text


def _split_top_level_commas(text: str) -> list[str]:
    parts: list[str] = []
    start = 0
    brace_depth = bracket_depth = paren_depth = 0
    for i, ch in enumerate(text):
        if ch == "{" and bracket_depth == 0:
            brace_depth += 1
        elif ch == "}" and bracket_depth == 0:
            brace_depth = max(0, brace_depth - 1)
        elif ch == "[" and brace_depth == 0:
            bracket_depth += 1
        elif ch == "]" and brace_depth == 0:
            bracket_depth = max(0, bracket_depth - 1)
        elif ch == "(" and brace_depth == 0 and bracket_depth == 0:
            paren_depth += 1
        elif ch == ")" and brace_depth == 0 and bracket_depth == 0:
            paren_depth = max(0, paren_depth - 1)
        elif ch == "," and brace_depth == bracket_depth == paren_depth == 0:
            parts.append(text[start:i].strip())
            start = i + 1
    parts.append(text[start:].strip())
    return parts


def _read_balanced(text: str, start: int, opener: str, closer: str) -> tuple[str, int]:
    if start >= len(text) or text[start] != opener:
        return "", start
    depth = 0
    body_start = start + 1
    for i in range(start, len(text)):
        ch = text[i]
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return text[body_start:i], i + 1
    return "", start


def _strip_outer_braces(text: str) -> str:
    body, end = _read_balanced(text, 0, "{", "}")
    if end == len(text):
        return body.strip()
    return text
