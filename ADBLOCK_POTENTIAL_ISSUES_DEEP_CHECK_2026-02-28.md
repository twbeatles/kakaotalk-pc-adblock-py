# KakaoTalk 광고차단 구현 심층 점검 (2026-02-28 반영본)

작성일: 2026-02-28  
최종 갱신: 2026-02-28  
기준: `README.md`, `CLAUDE.md`, `GEMINI.md`, `kakao_adblocker/*`, `tests/*`

## 점검 요약

- 잠재 이슈 문서에서 제안된 P1~P3 및 추가 권장 항목을 코드/테스트/문서에 반영했다.
- `--self-check`, startup 역롤백, UI 큐 디스패치, 트레이 import TTL 재시도, 설정 원자 저장이 반영되었다.
- 회귀 검증 결과: `pytest -q` 기준 `80 passed`.

## 반영 완료 항목

### 1) 시작프로그램 토글 정합성 (P1)

- 레지스트리 변경 후 설정 저장 실패 시 레지스트리 역롤백을 수행한다.
- 근거: `kakao_adblocker/ui.py::toggle_startup`.
- 테스트:
  - `tests/test_tray_controller_v11.py::test_toggle_startup_rolls_back_when_save_fails`

### 2) `main()` cleanup 보장 (P1)

- UI 실행 구간을 `try/finally`로 감싸 `stop_tray()`/`engine.stop()` cleanup을 보장한다.
- 근거: `kakao_adblocker/app.py::main`.
- 테스트:
  - `tests/test_app_v11.py::test_main_cleans_up_when_controller_start_fails`
  - `tests/test_app_v11.py::test_main_cleans_up_when_mainloop_fails`

### 3) 트레이 스레드-UI 스레드 브릿지 (P2)

- tray callback은 queue enqueue 후 Tk 메인스레드 drain에서 실행되도록 변경했다.
- 근거: `kakao_adblocker/ui.py::_safe_after`, `_drain_ui_queue`.
- 테스트:
  - `tests/test_tray_controller_v11.py::test_queue_bridge_processes_callbacks_in_order`

### 4) 트레이 모듈 import 재시도 정책 (P2)

- pystray/Pillow import 실패 시 TTL(30초) 내 재시도를 억제하고 TTL 경과 후 자동 재시도한다.
- 근거: `kakao_adblocker/ui.py::_load_tray_modules`.
- 테스트:
  - `tests/test_tray_controller_v11.py::test_load_tray_modules_retries_after_ttl`
  - `tests/test_tray_controller_v11.py::test_load_tray_modules_resets_failure_timestamp_on_success`

### 5) `_last_log` 동시성 보호 (P3)

- `_error_log_lock`으로 `_last_log` 갱신/정리 임계영역을 보호한다.
- 근거: `kakao_adblocker/event_engine.py::_set_error`.
- 테스트:
  - `tests/test_engine_v11.py::test_engine_set_error_is_thread_safe_under_stress`

### 6) 설정 파일 원자 저장

- settings/rules 저장을 temp 파일 + `os.replace` 방식으로 전환했다.
- 근거: `kakao_adblocker/config.py::_atomic_write_text`.
- 테스트:
  - `tests/test_config_v11.py::test_settings_save_writes_json_atomically`
  - `tests/test_config_v11.py::test_rules_save_writes_json_atomically`
  - `tests/test_config_v11.py::test_settings_save_preserves_existing_file_on_atomic_replace_failure`

### 7) `--self-check` 진단 모드

- 진단 항목: APPDATA 쓰기, `tasklist`, Run 레지스트리 접근, 트레이 모듈 import.
- 출력: `[OK]/[FAIL]` 라인 + summary.
- 종료 코드: 전부 통과 시 `0`, 하나라도 실패 시 `1`.
- 근거: `kakao_adblocker/app.py::_run_self_check`.
- 테스트:
  - `tests/test_app_v11.py::test_self_check_path_skips_engine_and_ui`
  - `tests/test_services_v11.py` probe 메서드 테스트

### 8) 복원 실패 상태 수동 초기화

- `LayoutOnlyEngine.reset_restore_failures()` 추가.
- 트레이 메뉴 `복원 실패 초기화` 추가.
- 근거: `kakao_adblocker/event_engine.py`, `kakao_adblocker/ui.py`.
- 테스트:
  - `tests/test_engine_v11.py::test_engine_can_reset_restore_failures_state`
  - `tests/test_tray_controller_v11.py::test_menu_reset_restore_failures_calls_engine`

## `.spec` 점검 결과

- `kakaotalk_adblock.spec`는 현재 변경사항에 대해 **추가 수정 불필요**.
- 이유:
  - `kakao_adblocker.services` hiddenimports 포함(진단 메서드 경로 커버)
  - `pystray`, `PIL` 및 `collect_submodules(...)` 포함(`--self-check` import 검사와 런타임 트레이 경로 커버)
  - 신규 외부 의존성 없음

## 문서 정합성 반영

- `README.md`: 신규 기능/안정화 항목 반영 + legacy v10 경로 반영
- `CLAUDE.md`: 루트 v10 제거 및 legacy 경로 반영
- `GEMINI.md`: `--self-check`, UI 큐 디스패치, TTL 재시도, probe 메서드 반영
- `legacy/README.md`: `legacy/카카오톡 광고제거 v10.0.py` 보관 항목 반영

## 검증 결과

- `pytest -q`: `80 passed`
- `python kakaotalk_layout_adblock_v11.py --self-check`:
  - 환경에 따라 `pystray` 미설치 시 트레이 import 항목이 `FAIL`로 표시될 수 있음(정상 동작).
