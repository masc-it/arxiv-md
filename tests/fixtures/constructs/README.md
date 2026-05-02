# Construct fixtures

One TeX feature per directory. Two required files plus optional preamble:

```
<category>/<name>/
  input.tex       body fragment OR full document (if it starts with \documentclass)
  expected.md     HAND-REVIEWED ground-truth markdown
  preamble.tex    optional, prepended only when input.tex is a body fragment
  source.txt      optional, attribution + rationale notes
```

The runner wraps body fragments in `\begin{document}…\end{document}`.

**Discipline**: every `expected.md` in this tree must have been read by a
human before commit. `UPDATE_SNAPSHOTS=1` is a bootstrap aid, not a
licence to commit converter output blind. See `docs/TESTS_GUIDE.md`.
