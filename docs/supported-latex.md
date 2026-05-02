# Supported inputs and LaTeX

`arxiv-md` is a best-effort Markdown extractor, not a TeX engine. It aims to
keep semantic content, preserve raw LaTeX for unsupported constructs, and report
what it could not model.

## Supported inputs

`tex-to-md` accepts:

- `.tex` files used directly as the main entry point.
- Source directories. The converter detects the main `.tex` file, usually the
  one containing `\documentclass`, then follows `\input` and `\include`.
- Source archives: `.tar`, `.tar.gz`, `.tgz`, `.zip`. Members are validated
  before extraction; see [`security.md`](security.md#archive-extraction).
- Single-file gzip bundles: `.gz`. Decompressed in memory under a safe `.tex`
  filename and treated as one source file.

`arxiv-to-md` accepts arXiv IDs or free-text search queries, downloads source
bundles, and runs the same pipeline per paper.

Unsupported inputs (`.pdf`, `.html`, `.rar`, `.7z`, single `.bib` files) fail
with `unsupported_archive` or `unreadable_source`. Unknown archive shapes are
not silently ignored and are not dispatched to third-party extractors.

## Non-goals

- **No TeX execution.** The pipeline never invokes `pdflatex`, `latexmk`,
  `kpsewhich`, or shell escape. `\write18` and shell-escape macros are inert.
- **No full layout fidelity.** Page geometry, float placement, typography,
  multi-column layout, and PDF typesetting are not reproduced.
- **No guaranteed macro/environment expansion.** Macro expansion is best-effort
  and capped by resource limits.
- **Best-effort tables, assets, and bibliography.** These may fall back to HTML,
  raw LaTeX, missing-asset warnings, or partial bibliography diagnostics.

## Native support matrix

| Family | Commands / environments | Output |
| --- | --- | --- |
| Document structure | `\section`–`\subparagraph`, `\title`, `\author`, `\date`, `\abstract` | Headings, frontmatter |
| Text formatting | `\textbf`, `\textit`, `\emph`, `\texttt`, `\underline`, `\textrm` | Strong/emphasis/code spans |
| Font declarations | `{\em ...}`, `{\bf ...}`, `{\it ...}`, `{\tt ...}`, `{\rm ...}`, `{\sc ...}`, `{\sf ...}` | Equivalent spans |
| Math | `$...$`, `\(...\)`, `$$...$$`, `\[...\]`, `equation`, `align`, `gather`, `multline` + starred | KaTeX-style math spans/blocks |
| Math wrappers | `\ensuremath`, `\texorpdfstring`, `\bm`, `\boldsymbol`, `\mathbb`, etc. | Math spans when outside math |
| Extended glyphs | `\dag`, `\ddag`, `\P`, `\S`, `\langle`, `\rangle`, `\infty`, etc. | Unicode text or math spans |
| Lists | `itemize`, `enumerate`, `description` | Nested list blocks |
| Figures | `figure`, `figure*`, `wrapfigure`, `subfigure` | Figure blocks with resolved assets |
| Tables | `table`, `tabular`, `longtable`, `tabularx`, `tabulary` | Structured table, HTML, or raw fallback |
| Bibliography | `\cite` variants, `thebibliography`, `\bibitem`, `\newblock`, `.bbl`, `.bib` | Citations and bibliography entries |
| Cross-references | `\ref`, `\eqref`, `\autoref`, `\cref`, `\Cref`, `\label` | Resolved numbered refs |
| Theorems | `theorem`, `lemma`, `proof`, `definition`, `proposition`, `corollary`, `remark` + starred + `\newtheorem` discovery | Quote/admonition-style blocks |
| Algorithms | `algorithm`, `algorithmic`, `algorithmicx`, `algpseudocode`; `\State`, `\While`, `\If`, `\For`, `\Return`, etc. | Fenced pseudocode |
| `siunitx` | `\SI`, `\si`, `\ang`, `\num`, `\SIrange`, `\numrange` | Formatted values and units |
| Macros | `\newcommand`, `\def`, `\renewcommand`, `\DeclareMathOperator`, `\newtheorem` | Expanded or discovered |
| Metadata | `\keywords`, `IEEEkeywords`, `CCSXML`, `\affiliation`, `\email` | Stripped or frontmatter |
| Box/quote envs | `tcolorbox`, `mdframed`, `quoting`, `adjustwidth`, `minipage`, `center` | Content extracted |

## Fallback policy

Unsupported constructs follow conservative fallback rules:

1. Preserve raw LaTeX as `RawLatex` blocks or `RawLatexSpan` inlines when the
   content may matter.
2. Emit typed warnings such as `unknown_command`, `unknown_env`,
   `table_raw_fallback`, `figure_missing`, or `unsupported_asset`.
3. Drop layout-only commands (`\vspace`, `\hspace`, `\clearpage`, `\noindent`,
   etc.) when they have no semantic content.

Unknown commands are never silently consumed. Per-document inventories appear in
`stats.unknown_command_counts` and `stats.unknown_env_counts`.
