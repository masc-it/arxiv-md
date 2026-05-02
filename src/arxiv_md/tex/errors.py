from __future__ import annotations

from typing import Any

from arxiv_md.tex._common import SourceSpan, TexWarning, warnings_json


class TexConvertError(Exception):
    """Base for converter failures with stable JSON `code`.

    `str(exc)` is human text only; use `to_json()` or `code` for programmatic
    handling instead of parsing messages.
    """

    code: str = "convert_error"

    def __init__(self, message: str, *, span: SourceSpan | None = None) -> None:
        super().__init__(message)
        self._message = message
        self.span = span

    def __str__(self) -> str:
        return self._message

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": str(self)}
        if self.span is not None:
            payload["span"] = self.span.to_json()
        return payload


class UnsafeArchiveError(TexConvertError):
    """Archive member failed path/symlink safety checks before extraction."""

    code = "unsafe_archive"


class UnsupportedArchiveError(TexConvertError):
    """Input archive format cannot be unpacked as an arXiv TeX source bundle."""

    code = "unsupported_archive"


class UnsafeOutputDirError(TexConvertError):
    """Requested output directory would overwrite or nest inside source input."""

    code = "unsafe_output_dir"


class SourceReadError(TexConvertError):
    """Source file could not be decoded or read within configured limits."""

    code = "unreadable_source"


class NoMainTexError(TexConvertError):
    """No high-confidence TeX entrypoint was found in the source tree."""

    code = "no_main_tex"


class NoParseableBodyError(TexConvertError):
    """Conversion completed but produced no meaningful Markdown body."""

    code = "no_parseable_body"


class OutputWriteError(TexConvertError):
    """Markdown, sidecar, or asset output could not be written."""

    code = "output_write_failed"


class ResourceLimitError(TexConvertError):
    """Configured `ResourceLimits` cap stopped conversion before more work."""

    code = "resource_limit"

    def __init__(
        self,
        message: str,
        *,
        limit: str,
        observed: int | None = None,
        cap: int | None = None,
        span: SourceSpan | None = None,
    ) -> None:
        super().__init__(message, span=span)
        self.limit = limit
        self.observed = observed
        self.cap = cap

    def to_json(self) -> dict[str, Any]:
        payload = super().to_json()
        payload["limit"] = self.limit
        if self.observed is not None:
            payload["observed"] = self.observed
        if self.cap is not None:
            payload["cap"] = self.cap
        return payload


class StrictConversionError(TexConvertError):
    """Strict mode failure carrying every warning that made output non-clean."""

    code = "strict_conversion_failed"

    def __init__(
        self,
        message: str,
        *,
        warnings: list[TexWarning] | None = None,
        span: SourceSpan | None = None,
    ) -> None:
        super().__init__(message, span=span)
        self.warnings: list[TexWarning] = list(warnings or [])

    def to_json(self) -> dict[str, Any]:
        payload = super().to_json()
        payload["warnings"] = warnings_json(self.warnings)
        return payload


__all__ = [
    "TexConvertError",
    "UnsafeArchiveError",
    "UnsupportedArchiveError",
    "UnsafeOutputDirError",
    "SourceReadError",
    "NoMainTexError",
    "NoParseableBodyError",
    "OutputWriteError",
    "ResourceLimitError",
    "StrictConversionError",
]
