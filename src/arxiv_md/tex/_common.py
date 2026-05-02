from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from arxiv_md.tex.model import Block

WARNING_CODES = {
    "missing_include",
    "unknown_command",
    "unknown_env",
    "unknown_macro",
    "parse_recovery",
    "figure_missing",
    "figure_ambiguous",
    "unsupported_asset",
    "table_raw_fallback",
    "macro_expansion_skipped",
    "bib_parse_partial",
    "asset_scan_capped",
    "pdfium_missing",
    "pillow_missing",
    "resource_limit",
}

FATAL_ERROR_CODES = {
    "unsafe_archive",
    "unsupported_archive",
    "unsafe_output_dir",
    "unreadable_source",
    "no_main_tex",
    "no_parseable_body",
    "output_write_failed",
    "resource_limit",
    "strict_conversion_failed",
    "internal_error",
}


@dataclass(slots=True)
class SourceSpan:
    """Original-source location for diagnostics after include/macro mapping.

    Offsets are Python string positions in `file`; `line` and `column` are
    one-based so CLI/JSON consumers can jump directly to source.
    """

    file: Path
    start_offset: int
    end_offset: int
    line: int
    column: int

    def to_json(self) -> dict[str, Any]:
        return {
            "file": str(self.file),
            "start_offset": self.start_offset,
            "end_offset": self.end_offset,
            "line": self.line,
            "column": self.column,
        }


@dataclass(slots=True)
class TexWarning:
    """Recoverable conversion diagnostic with stable machine-readable `code`.

    `message` is human text and may change; callers should branch on `code`.
    `span` is present only when source mapping survived the pipeline.
    """

    code: str
    message: str
    path: Path | None = None
    span: SourceSpan | None = None

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.path is not None:
            payload["path"] = str(self.path)
        if self.span is not None:
            payload["span"] = self.span.to_json()
        return payload


@dataclass(slots=True)
class BibEntry:
    """Bibliography entry after LaTeX cleanup; `key` matches citation keys."""

    key: str = ""
    text: str = ""


@dataclass(slots=True)
class TexDocument:
    """Semantic document IR returned by conversions.

    Schema is additive: consumers should ignore fields they do not understand and
    discriminate block/span variants with `BLOCK_TYPES` / `INLINE_TYPES`.
    """

    root_dir: Path
    main_tex: Path
    title: str = ""
    authors: list[str] = field(default_factory=list)
    abstract: list[Block] = field(default_factory=list)
    blocks: list[Block] = field(default_factory=list)
    bibliography: list[BibEntry] = field(default_factory=list)
    warnings: list[TexWarning] = field(default_factory=list)
    unknown_command_counts: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True)
class ConversionStats:
    """Aggregate conversion counters for dashboards and regression tracking.

    Counts summarize output quality; use `warnings` for per-location diagnostics.
    """

    tex_files_read: int = 0
    figures_total: int = 0
    figures_resolved: int = 0
    tables_html: int = 0
    tables_raw: int = 0
    unknown_commands: int = 0
    unknown_command_counts: dict[str, int] = field(default_factory=dict)
    unknown_env_counts: dict[str, int] = field(default_factory=dict)
    raw_fallback_command_counts: dict[str, int] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ResourceLimits:
    """Safety caps for converting untrusted arXiv source bundles.

    Exceeding a cap raises `ResourceLimitError` instead of partially processing
    hostile or accidentally huge inputs.
    """

    max_archive_members: int = 10_000
    max_archive_total_bytes: int = 512 * 1024 * 1024
    max_single_file_bytes: int = 64 * 1024 * 1024
    max_tex_source_bytes: int = 64 * 1024 * 1024
    max_include_files: int = 2_000
    max_asset_files_scanned: int = 50_000
    max_tex_files_scanned: int = 500
    max_bib_files_scanned: int = 2_000
    max_pdf_pages_rasterized: int = 1
    max_macro_expansion_depth: int = 32
    max_macro_expanded_nodes: int = 100_000
    max_table_nesting_depth: int = 4

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


