# Public release code audit — 2026-10-01

This audit covers the public AwnPhen runtime and Awn Studio release surface. It does not re-tune scientific thresholds or alter the frozen validation-selected measurement policy.

## Scope

- public Python package and wheel contents
- canonical model resolution and provenance
- automatic calibration entry points
- Awn Studio local HTTP service
- source/package bundle consistency
- release metadata and repository hygiene
- lightweight static analysis

## Findings fixed

### P1 — public calibration code drifted from the frozen scientific runtime

A release-only warning-suppression change had introduced fallback behavior inside the grid-calibration implementation. Although the common path was unaffected, this changed failure behavior for extreme inputs.

**Fix:** restored the public calibration module byte-for-byte from the frozen scientific runtime. Failure handling now lives at the public entry point instead of inside the scientific algorithm.

### P1 — automatic calibration could fail open

The CLI discarded grid-calibration QC and Awn Studio treated failed grid QC as a warning while still accepting the inferred scale. This could produce plausible-looking millimetre values from an invalid calibration.

**Fix:** automatic calibration now requires `affine_scale_adequate == true`. Failed QC instructs the user to perform manual calibration.

The original 1920×1312 editing-demo image does not satisfy grid-calibration QC and is therefore no longer used as the CLI inference demo. The CLI demo now uses validation image `IMG_9710`, for which the frozen calibration returns 59 px per 5 mm on both axes with all QC gates passing. The locked test set remains untouched.

### P1 — canonical model download was mutable

The public resolver downloaded `best.pt` from the current repository head. A future accidental replacement on the Hub could therefore change the model used by the same AwnPhen package version.

**Fix:** the default model is pinned to Hugging Face revision
`7622e142fd3ab720c19f9ed1de085f998eb8c2e6` and verified against SHA-256
`a7a5cf23bf5d35266e4fa6b1dc0244ee802026a381548bcd202f04b3ebf42097`.

### P2 — obsolete launcher wrote into the installation tree

An unused internal launcher remained in the public bundle and attempted to write PID/log files beneath its package root.

**Fix:** removed the unused launcher from both the readable Awn Studio source tree and the packaged bundle.

### P2 — local-service origin validation trusted the Host header

The model service accepted an Origin hostname derived from the request Host header in addition to localhost names.

**Fix:** browser write requests are now limited to HTTP origins on `localhost` or `127.0.0.1` at the supported local ports. The service itself defaults to binding `127.0.0.1`.

### P2 — Studio report URL did not match the generated file

A completed job advertised `.../image/report.html` although Awn Studio writes `integration_report.html` at the job root.

**Fix:** job metadata now points to the file that is actually generated and served.

### P2 — inference dependency allowed silent Ultralytics drift

The release accepted any Ultralytics 8.x version.

**Fix:** the public runtime now pins `ultralytics==8.4.140`, matching the canonical ROCm environment and the CPU smoke-test environment.

### P2 — no automated release gate

The initial public repository had no CI enforcing source/bundle synchronization or wheel contents.

**Fix:** added GitHub Actions release checks for Python 3.10/3.12, release tests, JavaScript syntax, wheel construction, and required bundled assets.

### P3 — quick-start virtual environment was not activated

The README created a venv and then immediately invoked `pip`, which could install into the caller's active Python environment.

**Fix:** documented explicit environment activation and `python -m pip`.

## Verification

- release tests: 9 passed
- high-signal Ruff checks (`F,E9`): passed
- dependency vulnerability scan (`pip-audit`): no known vulnerabilities found
- JavaScript syntax checks: passed
- canonical scientific runtime comparison: no unexpected drift
- pinned Hugging Face revision: resolved successfully
- canonical checkpoint SHA-256: matched
- replacement CLI demo calibration: 59 px / 5 mm on x and y; QC passed
- full CPU demo: completed through detection, reconciliation, Unified Growth, representative selection, and root normalization

## Residual limitations

1. The current Workbench contract carries one scalar `mm_per_px`. The calibration subsystem can estimate x/y periods separately, but anisotropic physical scaling is not represented end-to-end. This predates the public packaging and is intentionally not changed under the frozen scientific policy.
2. Awn Studio source is mirrored into the package bundle. A synchronization test prevents silent divergence, but a future release can simplify this by making one tree authoritative during build.
3. CI intentionally does not run heavyweight model inference. Full model smoke tests remain a release-time validation step.
4. Full Ruff output contains non-behavioural style and modernization suggestions in the frozen scientific runtime. These are not treated as release blockers and should not be applied mechanically to frozen code.
5. Ultralytics is pinned, but the entire transitive scientific dependency graph is not bit-for-bit locked across platforms. A future reproducibility release should provide tested platform-specific constraints rather than forcing one platform's PyTorch build onto every user.
