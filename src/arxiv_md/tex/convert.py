from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

from arxiv_md.cli_output import emit_error, emit_ok
from arxiv_md.tex._common import (
    DEFAULT_RASTER_DPI,
    ConversionStats,
    ConvertOptions,
    ConvertResult,
    WrittenResult,
    safe_slug,
    sidecar_payload,
)
from arxiv_md.tex.model import (
    Block,
    ListBlock,
    QuoteBlock,
    RawLatex,
    Table,
)
from arxiv_md.tex.archive import SourceTree, prepare_source_tree
from arxiv_md.tex.errors import (
    NoParseableBodyError,
    OutputWriteError,
    StrictConversionError,
    TexConvertError,
    UnsafeOutputDirError,
)
from arxiv_md.tex.assets import resolve_figure_assets
from arxiv_md.tex.lexer import Diagnostics, tokenize
from arxiv_md.tex.macro_engine import compile_macros, expand as macro_expand_ast
from arxiv_md.tex.macros import (
    build_strip_offset_map,
    collect_macros_full,
    discover_newtheorem,
    expand_env_shorthands,
    find_env_shorthand_macros,
    find_include_wrapper_macros,
    strip_tex_conditionals,
)
from arxiv_md.tex.parser import parse as ast_parse
from arxiv_md.tex.rendering import render_document_markdown
from arxiv_md.tex.source import expand_source
from arxiv_md.tex.transform.context import TransformContext
from arxiv_md.tex.transform.document import build_document


def convert_text(tex: str, options: ConvertOptions | None = None) -> ConvertResult:
    """In-memory conversion uses a temporary source root.

    Relative includes and assets only resolve when caller writes matching files into
    generated tree through another API; use `convert_path` for real source
    bundles. If `options.output_dir` is set, result is written before return.
    """
    options = options or ConvertOptions()
    with tempfile.TemporaryDirectory(prefix="arxiv-md-text-") as tmp:
        root_dir = Path(tmp)
        main_tex = root_dir / "main.tex"
        main_tex.write_text(tex, encoding="utf-8")
        tree = SourceTree(root_dir=root_dir, main_tex=main_tex, warnings=[])
        result = _convert_tree(tree, source_path=None, options=options)
        if options.output_dir is not None:
            write_result(result, options.output_dir)
        return result


def convert_path(
    path: Path | str, options: ConvertOptions | None = None
) -> ConvertResult:
    """Path-based conversion enforces source/output isolation before reading input.

    Archives extract under `output_dir` when configured, otherwise under a temp
    dir. `output_dir` must not be source tree or child, so conversion cannot
    overwrite user sources.
    """
    options = options or ConvertOptions()
    source_path = Path(path).expanduser().resolve()
    slug = safe_slug(options.document_slug or _source_slug(source_path))
    output_dir = (
        Path(options.output_dir).expanduser().resolve()
        if options.output_dir is not None
        else None
    )
    source_root = _source_root_for_guard(source_path)
    if output_dir is not None and source_root is not None:
        assert_safe_output_dir(source_root, output_dir)

    if output_dir is None:
        with tempfile.TemporaryDirectory(prefix="arxiv-md-source-") as tmp:
            tree = prepare_source_tree(source_path, Path(tmp), limits=options.limits)
            return _convert_path_tree(tree, source_path=source_path, options=options)

    output_dir.mkdir(parents=True, exist_ok=True)
    write_options = ConvertOptions(
        output_dir=output_dir,
        document_slug=slug,
        keep_source=options.keep_source,
        render_assets=options.render_assets,
        asset_mode=options.asset_mode,
        raster_dpi=options.raster_dpi,
        strict=options.strict,
        limits=options.limits,
    )
    tree = prepare_source_tree(source_path, output_dir, limits=options.limits)
    return _convert_path_tree(tree, source_path=source_path, options=write_options)


