"""TeX conversion API surface re-exported by `arxiv_md`.

Prefer imports from `arxiv_md` unless depending on TeX-specific namespace.
"""

from arxiv_md.tex._common import (
    BibEntry,
    ConversionStats,
    ConvertOptions,
    ConvertResult,
    ResourceLimits,
    SourceSpan,
    TexDocument,
    TexWarning,
    WrittenResult,
)
from arxiv_md.tex.convert import convert_path, convert_text, write_result
from arxiv_md.tex.errors import (
    NoMainTexError,
    NoParseableBodyError,
    OutputWriteError,
    SourceReadError,
    StrictConversionError,
    TexConvertError,
    UnsafeArchiveError,
    UnsafeOutputDirError,
    UnsupportedArchiveError,
)

__all__ = [
    "BibEntry",
    "ConversionStats",
    "ConvertOptions",
    "ConvertResult",
    "NoMainTexError",
    "NoParseableBodyError",
    "OutputWriteError",
    "ResourceLimits",
    "SourceReadError",
    "SourceSpan",
    "StrictConversionError",
    "TexConvertError",
    "TexDocument",
    "TexWarning",
    "UnsafeArchiveError",
    "UnsafeOutputDirError",
    "UnsupportedArchiveError",
    "WrittenResult",
    "convert_path",
    "convert_text",
    "write_result",
]