ASSET_MODES = {"rasterize", "copy", "skip"}
"""Asset mode vocabulary shared by API validation and CLI choices.

- ``rasterize`` (default): normalize rasterizable figures to PNG.
- ``copy``: copy supported asset files without conversion.
- ``skip``: resolve paths but write nothing (dry-run asset report).
"""

DEFAULT_RASTER_DPI: int = 120


@dataclass(slots=True)
class ConvertOptions:
    """Public conversion config shared by API and CLI.

    Invalid `asset_mode` or `raster_dpi < 1` raises `ValueError` at construction
    time so conversions fail before touching input files.
    """

    output_dir: Path | None = None
    document_slug: str | None = None
    keep_source: bool = False
    render_assets: bool = True
    strict: bool = False
    asset_mode: str = "rasterize"
    """How to handle rasterizable assets (PDF, JPEG).

    - ``"rasterize"`` (default): convert assets to PNG at :attr:`raster_dpi`.
    - ``"copy"``: copy assets verbatim, leaving downstream consumers to handle
      original formats.
    - ``"skip"``: resolve asset paths and count figures but write nothing to
      ``images/`` (dry-run mode for asset auditing).

    Only effective when ``render_assets=True``; when ``render_assets=False``
    the entire asset pipeline is skipped.
    """
    raster_dpi: int = DEFAULT_RASTER_DPI
    """DPI used when rasterizing PDF pages to PNG (default 120).

    Higher values produce sharper images at the cost of file size and
    rasterization time.  Only effective when ``asset_mode="rasterize"``.
    """
    limits: ResourceLimits = field(default_factory=ResourceLimits)

    def __post_init__(self) -> None:
        if self.asset_mode not in ASSET_MODES:
            raise ValueError(
                f"Invalid asset_mode={self.asset_mode!r}; "
                f"expected one of {sorted(ASSET_MODES)}"
            )
        if self.raster_dpi < 1:
            raise ValueError(f"raster_dpi must be ≥ 1, got {self.raster_dpi}")


@dataclass(slots=True)
class WrittenResult:
    """Filesystem paths produced by `write_result` or `ConvertOptions.output_dir`."""

    output_dir: Path
    markdown_path: Path
    sidecar_path: Path


@dataclass(slots=True)
class ConvertResult:
    """Conversion output with both rendered Markdown and typed document IR.

    `written` stays `None` for pure in-memory conversions and is populated only
    after `write_result` or conversion with `output_dir`.
    """

    markdown: str
    document: TexDocument
    stats: ConversionStats
    source_path: Path | None = None
    warnings: list[TexWarning] = field(default_factory=list)
    written: WrittenResult | None = None
    options: ConvertOptions = field(default_factory=ConvertOptions)


def safe_slug(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    value = value.strip("._-")
    return value or "document"


def warning(
    code: str,
    message: str,
    path: Path | None = None,
    span: SourceSpan | None = None,
) -> TexWarning:
    if code not in WARNING_CODES:
        raise ValueError(f"Unknown warning code: {code!r}")
    return TexWarning(code=code, message=message, path=path, span=span)


def warnings_json(warnings: list[TexWarning]) -> list[dict[str, Any]]:
    return [item.to_json() for item in warnings]


def relpath(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def sidecar_payload(
    *,
    source: Path | None,
    main_tex: Path,
    warnings: list[TexWarning],
    stats: ConversionStats,
    options: ConvertOptions | None = None,
) -> dict[str, Any]:
    opts = options or ConvertOptions()
    return {
        "ok": True,
        "source": str(source) if source is not None else None,
        "main_tex": str(main_tex),
        "converter": "tex",
        "warnings": warnings_json(warnings),
        "stats": stats.to_json(),
        "config": {
            "keep_source": opts.keep_source,
            "render_assets": opts.render_assets,
            "asset_mode": opts.asset_mode,
            "raster_dpi": opts.raster_dpi,
            "strict": opts.strict,
            "limits": opts.limits.to_json(),
        },
    }
