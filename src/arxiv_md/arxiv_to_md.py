from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path
from typing import TypedDict

from arxiv_md.cli_output import emit_error, emit_ok
from arxiv_md.download import (
    Paper,
    is_arxiv_id,
    normalize_arxiv_id,
    safe_filename,
    search as arxiv_search,
)
from arxiv_md.source_download import download_source
from arxiv_md.tex import ConvertOptions, TexConvertError, convert_path

DEFAULT_TOP_K = 1


class ConvertedPaper(TypedDict):
    arxiv_id: str
    source: str
    markdown: str
    sidecar: str
    warnings: int


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="arxiv-to-md",
        description="Download arXiv source bundles and convert TeX to Markdown.",
    )
    parser.add_argument("query", nargs="+", help="arXiv ID(s) or search query")
    parser.add_argument(
        "--top-k",
        type=int,
        default=DEFAULT_TOP_K,
        help="Top search results to convert",
    )
    parser.add_argument(
        "--outdir",
        required=True,
        help=(
            "Parent output directory for the batch. Each paper writes to "
            "<outdir>/<safe_arxiv_id>/document.md"
        ),
    )
    parser.add_argument(
        "--keep-archive",
        action="store_true",
        help="Keep downloaded source archive under <outdir>/.archives/",
    )
    parser.add_argument(
        "--keep-source",
        action="store_true",
        help="Keep extracted source tree under <outdir>/<safe_arxiv_id>/source",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON envelope on stdout",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    outdir = Path(args.outdir)
    try:
        papers = _resolve_papers(args.query, top_k=args.top_k)
    except RuntimeError as exc:
        if args.json:
            emit_error(str(exc), code="no_results")
        else:
            print(str(exc), file=sys.stderr)
        return 1

    code = run_papers(
        papers,
        outdir=outdir,
        keep_archive=args.keep_archive,
        keep_source=args.keep_source,
        as_json=args.json,
    )
    return code


def run_papers(
    papers: list[Paper],
    *,
    outdir: Path,
    keep_archive: bool = False,
    keep_source: bool = False,
    as_json: bool = False,
) -> int:

    outdir = Path(outdir).expanduser()
    outdir.mkdir(parents=True, exist_ok=True)
    downloaded: list[dict[str, str]] = []
    converted: list[ConvertedPaper] = []
    failed: list[dict[str, str]] = []

    archives_dir: Path | None = None
    if keep_archive:
        archives_dir = outdir / ".archives"
        archives_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="arxiv-md-archives-") as tmp_root:
        cache = Path(tmp_root)
        for paper in papers:
            slug = safe_filename(paper.arxiv_id)
            stem = cache / f"{slug}-source"
            try:
                archive_path = download_source(paper.arxiv_id, stem)
                if archive_path is None:
                    failed.append(
                        {
                            "arxiv_id": paper.arxiv_id,
                            "error": "No source bundle available",
                        }
                    )
                    if not as_json:
                        print(f"{paper.arxiv_id}: no source bundle", file=sys.stderr)
                    continue
                if not as_json:
                    print(f"Downloaded source: {archive_path}")

                document_dir = outdir / slug
                result = convert_path(
                    archive_path,
                    ConvertOptions(
                        output_dir=document_dir,
                        document_slug=slug,
                        keep_source=keep_source,
                    ),
                )
                if result.written is None:
                    raise RuntimeError("convert_path() did not write output")

                final_archive = archive_path
                if archives_dir is not None:
                    final_archive = archives_dir / archive_path.name
                    shutil.move(str(archive_path), str(final_archive))

                downloaded.append(
                    {"arxiv_id": paper.arxiv_id, "path": str(final_archive)}
                )
                warnings_count = len(getattr(result.document, "warnings", []) or [])
                converted.append(
                    {
                        "arxiv_id": paper.arxiv_id,
                        "source": str(final_archive),
                        "markdown": str(result.written.markdown_path),
                        "sidecar": str(result.written.sidecar_path),
                        "warnings": warnings_count,
                    }
                )
                if not as_json:
                    print(
                        f"Converted: {final_archive} -> {result.written.markdown_path}"
                    )
                    if warnings_count:
                        print(f"Warnings: {warnings_count}")
            except TexConvertError as exc:
                failed.append(
                    {
                        "arxiv_id": paper.arxiv_id,
                        "code": exc.code,
                        "error": str(exc),
                    }
                )
                if not as_json:
                    print(f"{paper.arxiv_id}: {exc}", file=sys.stderr)
            except Exception as exc:
                failed.append(
                    {
                        "arxiv_id": paper.arxiv_id,
                        "code": "internal_error",
                        "error": str(exc),
                    }
                )
                if not as_json:
                    print(f"{paper.arxiv_id}: {exc}", file=sys.stderr)

    if as_json:
        emit_ok({"downloaded": downloaded, "converted": converted, "failed": failed})
    return 1 if failed else 0


def _resolve_papers(values: list[str], *, top_k: int) -> list[Paper]:
    if all(is_arxiv_id(value) for value in values):
        ids = [normalize_arxiv_id(value) for value in values]
        return [
            Paper(
                arxiv_id=arxiv_id,
                title="",
                pdf_url="",
                abstract_url=f"https://arxiv.org/abs/{arxiv_id}",
            )
            for arxiv_id in ids
        ]

    query = " ".join(values)
    papers = arxiv_search(query, max_results=top_k)
    if not papers:
        raise RuntimeError(f"No arXiv results for: {query}")
    return papers


if __name__ == "__main__":
    raise SystemExit(main())
