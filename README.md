# arxiv-md

Good enough™ LaTeX to Markdown converter. Optimized on hundreds of arXiv papers from 2016 to 2026.

`arxiv-md` is a Python package and CLI for turning arXiv e-print bundles,
source directories, or single `.tex` files into:

```text
- document.md       # rendered Markdown
- conversion.json   # warnings, stats, options, paths
- images/           # optional rendered/copied figures
```

Unsupported TeX is preserved as raw LaTeX when possible and reported through typed diagnostics.
Output locations are explicit: callers choose the exact output directory, and conversion never writes into the source tree.

## Install

```bash
# Core library and CLIs
uv add arxiv-md

# Add optional pypdfium2/Pillow-backed PDF/JPEG → PNG rendering
uv add 'arxiv-md[assets]'

# CLI-only install
uv tool install 'arxiv-md[assets]'
```

Supports Python 3.10–3.13. Core library has no required runtime dependencies.

## Quickstart

```bash
# Single .tex file
tex-to-md paper.tex --outdir out/paper

# Source archive (.tar, .tar.gz, .tgz, .zip, .gz)
tex-to-md paper.tar.gz --outdir out/paper --json

# Download arXiv source by id and convert
arxiv-to-md 1706.03762 --outdir out
```

`--outdir` is mandatory. `tex-to-md` writes one document directly into that
folder. `arxiv-to-md` writes one subdirectory per paper.

Common asset modes:

- Default `rasterize` — PDF→PNG via pypdfium2, JPEG→PNG via Pillow; best compatibility, highest CPU/native-code exposure.
- `--asset-mode copy` — copy PDF/JPEG verbatim; faster, no optional asset deps needed.
- `--asset-mode skip` — resolve/count figures but write no images.
- `--no-assets` — text-only conversion; no `images/` directory.

Asset rendering extra uses pypdfium2 + Pillow; core install has no required deps and no AGPL PyMuPDF runtime dependency.

Full CLI reference: [`docs/cli.md`](docs/cli.md).

## Python API

```python
from pathlib import Path

from arxiv_md import ConvertOptions, convert_path, write_result

result = convert_path(Path("paper.tex"), ConvertOptions(render_assets=False))
print(result.markdown)
write_result(result, "out/paper")
```

`convert_path` returns `ConvertResult` with rendered Markdown, typed document IR, warnings, stats, and output paths when files are written.

Full API reference: [`docs/api.md`](docs/api.md).

## At a glance

Inputs:

- `.tex` files.
- Source directories with a detectable main `.tex` file.
- `.tar`, `.tar.gz`, `.tgz`, `.zip`, and single-file `.gz` source bundles.
- arXiv IDs or search queries via `arxiv-to-md`.

Native handling covers common paper structure: sections, frontmatter, inline formatting, math, lists, figures, tables, bibliography, citations, cross-references, theorem-like environments, algorithm pseudocode, common glyphs, `siunitx`, and common macro definitions.

Unsupported inputs (`.pdf`, `.html`, `.rar`, `.7z`, lone `.bib`).

## When to use it

Use `arxiv-md` when you need semantic Markdown for search, indexing, previews, datasets, or downstream text processing.

Do not use it when exact PDF layout matters. `arxiv-md` is not a TeX engine: it does not run `pdflatex`, reproduce page layout, or guarantee full macro and environment expansion.

## Docs

- [`docs/README.md`](docs/README.md) — documentation index.
- [`docs/cli.md`](docs/cli.md) — CLI usage, flags, output layout.
- [`docs/api.md`](docs/api.md) — library options, result shape, document IR.
- [`docs/supported-latex.md`](docs/supported-latex.md) — inputs, non-goals, support matrix.
- [`docs/diagnostics.md`](docs/diagnostics.md) — warnings, fatal errors, JSON envelopes.
- [`docs/security.md`](docs/security.md) — archive hardening, isolation, resource limits.
- [`docs/performance.md`](docs/performance.md) — benchmarks and asset-mode tradeoffs.

## License

MIT. See [LICENSE](LICENSE).
