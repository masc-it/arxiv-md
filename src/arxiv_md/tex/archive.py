from __future__ import annotations

import gzip
import shutil
import tarfile
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from arxiv_md.tex._common import ResourceLimits, TexWarning
from arxiv_md.tex.errors import (
    NoMainTexError,
    SourceReadError,
    UnsafeArchiveError,
    UnsupportedArchiveError,
)

ARCHIVE_SUFFIXES = {".tar", ".zip", ".tgz", ".gz"}
MAIN_NAME_BONUS = {"main.tex", "paper.tex", "ms.tex", "article.tex"}


@dataclass(slots=True)
class SourceTree:
    root_dir: Path
    main_tex: Path
    cleanup_dir: Path | None = None
    warnings: list[TexWarning] | None = None


def prepare_source_tree(
    source_path: Path,
    document_dir: Path,
    *,
    limits: ResourceLimits | None = None,
) -> SourceTree:
    source_path = source_path.expanduser().resolve()
    if not source_path.exists():
        raise SourceReadError(f"Source path does not exist: {source_path}")

    if source_path.is_dir():
        main_tex = detect_main_tex(source_path, limits=limits)
        return SourceTree(root_dir=source_path, main_tex=main_tex, warnings=[])

    if source_path.suffix.lower() == ".tex":
        return SourceTree(
            root_dir=source_path.parent, main_tex=source_path, warnings=[]
        )

    extract_dir = document_dir / "source"
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)
    _extract_archive(source_path, extract_dir, limits=limits or ResourceLimits())
    main_tex = detect_main_tex(extract_dir, limits=limits)
    return SourceTree(
        root_dir=extract_dir, main_tex=main_tex, cleanup_dir=extract_dir, warnings=[]
    )


_HIGH_CONFIDENCE = 10


_PRIORITY_NAMES = ("main.tex", "paper.tex", "ms.tex", "article.tex")


_PRIORITY_SUBDIRS = ("latex", "src")


def detect_main_tex(
    root_dir: Path,
    *,
    limits: ResourceLimits | None = None,
) -> Path:

    max_scan = (limits or ResourceLimits()).max_tex_files_scanned

    best_score = 0
    best_key: tuple = ()
    best_path: Path | None = None
    scanned = 0
    seen: set[Path] = set()

    def _consider(path: Path) -> bool:
        nonlocal best_score, best_key, best_path, scanned
        resolved = path.resolve()
        if resolved in seen:
            return False
        seen.add(resolved)
        scanned += 1
        score = score_main_tex(path, root_dir)
        if score <= 0:
            return False
        key = (len(path.relative_to(root_dir).parts), str(path))
        if score > best_score or (score == best_score and key < best_key):
            best_score = score
            best_key = key
            best_path = path
        return score >= _HIGH_CONFIDENCE

    for name in _PRIORITY_NAMES:
        candidate = root_dir / name
        if candidate.is_file() and _consider(candidate):
            return best_path  # type: ignore[return-value]
    for subdir in _PRIORITY_SUBDIRS:
        for name in _PRIORITY_NAMES:
            candidate = root_dir / subdir / name
            if candidate.is_file() and _consider(candidate):
                return best_path  # type: ignore[return-value]

    for path in sorted(root_dir.rglob("*.tex")):
        if not path.is_file():
            continue
        if path.resolve() in seen:
            continue
        if _consider(path):
            return best_path  # type: ignore[return-value]
        if scanned >= max_scan:
            break

    if best_path is None:
        raise NoMainTexError(f"No main .tex found in {root_dir}")
    return best_path


def score_main_tex(path: Path, root_dir: Path) -> int:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")[:200_000]
    except OSError:
        return 0

    score = 0
    if "\\documentclass" in text:
        score += 5
    if "\\begin{document}" in text:
        score += 5
    if path.name.lower() in MAIN_NAME_BONUS:
        score += 2
    if "\\title" in text or "\\maketitle" in text:
        score += 1
    if text.count("\\input") + text.count("\\include") >= 2:
        score += 1

    rel = path.relative_to(root_dir)
    if len(rel.parts) == 1 or rel.parts[0] in {"latex", "src"}:
        score += 1
    return score


