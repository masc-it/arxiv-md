from __future__ import annotations

import re
import shutil
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from arxiv_md.tex._common import (
    DEFAULT_RASTER_DPI,
    ConversionStats,
    ResourceLimits,
    TexDocument,
    TexWarning,
    warning,
)
from arxiv_md.tex.model import Figure

COMMON_EXTS = [".pdf", ".png", ".jpg", ".jpeg", ".svg", ".eps"]
SUPPORTED_COPY = {".png", ".svg"}
JPEG_EXTS = {".jpg", ".jpeg"}
AssetAction = Literal["copy", "rasterize_pdf", "rasterize_image", "skip"]


def collect_graphicspaths(source_text: str) -> list[str]:
    paths: list[str] = []
    for m in re.finditer(r"\\graphicspath\s*\{", source_text):
        start = m.end()
        depth = 1
        i = start
        while i < len(source_text) and depth > 0:
            ch = source_text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            i += 1
        if depth == 0:
            body = source_text[start : i - 1]
            paths.extend(
                item.strip()
                for item in re.findall(r"\{([^{}]+)\}", body)
                if item.strip()
            )
    return paths


class _PDFiumMissing(RuntimeError):
    pass


class _PillowMissing(RuntimeError):
    pass


def _is_cached(source: Path, target: Path) -> bool:
    try:
        return target.exists() and target.stat().st_mtime >= source.stat().st_mtime
    except OSError:
        return False


@dataclass(frozen=True, slots=True)
class AssetRequest:
    figure_index: int
    graphic_index: int
    graphic: str


@dataclass(frozen=True, slots=True)
class AssetPlan:
    request: AssetRequest
    source: Path
    target: Path
    rel_output: str
    action: AssetAction
    figure_number: int


@dataclass(slots=True)
class AssetPlanningResult:
    plans: list[AssetPlan] = field(default_factory=list)
    warnings: list[TexWarning] = field(default_factory=list)
    figures_total: int = 0


@dataclass(slots=True)
class MaterializationResult:
    outputs: dict[tuple[int, int], str] = field(default_factory=dict)
    warnings: list[TexWarning] = field(default_factory=list)
    figures_resolved: int = 0


class FigureAssetResolver:
    @classmethod
    def plan(
        cls,
        document: TexDocument,
        *,
        source_text: str,
        output_dir: Path,
        limits: ResourceLimits,
        asset_mode: str = "rasterize",
    ) -> AssetPlanningResult:
        images_dir = output_dir / "images"
        result = AssetPlanningResult()

        figures = [b for b in document.blocks if isinstance(b, Figure)]
        if not figures:
            return result

        prefixes = collect_graphicspaths(source_text)
        root_resolved = document.root_dir.resolve()
        bases = [document.root_dir] + [document.root_dir / p for p in prefixes]

        exact: dict[tuple[int, int], Path] = {}
        need_index = False
        for fi, fig in enumerate(figures):
            for gi, graphic in enumerate(fig.graphics):
                hit = _resolve_graphic_exact(graphic, bases, root_resolved)
                if hit is not None:
                    exact[(fi, gi)] = hit
                else:
                    need_index = True

        index: dict[str, list[Path]] = {}
        if need_index:
            index = _asset_index(
                document.root_dir, limits=limits, warnings=result.warnings
            )

        figure_no = 0
        is_skip = asset_mode == "skip"
        is_copy = asset_mode == "copy"

        for fi, block in enumerate(figures):
            raw_graphics = list(block.graphics)
            result.figures_total += len(raw_graphics)
            for gi, graphic in enumerate(raw_graphics):
                resolved = exact.get((fi, gi))
                if resolved is None and need_index:
                    resolved = _resolve_graphic_index(graphic, index, result.warnings)
                if resolved is None:
                    result.warnings.append(
                        warning(
                            "figure_missing",
                            f"Missing figure asset: {graphic}",
                        )
                    )
                    continue

                suffix = resolved.suffix.lower()
                if suffix == ".eps":
                    result.warnings.append(
                        warning(
                            "unsupported_asset",
                            f"EPS figure not converted: {resolved}",
                            resolved,
                        )
                    )
                    continue

                figure_no += 1
                action, target = cls._decide_action(
                    suffix,
                    resolved,
                    images_dir,
                    figure_no,
                    is_skip=is_skip,
                    is_copy=is_copy,
                    limits=limits,
                    warnings=result.warnings,
                )
                if action is None:
                    continue

                result.plans.append(
                    AssetPlan(
                        request=AssetRequest(
                            figure_index=fi,
                            graphic_index=gi,
                            graphic=graphic,
                        ),
                        source=resolved,
                        target=target,
                        rel_output=f"images/{target.name}",
                        action=action,
                        figure_number=figure_no,
                    )
                )
        return result

    @staticmethod
    def _decide_action(
        suffix: str,
        resolved: Path,
        images_dir: Path,
        figure_no: int,
        *,
        is_skip: bool,
        is_copy: bool,
        limits: ResourceLimits,
        warnings: list[TexWarning],
    ) -> tuple[AssetAction | None, Path]:
        base_target = _target_path(images_dir, figure_no, suffix)

        if is_skip:
            return "skip", base_target

        if suffix == ".pdf":
            if is_copy:
                return "copy", _target_path(images_dir, figure_no, suffix)

            try:
                size = resolved.stat().st_size
            except OSError:
                size = 0
            if size > limits.max_single_file_bytes:
                warnings.append(
                    warning(
                        "unsupported_asset",
                        f"PDF figure too large to rasterize "
                        f"({size} bytes > max_single_file_bytes="
                        f"{limits.max_single_file_bytes}): {resolved}",
                        resolved,
                    )
                )
                return None, base_target
            if limits.max_pdf_pages_rasterized < 1:
                warnings.append(
                    warning(
                        "unsupported_asset",
                        f"PDF rasterization disabled "
                        f"(max_pdf_pages_rasterized="
                        f"{limits.max_pdf_pages_rasterized}): {resolved}",
                        resolved,
                    )
                )
                return None, base_target
            return "rasterize_pdf", base_target.with_suffix(".png")

        if suffix in JPEG_EXTS:
            if is_copy:
                return "copy", _target_path(images_dir, figure_no, suffix)
            return "rasterize_image", base_target.with_suffix(".png")

        if suffix in SUPPORTED_COPY:
            return "copy", base_target

        warnings.append(
            warning(
                "unsupported_asset",
                f"Unsupported figure asset: {resolved}",
                resolved,
            )
        )
        return None, base_target


