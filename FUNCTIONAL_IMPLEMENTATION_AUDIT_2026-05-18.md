# Functional Implementation Audit Follow-up - 2026-05-18

## Scope

This document records the follow-up implementation pass for the v11 layout-only ad blocker audit.

Checked documentation surfaces:

- `README.md`
- `CLAUDE.md`
- `GEMINI.md`
- `legacy/README.md`

Checked ignore surface:

- `.gitignore`

## Resolved Findings

1. CI release verification now calls `scripts/build_release.ps1 -NoSign` without `-SkipSmokeCheck`, so hosted CI runs the built EXE packaged strict self-check.
2. `Invoke-StartupSmoke` no longer relies on unbounded `Start-Process -Wait`; it waits up to 60 seconds, kills the child process on timeout, restores `APPDATA`, and reports `packaged startup smoke timed out`.
3. Source-mode startup registration now treats an existing packaged command of `KakaoTalkLayoutAdBlocker_v11.exe --startup-launch --minimized` as healthy when the target EXE exists. Frozen mode still requires the current EXE command, and a direct UI toggle still writes the current-mode command.
4. Empty `EVA_ChildWindow` close counting now reflects confirmed window disappearance. A successful close request with a still-existing window is reported through `last_error` instead of increasing `closed_windows`.
5. Popup zero-size fallback and main child resize now include non-activating/no-z-order `SetWindowPos` flags; main child resize keeps `SWP_NOMOVE`.

## Markdown Consistency Updates

- `README.md` already reflects the implemented CI packaged self-check, startup smoke timeout, source-vs-packaged startup registration policy, confirmed empty-EVA close counting, and `SetWindowPos` flag behavior.
- `CLAUDE.md` already reflects the same runtime/build policy for future agent context.
- `GEMINI.md` was updated in this pass to remove the stale CI `-SkipSmokeCheck` wording and add the missing startup registration, close-counting, startup-smoke timeout, and `SetWindowPos` notes.
- `legacy/README.md` remains consistent because the active v11 runtime and CI do not target the legacy archive.

## `.gitignore` Review

No `.gitignore` change was required.

Verified coverage includes:

- generated build outputs: `build/`, `dist/`
- packaged/dev temp outputs: `.pytest_cache/`, `.pytest_tmp/`, `.tmp-packaged/`
- runtime diagnostics: `self-check.json`, `startup-trace.json`, `bootstrap-argv-report.json`
- window dumps: `window_dump_*.json`, `window_dump_series_*.json`
- self-heal backups and atomic-write temps: `*.broken-*`, `.layout_settings_v11.json*.tmp`, `.layout_rules_v11.json*.tmp`, `.selfcheck-write.tmp`
- logs: `*.log`, `window_inspection.log`, `adblock.log`

`git status --short --ignored` confirmed the current generated folders/files are ignored rather than pending for commit.

## Validation Snapshot

Completed during the implementation pass:

```text
pytest -q tests\test_services_v11.py tests\test_layout_engine_v11.py tests\test_release_pipeline_v11.py tests\test_engine_v11.py -q
PASS

.\scripts\dev_check.ps1
pyright: 0 errors, 0 warnings
pytest: 205 passed

python kakaotalk_layout_adblock_v11.py --self-check --json
exit_code: 0
checks: 7/7 passed
core_failed: 0
optional_failed: 0

powershell -ExecutionPolicy Bypass -File .\scripts\build_release.ps1 -NoSign
PASS
packaged strict self-check: PASS
startup smoke status: completed
signing: skipped by -NoSign

fresh packaged strict self-check
exit_code: 0
checks: 7/7 passed
core_failed: 0
optional_failed: 0
```

The release build initially hit a locked previous `dist\KakaoTalkLayoutAdBlocker_v11.exe`; the two existing processes running that EXE were stopped, then the fresh build completed successfully.

Fresh built EXE proof:

- path: `dist\KakaoTalkLayoutAdBlocker_v11.exe`
- size: `33166558` bytes
- SHA256: `1178F97A951E2D0DF48202303F0A33F405DFDA94F725096EA1B21DC00F507F9E`