def _check_member_count(count: int, limits: ResourceLimits) -> None:
    if count > limits.max_archive_members:
        raise UnsafeArchiveError(
            f"Archive has {count} members, exceeds cap {limits.max_archive_members}"
        )


def _check_file_size(name: str, size: int, limits: ResourceLimits) -> None:
    if size > limits.max_single_file_bytes:
        raise UnsafeArchiveError(
            f"Archive member {name!r} declares {size} bytes, "
            f"exceeds single-file cap {limits.max_single_file_bytes}"
        )


def _check_total_size(total: int, limits: ResourceLimits) -> None:
    if total > limits.max_archive_total_bytes:
        raise UnsafeArchiveError(
            f"Archive total uncompressed size {total} exceeds cap "
            f"{limits.max_archive_total_bytes}"
        )


def _extract_tar(archive_path: Path, extract_dir: Path, limits: ResourceLimits) -> None:
    with tarfile.open(archive_path) as tf:
        members = tf.getmembers()
        _check_member_count(len(members), limits)
        total = 0
        for member in members:
            _validate_archive_name(member.name, extract_dir)
            if member.issym() or member.islnk():
                raise UnsafeArchiveError(f"Unsafe archive member link: {member.name}")
            size = max(0, int(getattr(member, "size", 0) or 0))
            _check_file_size(member.name, size, limits)
            total += size
            _check_total_size(total, limits)
        tf.extractall(extract_dir, filter="data")


def _extract_zip(archive_path: Path, extract_dir: Path, limits: ResourceLimits) -> None:
    with zipfile.ZipFile(archive_path) as zf:
        infos = zf.infolist()
        _check_member_count(len(infos), limits)
        total = 0
        for info in infos:
            _validate_archive_name(info.filename, extract_dir)
            if _zip_is_symlink(info):
                raise UnsafeArchiveError(
                    f"Unsafe archive member symlink: {info.filename}"
                )

            size = max(0, int(getattr(info, "file_size", 0) or 0))
            _check_file_size(info.filename, size, limits)
            total += size
            _check_total_size(total, limits)
        zf.extractall(extract_dir)


def _extract_gz(archive_path: Path, extract_dir: Path, limits: ResourceLimits) -> None:

    target = extract_dir / archive_path.with_suffix("").name
    if target.suffix.lower() != ".tex":
        target = target.with_suffix(".tex")
    cap = min(limits.max_archive_total_bytes, limits.max_single_file_bytes)
    chunk_size = 64 * 1024
    written = 0
    try:
        with gzip.open(archive_path, "rb") as src, target.open("wb") as dst:
            while True:
                chunk = src.read(chunk_size)
                if not chunk:
                    break
                written += len(chunk)
                if written > cap:
                    raise UnsafeArchiveError(f"gzip stream exceeds cap {cap} bytes")
                dst.write(chunk)
    except UnsafeArchiveError:
        try:
            target.unlink()
        except FileNotFoundError:
            pass
        raise


_ArchiveExtractor = Callable[[Path, Path, ResourceLimits], None]

_ARCHIVE_EXTRACTORS: tuple[tuple[tuple[str, ...], _ArchiveExtractor], ...] = (
    ((".tar", ".tar.gz", ".tgz"), _extract_tar),
    ((".zip",), _extract_zip),
    ((".gz",), _extract_gz),
)


def _extract_archive(
    archive_path: Path,
    extract_dir: Path,
    *,
    limits: ResourceLimits,
) -> None:
    lower = archive_path.name.lower()
    for suffixes, extractor in _ARCHIVE_EXTRACTORS:
        if lower.endswith(suffixes):
            extractor(archive_path, extract_dir, limits)
            return
    raise UnsupportedArchiveError(f"Unsupported TeX source archive: {archive_path}")


def _validate_archive_name(name: str, extract_dir: Path) -> None:
    member_path = Path(name)
    if member_path.is_absolute() or ".." in member_path.parts:
        raise UnsafeArchiveError(f"Unsafe archive path: {name}")
    resolved = (extract_dir / member_path).resolve()
    root = extract_dir.resolve()
    if resolved != root and root not in resolved.parents:
        raise UnsafeArchiveError(f"Archive path escapes destination: {name}")


def _zip_is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = info.external_attr >> 16
    return (mode & 0o170000) == 0o120000
