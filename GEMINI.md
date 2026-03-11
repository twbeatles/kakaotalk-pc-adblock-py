# AI Context: KakaoTalk Layout AdBlocker v11

## Project Snapshot

- Platform: Windows
- Runtime: Python 3.9+
- Version line: `v11`
- Scope: Layout-only ad blocking (no hosts, no DNS flush, no AdFit registry writes)
- Non-Windows execution: fail-fast with message and exit code `2`
- Polling model: adaptive (active 50ms / idle 200ms by default)

## Runtime Entry

- Main script: `kakaotalk_layout_adblock_v11.py`
- Legacy script: `legacy/카카오톡 광고제거 v10.0.py` (deprecated notice only)
- `--dump-tree` runs in a lightweight path without UI/tray module import
- `--self-check` runs diagnostics only (no UI/tray/engine start)
- package `kakao_adblocker` exports are lazy-resolved via `__getattr__`
- static analysis baseline is fixed by root `pyrightconfig.json`; `requirements-dev.txt` includes `pyright`

## Architecture

- `config.py`
  - `LayoutSettingsV11`, `LayoutRulesV11`
  - AppData path: `%APPDATA%\KakaoTalkAdBlockerLayout`
  - advanced perf knobs: `idle_poll_interval_ms`, `pid_scan_interval_ms`, `cache_cleanup_interval_ms`
  - missing new perf fields are backfilled with safe defaults
  - new rules flags: `hide_bottom_banner_without_token=false`, `close_empty_eva_child_requires_ad_signal=true`
  - new rules key: `popup_ad_classes=["AdFitWebView"]`
  - rules loader falls back `ad_candidate_classes` to `main_window_classes` when missing/invalid
  - malformed/non-object JSON input is backed up as `*.broken-YYYYMMDD-HHMMSS` and then self-healed with default JSON
  - inverted banner bounds (`banner_min_height_px > banner_max_height_px`) are auto-normalized
  - broken-backup cleanup policy is enforced on every load (`>30 days` purge + keep latest `10`)
  - rules string integrity self-check warns on mojibake signatures / replacement char (`�`)
  - `consume_load_warnings()` exposes startup warnings to app layer
- `event_engine.py`
  - `LayoutOnlyEngine`: single watch+apply polling loop
  - when blocking is OFF, watch/apply both pause and loop waits in low-cost mode (`1.0s`)
  - main window detection uses `main_window_classes` from rules
  - candidate and confirmed main-window counts are tracked separately; apply uses confirmed handles only
  - ad candidate filtering uses `ad_candidate_classes` (default: `EVA_Window_Dblclk`, `EVA_Window`) + legacy exact/substring signatures
  - non-main top-level KakaoTalk windows are scanned for direct-child popup classes and matched `AdFitWebView`-style popups are closed/hidden/zero-sized with upstream parity behavior
  - empty-title main windows can still be detected via child signature fallback (`OnlineMainView` / `LockModeView`)
  - synchronous warm-up scan/apply on engine start runs only when enabled
  - empty-string text cache uses short TTL refresh to reduce startup detection lag
  - hidden/moved windows are restored when blocking is disabled or engine stops
  - once stop begins, new hide/close/apply work is blocked so a timed-out join does not re-hide windows after restore
  - aggressive-hide windows are restored immediately when aggressive mode is turned OFF, followed by an immediate rescan/reapply
  - hidden windows are automatically restored when they no longer match aggressive/legacy signatures, preventing stale hides
  - stop join timeout (`2.0s`) emits state/log warning and proceeds with shutdown flow
  - restore failures keep snapshots for retry on next restore cycle
  - `EngineState` includes `restore_failures` / `last_restore_error`
  - `WindowIdentity(hwnd,pid,class)` keyed caches protect against HWND reuse side effects
  - watch scan path avoids geometry/visibility calls; dump-tree path still collects full geometry
  - process-id scan and cache cleanup are interval-throttled for idle CPU savings
  - process scan warnings (psutil failure, tasklist fallback/failure) are propagated to status/log (`last_error`)
  - default idle->active detection target is <= 200ms
  - `report_warning()` allows startup warning propagation to tray status context, and the prioritized startup warning is applied after engine start so it remains visible
- `layout_engine.py`
  - Main/lock view resize formulas
  - aggressive detection separates token signals from geometry-only bottom-banner heuristics
  - token-less bottom `Chrome_WidgetWin_*` panels are not hidden by default; subtree token signals can still trigger aggressive hide
  - short ASCII ad tokens are word-boundary matched to reduce false positives
