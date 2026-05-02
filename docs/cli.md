# CLI reference

`arxiv-md` ships two user-facing CLIs:

- `tex-to-md` — convert local `.tex`, source directories, or source archives.
- `arxiv-to-md` — download arXiv source bundles, then run the same conversion pipeline.

Both require `--outdir` and never write into the source tree.

## Quick examples

```bash
# Convert a single .tex file
tex-to-md paper.tex --outdir out/paper

# Convert a source archive and print machine-readable result
tex-to-md paper.tar.gz --outdir out/paper --json

# Download one arXiv paper by id and convert it
arxiv-to-md 1706.03762 --outdir out
```

## Output layout

`tex-to-md` treats `--outdir` as the exact document output directory:

```text
out/paper/
  document.md
  conversion.json
  images/             # omitted with --no-assets
  source/             # only with --keep-source
```

`arxiv-to-md` treats `--outdir` as a batch parent directory:

```text
out/
  1706.03762/
    document.md
    conversion.json
    images/
  .archives/          # only with --keep-archive
```

## `tex-to-md`

Convert a local source into Markdown.

```text
tex-to-md SOURCE --outdir OUTDIR
                 [--document-slug SLUG]
                 [--keep-source]
                 [--no-assets]
                 [--asset-mode {rasterize,copy,skip}]
                 [--raster-dpi DPI]
                 [--strict]
                 [--json]
```

`SOURCE` may be a `.tex` file, source directory, `.tar`, `.tar.gz`, `.tgz`,
`.zip`, or single-file `.gz` bundle.

| Flag | Meaning |
| --- | --- |
| `--outdir OUTDIR` | Required exact output directory. Refuses paths inside source tree. |
| `--document-slug SLUG` | Override internal slug. Does not change output filenames. |
| `--keep-source` | Keep copied/extracted source at `OUTDIR/source/`. |
| `--no-assets` | Skip figure output; no `images/` directory. |
| `--asset-mode rasterize` | Default. Render PDF to PNG via pypdfium2 and JPEG to PNG via Pillow. Requires optional `arxiv-md[assets]` deps for full coverage; best Markdown compatibility, highest CPU/native-code cost. |
| `--asset-mode copy` | Copy PDF/JPEG verbatim. Faster, no optional asset deps needed. |
| `--asset-mode skip` | Resolve/count figures but write no image files. Fastest asset-aware dry run. |
| `--raster-dpi DPI` | PDF→PNG rasterization DPI. Default: `120`. |
| `--strict` | Fail when any warning is emitted. |
| `--json` | Emit JSON success/error envelope. See [`diagnostics.md`](diagnostics.md#json-envelopes). |

Examples:

```bash
# Convert a source directory
tex-to-md path/to/paper-src --outdir out/paper

# Convert a tar archive, skip figures, emit JSON
tex-to-md paper.tar.gz --outdir out/paper --no-assets --json

# Keep extracted source next to output
tex-to-md paper.tar --outdir out/paper --keep-source

# Fast path when downstream can read PDF/JPEG figures; no optional asset deps needed
tex-to-md paper.tar.gz --outdir out/paper --asset-mode copy

# Higher quality rasterization
tex-to-md paper.tar.gz --outdir out/paper --raster-dpi 300

# Dry-run asset resolution
tex-to-md paper.tar.gz --outdir out/paper --asset-mode skip

# Treat warnings as failures
tex-to-md paper-src --outdir out/paper --strict
```

## `arxiv-to-md`

Download arXiv source bundles and convert each result into a per-paper directory.

```text
arxiv-to-md QUERY [QUERY ...] --outdir OUTDIR
                   [--top-k N]
                   [--keep-archive]
                   [--keep-source]
                   [--json]
```

`QUERY` may be an arXiv ID (`1706.03762`, `2401.00001`) or free-text search
query. For searches, `--top-k` controls how many results are converted.

| Flag | Meaning |
| --- | --- |
| `--outdir OUTDIR` | Required batch parent directory. |
| `--top-k N` | Number of search results to convert. |
| `--keep-archive` | Keep downloaded source bundles under `OUTDIR/.archives/`. |
| `--keep-source` | Keep extracted source under each paper output directory. |
| `--json` | Emit JSON success/error envelope. |

Examples:

```bash
# Convert one paper by ID
arxiv-to-md 2401.00001 --outdir out

# Convert several papers, keeping source archives
arxiv-to-md 2401.00001 2402.00002 --outdir out --keep-archive

# Search and convert top 3 results
arxiv-to-md "diffusion language models" --top-k 3 --outdir out --json
```

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Success. |
| `1` | Conversion failed. With `--json`, inspect `error.code`. |
| `2` | CLI usage error from argparse, such as missing `--outdir`. |
