from __future__ import annotations

import bisect
import re
from dataclasses import dataclass, field
from pathlib import Path

from arxiv_md.tex._common import ResourceLimits, SourceSpan, TexWarning, warning
from arxiv_md.tex.errors import ResourceLimitError, SourceReadError

INCLUDE_RE = re.compile(r"\\(input|include|subfile)\s*\{([^{}]+)\}")


@dataclass(slots=True)
class ExpandedSegment:
    expanded_start: int
    expanded_end: int
    source_file: Path
    source_start: int
    source_end: int


@dataclass(slots=True)
class ExpandedSource:
    text: str
    files_read: list[Path] = field(default_factory=list)
    warnings: list[TexWarning] = field(default_factory=list)
    segments: list[ExpandedSegment] = field(default_factory=list)
    source_texts: dict[Path, str] = field(default_factory=dict)

    _segment_starts: tuple[int, ...] | None = field(default=None, repr=False)
    _line_starts_cache: dict[Path, tuple[int, ...]] | None = field(
        default=None, repr=False
    )

    def _get_segment_starts(self) -> tuple[int, ...]:
        if self._segment_starts is None:
            self._segment_starts = tuple(s.expanded_start for s in self.segments)
        return self._segment_starts

    def _get_line_starts(self, path: Path) -> tuple[int, ...]:
        if self._line_starts_cache is None:
            self._line_starts_cache = {}
        cached = self._line_starts_cache.get(path)
        if cached is not None:
            return cached
        text = self.source_texts.get(path, "")
        starts = _build_line_starts(text)
        self._line_starts_cache[path] = starts
        return starts

    def span_for_offset(self, start: int, end: int | None = None) -> SourceSpan | None:
        return span_for_offset(self, start, end)


class SourceReader:
    def __init__(
        self,
        root_dir: Path,
        *,
        limits: ResourceLimits | None = None,
    ) -> None:
        self.root_dir = root_dir
        self.limits = limits or ResourceLimits()
        self.cache: dict[Path, str] = {}
        self.files_read: list[Path] = []
        self.warnings: list[TexWarning] = []
        self._included: set[Path] = set()

        self._buf: list[str] = []
        self._buf_len: int = 0
        self._segments: list[ExpandedSegment] = []

    def expand(self, main_tex: Path) -> ExpandedSource:

        self._buf = []
        self._buf_len = 0
        self._segments = []
        self._expand_file(main_tex.resolve(), stack=[])
        text = "".join(self._buf)

        encoded_len = len(text.encode("utf-8"))
        cap = self.limits.max_tex_source_bytes
        if encoded_len > cap:
            raise ResourceLimitError(
                f"Expanded TeX source is {encoded_len} bytes, exceeds "
                f"max_tex_source_bytes={cap}",
                limit="max_tex_source_bytes",
                observed=encoded_len,
                cap=cap,
            )
        return ExpandedSource(
            text=text,
            files_read=self.files_read,
            warnings=self.warnings,
            segments=self._segments,
            source_texts=dict(self.cache),
        )

    def _emit_separator(self, sep: str) -> None:
        if not sep:
            return
        self._buf.append(sep)
        self._buf_len += len(sep)

    def _emit_chunk(self, source_file: Path, source_start: int, chunk: str) -> None:
        if not chunk:
            return
        expanded_start = self._buf_len
        expanded_end = expanded_start + len(chunk)
        source_end = source_start + len(chunk)
        if self._segments:
            last = self._segments[-1]
            if (
                last.source_file == source_file
                and last.expanded_end == expanded_start
                and last.source_end == source_start
            ):
                last.expanded_end = expanded_end
                last.source_end = source_end
                self._buf.append(chunk)
                self._buf_len = expanded_end
                return
        self._segments.append(
            ExpandedSegment(
                expanded_start=expanded_start,
                expanded_end=expanded_end,
                source_file=source_file,
                source_start=source_start,
                source_end=source_end,
            )
        )
        self._buf.append(chunk)
        self._buf_len = expanded_end

    def _expand_file(self, path: Path, stack: list[Path]) -> None:
        path = path.resolve()
        if path in stack:
            self.warnings.append(
                warning("missing_include", f"Include cycle skipped: {path}", path)
            )
            return
        if path in self._included:
            return
        self._included.add(path)

        text = self._read_text(path)
        self.files_read.append(path)
        cap = self.limits.max_include_files
        if len(self.files_read) > cap:
            raise ResourceLimitError(
                f"Include count exceeds max_include_files={cap} "
                f"(latest include: {path})",
                limit="max_include_files",
                observed=len(self.files_read),
                cap=cap,
            )
        self._emit_with_includes(text, current=path, stack=stack)

    def _emit_with_includes(self, text: str, current: Path, stack: list[Path]) -> None:
        line_start = 0
        n = len(text)
        while line_start < n:
            nl = text.find("\n", line_start)
            line_end = n if nl < 0 else nl + 1
            line = text[line_start:line_end]
            comment_at = _find_unescaped_percent(line)
            if comment_at < 0:
                prefix_end = line_end
                suffix_end = line_end
            else:
                prefix_end = line_start + comment_at
                suffix_end = line_end
            self._emit_with_include_matches(
                text=text,
                current=current,
                stack=stack,
                prefix_start=line_start,
                prefix_end=prefix_end,
            )

            if suffix_end > prefix_end:
                self._emit_chunk(current, prefix_end, text[prefix_end:suffix_end])
            line_start = line_end

    def _emit_with_include_matches(
        self,
        *,
        text: str,
        current: Path,
        stack: list[Path],
        prefix_start: int,
        prefix_end: int,
    ) -> None:
        cursor = prefix_start
        for m in INCLUDE_RE.finditer(text, prefix_start, prefix_end):
            if m.start() > cursor:
                self._emit_chunk(current, cursor, text[cursor : m.start()])
            include_name = m.group(2).strip()
            include_path = self._resolve_include(
                include_name, current_dir=current.parent
            )
            if include_path is None:
                self.warnings.append(
                    warning(
                        "missing_include", f"Missing include: {include_name}", current
                    )
                )

                self._emit_chunk(current, m.start(), text[m.start() : m.end()])
            else:
                self._emit_separator("\n")
                self._expand_file(include_path, stack=[*stack, current])
                self._emit_separator("\n")
            cursor = m.end()
        if cursor < prefix_end:
            self._emit_chunk(current, cursor, text[cursor:prefix_end])

    def _read_text(self, path: Path) -> str:
        if path in self.cache:
            return self.cache[path]

        cap = self.limits.max_single_file_bytes
        try:
            size = path.stat().st_size
        except OSError as exc:
            raise SourceReadError(f"Cannot stat TeX source {path}: {exc}") from exc
        if size > cap:
            raise ResourceLimitError(
                f"TeX source {path} is {size} bytes, exceeds "
                f"max_single_file_bytes={cap}",
                limit="max_single_file_bytes",
                observed=size,
                cap=cap,
            )
        try:
            data = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            data = path.read_text(encoding="latin-1")
        except OSError as exc:
            raise SourceReadError(f"Cannot read TeX source {path}: {exc}") from exc
        self.cache[path] = data
        return data

    def _resolve_include(self, name: str, current_dir: Path) -> Path | None:
        candidates: list[Path] = []
        raw = Path(name)
        names = [raw]
        if raw.suffix == "":
            names.insert(0, raw.with_suffix(".tex"))
        for base in (current_dir, self.root_dir):
            for item in names:
                candidates.append((base / item).resolve())
        for candidate in candidates:
            try:
                candidate.relative_to(self.root_dir.resolve())
            except ValueError:
                continue
            if candidate.is_file():
                return candidate
        return None


