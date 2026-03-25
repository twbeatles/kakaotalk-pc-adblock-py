# Implementation Audit 2026-03-25

## Implementation Status

- Implemented on this branch:
- lazy runtime path helpers (`resolve_app_data_dir`, `get_runtime_paths`) with compatibility aliases retained
- startup-launch shell wait reordering before `Tk()` / tray construction
- structured self-check records with `--json`, core vs optional exit behavior, and startup trace/report plumbing
- logger handler remove+close cleanup plus non-propagating fallback logger behavior
- workspace-local pytest temp usage in `dev_check.ps1` / `smoke_check.ps1`
- release URL correction to GitHub releases and explicit PyInstaller `.ico` wiring

## Scope

This review compared the current implementation against `CLAUDE.md`, `README.md`, core runtime modules, tests, and build scripts.

The tray visibility bug fixed on 2026-03-25 is intentionally excluded from the findings below. This document focuses on additional latent risks and worthwhile follow-up work.

## Validation Snapshot

- `python -m pyright`: `0 errors`, `1 warning` (`psutil` source resolution only)
- `python -m pytest -q --basetemp .pytest_tmp`: `151 passed`
- `python -m PyInstaller --noconfirm --clean --distpath dist --workpath build kakaotalk_adblock.spec`: build succeeded
- `python kakaotalk_layout_adblock_v11.py --self-check`: failed in the current restricted environment due to `APPDATA` write, logging file open, `tasklist`, and Run-registry access limits

The codebase is generally in a healthy state. The main open risks are startup-path timing, environment-coupled diagnostics, and release-tooling robustness.

## Findings

### 1. High: `APPDATA` path resolution is eager and side-effectful at import time

- Evidence: `kakao_adblocker/config.py:41-50`
- `get_app_data_dir()` calls `path.mkdir(...)` during module import, and `APPDATA_DIR = get_app_data_dir()` is evaluated immediately.
- Impact:
  - A locked or redirected `%APPDATA%` can break import before `main()`, fallback logging, or `--self-check` can report anything useful.
  - Build/test scripts cannot reliably redirect runtime state after import because the path constants are already frozen.
  - This also makes packaged smoke validation more brittle than necessary.
- Recommendation:
  - Make appdata resolution lazy.
  - Split `resolve_app_data_dir()` from `ensure_app_data_dir()`.
  - Delay directory creation until the first real file operation or self-check step.

### 2. High: startup-launch creates the Tk window before shell-readiness wait

- Evidence: `kakao_adblocker/app.py:165-170`, `kakao_adblocker/ui.py:91-93`
- In the `--startup-launch` path, `tk.Tk()` and `TrayController(...)` are created before `StartupManager.wait_for_shell_ready()`.
- Impact:
  - Login/startup launches can still create a visible window before Explorer/tray readiness is confirmed.
  - This can produce startup flicker or race with tray initialization even if later logic hides the window.
  - It weakens the intent of the existing shell-readiness safeguard.
- Recommendation:
  - Move shell-readiness waiting ahead of `tk.Tk()` and `TrayController(...)` creation when `--startup-launch` is active.
  - Add a regression test that asserts shell wait happens before UI construction on startup launch.

### 3. Medium: packaged smoke check is coupled to optional machine permissions

- Evidence: `scripts/build_release.ps1:77-80`, `kakao_adblocker/app.py:98-114`
- The release build currently gates success on `--self-check`, and that self-check requires all of the following to pass:
  - `%APPDATA%` write
  - logging file open
  - `tasklist`
  - Run-registry read/write access
  - Tk boot
  - tray import
- Impact:
  - A healthy EXE can fail release packaging on locked-down machines where only optional features are restricted.
  - This is especially risky for corporate Windows environments, CI runners, or sandboxed build hosts.
- Recommendation:
  - Split self-check into `core` and `optional` groups, or add a dedicated packaged-smoke mode.
  - For build smoke, isolate `%APPDATA%` to a temp directory and treat startup-registry capability as non-blocking unless explicitly requested.

### 4. Medium: logger reinitialization clears handlers without closing them

- Evidence: `kakao_adblocker/logging_setup.py:29-49`, `kakao_adblocker/app.py:83-91`
- Both the normal logger setup and fallback logger path call `logger.handlers.clear()` but do not close the removed handlers first.
- Impact:
  - Repeated initialization in the same process can leave file handles open.
  - This can interfere with log rotation, tests, embedded execution, or future control-panel style relaunch flows.
- Recommendation:
  - Iterate existing handlers, remove and close each one explicitly.
  - Set `logger.propagate = False` to avoid duplicate emission if the root logger is configured by another host process.

### 5. Medium: local verification scripts are still sensitive to host temp/permission quirks

- Evidence: `scripts/dev_check.ps1:21-22`
- `dev_check.ps1` runs plain `pytest -q` with the default pytest temp base.
- Observed in this workspace: default pytest temp resolution hit `PermissionError` on `%TEMP%\\pytest-of-<user>`, while `--basetemp .pytest_tmp` passed cleanly.
- Impact:
  - Developers can see false-negative test failures unrelated to the code.
  - This makes local validation noisier and harder to trust.
- Recommendation:
  - Run pytest with a workspace-local base temp by default, for example `--basetemp .pytest_tmp`.
  - Optionally clean that directory at the end of the script.

### 6. Low: release-link naming and destination are inconsistent

- Evidence: `kakao_adblocker/services.py:323-327`
- `ReleaseService.open_releases_page()` opens the repository root, not the releases page.
- Impact:
  - This is not a runtime bug, but the naming is misleading.
  - It makes maintenance and UI wording less precise than the rest of the project.
- Recommendation:
  - Either rename the method to `open_repository_page()` or change the URL to the actual releases page.

## Additions Worth Implementing

- Add an automated packaged tray smoke path.
- Rationale: the recent tray visibility bug escaped because current coverage is unit-test heavy and packaged GUI behavior is still manual-only.
- Practical option: add a hidden debug flag that writes a short startup trace file containing `tray_import_ok`, `tray_setup_ok`, `tray_visible_requested`, and `startup_launch` outcomes.

- Add an isolated build-smoke environment to `scripts/build_release.ps1`.
- Practical option: inject a temporary `%APPDATA%` directory for the packaged self-check process and optionally allow `-PythonExe` parity with `dev_check.ps1`.

- Add an explicit application `.ico` to the PyInstaller spec.
- Evidence: `kakaotalk_adblock.spec` currently sets version metadata but no custom `icon=...`.
- Impact: Explorer/taskbar branding can diverge from the in-app tray icon.

- Add a structured diagnostic output mode.
- Practical option: `--self-check --json` or `--health-report <path>`.
- This would help support, regression triage, and future automation more than parsing localized stdout text.

## Suggested Execution Order

1. Refactor `APPDATA` handling to be lazy and non-fatal at import time.
2. Move startup shell-wait ahead of Tk/UI construction.
3. Split packaged smoke into core vs optional capability checks.
4. Fix logger handler cleanup.
5. Harden `dev_check.ps1` with workspace-local pytest temp storage.
6. Clean up release-link naming and add packaging polish items.

## Closing Note

The implementation is already much more disciplined than a typical Windows utility repo of this size. Most remaining work is not engine correctness; it is startup-path robustness, diagnosability, and build reproducibility.