def write_result(result: ConvertResult, output_dir: Path | str) -> WrittenResult:
    """Pure conversion results materialize delayed assets here.

    This call may resolve/copy assets and re-render Markdown before writing
    `document.md` and `conversion.json`. Write failures raise `OutputWriteError`.
    """
    document_dir = Path(output_dir).expanduser()
    try:
        document_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OutputWriteError(
            f"Cannot create output directory {document_dir}: {exc}"
        ) from exc
    _maybe_render_late_assets(result, document_dir)
    markdown_path = document_dir / "document.md"
    sidecar_path = document_dir / "conversion.json"
    try:
        markdown_path.write_text(result.markdown, encoding="utf-8")
    except OSError as exc:
        raise OutputWriteError(
            f"Cannot write Markdown to {markdown_path}: {exc}"
        ) from exc
    payload = sidecar_payload(
        source=result.source_path,
        main_tex=result.document.main_tex,
        warnings=result.warnings,
        stats=result.stats,
        options=result.options,
    )
    try:
        sidecar_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise OutputWriteError(
            f"Cannot write sidecar to {sidecar_path}: {exc}"
        ) from exc
    result.written = WrittenResult(
        output_dir=document_dir,
        markdown_path=markdown_path,
        sidecar_path=sidecar_path,
    )
    return result.written


def _maybe_render_late_assets(result: ConvertResult, document_dir: Path) -> None:

    options = result.options
    if not options.render_assets:
        return
    if options.output_dir is not None:
        return
    if result.source_path is None:
        return
    document = result.document
    if not document.root_dir.exists() or not document.main_tex.exists():
        return
    try:
        expanded = expand_source(
            document.root_dir, document.main_tex, limits=options.limits
        )
    except Exception:
        return
    resolve_figure_assets(
        document,
        output_dir=document_dir,
        source_text=expanded.text,
        stats=result.stats,
        limits=options.limits,
        asset_mode=options.asset_mode,
        raster_dpi=options.raster_dpi,
    )
    result.markdown = render_document_markdown(document)


def _convert_path_tree(
    tree: SourceTree,
    *,
    source_path: Path,
    options: ConvertOptions,
) -> ConvertResult:
    try:
        result = _convert_tree(tree, source_path=source_path, options=options)
        if options.output_dir is not None:
            write_result(result, options.output_dir)
        return result
    except Exception:
        if tree.cleanup_dir and not options.keep_source and tree.cleanup_dir.exists():
            shutil.rmtree(tree.cleanup_dir, ignore_errors=True)
        raise
    finally:
        if tree.cleanup_dir and not options.keep_source and tree.cleanup_dir.exists():
            shutil.rmtree(tree.cleanup_dir, ignore_errors=True)