class AssetMaterializer:
    def __init__(
        self,
        images_dir: Path,
        *,
        limits: ResourceLimits,
        raster_dpi: int = DEFAULT_RASTER_DPI,
    ) -> None:
        self._images_dir = images_dir
        self._limits = limits
        self._raster_dpi = raster_dpi
        self._dir_ready = False
        self._pdfium_unavailable = False
        self._pillow_unavailable = False

    def write(self, plans: list[AssetPlan]) -> MaterializationResult:
        result = MaterializationResult()
        for plan in plans:
            rel = self._materialize(plan, result.warnings)
            if rel is not None:
                key = (plan.request.figure_index, plan.request.graphic_index)
                result.outputs[key] = rel
                result.figures_resolved += 1
        return result

    def _ensure_dir(self) -> None:
        if not self._dir_ready:
            self._images_dir.mkdir(parents=True, exist_ok=True)
            self._dir_ready = True

    def _materialize(self, plan: AssetPlan, warnings: list[TexWarning]) -> str | None:
        if plan.action == "skip":
            return plan.rel_output
        if plan.action == "copy":
            return self._copy(plan, warnings)
        if plan.action == "rasterize_pdf":
            return self._do_rasterize_pdf(plan, warnings)
        if plan.action == "rasterize_image":
            return self._do_rasterize_image(plan, warnings)
        return None  # pragma: no cover

    def _copy(self, plan: AssetPlan, warnings: list[TexWarning]) -> str | None:
        if _is_cached(plan.source, plan.target):
            return plan.rel_output
        try:
            self._ensure_dir()
            shutil.copyfile(plan.source, plan.target)
        except Exception as exc:
            msg = (
                f"Could not copy PDF figure {plan.source}: {exc}"
                if plan.source.suffix.lower() == ".pdf"
                else f"Could not copy figure {plan.source}: {exc}"
            )
            warnings.append(warning("unsupported_asset", msg, plan.source))
            return None
        return f"images/{plan.target.name}"

    def _do_rasterize_pdf(
        self, plan: AssetPlan, warnings: list[TexWarning]
    ) -> str | None:
        if self._pdfium_unavailable:
            return None
        if _is_cached(plan.source, plan.target):
            return plan.rel_output
        try:
            self._ensure_dir()
            _rasterize_pdf(
                plan.source,
                plan.target,
                limits=self._limits,
                dpi=self._raster_dpi,
            )
        except _PDFiumMissing:
            self._pdfium_unavailable = True
            warnings.append(
                warning(
                    "pdfium_missing",
                    "pypdfium2 is required to rasterize PDF figures "
                    "and is not installed. Install with "
                    "`pip install arxiv-md[assets]` or "
                    "`pip install pypdfium2`. PDF figures are "
                    "skipped for the rest of this conversion.",
                    plan.source,
                )
            )
            return None
        except Exception as exc:
            warnings.append(
                warning(
                    "unsupported_asset",
                    f"Could not rasterize PDF figure {plan.source}: {exc}",
                    plan.source,
                )
            )
            return None
        return f"images/{plan.target.name}"

    def _do_rasterize_image(
        self, plan: AssetPlan, warnings: list[TexWarning]
    ) -> str | None:
        suffix = plan.source.suffix.lower()
        if self._pillow_unavailable:
            return self._jpeg_fallback_copy(plan, suffix, warnings)
        if _is_cached(plan.source, plan.target):
            return plan.rel_output
        try:
            self._ensure_dir()
            _rasterize_image(plan.source, plan.target, limits=self._limits)
        except _PillowMissing:
            self._pillow_unavailable = True
            warnings.append(
                warning(
                    "pillow_missing",
                    "Pillow (`PIL`) is required to normalize "
                    "JPEG figures to PNG and is not installed. Install "
                    "with `pip install arxiv-md[assets]` or "
                    "`pip install pillow`. Falling back to raw "
                    "copy for the rest of this conversion.",
                    plan.source,
                )
            )
            return self._jpeg_fallback_copy(plan, suffix, warnings)
        except Exception as exc:
            warnings.append(
                warning(
                    "unsupported_asset",
                    f"JPEG copied without PNG normalization: {plan.source}: {exc}",
                    plan.source,
                )
            )
            return self._jpeg_fallback_copy(plan, suffix, warnings)
        return f"images/{plan.target.name}"

    def _jpeg_fallback_copy(
        self,
        plan: AssetPlan,
        suffix: str,
        warnings: list[TexWarning],
    ) -> str | None:
        target = _target_path(self._images_dir, plan.figure_number, suffix)
        if _is_cached(plan.source, target):
            return f"images/{target.name}"
        try:
            self._ensure_dir()
            shutil.copyfile(plan.source, target)
        except Exception as exc:
            warnings.append(
                warning(
                    "unsupported_asset",
                    f"Could not copy figure {plan.source}: {exc}",
                    plan.source,
                )
            )
            return None
        return f"images/{target.name}"


