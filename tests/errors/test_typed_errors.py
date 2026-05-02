from __future__ import annotations

from pathlib import Path

import pytest

from arxiv_md import (
    ConvertOptions,
    NoMainTexError,
    StrictConversionError,
    UnsafeOutputDirError,
    convert_path,
    convert_text,
)


def _wrap(body: str) -> str:
    return r"\begin{document}" + body + r"\end{document}"


def test_no_main_tex_in_empty_dir(tmp_path: Path) -> None:
    with pytest.raises(NoMainTexError) as exc:
        convert_path(tmp_path)
    assert exc.value.code == "no_main_tex"
    assert exc.value.to_json()["code"] == "no_main_tex"


def test_unsafe_output_dir_inside_source(simple_paper: Path) -> None:
    nested = simple_paper / "out"
    opts = ConvertOptions(output_dir=nested)
    with pytest.raises(UnsafeOutputDirError) as exc:
        convert_path(simple_paper, opts)
    assert exc.value.code == "unsafe_output_dir"


def test_strict_mode_raises_on_warning() -> None:
    with pytest.raises(StrictConversionError) as exc:
        convert_text(
            _wrap(r"\begin{mystery}X\end{mystery}"), ConvertOptions(strict=True)
        )
    payload = exc.value.to_json()
    assert payload["code"] == "strict_conversion_failed"