- `protocols.py`
  - structural typing boundaries for Win32 API / joinable thread / UI root / engine state
  - keeps runtime module contracts compatible with test doubles
- `ui.py`
  - `TrayController` (status, toggle, aggressive mode, startup, restore-failure reset, logs, release page, exit)
  - startup notice is skipped when launching minimized
  - minimized-start requests are ignored when tray modules are unavailable
  - tray readiness is confirmed via startup signal; startup timeout (`1.5s`) disables tray mode
  - unexpected tray runtime exit disables tray mode and restores main window visibility
  - window close action switches from hide to shutdown when tray is unavailable
  - startup setting is synchronized from registry on app start
  - startup toggle rolls registry back on settings-save failure
  - setting save failures roll back values (`enabled`, `run_on_startup`, `aggressive_mode`)
  - aggressive mode toggle is pushed into the engine immediately after a successful save
  - status text includes last error and last tick context
  - status text shows confirmed main-window count and appends candidate count only when larger
  - status text labels cumulative counters explicitly (`누적 숨김`, `누적 리사이즈`)
  - status text includes restore failure count/context when present
  - controller-local UI warnings (`tray unavailable`, startup registry rollback issues) surface when engine error is absent
  - pystray/Pillow are loaded lazily and retried after TTL (30s) when import fails
  - tray callbacks are queued and drained on Tk main thread
  - status tick scheduling (`root.after`) also swallows shutdown-race errors
  - startup load-warning propagation uses priority (`heal failure > auto-heal > others`)
- `services.py`
  - process scan, startup registry, shell/open-url helpers
  - psutil process scan uses per-process exception isolation
  - psutil init/loop failure falls back to `tasklist` scan
  - `ProcessInspector.consume_last_warning()` provides scan diagnostics to the engine
  - `StartupManager.probe_access()` validates both Run-registry read and write access
  - diagnostics helpers: `ProcessInspector.probe_tasklist()`, `StartupManager.probe_access()`
- `win32_api.py`
  - user32 API bindings explicitly define `argtypes/restype`
  - exposes `get_last_error()` for debug telemetry on ShowWindow/SetWindowPos failures

## Key Resize Rules

- `OnlineMainView*`:
  - width = `parent_width - 2`
  - height = `parent_height - 31`
- `LockModeView*`:
  - width = `parent_width - 2`
  - height = `parent_height`

## Important Files

- `layout_settings_v11.json`
- `layout_rules_v11.json`
- `kakaotalk_adblock.spec`
- `legacy/specs/kakaotalk_adblock_v10.spec` (legacy spec archive)

## Build Notes

- `kakaotalk_adblock.spec` resolves entry script and data files from project-root absolute paths for stable `pyinstaller` invocation.
- `kakaotalk_adblock.spec` explicitly includes runtime modules (`kakao_adblocker.app`, `kakao_adblocker.config`, `kakao_adblocker.event_engine`, `kakao_adblocker.layout_engine`, `kakao_adblocker.logging_setup`, `kakao_adblocker.services`, `kakao_adblocker.ui`, `kakao_adblocker.win32_api`, `pystray`, `PIL`, `tkinter`) in `hiddenimports`.
- `kakaotalk_adblock.spec` also includes `kakao_adblocker.protocols` to keep typed runtime imports explicit in onefile packaging.
- `kakaotalk_adblock.spec` also includes `collect_submodules("pystray")` and `collect_submodules("PIL")` to avoid onefile runtime import misses.
- `kakaotalk_adblock.spec` includes package root `kakao_adblocker` so lazy exports remain importable in onefile builds and tooling paths.
- popup parity (`popup_ad_classes` / `AdFitWebView`) stays inside existing modules, so no extra hidden-import or hook change is required.
- `--self-check` now exercises dynamic Tk diagnostics as well, so explicit `tkinter` hidden imports keep onefile packaging deterministic.

## Legacy Archive

Legacy code/assets were moved under `legacy/`:

- `legacy/kakao_adblocker/legacy.py`
- `legacy/backup/*`
- `legacy/tools/*`
- `legacy/configs/*`
- `legacy/scripts/*`
- `legacy/카카오톡 광고제거 v10.0.py`
- archived legacy files keep per-file `pyright` directives to preserve behavior while maintaining repo-wide type-check pass