def _convert_tree(
    tree: SourceTree,
    *,
    source_path: Path | None,
    options: ConvertOptions,
) -> ConvertResult:
    stats = ConversionStats()
    warnings = list(tree.warnings or [])

    expanded = expand_source(tree.root_dir, tree.main_tex, limits=options.limits)

    # Detect include-wrapper macros and re-expand with aliases
    include_aliases = find_include_wrapper_macros(expanded.text)
    if include_aliases:
        expanded = expand_source(
            tree.root_dir,
            tree.main_tex,
            limits=options.limits,
            include_aliases=include_aliases,
        )

    warnings.extend(expanded.warnings)
    stats.tex_files_read = len(expanded.files_read)

    tex_text = strip_tex_conditionals(expanded.text)

    macro_warnings: list = []
    collected = collect_macros_full(tex_text, macro_warnings)
    macros_dict = collected.macros
    stripped_text = collected.stripped
    warnings.extend(macro_warnings)

    # Expand env-shorthand macros (\be → \begin{equation}, etc.) at text
    # level so the parser sees real \begin/\end pairs.
    env_shorthands = find_env_shorthand_macros(macros_dict)
    if env_shorthands:
        stripped_text = expand_env_shorthands(stripped_text, env_shorthands)
        for name in env_shorthands:
            del macros_dict[name]

    strip_map = build_strip_offset_map(collected.remove_ranges)

    def _diag_mapper(start: int, end: int | None):
        expanded_start = strip_map.translate(start)
        expanded_end = strip_map.translate(end) if end is not None else None
        return expanded.span_for_offset(expanded_start, expanded_end)

    diag = Diagnostics(warnings=list(warnings), mapper=_diag_mapper)
    tokens = tokenize(stripped_text, diag)
    macro_signatures: dict[str, str] = {}
    for name, m in macros_dict.items():
        if m.argc <= 0:
            continue
        if m.default is not None:
            macro_signatures[name] = "o" + "m" * (m.argc - 1)
        else:
            macro_signatures[name] = "m" * m.argc
    ast_nodes = ast_parse(
        tokens,
        diag,
        source_text=stripped_text,
        extra_signatures=macro_signatures,
    )
    compiled = compile_macros(macros_dict, diag)
    ast_nodes = macro_expand_ast(ast_nodes, compiled, diag, limits=options.limits)

    custom_theorems = discover_newtheorem(expanded.text)
    theorem_env_titles: dict[str, str] = {}
    if custom_theorems:
        from arxiv_md.tex.transform.handlers.theorems import ALL_BUILTIN_THEOREM_ENVS

        theorem_env_titles = {
            name: title
            for name, title in custom_theorems.items()
            if name not in ALL_BUILTIN_THEOREM_ENVS
        }

    ctx = TransformContext(
        diag=diag,
        source_text=stripped_text,
        macros=compiled,
        limits=options.limits,
        theorem_env_titles=theorem_env_titles,
    )
    document = build_document(
        ctx,
        ast_nodes,
        root_dir=tree.root_dir,
        main_tex=tree.main_tex,
    )

    if (
        source_path is not None
        and options.output_dir is not None
        and options.render_assets
    ):
        resolve_figure_assets(
            document,
            output_dir=options.output_dir,
            source_text=stripped_text,
            stats=stats,
            limits=options.limits,
            asset_mode=options.asset_mode,
            raster_dpi=options.raster_dpi,
        )

    warnings = list(document.warnings)
    stats.unknown_command_counts = dict(sorted(document.unknown_command_counts.items()))
    stats.unknown_commands = sum(stats.unknown_command_counts.values())
    stats.unknown_env_counts = _unknown_env_counts(warnings)
    stats.raw_fallback_command_counts = _raw_fallback_command_counts(document.blocks)
    stats.tables_raw = sum(1 for item in warnings if item.code == "table_raw_fallback")
    stats.tables_html = sum(
        1
        for block in document.blocks
        if isinstance(block, Table) and block.parse_status == "structured"
    )

    markdown = render_document_markdown(document)
    if not _meaningful(markdown):
        raise NoParseableBodyError("No parseable TeX body produced")
    if options.strict and warnings:
        first = warnings[0]
        raise StrictConversionError(
            f"TeX conversion warnings in strict mode: {first.code}: {first.message}",
            warnings=list(warnings),
        )

    return ConvertResult(
        markdown=markdown,
        document=document,
        stats=stats,
        source_path=source_path,
        warnings=warnings,
        options=options,
    )