def resolve_figure_assets(
    document: TexDocument,
    *,
    output_dir: Path,
    source_text: str,
    stats: ConversionStats,
    limits: ResourceLimits | None = None,
    asset_mode: str = "rasterize",
    raster_dpi: int = DEFAULT_RASTER_DPI,
) -> None:

    limits = limits or ResourceLimits()

    plan_result = FigureAssetResolver.plan(
        document,
        source_text=source_text,
        output_dir=output_dir,
        limits=limits,
        asset_mode=asset_mode,
    )
    document.warnings.extend(plan_result.warnings)
    stats.figures_total += plan_result.figures_total

    if not plan_result.plans:
        return

    images_dir = output_dir / "images"
    materializer = AssetMaterializer(images_dir, limits=limits, raster_dpi=raster_dpi)
    mat_result = materializer.write(plan_result.plans)
    document.warnings.extend(mat_result.warnings)
    stats.figures_resolved += mat_result.figures_resolved

    figures = [b for b in document.blocks if isinstance(b, Figure)]
    per_figure: dict[int, list[str]] = {}
    for (fi, _gi), rel in mat_result.outputs.items():
        per_figure.setdefault(fi, []).append(rel)
    for fi, block in enumerate(figures):
        rels = per_figure.get(fi)
        if rels:
            block.images = list(rels)


def _target_path(images_dir: Path, number: int, suffix: str) -> Path:
    suffix = suffix.lower()
    if suffix == ".jpeg":
        suffix = ".jpg"
    return images_dir / f"figure-{number:03d}{suffix}"


def _rasterize_pdf(
    source: Path,
    target: Path,
    *,
    limits: ResourceLimits,
    dpi: int = DEFAULT_RASTER_DPI,
) -> None:
    pdfium = _require_pdfium()
    doc = pdfium.PdfDocument(str(source))
    try:
        page_count = min(len(doc), max(1, limits.max_pdf_pages_rasterized))
        if page_count <= 0:
            return
        page = doc[0]
        try:
            scale = dpi / 72
            bitmap = page.render(
                scale=scale,
                rotation=0,
                rev_byteorder=True,
                fill_color=(255, 255, 255, 255),
            )
            try:
                _save_pdfium_bitmap_png(bitmap, target)
            finally:
                bitmap.close()
        finally:
            page.close()
    finally:
        doc.close()


def _rasterize_image(
    source: Path, target: Path, *, limits: ResourceLimits | None = None
) -> None:
    del limits
    Image = _require_pillow()
    with Image.open(source) as img:
        img.convert("RGB").save(target, format="PNG")


def _require_pdfium():
    try:
        import pypdfium2 as pdfium  # type: ignore[import-untyped]
    except ImportError as exc:
        raise _PDFiumMissing(
            "pypdfium2 is required to rasterize PDF assets; "
            "install with `arxiv-md[assets]`"
        ) from exc
    return pdfium


