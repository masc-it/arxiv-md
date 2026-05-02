# Security model

`arxiv-md` is designed for untrusted arXiv source bundles. A hostile bundle may
try to escape extraction, exhaust resources, trigger TeX build hooks, or attack
asset decoders. The default pipeline avoids TeX execution, validates archive
members, isolates output, and exposes resource controls.

## Guarantees

- No TeX execution: no `pdflatex`, `latexmk`, `kpsewhich`, `\write18`, shell
  escape, or external TeX toolchain.
- Archive members are validated before extraction.
- Absolute paths, traversal, symlinks, and hard links are rejected.
- `--outdir` is explicit and cannot resolve inside the source tree.
- Temporary downloads and extraction trees are cleaned up unless explicitly kept.
- Asset rasterization is optional and can be skipped or replaced with copy mode.

## Archive extraction

For `.tar`, `.tar.gz`, `.tgz`, and `.zip`, every member is checked before bytes
are extracted. A bundle is rejected with `unsafe_archive` if any member:

- has an absolute path such as `/etc/passwd` or `C:\...`,
- contains `..` traversal components,
- resolves outside the extraction directory,
- is a symlink or hard link.

Tar bundles use Python `tarfile`'s safe `data` filter as a second line of
defense. Single-file `.gz` inputs are streamed under a safe `.tex` filename and
are not treated as archive containers.

Unknown archive shapes (`.rar`, `.7z`, etc.) fail with `unsupported_archive`
instead of being passed to third-party extractors.

## Output isolation

- `--outdir` is always required.
- No in-place conversion mode exists.
- `tex-to-md` treats `--outdir` as the exact document output directory.
- `arxiv-to-md` treats `--outdir` as a batch parent directory.
- Source trees are kept only with `--keep-source`.
- Downloaded source archives are kept only with `--keep-archive`.

## No TeX execution

The converter parses and transforms TeX in process. It does not invoke external
TeX tools and does not evaluate shell escape macros. Installing a TeX
distribution is not required.

Macro expansion uses an in-process expander with hard recursion and node-count
caps; see [resource limits](#resource-limits).

## Asset rasterization

Asset rendering is the only path that touches optional third-party native code
(pypdfium2/Pillow) on attacker-controlled bytes. The optional asset stack uses
pypdfium2 + Pillow and does not require an AGPL PyMuPDF runtime dependency. Use
one of these modes to control risk and cost:

| Mode | CLI | API | Behavior |
| --- | --- | --- | --- |
| No assets | `--no-assets` | `render_assets=False` | Skip asset resolution/output; no `images/`. |
| Rasterize | default | `asset_mode="rasterize"` | Render PDF to PNG via pypdfium2 and JPEG to PNG via Pillow; best compatibility, highest CPU/native-code exposure. |
| Copy | `--asset-mode copy` | `asset_mode="copy"` | Copy PDF/JPEG verbatim; no optional asset deps needed. |
| Skip | `--asset-mode skip` | `asset_mode="skip"` | Resolve/count figures but write no images. |

Rasterize mode renders only the first PDF page for each figure. If pypdfium2 is
missing, affected PDF figures emit `pdfium_missing` warnings instead of crashing
conversion. If Pillow is missing, JPEG figures emit `pillow_missing` warnings and
fall back to raw copy.

PNG and SVG sources are copied verbatim. EPS sources are not rendered and emit
`unsupported_asset` warnings.

## Resource limits

`ResourceLimits` is importable from `arxiv_md` and can be passed through
`ConvertOptions(limits=...)`.

| Field | Default | Purpose |
| --- | ---: | --- |
| `max_archive_members` | `10_000` | Cap tar/zip member count. |
| `max_archive_total_bytes` | `512 MiB` | Cap total uncompressed archive size. |
| `max_single_file_bytes` | `64 MiB` | Cap individual source/archive member size. |
| `max_tex_source_bytes` | `64 MiB` | Cap aggregate loaded TeX source. |
| `max_include_files` | `2_000` | Cap `\input` / `\include` chain length. |
| `max_asset_files_scanned` | `50_000` | Bound figure asset lookup walks. |
| `max_bib_files_scanned` | `2_000` | Bound bibliography file scans. |
| `max_pdf_pages_rasterized` | `1` | Render only first page per PDF figure. |
| `max_macro_expansion_depth` | `32` | Prevent infinite macro recursion. |
| `max_macro_expanded_nodes` | `100_000` | Bound total macro-expanded AST nodes. |

Example stricter limits:

```python
from pathlib import Path

from arxiv_md import ConvertOptions, ResourceLimits, convert_path

opts = ConvertOptions(
    output_dir=Path("out/paper"),
    limits=ResourceLimits(
        max_archive_total_bytes=64 * 1024 * 1024,
        max_archive_members=2_000,
        max_macro_expanded_nodes=20_000,
    ),
)
result = convert_path(Path("paper.tar.gz"), opts)
```

Limit hits produce typed warnings or fatal `resource_limit` errors depending on
which cap was breached. See [`diagnostics.md`](diagnostics.md#fatal-error-codes).
