from __future__ import annotations

import gzip
import shutil
from io import BytesIO
from pathlib import Path
from urllib import error, request

from arxiv_md.download import USER_AGENT, base_arxiv_id, safe_filename


def source_url(arxiv_id: str) -> str:
    return f"https://arxiv.org/e-print/{base_arxiv_id(arxiv_id)}"


def download_source(arxiv_id: str, destination: Path) -> Path | None:
    destination = destination.expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    req = request.Request(source_url(arxiv_id), headers={"User-Agent": USER_AGENT})
    try:
        with request.urlopen(req, timeout=120) as resp:
            payload = resp.read()
    except error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise RuntimeError(f"Source download failed: HTTP {exc.code}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Source download failed: {exc.reason}") from exc

    suffix = detect_source_suffix(payload)
    if suffix is None:
        return None

    target = _target_path(arxiv_id, destination, suffix)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return target


def detect_source_suffix(payload: bytes) -> str | None:
    head = payload[:512]
    if head.startswith(b"%PDF"):
        return None
    if head.startswith(b"PK\x03\x04") or head.startswith(b"PK\x05\x06"):
        return ".zip"
    if _looks_like_tar(payload):
        return ".tar"
    if head.startswith(b"\x1f\x8b"):
        try:
            with gzip.GzipFile(fileobj=BytesIO(payload)) as gz:
                sample = gz.read(1024)
        except Exception:
            sample = b""
        if _looks_like_tar(sample):
            return ".tar.gz"
        return ".tex.gz"
    if b"\\documentclass" in head or b"\\begin{document}" in head:
        return ".tex"
    return None


def _target_path(arxiv_id: str, destination: Path, suffix: str) -> Path:
    if destination.exists() and destination.is_dir():
        return destination / f"{safe_filename(base_arxiv_id(arxiv_id))}{suffix}"
    if destination.suffix:
        stem = destination.name
        for old_suffix in (".tar.gz", ".tex.gz", ".tgz", ".tar", ".zip", ".gz", ".tex"):
            if stem.lower().endswith(old_suffix):
                stem = stem[: -len(old_suffix)]
                break
        return destination.with_name(stem + suffix)
    return destination.with_name(destination.name + suffix)


def _looks_like_tar(payload: bytes) -> bool:
    return len(payload) > 262 and payload[257:262] == b"ustar"


def copy_or_link_source(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    return destination
