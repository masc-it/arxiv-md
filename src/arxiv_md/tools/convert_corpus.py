from __future__ import annotations

import argparse
import csv
import io
import json
import statistics
import sys
import time
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from arxiv_md import ConvertOptions, convert_path

ARCHIVE_SUFFIXES: tuple[str, ...] = (
    ".tar.gz",
    ".tar.bz2",
    ".tgz",
    ".tbz2",
    ".tar",
    ".zip",
    ".gz",
)


@dataclass(slots=True)
class EntryReport:
    name: str
    path: str
    kind: str
    status: str
    elapsed_s: float = 0.0
    warnings: int = 0
    warning_codes: dict[str, int] = field(default_factory=dict)
    output_bytes: int = 0
    output_dir: str | None = None
    error_type: str | None = None
    error_message: str | None = None

    def to_row(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "kind": self.kind,
            "status": self.status,
            "elapsed_s": round(self.elapsed_s, 4),
            "warnings": self.warnings,
            "warning_codes": self.warning_codes,
            "output_bytes": self.output_bytes,
            "output_dir": self.output_dir,
            "error_type": self.error_type,
            "error_message": self.error_message,
        }


@dataclass(slots=True)
class CorpusSummary:
    input_dir: str
    total: int
    converted: int
    failed: int
    skipped: int
    total_elapsed_s: float
    mean_elapsed_s: float
    median_elapsed_s: float
    max_elapsed_s: float
    total_output_bytes: int
    total_warnings: int
    entries: list[EntryReport]

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)

        return data


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m arxiv_md.tools.convert_corpus",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "input_dir",
        type=Path,
        help="Directory containing source archives / source dirs / .tex files",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="-",
        help="Summary output path (default: stdout `-`)",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=("json", "csv"),
        default="json",
        help="Summary format (default: json)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Optional dir to write converted Markdown + sidecars per entry",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap number of entries processed (smoke runs)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Pass strict=True to ConvertOptions (fail on tex warnings)",
    )
    parser.add_argument(
        "--keep-source",
        action="store_true",
        help="When --output-dir is set, keep extracted source tree per entry",
    )
    parser.add_argument(
        "--no-assets",
        action="store_true",
        help="Disable asset resolution (render_assets=False)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-entry progress lines on stderr",
    )
    return parser


def discover_entries(input_dir: Path) -> list[tuple[Path, str]]:

    entries: list[tuple[Path, str]] = []
    for child in sorted(input_dir.iterdir()):
        if child.is_dir():
            if any(child.rglob("*.tex")):
                entries.append((child, "dir"))
            else:
                entries.append((child, "skipped"))
            continue
        if child.is_file():
            lower = child.name.lower()
            if lower.endswith(".tex"):
                entries.append((child, "tex"))
            elif any(lower.endswith(suf) for suf in ARCHIVE_SUFFIXES):
                entries.append((child, "archive"))
            else:
                entries.append((child, "skipped"))
    return entries


def _slug_for(path: Path) -> str:

    name = path.name
    for suf in ARCHIVE_SUFFIXES:
        if name.lower().endswith(suf):
            return name[: -len(suf)]
    if name.lower().endswith(".tex"):
        return name[:-4]
    return name


def _output_subdir(path: Path) -> str:

    name = path.name
    if path.is_dir():
        return name
    return name.replace(".", "_")


def _dir_size(path: Path) -> int:
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                continue
    return total


