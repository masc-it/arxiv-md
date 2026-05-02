# Keywords

## Project
- arxiv-md
- arXiv
- LaTeX to Markdown converter
- TeX source extraction
- semantic Markdown
- Python package
- Python 3.10–3.13
- MIT license
- uv build backend

## Entry points
- tex-to-md CLI
- arxiv-to-md CLI
- tex-ast CLI
- convert_path
- convert_text
- write_result
- ConvertOptions
- ConvertResult
- WrittenResult
- ConversionStats
- ResourceLimits

## Inputs
- .tex file
- source directory
- main tex detection
- \input
- \include
- .tar archive
- .tar.gz archive
- .tgz archive
- .zip archive
- .gz single-file bundle
- arXiv ID
- arXiv search query
- unsupported .pdf input
- unsupported .html input
- unsupported .rar input
- unsupported .7z input
- lone .bib rejection

## Outputs
- document.md
- conversion.json
- images directory
- source directory keep-source
- per-paper output dirs
- .archives directory
- JSON envelope
- output_dir option
- document_slug

## Pipeline
- archive extraction
- source reader
- lexer
- parser
- macro engine
- macro expansion
- transform pipeline
- static handler dispatch
- block IR
- inline IR
- Markdown rendering
- asset resolution
- bibliography resolution
- cross-reference resolution

## Lexing
- TokKind
- Token
- Lexer
- tokenize
- verbatim handling
- comment skipping
- dimension parsing
- glue parsing
- control word

## Parser
- Parser class
- parse
- parse_text
- AST nodes
- Group node
- Diagnostics
- balanced groups
- environment begin/end

## Macros
- \newcommand
- \def
- \renewcommand
- \DeclareMathOperator
- \newtheorem discovery
- \let
- newenvironment skip
- xspace inert pattern
- unsafe macro body detection
- argc parsing
- optional bracket defaults
- compile_macros
- CompiledMacro
- macro recursion limits
- StripOffsetMap
- collect_macros

## Math
- inline math $...$
- inline math \(...\)
- display math $$...$$
- display math \[...\]
- equation env
- align env
- gather env
- multline env
- starred math envs
- KaTeX-style spans
- \ensuremath
- \texorpdfstring
- \bm
- \boldsymbol
- \mathbb
- math accents
- math layout wrappers
- math comments stripping
- expand_math_text

## Document structure
- \section
- \subsection
- \subsubsection
- \paragraph
- \subparagraph
- \title
- \author
- \date
- \abstract
- frontmatter
- Heading
- Paragraph
- heading level clamp 1..6

## Inline formatting
- \textbf
- \textit
- \emph
- \texttt
- \underline
- \textrm
- {\em ...}
- {\bf ...}
- {\it ...}
- {\tt ...}
- {\rm ...}
- {\sc ...}
- {\sf ...}
- StrongSpan
- EmphasisSpan
- CodeSpan
- LinkSpan
- TextSpan
- SuperscriptSpan
- SubscriptSpan
- RawLatexSpan
- MathSpan
- ReferenceSpan
- CitationSpan

## Lists
- itemize
- enumerate
- description
- ListBlock
- nested lists

## Figures and assets
- figure env
- figure* env
- wrapfigure
- subfigure
- Figure block
- figure label
- figure caption
- CaptionPosition
- asset rendering
- rasterize mode
- copy mode
- skip mode
- raster_dpi
- pypdfium2
- Pillow
- PDF to PNG
- JPEG to PNG
- relative image paths
- figure_missing warning
- unsupported_asset warning

## Tables
- tabular
- table env
- longtable
- tabularx
- tabulary
- Table block
- TableRow
- TableCell
- TableColumn
- TableSection
- TableSectionKind
- TableRule
- TableRuleKind
- TableAlign
- TableVAlign
- TableStyle
- TableCellStyle
- TableRowStyle
- TableParseStatus
- HTML fallback
- raw LaTeX fallback
- table_raw_fallback warning

## Bibliography
- \cite
- \citep
- \citet
- thebibliography env
- \bibitem
- \newblock
- .bbl parsing
- .bib parsing
- BibEntry
- citations resolution

## Cross-references
- \ref
- \eqref
- \autoref
- \cref
- \Cref
- \label
- numbered refs

## Theorems
- theorem env
- lemma env
- proof env
- definition env
- proposition env
- corollary env
- remark env
- starred theorems
- QuoteBlock admonition

## Algorithms
- algorithm env
- algorithmic env
- algorithmicx
- algpseudocode
- \State
- \While
- \If
- \For
- \Return
- fenced pseudocode

## SI units
- siunitx
- \SI
- \si
- \ang
- \num
- \SIrange
- \numrange

## Boxes and quotes
- tcolorbox
- mdframed
- quoting
- adjustwidth
- minipage
- center env

## Glyphs
- \dag
- \ddag
- \P
- \S
- \langle
- \rangle
- \infty
- Unicode replacement

## Metadata
- \keywords
- IEEEkeywords
- CCSXML
- \affiliation
- \email

## Code blocks
- CodeBlock
- verbatim env

## Diagnostics
- TexWarning
- warning code
- warning message
- SourceSpan
- source position
- StrictConversionError
- strict mode
- unknown_command warning
- unknown_env warning
- raw_fallback counts
- unknown_command_counts
- unknown_env_counts

## Errors
- TexConvertError
- NoMainTexError
- NoParseableBodyError
- OutputWriteError
- SourceReadError
- UnsafeArchiveError
- UnsafeOutputDirError
- UnsupportedArchiveError
- ResourceLimitError

## Security
- no TeX execution
- no shell escape
- \write18 inert
- archive path validation
- output dir guard
- assert_safe_output_dir
- resource limits
- macro expansion cap
- archive extraction cap
- include depth cap
- asset scan cap

## Internal handler context
- static env dispatch
- static inline dispatch
- Env handler
- Command handler
- TransformContextProtocol
- ctx.block_ir
- ctx.inline_ir
- ctx.inline_markdown
- ctx.inline_html
- ctx.inline_plain
- ctx.env_full_raw
- ctx.env_inner_raw
- ctx.diag
- ctx.macros
- ctx.limits

## CLI flags
- --outdir
- --document-slug
- --keep-source
- --keep-archive
- --no-assets
- --asset-mode
- --raster-dpi
- --strict
- --json
- --top-k
- exit code 0/1/2

## Document IR
- TexDocument
- Block
- InlineNode
- BLOCK_TYPES
- INLINE_TYPES
- MathBlock
- RawLatex
- isinstance discrimination
- additive schema evolution

## arXiv download
- arxiv id parsing
- arxiv search API
- source bundle download
- source_download module
- top-k results

## Tools
- convert_corpus script
- dump_ast tool
- corpus regression

## Testing
- pytest
- hypothesis property tests
- snapshot tests
- corpus regression tests
- architecture lint tests
- import cycle check
- conftest fixtures
- slow marker
- architecture marker
- runslow opt-in
- runarchitecture opt-in

## Tooling
- ruff
- mypy
- pre-commit
- deptry
- vulture
- radon
- xenon
- pytest-cov
- uv lockfile
- uv_build backend

## Docs
- docs/README.md
- docs/api.md
- docs/cli.md
- docs/supported-latex.md
- docs/diagnostics.md
- docs/security.md
- docs/static-handlers-audit.md
- docs/performance.md
- TESTS_GUIDE.md
- CHANGELOG.md
