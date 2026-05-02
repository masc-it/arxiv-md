from __future__ import annotations

import re
from pathlib import Path

from arxiv_md.tex._common import BibEntry, ResourceLimits, TexWarning, warning


def parse_bibliography(
    root_dir: Path,
    source_text: str,
    warnings: list[TexWarning],
    *,
    limits: ResourceLimits | None = None,
) -> list[BibEntry]:
    entries = _parse_thebibliography(source_text)
    if entries:
        return entries

    caps = limits or ResourceLimits()
    state = _ScanState(
        cap=caps.max_bib_files_scanned, max_bytes=caps.max_single_file_bytes
    )

    for bbl in sorted(root_dir.rglob("*.bbl")):
        if state.cap_reached(bbl, warnings):
            break
        state.scanned += 1
        if not state.size_ok(bbl, warnings):
            continue
        try:
            entries = _parse_thebibliography(
                bbl.read_text(encoding="utf-8", errors="ignore")
            )
        except OSError:
            continue
        if entries:
            return entries

    bib_entries: list[BibEntry] = []
    for bib in sorted(root_dir.rglob("*.bib")):
        if state.cap_reached(bib, warnings):
            break
        state.scanned += 1
        if not state.size_ok(bib, warnings):
            continue
        try:
            bib_entries.extend(
                _parse_bib(bib.read_text(encoding="utf-8", errors="ignore"))
            )
        except OSError:
            warnings.append(
                warning("bib_parse_partial", f"Could not read bibliography: {bib}", bib)
            )
    return bib_entries


class _ScanState:
    __slots__ = ("cap", "max_bytes", "scanned", "_cap_warned")

    def __init__(self, cap: int, max_bytes: int) -> None:
        self.cap = cap
        self.max_bytes = max_bytes
        self.scanned = 0
        self._cap_warned = False

    def cap_reached(self, path: Path, warnings: list[TexWarning]) -> bool:
        if self.scanned < self.cap:
            return False
        if not self._cap_warned:
            warnings.append(
                warning(
                    "resource_limit",
                    f"Bibliography scan stopped at max_bib_files_scanned={self.cap}; "
                    f"remaining .bbl/.bib files ignored starting with {path}",
                    path,
                )
            )
            self._cap_warned = True
        return True

    def size_ok(self, path: Path, warnings: list[TexWarning]) -> bool:
        try:
            size = path.stat().st_size
        except OSError:
            return True
        if size > self.max_bytes:
            warnings.append(
                warning(
                    "resource_limit",
                    f"Bibliography file skipped: {path} size={size} exceeds "
                    f"max_single_file_bytes={self.max_bytes}",
                    path,
                )
            )
            return False
        return True


def _parse_thebibliography(text: str) -> list[BibEntry]:
    env = re.search(
        r"\\begin\{thebibliography\}(?:\{[^{}]*\})?(.*?)\\end\{thebibliography\}",
        text,
        re.S,
    )
    if not env:
        return []
    body = env.group(1)
    chunks = re.split(r"(?=\\bibitem)", body)
    entries: list[BibEntry] = []
    for chunk in chunks:
        match = re.match(
            r"\\bibitem(?:\[[^\]]*\])?\{([^{}]+)\}(.*)", chunk.strip(), re.S
        )
        if not match:
            continue
        key = match.group(1).strip()
        value = _clean_latex_text(match.group(2))
        entries.append(BibEntry(key=key, text=value))
    return entries


def _parse_bib(text: str) -> list[BibEntry]:
    entries: list[BibEntry] = []
    for match in re.finditer(r"@\w+\s*\{\s*([^,]+),(.*?)\n\}", text, re.S):
        key = match.group(1).strip()
        body = match.group(2)
        title = _field(body, "title")
        author = _field(body, "author")
        year = _field(body, "year")
        pieces = [piece for piece in (author, title, year) if piece]
        entries.append(BibEntry(key=key, text=". ".join(pieces)))
    return entries


def _field(body: str, name: str) -> str:
    match = re.search(name + r"\s*=\s*[\{\"](.*?)[\}\"]\s*,", body, re.I | re.S)
    if not match:
        return ""
    return _clean_latex_text(match.group(1))


def _clean_latex_text(text: str) -> str:

    from arxiv_md.tex.lexer import Diagnostics
    from arxiv_md.tex.parser import parse_text
    from arxiv_md.tex.transform.context import TransformContext
    from arxiv_md.tex.transform.inline_render import InlineSerializer

    diag = Diagnostics()
    nodes = parse_text(text, diag)
    ctx = TransformContext(
        diag=diag,
        source_text=text,
        macros={},
        inline_serializer=InlineSerializer(ref_style="bracket"),
    )
    return ctx.inline_markdown(nodes)
