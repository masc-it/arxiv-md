from __future__ import annotations

import argparse
import sys
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any

from arxiv_md.tex.ast import Command, Env, Group, Math, Node, Text, Verbatim
from arxiv_md.tex.lexer import Diagnostics, tokenize
from arxiv_md.tex.parser import parse as ast_parse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tex-ast", description=__doc__)
    parser.add_argument("source", help="Path to a .tex file")
    parser.add_argument(
        "--tokens", action="store_true", help="Print token stream instead of AST"
    )
    parser.add_argument(
        "--warnings",
        action="store_true",
        help="Print diagnostics (always shown if tokens/AST omitted)",
    )
    parser.add_argument("--max-depth", type=int, default=8, help="Tree depth to print")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    text = Path(args.source).expanduser().read_text(encoding="utf-8")
    diag = Diagnostics()
    tokens = tokenize(text, diag)

    if args.tokens:
        for tok in tokens:
            print(
                f"{tok.pos:>6} {tok.kind:<22} {_short(tok.value)}{(' [' + tok.meta + ']') if tok.meta else ''}"
            )
    else:
        nodes = ast_parse(tokens, diag, source_text=text)
        _dump(nodes, depth=0, max_depth=args.max_depth)

    if args.warnings or not (args.tokens):
        if diag.warnings:
            print("\n# warnings", file=sys.stderr)
            for w in diag.warnings:
                print(f"  {w.code}: {w.message}", file=sys.stderr)
    return 0


def _short(value: str) -> str:
    if len(value) > 60:
        return repr(value[:57] + "...")
    return repr(value)


def _dump(nodes: list[Node], *, depth: int, max_depth: int) -> None:
    indent = "  " * depth
    for n in nodes:
        if isinstance(n, Text):
            print(f"{indent}Text {_short(n.value)} @ {n.pos}")
            continue
        if isinstance(n, Math):
            body = n.body[0].value if n.body and isinstance(n.body[0], Text) else ""
            kind = "Math$$" if n.display else "Math$"
            print(f"{indent}{kind} {_short(body)} @ {n.pos}")
            continue
        if isinstance(n, Verbatim):
            kind = "VerbInline" if n.inline else "Verbatim"
            print(f"{indent}{kind}[{n.language}] {_short(n.text)} @ {n.pos}")
            continue
        if isinstance(n, Command):
            star = "*" if n.star else ""
            print(
                f"{indent}\\{n.name}{star} opt={len(n.opt_args)} args={len(n.args)} @ {n.pos}"
            )
            if depth < max_depth:
                for i, g in enumerate(n.opt_args):
                    print(f"{indent}  [opt {i}]")
                    _dump(g.children, depth=depth + 2, max_depth=max_depth)
                for i, g in enumerate(n.args):
                    print(f"{indent}  {{arg {i}}}")
                    _dump(g.children, depth=depth + 2, max_depth=max_depth)
            continue
        if isinstance(n, Env):
            print(
                f"{indent}Env[{n.name}] opt={len(n.opt_args)} args={len(n.args)} body={len(n.body)} @ {n.pos}"
            )
            if depth < max_depth:
                for i, g in enumerate(n.args):
                    print(f"{indent}  {{env arg {i}}}")
                    _dump(g.children, depth=depth + 2, max_depth=max_depth)
                _dump(n.body, depth=depth + 1, max_depth=max_depth)
            continue
        if isinstance(n, Group):
            print(f"{indent}Group @ {n.pos}")
            if depth < max_depth:
                _dump(n.children, depth=depth + 1, max_depth=max_depth)
            continue

        cls = type(n).__name__
        meta = _node_meta(n)
        print(f"{indent}{cls} {meta} @ {n.pos}")


def _node_meta(n: Any) -> str:
    if not is_dataclass(n):
        return ""
    bits = []
    for f in fields(n):
        if f.name == "pos":
            continue
        v = getattr(n, f.name)
        if isinstance(v, (str, int, bool)) and v not in ("", 0, False):
            bits.append(f"{f.name}={v!r}")
    return " ".join(bits)


if __name__ == "__main__":
    raise SystemExit(main())