def build_parser(
    parent: argparse._SubParsersAction | None = None,
) -> argparse.ArgumentParser:
    kwargs: dict = dict(description=__doc__)
    if parent is not None:
        parser = parent.add_parser("convert-tex", **kwargs)
    else:
        parser = argparse.ArgumentParser(prog="tex-to-md", **kwargs)
    parser.add_argument(
        "source_path", help=".tex file, source directory, or arXiv source archive"
    )
    parser.add_argument(
        "--outdir",
        required=True,
        help="Document output directory (will contain document.md, conversion.json, images/)",
    )
    parser.add_argument("--document-slug", help="Output document slug")
    parser.add_argument(
        "--keep-source",
        action="store_true",
        help="Keep extracted archive source tree under <outdir>/source",
    )
    parser.add_argument(
        "--no-assets",
        action="store_true",
        help="Do not render/copy figure assets",
    )
    parser.add_argument(
        "--asset-mode",
        choices=["rasterize", "copy", "skip"],
        default="rasterize",
        help=(
            "How to handle PDF/JPEG assets. "
            "'rasterize' (default): convert supported assets to PNG "
            "(install arxiv-md[assets] for full coverage). "
            "'copy': copy as-is (no optional asset deps needed). "
            "'skip': resolve paths but write nothing."
        ),
    )
    parser.add_argument(
        "--raster-dpi",
        type=int,
        default=DEFAULT_RASTER_DPI,
        metavar="DPI",
        help=f"DPI for PDF rasterization (default: {DEFAULT_RASTER_DPI})",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail when conversion warnings are emitted",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON envelope on stdout",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source_path = Path(args.source_path)
    slug = safe_slug(args.document_slug or _source_slug(source_path))
    output_dir = Path(args.outdir)
    options = ConvertOptions(
        output_dir=output_dir,
        document_slug=slug,
        keep_source=args.keep_source,
        render_assets=not args.no_assets,
        asset_mode=args.asset_mode,
        raster_dpi=args.raster_dpi,
        strict=args.strict,
    )
    try:
        result = convert_path(source_path, options)
    except TexConvertError as exc:
        if args.json:
            extra = {
                k: v for k, v in exc.to_json().items() if k not in {"code", "message"}
            }
            emit_error(str(exc), code=exc.code, **extra)
        else:
            print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        if args.json:
            emit_error(str(exc), code="internal_error")
        else:
            print(str(exc), file=sys.stderr)
        return 1

    assert result.written is not None
    warnings_count = len(getattr(result.document, "warnings", []) or [])
    converted = [
        {
            "source": str(source_path),
            "markdown": str(result.written.markdown_path),
            "sidecar": str(result.written.sidecar_path),
            "warnings": warnings_count,
        }
    ]
    if args.json:
        emit_ok({"converted": converted, "failed": []})
    else:
        print(f"Converted: {source_path} -> {result.written.markdown_path}")
        if warnings_count:
            print(f"Warnings: {warnings_count}")
    return 0


def _unknown_env_counts(warnings: list) -> dict[str, int]:
    counts: Counter[str] = Counter()
    prefix = "Unknown environment preserved: "
    for item in warnings:
        if getattr(item, "code", "") == "unknown_env" and item.message.startswith(
            prefix
        ):
            counts[item.message[len(prefix) :]] += 1
    return dict(sorted(counts.items()))


def _raw_fallback_command_counts(blocks: list[Block]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for block in blocks:
        if isinstance(block, RawLatex):
            counts.update(_scan_latex_commands(block.text))
        elif isinstance(block, Table):
            if block.parse_status == "raw_fallback" and block.raw_latex is not None:
                counts.update(_scan_latex_commands(block.raw_latex))

            for section in block.sections:
                for row in section.rows:
                    for cell in row.cells:
                        counts.update(_raw_fallback_command_counts(cell.blocks))
        elif isinstance(block, ListBlock):
            for item in block.items:
                counts.update(_raw_fallback_command_counts(item))
        elif isinstance(block, QuoteBlock):
            counts.update(_raw_fallback_command_counts(block.blocks))
    return dict(sorted(counts.items()))


def _scan_latex_commands(text: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for name in re.findall(r"\\([A-Za-z@]+|.)", text):
        if len(name) == 1 and not name.isalpha() and name not in {"&", "%", "_"}:
            continue
        counts[f"\\{name}"] += 1
    return counts


def _source_slug(source_path: Path) -> str:
    name = source_path.name
    if source_path.is_dir():
        return name
    for suffix in (".tar.gz", ".tgz", ".tar", ".zip", ".gz"):
        if name.lower().endswith(suffix):
            return name[: -len(suffix)]
    return source_path.stem if source_path.suffix else name


def _meaningful(markdown: str) -> bool:
    content = [
        line
        for line in markdown.splitlines()
        if line.strip() and not line.startswith("#")
    ]
    return bool(markdown.strip()) and bool(content)


def _source_root_for_guard(source_path: Path) -> Path | None:
    if not source_path.exists():
        return None
    if source_path.is_dir():
        return source_path.resolve()
    if source_path.suffix.lower() == ".tex":
        return source_path.parent.resolve()
    return None


def assert_safe_output_dir(source_root: Path, output_dir: Path) -> None:
    """Reject output locations that would clobber or nest inside source input."""
    source_root = source_root.resolve()
    output_dir = output_dir.resolve()
    if output_dir == source_root or source_root in output_dir.parents:
        raise UnsafeOutputDirError(
            f"Output directory must not be inside source tree: {output_dir}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
