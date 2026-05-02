# Tests Guide

## Core principle

Test user-visible contracts through public entry points.

A refactor that preserves behavior should keep tests green. A behavior change users can observe should make one focused test fail.

## Test value rubric

Before adding or keeping a test, answer:

1. Which public contract does this protect?
2. Which existing test layer would miss this bug?
3. Does failure point to one clear cause?
4. Can implementation change while test stays green?
5. Does it run fast enough for its run mode?

Keep tests that pass this rubric. Rewrite weak tests as contract tests.

## Suite layers

Each layer owns one kind of contract. Prefer one owner per behavior.

| Layer | Scope | Contract asserted | Bug caught |
|---|---|---|---|
| Construct corpus | One TeX feature per fixture | Markdown equals hand-reviewed `expected.md` | Specific feature render drift |
| Paper snapshots | Curated whole papers | Full Markdown snapshot | Cross-feature integration drift |
| Real-paper regression | arXiv source bundles | Conversion succeeds with non-empty output | Real-world TeX crash |
| Typed errors | Public failure modes | error class, stable `code`, JSON shape | Untyped or unstable errors |
| Property fuzz | Public conversion API | typed failures only; typed warnings/stats | Crash on strange input |
| Public API surface | `arxiv_md` exports | required names importable and in `__all__` | accidental API removal |
| CLI contract | argv → exit/files/output | exit codes, files, sidecars, JSON policy | CLI behavior drift |
| Architecture | source-level invariants | import boundaries and structural guardrails | architectural regressions |

Default suite stays fast. Slow and architecture layers are opt-in.

## Contract ownership

Let one layer own each behavior.

- Rendering correctness lives in construct fixtures and paper snapshots.
- Warning shape lives in property tests.
- Error shape lives in typed-error tests.
- File writing and exit behavior live in CLI/API write tests.
- Public export promises live in public-surface tests.

When a new test overlaps an existing owner, add a fixture or strengthen owner instead.

## Construct corpus

Construct fixtures are parsing/rendering spec.

### Shape

```text
tests/fixtures/constructs/<category>/<name>/
  input.tex       required: body fragment or full document
  expected.md     required: hand-reviewed Markdown
  preamble.tex    optional: macros/envs needed by this construct
```

### Wrapping

If `input.tex` starts with `\documentclass`, runner treats it as a complete document. Otherwise runner composes:

```tex
<preamble.tex if present>
\begin{document}
<input.tex>
\end{document}
```

### Workflow

1. Create minimal `input.tex` that isolates one feature.
2. Generate `expected.md` with snapshot update mode.
3. Read output as Markdown contract, not current implementation output.
4. Commit only reviewed expected output.
5. On drift, review diff and choose correct behavior before updating.

### Sourcing

Drive constructs from real papers and observed frequency.

Prioritize:

1. daily TeX: sections, paragraphs, inline styles, math, refs, citations, figures, simple tables, lists
2. common tricky TeX: align/equation, longtable, captions/labels, footnotes, links, verbatim, macros
3. long tail: algorithms, theorems, subfigures, colors, drawing fallbacks, unicode, math comments

## Paper snapshots

Use curated whole-paper fixtures for integration behavior.

Snapshot diffs are review surface. Snapshot update commits should state why new output is correct. Keep fixture count small enough for default suite speed.

## Real-paper regression

Use checked-in source bundles behind slow marker.

Contract:

- conversion returns without untyped failure
- Markdown is non-empty
- diagnostics remain inspectable

Use this layer to catch reality gaps, then distill bugs into construct fixtures.

## Public API tests

Use root package imports for compatibility promises.

Assert:

- required names are importable from `arxiv_md`
- required names are present in `arxiv_md.__all__`
- public functions return documented result objects for representative inputs

Prefer behavior over object existence. Public API tests protect user imports and documented calls.

## CLI tests

Treat CLI as a user contract.

Assert:

- successful conversion returns zero
- expected files exist and contain key data
- missing required args return non-zero
- invalid paths return non-zero
- JSON mode emits machine-readable envelopes
- sidecar config mirrors user-visible options