def _require_pillow():
    try:
        from PIL import Image  # type: ignore[import-untyped]
    except ImportError as exc:
        raise _PillowMissing(
            "Pillow is required to normalize JPEG assets; "
            "install with `arxiv-md[assets]`"
        ) from exc
    return Image


def _save_pdfium_bitmap_png(bitmap, target: Path) -> None:
    width = int(bitmap.width)
    height = int(bitmap.height)
    stride = int(bitmap.stride)
    mode = str(bitmap.mode)
    channels = int(bitmap.n_channels)
    raw = bytes(bitmap.buffer)
    rows = [_png_scanline(raw, y, width, stride, mode, channels) for y in range(height)]
    color_type = 0 if mode == "L" else 2
    _write_png(target, width, height, color_type, b"".join(rows))


def _png_scanline(
    raw: bytes,
    y: int,
    width: int,
    stride: int,
    mode: str,
    channels: int,
) -> bytes:
    start = y * stride
    row = raw[start : start + stride]
    if mode == "L":
        return b"\x00" + row[:width]
    if mode == "RGB":
        return b"\x00" + row[: width * 3]
    if mode == "BGR":
        return b"\x00" + _swap_rgb(row[: width * 3], 3)
    if mode in {"RGBx", "RGBA"}:
        return b"\x00" + _drop_alpha_or_padding(row, width, reverse=False)
    if mode in {"BGRx", "BGRA"}:
        return b"\x00" + _drop_alpha_or_padding(row, width, reverse=True)
    raise ValueError(f"Unsupported PDFium bitmap mode: {mode!r} ({channels} channels)")


def _drop_alpha_or_padding(row: bytes, width: int, *, reverse: bool) -> bytes:
    data = bytearray()
    for i in range(width):
        chunk = row[i * 4 : i * 4 + 3]
        data.extend(reversed(chunk) if reverse else chunk)
    return bytes(data)


def _swap_rgb(row: bytes, channels: int) -> bytes:
    data = bytearray()
    for i in range(0, len(row), channels):
        chunk = row[i : i + channels]
        data.extend((chunk[2], chunk[1], chunk[0]))
    return bytes(data)


def _write_png(
    target: Path,
    width: int,
    height: int,
    color_type: int,
    scanlines: bytes,
) -> None:
    header = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    payload = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(scanlines))
        + _png_chunk(b"IEND", b"")
    )
    target.write_bytes(payload)


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(kind + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)


def _asset_index(
    root_dir: Path,
    *,
    limits: ResourceLimits | None = None,
    warnings: list[TexWarning] | None = None,
) -> dict[str, list[Path]]:

    limits = limits or ResourceLimits()
    cap = limits.max_asset_files_scanned
    index: dict[str, list[Path]] = {}
    scanned = 0
    capped = False
    for path in root_dir.rglob("*"):
        if scanned >= cap:
            capped = True
            break
        scanned += 1
        if not path.is_file():
            continue
        if path.suffix.lower() not in COMMON_EXTS:
            continue
        index.setdefault(path.name.lower(), []).append(path)
        index.setdefault(path.stem.lower(), []).append(path)
    if capped and warnings is not None:
        warnings.append(
            warning(
                "asset_scan_capped",
                f"Asset scan stopped after {cap} entries "
                f"(max_asset_files_scanned={cap}); some figure references may "
                f"not resolve.",
            )
        )
    return index


def _resolve_graphic_exact(
    value: str,
    bases: list[Path],
    root_resolved: Path,
) -> Path | None:
    value = value.strip().strip("{}")
    path = Path(value)
    names = [path]
    if path.suffix == "":
        names.extend(Path(str(path) + ext) for ext in COMMON_EXTS)
    for base in bases:
        for name in names:
            candidate = (base / name).resolve()
            try:
                candidate.relative_to(root_resolved)
            except ValueError:
                continue
            if candidate.is_file():
                return candidate
    return None


def _resolve_graphic_index(
    value: str,
    index: dict[str, list[Path]],
    warnings: list[TexWarning],
) -> Path | None:
    value = value.strip().strip("{}")
    path = Path(value)
    matches = index.get(path.name.lower()) or index.get(path.stem.lower()) or []
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        warnings.append(warning("figure_ambiguous", f"Ambiguous figure asset: {value}"))
    return None


def _resolve_graphic(
    value: str,
    root_dir: Path,
    prefixes: list[str],
    index: dict[str, list[Path]],
    warnings: list[TexWarning],
) -> Path | None:
    bases = [root_dir, *[root_dir / p for p in prefixes]]
    root_resolved = root_dir.resolve()
    hit = _resolve_graphic_exact(value, bases, root_resolved)
    if hit is not None:
        return hit
    return _resolve_graphic_index(value, index, warnings)
