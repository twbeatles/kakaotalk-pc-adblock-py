# Rust workspace

Python v11 remains the default release. This tree is the native port.

## Status

- **Done:** `kakao-core` golden parity against `tests/fixtures/golden/*.json` (10/10).
- **Not done:** Win32, shadow mode, mutation, tray, updater. See the remaining plan.

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
