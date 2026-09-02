# Rust workspace

This is the **default** KakaoTalk Layout AdBlocker implementation.

Python v11 is archived at `../legacy/python-v11/` and kept for golden/regression tests.

## Status

- `kakao-core` golden 10/10
- `kakao-win32` + tray
- `kakao-app` (`kakao-adblock-rs`): `--shadow`, `--apply`, dump, self-check, tray UI
- Release EXE: `../dist/KakaoTalkLayoutAdBlocker_v11.exe` via `../scripts/build_release.ps1 -NoSign`

## Docs

- Full contract: [`../kakaotalk_rust_migration_plan.md`](../kakaotalk_rust_migration_plan.md)
- **Next agent starts here:** [`../docs/superpowers/plans/2026-09-02-rust-native-remaining.md`](../docs/superpowers/plans/2026-09-02-rust-native-remaining.md)
- Algorithm freeze: [`../CLAUDE.md`](../CLAUDE.md)

## Commands

```powershell
python -m kakao_adblocker.dev.export_fixture_decisions --check
cd rust
cargo test --workspace
cargo clippy --all-targets --all-features -- -D warnings
cargo fmt --all -- --check
```