def expand_source(
    root_dir: Path,
    main_tex: Path,
    *,
    limits: ResourceLimits | None = None,
) -> ExpandedSource:
    return SourceReader(root_dir, limits=limits).expand(main_tex)


def span_for_offset(
    expanded: ExpandedSource,
    start: int,
    end: int | None = None,
) -> SourceSpan | None:
    if start < 0 or start > len(expanded.text):
        return None
    if not expanded.segments:
        return None
    if end is None or end < start:
        end = start
    seg = _segment_containing(
        expanded.segments,
        start,
        expanded._get_segment_starts(),
    )
    if seg is None:
        return None
    delta = start - seg.expanded_start
    src_start = seg.source_start + delta
    span_len = min(end, seg.expanded_end) - start
    if span_len < 0:
        span_len = 0
    src_end = src_start + span_len
    line_starts = expanded._get_line_starts(seg.source_file)
    line, column = _line_column_fast(line_starts, src_start)
    return SourceSpan(
        file=seg.source_file,
        start_offset=src_start,
        end_offset=src_end,
        line=line,
        column=column,
    )


def _segment_containing(
    segments: list[ExpandedSegment],
    offset: int,
    starts: tuple[int, ...] | None = None,
) -> ExpandedSegment | None:
    if not segments:
        return None
    if starts is None:
        starts = tuple(s.expanded_start for s in segments)
    idx = bisect.bisect_right(starts, offset) - 1
    if idx < 0:
        return None
    seg = segments[idx]
    if seg.expanded_start <= offset < seg.expanded_end:
        return seg
    return None


def _build_line_starts(text: str) -> tuple[int, ...]:
    starts = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            starts.append(i + 1)
    return tuple(starts)


def _line_column_fast(
    line_starts: tuple[int, ...],
    offset: int,
) -> tuple[int, int]:
    if not line_starts:
        return 1, 1
    if offset < 0:
        offset = 0
    idx = bisect.bisect_right(line_starts, offset) - 1
    if idx < 0:
        idx = 0
    line = idx + 1
    column = offset - line_starts[idx] + 1
    return line, column


def _line_column(text: str, offset: int) -> tuple[int, int]:
    if not text:
        return 1, 1
    return _line_column_fast(_build_line_starts(text), offset)


def _find_unescaped_percent(line: str) -> int:
    escaped = False
    for idx, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "%":
            return idx
    return -1
