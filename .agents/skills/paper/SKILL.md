---
name: paper
description: Fetch, read, summarize, or cite an arXiv paper using arxiv-md. Use when user provides an arxiv URL or ID and asks for analysis, summaries, or findings.
disable-model-invocation: true
---

# Skill: Paper Analysis via arxiv-md

Use when user asks to fetch, read, summarize, or cite an arXiv paper.

---

## Step 1 — Fetch paper with arxiv-md

```bash
uv run arxiv-to-md <ARXIV_ID> --outdir data/papers
```

Extract ID from URL: `https://arxiv.org/abs/2601.07892` → `2601.07892`. Output lands at `data/papers/<ARXIV_ID>/document.md`.

---

## Step 2 — Build section boundary map

Immediately after fetch, build a map of all section headers and their line numbers. Reuse this map throughout all subsequent steps.

```bash
cat -n data/papers/<ID>/document.md | grep -E "^\s*[0-9]+\s+#{1,6} "
```

Store mentally (or in a scratch variable) as: `line → heading text`. Lines before the first heading belong to `# Abstract`.

---

## Step 3 — Orient and collect keywords

Read the first ~30 lines to capture title, abstract, and intro:

```
Read: path=data/papers/<ID>/document.md, offset=1, limit=100
```

From the abstract and intro, extract a rich set of keywords covering: core claims, named methods/modules, metrics, baselines, datasets, and domain terms. Store them in `data/papers/<ID>/keywords.md` as a bullet list grouped semantically. Example:

```markdown
## Method
- Sherry
- Arenas
- 3:4 sparsity
- 1.25-bit
- annealing residual synapse

## Problem
- weight trapping
- gradient homogenization
- representational collapse

## Hardware / Efficiency
- SIMD alignment
- LUT-based inference
- AVX2 vpshufb
- token generation speed

## Baselines
- TequilaLLM
- BitNet
- ParetoQ
- TernaryLLM

## Metrics / Benchmarks
- ARC-Challenge
- HellaSwag
- WinoGrande
- Effective Rank
- t/s
```

These keywords drive all grep searches in subsequent steps.

---

## Step 4 — Find exact line numbers with grep

Use `data/papers/<ID>/keywords.md` as the seed for search terms.

Always use `cat -n` piped to `grep` to get true line numbers:

```bash
cat -n data/papers/<ID>/document.md | grep -E "<pattern>"
```

Examples:
```bash
# Find a specific claim
cat -n data/papers/2601.07892/document.md | grep -E "weight trapping|ER <"

# Find table rows with numbers
cat -n data/papers/2601.07892/document.md | grep -E "45\.55|38\.80"

# Find section headers
cat -n data/papers/2601.07892/document.md | grep -E "^## |^### "
```

The number in the first column is the exact line number.

---

## Step 5 — Read targeted sections

Once line numbers are known, use `Read` with `offset`/`limit` to pull exact context:

```
Read: path=..., offset=<line_start>, limit=<n_lines>
```

Iterate: grep a keyword → get line N → Read offset=N-2, limit=20 to see context.

---

## Step 6 — Cite with exact line ranges

Use line numbers from `cat -n | grep`, not estimated offsets from Read calls.

### Inline citation format

As you write each response section, accumulate the line numbers you drew from. After the last paragraph of each response section, append a citation block in curly braces:

```
{ ## 3. Method, [L254, L266-L267]; ### 3.1 Architecture, [L310] }
```

Rules:
- **Header level + name**: verbatim from the paper heading (e.g. `## 3. Method`), determined via the section boundary map built in Step 2.
- **Lines before first heading**: attribute to `# Abstract`.
- **Multiple paper sections**: separate with `;` within the same block.
- **Lines crossing a section boundary**: split into two entries at the boundary.
- **Non-contiguous lines in same section**: list individually — `[L10, L15, L20]`.
- **Ranges**: `L20-L33`. Single lines: `L10`.
- **No lines cited** in a response section: omit the block entirely.
