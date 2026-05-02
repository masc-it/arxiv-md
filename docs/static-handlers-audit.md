# Static handler dispatch

Task: ARX-STATIC-HANDLERS-342

Conversion now uses fixed command and environment dispatch tables in source code.
Built-in LaTeX support is selected by command/environment name, then unknown
inputs fall back to typed diagnostics plus preserved/raw output where possible.

## Environment dispatch

Environment dispatch lives in
`src/arxiv_md/tex/transform/handlers/env_dispatch.py`.

Order:

1. `dispatch_env(ctx, env)` checks `ENV_HANDLERS` by `env.name`.
2. If no fixed handler exists, `ctx.theorem_env_titles` supplies titles learned
   from `\newtheorem` declarations for that conversion only.
3. If still unknown, `unknown_env(env, ctx)` preserves raw LaTeX and records the
   unknown environment count.

| Category | Environment names | Handler |
| --- | --- | --- |
| Math | `align`, `align*`, `alignat`, `alignat*`, `displaymath`, `eqnarray`, `eqnarray*`, `equation`, `equation*`, `gather`, `gather*`, `multline`, `multline*`, `split` | `math_env` |
| Lists | `description`, `enumerate`, `itemize` | `list_env` |
| Figures | `SCfigure`, `figure`, `figure*`, `subfloat`, `wrapfigure`, `wrapfigure*` | `figure_env` |
| TikZ fallback | `axis`, `loglogaxis`, `pgfpicture`, `pgfplots`, `semilogxaxis`, `semilogyaxis`, `tikzpicture` | `tikz_env` |
| Table wrappers | `table`, `table*`, `wraptable`, `wraptable*` | `table_wrapper_env` |
| Longtable | `longtable` | `longtable_env` |
| Tabular-like | `array`, `tabu`, `tabular`, `tabular*`, `tabularx` | `tabular_standalone` |
| Containers | `CJK`, `CJK*`, `adjustbox`, `adjustwidth`, `center`, `flushleft`, `flushright`, `footnotesize`, `mdframed`, `minipage`, `quoting`, `scriptsize`, `small`, `subfigure`, `subfigure*`, `subtable`, `subtable*`, `tiny` | body walk |
| Quote envs | `displayquote`, `quotation`, `quote` | `QuoteBlock` |
| Skip-body envs | `CCSXML`, `IEEEkeywords`, `abstract`, `document`, `keywords`, `thebibliography` | skip |
| Boxes | `tcolorbox`, `tcblisting` | quote/code handlers |
| Algorithms | `algorithm`, `algorithm*` | `algorithm_env` |
| Algorithmic | `algorithmic`, `algorithmicx`, `algpseudocode` | `algorithmic_env` |
| Theorem/proof | built-in theorem/proof env names from `ALL_BUILTIN_THEOREM_ENVS` | `make_theorem_handler(title)` |

## Inline command dispatch

Inline dispatch lives in `src/arxiv_md/tex/transform/inline.py`.

Order:

1. Built-in command specs in `BUILTIN_COMMAND_SPECS` run first.
2. Unknown commands fall back to `UnknownCommandHandler`, which counts the
   command name and renders braced args as inline content.

Static `siunitx` command support is built in for:

- `SI`
- `si`
- `ang`
- `num`
- `SIrange`
- `numrange`

## Public API docs check

`docs/api.md` lists current `ConvertOptions` fields only:

- `output_dir`
- `document_slug`
- `keep_source`
- `render_assets`
- `asset_mode`
- `raster_dpi`
- `strict`
- `limits`

Docs index pages link only to supported docs that exist in this tree.