def _count_warning_codes(warnings: Iterable[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for w in warnings:
        code = getattr(w, "code", "unknown")
        counts[code] = counts.get(code, 0) + 1
    return counts


def _print_progress(quiet: bool, progress_stream: Any, message: str) -> None:
    if not quiet:
        print(message, file=progress_stream)


def _entry_output_dir(output_dir: Path | None, path: Path) -> Path | None:
    if output_dir is None:
        return None
    per_entry_out = output_dir / _output_subdir(path)
    per_entry_out.mkdir(parents=True, exist_ok=True)
    return per_entry_out


def _skipped_report(path: Path) -> EntryReport:
    return EntryReport(
        name=path.name,
        path=str(path),
        kind="skipped",
        status="skipped",
        error_type="UnsupportedEntry",
        error_message="not an archive, .tex file, or source dir",
    )


def _entry_options(
    path: Path,
    per_entry_out: Path | None,
    *,
    keep_source: bool,
    strict: bool,
    no_assets: bool,
) -> ConvertOptions:
    return ConvertOptions(
        output_dir=per_entry_out,
        document_slug=_slug_for(path),
        keep_source=keep_source,
        strict=strict,
        render_assets=not no_assets,
    )


def _failed_report(
    path: Path,
    kind: str,
    elapsed: float,
    exc: Exception,
    per_entry_out: Path | None,
) -> EntryReport:
    return EntryReport(
        name=path.name,
        path=str(path),
        kind=kind,
        status="fail",
        elapsed_s=elapsed,
        error_type=type(exc).__name__,
        error_message=str(exc),
        output_dir=str(per_entry_out) if per_entry_out else None,
    )


def _output_bytes(result: Any, per_entry_out: Path | None) -> int:
    if per_entry_out is not None and per_entry_out.is_dir():
        return _dir_size(per_entry_out)
    return len(result.markdown.encode("utf-8"))


def _success_report(
    path: Path,
    kind: str,
    elapsed: float,
    result: Any,
    per_entry_out: Path | None,
) -> EntryReport:
    warnings = list(result.warnings)
    return EntryReport(
        name=path.name,
        path=str(path),
        kind=kind,
        status="ok",
        elapsed_s=elapsed,
        warnings=len(warnings),
        warning_codes=_count_warning_codes(warnings),
        output_bytes=_output_bytes(result, per_entry_out),
        output_dir=str(per_entry_out) if per_entry_out else None,
    )


def _process_entry(
    path: Path,
    kind: str,
    *,
    output_dir: Path | None,
    keep_source: bool,
    strict: bool,
    no_assets: bool,
    quiet: bool,
    progress_stream: Any,
) -> EntryReport:

    if kind == "skipped":
        _print_progress(quiet, progress_stream, f"  skip  {path.name}")
        return _skipped_report(path)

    per_entry_out = _entry_output_dir(output_dir, path)
    options = _entry_options(
        path,
        per_entry_out,
        keep_source=keep_source,
        strict=strict,
        no_assets=no_assets,
    )

    t0 = time.perf_counter()
    try:
        result = convert_path(path, options)
    except Exception as exc:  # noqa: BLE001 — benchmark must catch all
        elapsed = time.perf_counter() - t0
        _print_progress(
            quiet,
            progress_stream,
            f"  FAIL  {path.name}: {type(exc).__name__}: {exc}",
        )
        return _failed_report(path, kind, elapsed, exc, per_entry_out)

    elapsed = time.perf_counter() - t0
    report = _success_report(path, kind, elapsed, result, per_entry_out)
    _print_progress(
        quiet,
        progress_stream,
        f"  ok    {path.name}  "
        f"({elapsed * 1000:.1f} ms, {report.output_bytes} B, {report.warnings} warn)",
    )
    return report


def _successful_reports(reports: list[EntryReport]) -> list[EntryReport]:
    return [r for r in reports if r.status == "ok"]


def _count_status(reports: list[EntryReport], status: str) -> int:
    return sum(1 for r in reports if r.status == status)


def _elapsed_values(reports: list[EntryReport]) -> list[float]:
    return [r.elapsed_s for r in reports]


def _timing_summary(timed: list[float]) -> tuple[float, float, float, float]:
    total_elapsed = sum(timed)
    mean_elapsed = total_elapsed / len(timed) if timed else 0.0
    median_elapsed = statistics.median(timed) if timed else 0.0
    max_elapsed = max(timed) if timed else 0.0
    return total_elapsed, mean_elapsed, median_elapsed, max_elapsed


def _total_output_bytes(reports: list[EntryReport]) -> int:
    return sum(r.output_bytes for r in reports)


def _total_warnings(reports: list[EntryReport]) -> int:
    return sum(r.warnings for r in reports)


def _aggregate_reports(reports: list[EntryReport], input_dir: Path) -> CorpusSummary:

    ok = _successful_reports(reports)
    total_elapsed, mean_elapsed, median_elapsed, max_elapsed = _timing_summary(
        _elapsed_values(ok)
    )

    return CorpusSummary(
        input_dir=str(input_dir),
        total=len(reports),
        converted=len(ok),
        failed=_count_status(reports, "fail"),
        skipped=_count_status(reports, "skipped"),
        total_elapsed_s=round(total_elapsed, 4),
        mean_elapsed_s=round(mean_elapsed, 4),
        median_elapsed_s=round(median_elapsed, 4),
        max_elapsed_s=round(max_elapsed, 4),
        total_output_bytes=_total_output_bytes(ok),
        total_warnings=_total_warnings(ok),
        entries=reports,
    )


def run_corpus(
    input_dir: Path,
    *,
    output_dir: Path | None = None,
    limit: int | None = None,
    strict: bool = False,
    keep_source: bool = False,
    no_assets: bool = False,
    quiet: bool = True,
    progress_stream: Any = sys.stderr,
) -> CorpusSummary:

    input_dir = input_dir.expanduser().resolve()
    if not input_dir.is_dir():
        raise NotADirectoryError(f"input_dir is not a directory: {input_dir}")

    if output_dir is not None:
        output_dir = output_dir.expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

    entries = discover_entries(input_dir)
    if limit is not None:
        entries = entries[:limit]

    reports = [
        _process_entry(
            path,
            kind,
            output_dir=output_dir,
            keep_source=keep_source,
            strict=strict,
            no_assets=no_assets,
            quiet=quiet,
            progress_stream=progress_stream,
        )
        for path, kind in entries
    ]
    return _aggregate_reports(reports, input_dir)


def render_summary(summary: CorpusSummary, fmt: str) -> str:
    if fmt == "json":
        payload = {
            "input_dir": summary.input_dir,
            "total": summary.total,
            "converted": summary.converted,
            "failed": summary.failed,
            "skipped": summary.skipped,
            "total_elapsed_s": summary.total_elapsed_s,
            "mean_elapsed_s": summary.mean_elapsed_s,
            "median_elapsed_s": summary.median_elapsed_s,
            "max_elapsed_s": summary.max_elapsed_s,
            "total_output_bytes": summary.total_output_bytes,
            "total_warnings": summary.total_warnings,
            "entries": [r.to_row() for r in summary.entries],
        }
        return json.dumps(payload, indent=2, sort_keys=False) + "\n"

    if fmt == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "name",
                "path",
                "kind",
                "status",
                "elapsed_s",
                "warnings",
                "warning_codes",
                "output_bytes",
                "output_dir",
                "error_type",
                "error_message",
            ]
        )
        for r in summary.entries:
            writer.writerow(
                [
                    r.name,
                    r.path,
                    r.kind,
                    r.status,
                    f"{r.elapsed_s:.4f}",
                    r.warnings,
                    json.dumps(r.warning_codes, sort_keys=True),
                    r.output_bytes,
                    r.output_dir or "",
                    r.error_type or "",
                    r.error_message or "",
                ]
            )

        writer.writerow(
            [
                "__aggregate__",
                summary.input_dir,
                "__aggregate__",
                "summary",
                f"{summary.total_elapsed_s:.4f}",
                summary.total_warnings,
                json.dumps(
                    {
                        "converted": summary.converted,
                        "failed": summary.failed,
                        "skipped": summary.skipped,
                        "mean_elapsed_s": summary.mean_elapsed_s,
                        "median_elapsed_s": summary.median_elapsed_s,
                        "max_elapsed_s": summary.max_elapsed_s,
                    },
                    sort_keys=True,
                ),
                summary.total_output_bytes,
                "",
                "",
                "",
            ]
        )
        return buf.getvalue()

    raise ValueError(f"unknown format: {fmt!r}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = run_corpus(
            args.input_dir,
            output_dir=args.output_dir,
            limit=args.limit,
            strict=args.strict,
            keep_source=args.keep_source,
            no_assets=args.no_assets,
            quiet=args.quiet,
        )
    except (NotADirectoryError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 2

    rendered = render_summary(summary, args.format)
    if args.output == "-":
        sys.stdout.write(rendered)
    else:
        Path(args.output).expanduser().write_text(rendered, encoding="utf-8")
        if not args.quiet:
            print(f"summary written to {args.output}", file=sys.stderr)

    return 0 if summary.failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
