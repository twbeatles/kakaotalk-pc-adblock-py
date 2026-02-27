# AI Context: KakaoTalk Layout AdBlocker v11

## Project Snapshot

- Platform: Windows
- Runtime: Python 3.9+
- Version line: `v11`
- Scope: Layout-only ad blocking (no hosts, no DNS flush, no AdFit registry writes)
- Non-Windows execution: fail-fast with message and exit code `2`
- Polling model: adaptive (active 100ms / idle 500ms by default)

## Runtime Entry

- Main script: `kakaotalk_layout_adblock_v11.py`
- Legacy script: `카카오톡 광고제거 v10.0.py` (deprecated notice only)
- `--dump-tree` runs in a lightweight path without UI/tray module import
- package `kakao_adblocker` exports are lazy-resolved via `__getattr__`

## Architecture

- `config.py`
  - `LayoutSettingsV11`, `LayoutRulesV11`
  - AppData path: `%APPDATA%\KakaoTalkAdBlockerLayout`
  - advanced perf knobs: `idle_poll_interval_ms`, `pid_scan_interval_ms`, `cache_cleanup_interval_ms`
  - missing new perf fields are backfilled with safe defaults
- `event_engine.py`
  - `LayoutOnlyEngine`: watch/apply polling loops
  - main window detection uses `main_window_classes` from rules
  - ad candidate filtering uses `ad_candidate_classes` + `Chrome Legacy Window` signature
  - hidden/moved windows are restored when blocking is disabled or engine stops
  - cache dictionaries are protected by a shared lock
  - process-id scan and cache cleanup are interval-throttled for idle CPU savings
  - default idle->active detection target is <= 500ms
- `layout_engine.py`
  - Main/lock view resize formulas
  - Aggressive bottom-banner heuristics
  - short ASCII ad tokens are word-boundary matched to reduce false positives
- `ui.py`
  - `TrayController` (status, toggle, aggressive mode, startup, logs, release page, exit)
  - startup notice is skipped when launching minimized
  - startup setting is synchronized from registry on app start
  - status text includes last error and last tick context
  - pystray/Pillow are loaded lazily when tray setup starts
- `services.py`
  - process scan, startup registry, shell/open-url helpers

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
- `kakaotalk_adblock.spec` explicitly includes lazy-import modules (`kakao_adblocker.app`, `kakao_adblocker.ui`, `pystray`, `PIL`) in `hiddenimports`.

## Legacy Archive

Legacy code/assets were moved under `legacy/`:

- `legacy/kakao_adblocker/legacy.py`
- `legacy/backup/*`
- `legacy/tools/*`
- `legacy/configs/*`
- `legacy/scripts/*`
