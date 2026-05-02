# Architecture tests

Source-scan / structural lint. **Opt-in only**: pass
`--runarchitecture` to include them. They are not behaviour tests and
must never gate normal CI.

Add a check here when:

- a load-bearing structural invariant is hard to phrase as behaviour
  (e.g. import-cycle prevention via subprocess load),
- and the failure mode is impossible to detect via the public API.

If a check can be expressed as a behaviour test, do that instead.
