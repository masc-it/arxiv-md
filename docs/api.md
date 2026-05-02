# Python API

Import public conversion APIs and IR classes from `arxiv_md`.

## Quick example

```python
from pathlib import Path

from arxiv_md import ConvertOptions, convert_path, write_result

result = convert_path(Path("paper.tex"), ConvertOptions(render_assets=False))
print(result.markdown)
write_result(result, "out/paper")
```

## Conversion entry points

| Function | Use |
| --- | --- |
| `convert_path(path, options=None)` | Convert a `.tex` file, source directory, or source bundle. |
| `convert_text(source, options=None)` | Convert TeX already loaded in memory. |
| `write_result(result, output_dir)` | Materialize an in-memory result as `document.md`, `conversion.json`, and assets. |

When `ConvertOptions.output_dir` is set, `convert_path` writes files eagerly.
When it is `None`, conversion runs in memory and `result.written` stays `None`.

## Options

```python
from pathlib import Path

from arxiv_md import ConvertOptions, convert_path

result = convert_path(
    Path("paper.tar.gz"),
    ConvertOptions(
        output_dir=Path("out/paper"),
        document_slug="paper",
        keep_source=False,
        render_assets=True,
        asset_mode="rasterize",  # "rasterize" | "copy" | "skip"
        raster_dpi=120,
        strict=False,
    ),
)
```

| Option | Meaning |
| --- | --- |
| `output_dir` | Optional exact output directory. If unset, convert in memory. |
| `document_slug` | Override internal document slug. Output filenames stay fixed. |
| `keep_source` | Keep copied/extracted source tree under output directory. |
| `render_assets` | Enable/disable figure asset output. CLI equivalent: `--no-assets` when false. |
| `asset_mode` | `"rasterize"`, `"copy"`, or `"skip"`. Rasterize uses optional pypdfium2/Pillow and writes PNGs; copy avoids optional deps by preserving PDF/JPEG; skip resolves/counts only. |
| `raster_dpi` | PDF→PNG rasterization DPI used only by `asset_mode="rasterize"`. |
| `strict` | Raise failure when warnings are emitted. |
| `limits` | Optional `ResourceLimits` for archive/source/macro/asset caps. |

## Result shape

`convert_path` and `convert_text` return `ConvertResult`.

| Field | Meaning |
| --- | --- |
| `markdown` | Rendered Markdown string. |
| `document` | Typed `TexDocument` IR. |
| `warnings` | List of typed non-fatal diagnostics. |
| `stats` | Counts and conversion statistics, including unknown commands/envs. |
| `written` | Output paths when files were written; otherwise `None`. |

Example warning handling:

```python
for warning in result.warnings:
    print(warning.code, warning.message)
```

Diagnostics schema: [`diagnostics.md`](diagnostics.md).

Asset extras are optional. Install `arxiv-md[assets]` for pypdfium2-backed PDF rasterization and Pillow-backed JPEG normalization. Core API usage works without optional asset deps when `render_assets=False`, `asset_mode="copy"`, or `asset_mode="skip"`.

## Document IR

`ConvertResult.document` is a `TexDocument`. Block and inline classes are part
of the public API and exported from `arxiv_md`.

```python
from arxiv_md import Figure, Heading, Paragraph, TexDocument

for block in result.document.blocks:
    if isinstance(block, Heading):
        print("#" * block.level, block.children)
    elif isinstance(block, Figure):
        print("figure", block.images, block.label)
    elif isinstance(block, Paragraph):
        print(block.children)
```

Common block classes include `Paragraph`, `Heading`, `Figure`, `Table`,
`MathBlock`, `ListBlock`, `QuoteBlock`, `CodeBlock`, and `RawLatex`.

Inline content is represented as typed nodes such as `TextSpan`, `StrongSpan`,
`EmphasisSpan`, `CodeSpan`, `LinkSpan`, `ReferenceSpan`, `CitationSpan`,
`MathSpan`, `SuperscriptSpan`, `SubscriptSpan`, and `RawLatexSpan`.

## Schema contract

The IR exported from `arxiv_md` is the public document schema.

Consumer rules:

- Discriminate by class (`isinstance(block, Heading)`), not by private strings
  or dict fields.
- Inline fields (`Paragraph.children`, `Heading.children`, `Figure.caption`,
  `Table.caption`) contain inline IR, not pre-rendered Markdown.
- `Heading.level` is clamped to Markdown levels `1..6`.
- `Figure.images` are relative Markdown paths such as `images/figure-001.png`.
- Raw/unsupported figures and tables preserve raw LaTeX where possible.
- `ListBlock.items` preserves nested blocks; it is not a flattened list.
- Schema evolution is additive in minor releases. Field removals, renames, or
  meaning changes require a major version bump.
- `conversion.json` summaries follow the same additive-or-version-bump rule.
