# Performance guide

Benchmarks below were measured on an Apple M-series laptop over 174 papers (87
NLP + 87 CV) from `data/dataset`. Treat numbers as directional; asset count and
PDF complexity dominate wall time.

## Recommendations

- Use `--no-assets` for text extraction, search indexing, NLP, and diffing.
- Use `--asset-mode copy` when downstream can read PDF/JPEG figures directly.
- Use default rasterization only when PNG figure output is required; it uses optional pypdfium2/Pillow backends.
- Lower `--raster-dpi` for previews; raise it only for high-DPI/archival output.
- Reuse output directories for incremental runs; asset writes are mtime-cached.

## Conversion without assets

```bash
tex-to-md paper.tar.gz --outdir out/paper --no-assets
```

| Metric | NLP (87) | CV (87) | Combined (174) |
| --- | ---: | ---: | ---: |
| Median | 70 ms | 88 ms | 79 ms |
| Mean | 91 ms | 106 ms | 98 ms |
| P95 | 227 ms | 227 ms | 227 ms |
| Max | 362 ms | 627 ms | 627 ms |

Pure TeX→Markdown conversion runs at roughly **80 ms median** per paper when
asset work is disabled.

## Asset modes compared

Single asset-heavy paper: `cv/2604.21931`, 17 figures.

| Mode | Command | Time | Speedup |
| --- | --- | ---: | ---: |
| Rasterize | default | 3234 ms | 1× |
| Copy | `--asset-mode copy` | 421 ms | 7.7× |
| Skip | `--asset-mode skip` | 414 ms | 7.8× |
| No assets | `--no-assets` | 413 ms | 7.8× |

Rasterization dominates when papers contain many PDF/JPEG figures because pypdfium2/Pillow decode/render and PNG writes cost more than copying paths. `copy` and `skip` avoid optional asset deps and are preferred when downstream can consume original figure files or image output is not needed.

## Rasterization DPI

`--raster-dpi` controls PDF→PNG resolution. Lower is faster and smaller; higher
is sharper and larger.

| DPI | Relative speed | Use case |
| ---: | ---: | --- |
| 72 | ~2× faster | Thumbnails, previews |
| 120 | baseline | Default, web/Markdown display |
| 200 | ~0.4× slower | Print-quality |
| 300 | ~0.25× slower | High-DPI / archival |

## Where time goes

For `cv/2604.21931` with 17 resolved figures in rasterize mode:

| Stage | Time | Share |
| --- | ---: | ---: |
| Source prep (tar extraction) | 366 ms | 11% |
| Parse + transform | 38 ms | 1% |
| Asset resolution + rasterization | 2826 ms | 87% |
| Markdown render | <1 ms | <1% |

Within PDF/image backends, decode/render and PNG encode/write are CPU-bound.
Thread-based parallelism gave no speedup in evaluation; process-based
parallelism helped but was deferred because `copy` and `skip` modes avoid most
cost with less platform risk.

## Incremental re-runs

When re-converting into the same output directory, existing asset targets are
skipped if they are at least as new as the source file. This makes incremental
asset-heavy re-runs much cheaper.

## Safety limits

Large-archive and macro caps are documented in [`security.md`](security.md#resource-limits).
Tighten them with `ConvertOptions(limits=ResourceLimits(...))` for hosted or
batch scenarios.