Each accepted flag should have a concrete expected behavior. If behavior varies, split cases by input that makes outcome deterministic.

## Typed-error tests

Trigger real failure modes through public API.

For each public error path, assert:

- raised class user catches
- stable `.code`
- `.to_json()` keys callers consume
- CLI maps failure to documented exit/output shape when applicable

Inheritance matters when users catch the base error in a real scenario; cover that through an API call that raises and is caught as the base class.

## Property tests

Use properties for broad input space, not exact rendering.

Good properties:

- conversion returns result or raises typed converter error
- warnings are typed and have stable `code`/`message`
- stats maps use string keys and non-negative integer counts
- output strings remain valid strings for arbitrary valid input text

Keep examples small and deadlines practical. When property finds a rendering bug, add a focused construct fixture.

## Fixtures and mocks

Prefer real TeX, real temp dirs, real archives, and in-process CLI calls.

Use mocks for boundaries that are expensive, external, or hard to force:

- network
- time
- missing optional capability
- resource-limit edge
- permission/write failure

Keep parser, transformer, renderer, and public API unmocked so tests exercise real behavior.

## Architecture checks

Place source-scan and structural guardrails under architecture marker.

Use this layer for invariants that behavior tests cannot express:

- import boundaries
- import cycles
- private-module coupling
- package import cleanliness

Keep architecture checks opt-in unless they are fast and essential to user contract.

## Speed budget

Default suite target: under 5 seconds on dev laptop.

Use markers:

```bash
uv run pytest                              # fast default suite
uv run pytest --runslow                    # includes real-paper corpus
uv run pytest --runarchitecture            # includes architecture checks
uv run pytest --runslow --runarchitecture  # full suite
```

A slow default test should earn its cost by covering a high-value contract no faster test can cover.

## Maintenance loop

When adding behavior:

1. Add or update construct fixture for rendering behavior.
2. Add API/CLI/error/property test only if behavior belongs outside rendering.
3. Run default suite.
4. Review snapshots by reading rendered output.
5. Keep test count focused; strengthen existing owners before adding overlaps.

When fixing bugs:

1. Reproduce with smallest public entry point.
2. Add construct fixture or contract test that fails before fix.
3. Fix implementation.
4. Update snapshots only after review.
5. Move broad regression into focused fixture when possible.

## North star examples

### Construct

```python
def test_construct_renders(construct: Path) -> None:
    actual = convert_text(compose(construct)).markdown
    expected = (construct / "expected.md").read_text(encoding="utf-8")
    assert actual == expected
```

### Paper snapshot

```python
def test_paper_matches_snapshot(name: str, fixtures_root: Path, assert_snapshot) -> None:
    md = convert_path(fixtures_root / name).markdown
    assert_snapshot(f"{name}.md", md)
```

### CLI

```python
def test_converts_simple_paper(run_cli, simple_paper, tmp_path: Path) -> None:
    out = run_cli("tex-to-md", [str(simple_paper), "--outdir", str(tmp_path)])
    assert out.exit_code == 0
    assert (tmp_path / "document.md").is_file()
    assert (tmp_path / "conversion.json").is_file()
```

### Typed error

```python
def test_empty_directory_has_stable_error(tmp_path: Path) -> None:
    with pytest.raises(NoMainTexError) as exc:
        convert_path(tmp_path)
    assert exc.value.code == "no_main_tex"
    assert exc.value.to_json()["code"] == "no_main_tex"
```

### Property

```python
@given(body=tex_noise)
def test_convert_text_failures_are_typed(body: str) -> None:
    try:
        result = convert_text(rf"\begin{{document}}{body}\end{{document}}")
    except TexConvertError:
        return
    assert isinstance(result.markdown, str)
```

## Summary

- Test contracts through public entry points.
- Let each behavior have one test owner.
- Use fixtures as rendering spec.
- Use properties for crash resistance.
- Use typed-error tests for failure contracts.
- Use CLI tests for user command behavior.
- Keep default suite fast.
- Review snapshots as product output.
