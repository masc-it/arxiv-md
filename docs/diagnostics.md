# Diagnostics and JSON

Conversion problems are typed. Non-fatal problems become warnings; fatal
problems abort conversion with stable error codes.

## Library diagnostics

`ConvertResult.warnings` contains `TexWarning` records. Each warning has:

| Field | Meaning |
| --- | --- |
| `code` | Stable machine-readable identifier. New codes are additive. |
| `message` | Human-readable detail. Do not parse it. |
| `path` | Optional source path when no precise offset exists. |
| `span` | Optional precise source location. See [source spans](#source-spans). |

Warnings never abort conversion unless `ConvertOptions(strict=True)` is used.
Strict mode fails with `strict_conversion_failed` and includes the original
warnings in the error payload.

## JSON envelopes

`--json` emits one pretty-printed JSON document per invocation.

### `tex-to-md` success

```json
{
  "ok": true,
  "converted": [
    {
      "source": "paper-src",
      "markdown": "out/paper/document.md",
      "sidecar": "out/paper/conversion.json",
      "warnings": 0
    }
  ],
  "failed": []
}
```

### `arxiv-to-md` success

```json
{
  "ok": true,
  "downloaded": [
    {"arxiv_id": "2401.00001", "path": "out/.archives/2401.00001-source.tar.gz"}
  ],
  "converted": [
    {
      "arxiv_id": "2401.00001",
      "source": "out/.archives/2401.00001-source.tar.gz",
      "markdown": "out/2401.00001/document.md",
      "sidecar": "out/2401.00001/conversion.json"
    }
  ],
  "failed": []
}
```

### Error envelope

```json
{
  "ok": false,
  "error": {
    "code": "unsafe_output_dir",
    "message": "Output directory must not be inside source tree: ..."
  }
}
```

Error envelopes may include additional structured fields next to `code` and
`message`, such as `span`, `warnings`, `limit`, `observed`, or `cap`.

## Warning shape

Span-bearing warning:

```json
{
  "code": "parse_recovery",
  "message": "Unterminated \\verb",
  "span": {
    "file": "main.tex",
    "start_offset": 142,
    "end_offset": 142,
    "line": 7,
    "column": 13
  }
}
```

File-level warning:

```json
{
  "code": "bib_parse_partial",
  "message": "Could not read bibliography: refs.bib",
  "path": "refs.bib"
}
```

## Warning codes

| Code | Emitted when |
| --- | --- |
| `missing_include` | `\input` / `\include` target cannot be located, or include cycle skipped. |
| `unknown_command` | Reserved for unrecognized LaTeX commands; per-command counts surface in stats. |
| `unknown_env` | Unknown environment preserved as raw LaTeX. |
| `unknown_macro` | Macro engine could not resolve a macro reference. |
| `parse_recovery` | Parser recovered from malformed input, such as unterminated `\verb`. |
| `figure_missing` | `\includegraphics` asset could not be resolved. |
| `figure_ambiguous` | Multiple candidate assets matched one `\includegraphics` reference. |
| `unsupported_asset` | Asset format cannot be inlined or rendered. |
| `table_raw_fallback` | Table could not be lowered to structured output or HTML. |
| `macro_expansion_skipped` | Macro/environment definition was rejected or skipped. |
| `bib_parse_partial` | Bibliography file could not be fully read or parsed. |
| `asset_scan_capped` | Asset directory walk hit `ResourceLimits.max_asset_scan_files`. |
| `pdfium_missing` | PDF rasterization requested but optional pypdfium2 backend is missing. |
| `pillow_missing` | JPEG normalization requested but optional Pillow backend is missing. |
| `resource_limit` | Non-fatal resource cap was hit and output degraded. |

## Fatal error codes

Fatal failures surface as typed `TexConvertError` subclasses in the library and
as `error.code` in CLI JSON.

| Code | Exception class | Raised when |
| --- | --- | --- |
| `unsafe_archive` | `UnsafeArchiveError` | Archive has unsafe paths, links, or cap violations. |
| `unsupported_archive` | `UnsupportedArchiveError` | Source bundle is not a recognized TeX archive. |
| `unsafe_output_dir` | `UnsafeOutputDirError` | Output directory resolves into source tree. |
| `unreadable_source` | `SourceReadError` | Source path or `.tex` file cannot be read. |
| `no_main_tex` | `NoMainTexError` | No main `.tex` entry point can be found. |
| `no_parseable_body` | `NoParseableBodyError` | Conversion produced no parseable body content. |
| `output_write_failed` | `OutputWriteError` | Markdown, sidecar, or asset write failed. |
| `resource_limit` | `ResourceLimitError` | Fatal resource cap exceeded. |
| `strict_conversion_failed` | `StrictConversionError` | Strict mode saw one or more warnings. |
| `internal_error` | No dedicated class | Unexpected exception escaped CLI catch-all. |

Payload extensions:

- `strict_conversion_failed` includes `warnings` with original warning records.
- `resource_limit` includes `limit` and may include `observed` / `cap`.
- Fatal errors with known source locations include `span`.

## Source spans

`SourceSpan` maps parser offsets back to original source files after include
expansion.

```python
from dataclasses import dataclass
from pathlib import Path

@dataclass(slots=True)
class SourceSpan:
    file: Path
    start_offset: int
    end_offset: int
    line: int
    column: int
```

JSON shape:

```json
{"file": "main.tex", "start_offset": 142, "end_offset": 142, "line": 7, "column": 13}
```

Spans are best-effort. File-level diagnostics that have no offset anchor use
`path` only.

## CLI exit codes

| Code | Meaning |
| --- | --- |
| `0` | Success. |
| `1` | Conversion failure. |
| `2` | Argparse usage error. |
