# Rust workspace

Python v11 remains the default release. This tree is the native port.

## Status

- **Done:** `kakao-core` golden 10/10, `kakao-win32`, `kakao-app` (`kakao-adblock-rs`) with `--shadow`, `--apply`, dump, self-check, updater verify.
- **Not the default release:** Python v11 still ships. Do not archive Python until live DoD.
- **Manual:** tray icon UI, live KakaoTalk matrix.

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
