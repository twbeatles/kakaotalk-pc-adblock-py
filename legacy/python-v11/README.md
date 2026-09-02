# Python v11 reference implementation

Archived layout-only engine used as the golden/regression reference for the Rust port.

```powershell
$env:PYTHONPATH = (Resolve-Path ..\..\).Path + "\legacy\python-v11"
python kakaotalk_layout_adblock_v11.py --self-check --json
python -m kakao_adblocker.dev.export_fixture_decisions --check
```

Do not use this as the default user-facing app. Ship `dist/KakaoTalkLayoutAdBlocker_v11.exe`.
