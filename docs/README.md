# Documentation

Use this index after the README quickstart.

## Start here

- [`cli.md`](cli.md) — `tex-to-md`, `arxiv-to-md`, flags, output layout, exit codes.
- [`api.md`](api.md) — `convert_path`, `convert_text`, `write_result`, options, IR.

## Reference

- [`supported-latex.md`](supported-latex.md) — supported inputs, non-goals, native TeX support, fallback policy.
- [`diagnostics.md`](diagnostics.md) — warning shape, fatal errors, JSON envelopes, source spans.
- [`security.md`](security.md) — archive hardening, output isolation, resource limits, asset rasterization.
- [`static-handlers-audit.md`](static-handlers-audit.md) — built-in static command/environment dispatch internals.
- [`performance.md`](performance.md) — benchmark data and asset-mode recommendations.

## Common tasks

| Task | Doc |
| --- | --- |
| Convert local source or archive | [`cli.md#tex-to-md`](cli.md#tex-to-md) |
| Download and convert arXiv papers | [`cli.md#arxiv-to-md`](cli.md#arxiv-to-md) |
| Use library in memory | [`api.md#conversion-entry-points`](api.md#conversion-entry-points) |
| Inspect typed document IR | [`api.md#document-ir`](api.md#document-ir) |
| Consume JSON output | [`diagnostics.md#json-envelopes`](diagnostics.md#json-envelopes) |
| Handle warnings and fatal errors | [`diagnostics.md#library-diagnostics`](diagnostics.md#library-diagnostics) |
| Avoid asset rasterization | [`security.md#asset-rasterization`](security.md#asset-rasterization) |
| Choose fastest asset mode | [`performance.md#recommendations`](performance.md#recommendations) |
