from __future__ import annotations

from arxiv_md.tex.ast import Command, Env, Node
from arxiv_md.tex.handler_types import EnvHandler, TransformContextProtocol
from arxiv_md.tex.model import Block, Paragraph, QuoteBlock, TextSpan


BUILTIN_THEOREM_ENVS: dict[str, str] = {
    "proof": "Proof",
    "theorem": "Theorem",
    "lemma": "Lemma",
    "remark": "Remark",
    "definition": "Definition",
    "statement": "Statement",
    "proposition": "Proposition",
    "corollary": "Corollary",
    "conjecture": "Conjecture",
    "example": "Example",
    "observation": "Observation",
    "claim": "Claim",
    "fact": "Fact",
    "assumption": "Assumption",
    "notation": "Notation",
    "property": "Property",
    "question": "Question",
    "problem": "Problem",
    "exercise": "Exercise",
    "solution": "Solution",
    "case": "Case",
    "condition": "Condition",
    "criterion": "Criterion",
    "hypothesis": "Hypothesis",
    "axiom": "Axiom",
}


BUILTIN_THEOREM_STARRED: dict[str, str] = {
    f"{k}*": v for k, v in BUILTIN_THEOREM_ENVS.items()
}

ALL_BUILTIN_THEOREM_ENVS: dict[str, str] = {
    **BUILTIN_THEOREM_ENVS,
    **BUILTIN_THEOREM_STARRED,
}


def make_theorem_handler(display_title: str) -> EnvHandler:

    def _handler(env: Env, ctx: TransformContextProtocol) -> list[Block]:
        return _theorem_env(env, ctx, display_title)

    return _handler


def _theorem_env(
    env: Env,
    ctx: TransformContextProtocol,
    display_title: str,
) -> list[Block]:
    from arxiv_md.tex.transform.blocks import walk_blocks

    label = _extract_label(env, ctx)

    is_proof = env.name.rstrip("*") == "proof" or display_title.lower() == "proof"
    is_numbered = not is_proof and not env.name.endswith("*")
    title = display_title
    if is_numbered:
        title = f"{title} {ctx.next_theorem_number()}"
    annotation, body_nodes = _extract_annotation(env, ctx)
    if annotation:
        title = f"{title} ({annotation})"
    title = f"{title}."

    blocks = walk_blocks(ctx, body_nodes)
    if is_proof:
        _append_qed(blocks)

    return [QuoteBlock(blocks=blocks, title=title, label=label)]


def _append_qed(blocks: list[Block]) -> None:
    if blocks and isinstance(blocks[-1], Paragraph):
        blocks[-1].children.append(TextSpan(text=" ∎"))
        return
    blocks.append(Paragraph(children=[TextSpan(text="∎")]))


def _extract_label(env: Env, ctx: TransformContextProtocol) -> str | None:
    for node in env.body:
        if isinstance(node, Command) and node.name == "label" and node.args:
            return ctx.inline_markdown(node.args[0].children).strip() or None
    return None


def _extract_annotation(
    env: Env, ctx: TransformContextProtocol
) -> tuple[str, list[Node]]:
    if env.opt_args:
        text = ctx.inline_markdown(env.opt_args[0].children).strip()
        return text, list(env.body)

    from arxiv_md.tex.ast import Text as AstText

    body = list(env.body)

    start = 0
    while start < len(body):
        node = body[start]
        if not isinstance(node, AstText) or node.value.strip():
            break
        start += 1
    first_node = body[start] if start < len(body) else None
    if not isinstance(first_node, AstText):
        return "", body
    first_val = first_node.value.lstrip()
    if not first_val.startswith("["):
        return "", body

    depth = 0
    parts: list[str] = []
    for j in range(start, len(body)):
        node = body[j]
        if not isinstance(node, AstText):
            break
        text = node.value
        for ci, ch in enumerate(text):
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    parts.append(text[:ci])
                    remainder = text[ci + 1 :]
                    annotation = "".join(parts)

                    if annotation.startswith("["):
                        annotation = annotation[1:]
                    annotation = annotation.strip()
                    new_body = body[:start]
                    if remainder.strip():
                        new_body.append(AstText(pos=node.pos, value=remainder))
                    new_body.extend(body[j + 1 :])
                    return annotation, new_body
        parts.append(text)

    return "", body
