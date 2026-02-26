# AI Context: KakaoTalk Layout AdBlocker v11

## Project Snapshot

- Platform: Windows
- Runtime: Python 3.9+
- Version line: `v11`
- Scope: Layout-only ad blocking (no hosts, no DNS flush, no AdFit registry writes)

## Runtime Entry

- Main script: `kakaotalk_layout_adblock_v11.py`
- Legacy script: `카카오톡 광고제거 v10.0.py` (deprecated notice only)

## Architecture

- `config.py`
  - `LayoutSettingsV11`, `LayoutRulesV11`
  - AppData path: `%APPDATA%\KakaoTalkAdBlockerLayout`
- `event_engine.py`
  - `LayoutOnlyEngine`: watch/apply polling loops
- `layout_engine.py`
  - Main/lock view resize formulas
  - Aggressive bottom-banner heuristics
- `ui.py`
  - `TrayController` (status, toggle, startup, logs, release page, exit)
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
- `kakaotalk_adblock_v10.spec` (legacy filename, v11 build target)

## Legacy Archive

Legacy code/assets were moved under `legacy/`:

- `legacy/kakao_adblocker/legacy.py`
- `legacy/backup/*`
- `legacy/tools/*`
- `legacy/configs/*`
- `legacy/scripts/*`
