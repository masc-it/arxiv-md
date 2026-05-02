from __future__ import annotations

import builtins
import json
import struct
import sys
from pathlib import Path

import pytest

from arxiv_md import ConvertOptions, ConvertResult, Figure, convert_path


def _write_tex_with_jpeg(root: Path, *, image_name: str = "plot.jpg") -> Path:
    return _write_tex_with_asset(root, image_name=image_name)


def _write_tex_with_asset(root: Path, *, image_name: str) -> Path:
    return _write_tex_with_assets(root, image_names=[image_name])


def _write_tex_with_assets(root: Path, *, image_names: list[str]) -> Path:
    body = "\n".join(f"\\includegraphics{{{name}}}" for name in image_names)
    (root / "main.tex").write_text(
        f"\\begin{{document}}\nText before.\n{body}\n\\end{{document}}\n",
        encoding="utf-8",
    )
    return root / "main.tex"


def _minimal_pdf(width: int = 72, height: int = 36) -> bytes:
    content = f"0.9 0.1 0.1 rg 0 0 {width} {height} re f\n".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] "
            "/Resources << >> /Contents 4 0 R >>"
        ).encode("ascii"),
        (
            b"<< /Length "
            + str(len(content)).encode("ascii")
            + b" >>\nstream\n"
            + content
            + b"endstream"
        ),
    ]
    data = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(data))
        data.extend(f"{number} 0 obj\n".encode("ascii"))
        data.extend(obj)
        data.extend(b"\nendobj\n")
    xref_offset = len(data)
    data.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    data.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    data.extend(
        (
            f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(data)


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    return struct.unpack(">II", data[16:24])


def _figure_image_paths(result: ConvertResult) -> list[str]:
    paths: list[str] = []
    for block in result.document.blocks:
        if isinstance(block, Figure):
            paths.extend(block.images)
    return paths


def test_rasterize_pdf_writes_png_with_dpi_scaling(tmp_path: Path) -> None:
    pytest.importorskip("pypdfium2")
    source = tmp_path / "src"
    out = tmp_path / "out"
    source.mkdir()
    _write_tex_with_asset(source, image_name="plot.pdf")
    (source / "plot.pdf").write_bytes(_minimal_pdf())

    result = convert_path(
        source,
        ConvertOptions(output_dir=out, asset_mode="rasterize", raster_dpi=144),
    )

    png = out / "images" / "figure-001.png"
    assert png.exists()
    assert _png_size(png) == (144, 72)
    assert "images/figure-001.png" in result.markdown
    assert result.stats.figures_total == 1
    assert result.stats.figures_resolved == 1
    assert not result.warnings


def test_rasterize_pdf_reports_missing_pdfium(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from arxiv_md.tex import assets as assets_mod

    source = tmp_path / "src"
    out = tmp_path / "out"
    source.mkdir()
    _write_tex_with_asset(source, image_name="plot.pdf")
    (source / "plot.pdf").write_bytes(b"%PDF-1.4\n")

    def missing_pdfium():  # type: ignore[no-untyped-def]
        raise assets_mod._PDFiumMissing("missing pypdfium2")

    monkeypatch.setattr(assets_mod, "_require_pdfium", missing_pdfium)

    result = convert_path(
        source, ConvertOptions(output_dir=out, asset_mode="rasterize")
    )

    assert not (out / "images" / "figure-001.png").exists()
    assert [(w.code, w.message) for w in result.warnings] == [
        (
            "pdfium_missing",
            "pypdfium2 is required to rasterize PDF figures and is not installed. "
            "Install with `pip install arxiv-md[assets]` or `pip install pypdfium2`. "
            "PDF figures are skipped for the rest of this conversion.",
        )
    ]


def test_rasterize_jpeg_writes_valid_png(tmp_path: Path) -> None:
    Image = pytest.importorskip("PIL.Image")
    source = tmp_path / "src"
    out = tmp_path / "out"
    source.mkdir()
    _write_tex_with_jpeg(source)
    Image.new("RGB", (1, 1), (255, 0, 0)).save(source / "plot.jpg", format="JPEG")

    result = convert_path(
        source,
        ConvertOptions(output_dir=out, asset_mode="rasterize"),
    )

    png = out / "images" / "figure-001.png"
    assert png.exists()
    assert png.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    with Image.open(png) as img:
        assert img.format == "PNG"
        assert img.size == (1, 1)
    assert "images/figure-001.png" in result.markdown
    assert not (out / "images" / "figure-001.jpg").exists()


def test_rasterize_assets_write_manifest_and_relative_image_paths(
    tmp_path: Path,
) -> None:
    Image = pytest.importorskip("PIL.Image")
    pytest.importorskip("pypdfium2")
    source = tmp_path / "src"
    out = tmp_path / "out"
    source.mkdir()
    _write_tex_with_assets(source, image_names=["plot.pdf", "photo.jpg"])
    (source / "plot.pdf").write_bytes(_minimal_pdf())
    Image.new("RGB", (2, 1), (0, 255, 0)).save(source / "photo.jpg", format="JPEG")

    result = convert_path(
        source,
        ConvertOptions(output_dir=out, asset_mode="rasterize", raster_dpi=72),
    )

    assert result.written is not None
    assert result.written.markdown_path == out.resolve() / "document.md"
    assert result.written.sidecar_path == out.resolve() / "conversion.json"
    assert result.written.markdown_path.read_text(encoding="utf-8") == result.markdown
    sidecar = json.loads(result.written.sidecar_path.read_text(encoding="utf-8"))
    assert sidecar["config"]["asset_mode"] == "rasterize"
    assert sidecar["config"]["raster_dpi"] == 72
    assert sidecar["stats"]["figures_total"] == 2
    assert sidecar["stats"]["figures_resolved"] == 2
    assert sidecar["warnings"] == []
    assert _figure_image_paths(result) == [
        "images/figure-001.png",
        "images/figure-002.png",
    ]
    assert "images/figure-001.png" in result.markdown
    assert "images/figure-002.png" in result.markdown
    assert (out / "images" / "figure-001.png").is_file()
    assert (out / "images" / "figure-002.png").is_file()
    assert not (out / "images" / "figure-001.pdf").exists()
    assert not (out / "images" / "figure-002.jpg").exists()


def test_rasterize_jpeg_reports_missing_pillow_and_falls_back_to_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "src"
    out = tmp_path / "out"
    source.mkdir()
    _write_tex_with_jpeg(source)
    (source / "plot.jpg").write_bytes(b"jpeg bytes copied without decoding")
    monkeypatch.setitem(sys.modules, "PIL", None)

    result = convert_path(
        source,
        ConvertOptions(output_dir=out, asset_mode="rasterize"),
    )

    assert (out / "images" / "figure-001.jpg").read_bytes() == (
        b"jpeg bytes copied without decoding"
    )
    assert "images/figure-001.jpg" in result.markdown
    assert [(w.code, w.message) for w in result.warnings] == [
        (
            "pillow_missing",
            "Pillow (`PIL`) is required to normalize JPEG figures to PNG "
            "and is not installed. Install with `pip install arxiv-md[assets]` "
            "or `pip install pillow`. Falling back to raw copy for the rest "
            "of this conversion.",
        )
    ]


@pytest.mark.parametrize("asset_mode", ["copy", "skip"])
@pytest.mark.parametrize(
    ("asset_name", "payload"),
    [
        ("plot.pdf", b"%PDF-1.4\nraw pdf payload"),
        ("plot.jpg", b"raw jpeg payload"),
    ],
)
def test_copy_and_skip_modes_do_not_import_raster_backends(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    asset_mode: str,
    asset_name: str,
    payload: bytes,
) -> None:
    source = tmp_path / "src"
    out = tmp_path / "out"
    source.mkdir()
    _write_tex_with_asset(source, image_name=asset_name)
    (source / asset_name).write_bytes(payload)

    real_import = builtins.__import__

    def guard_import(  # type: ignore[no-untyped-def]
        name, globals=None, locals=None, fromlist=(), level=0
    ):
        if name == "pypdfium2" or name.startswith("pypdfium2."):
            raise AssertionError(f"unexpected pypdfium2 import in {asset_mode} mode")
        if name == "PIL" or name.startswith("PIL."):
            raise AssertionError(f"unexpected Pillow import in {asset_mode} mode")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guard_import)

    result = convert_path(source, ConvertOptions(output_dir=out, asset_mode=asset_mode))

    expected_rel = f"images/figure-001{Path(asset_name).suffix}"
    assert _figure_image_paths(result) == [expected_rel]
    assert expected_rel in result.markdown
    if asset_mode == "copy":
        copied = out / "images" / f"figure-001{Path(asset_name).suffix}"
        assert copied.read_bytes() == payload
    else:
        assert not (out / "images").exists()
