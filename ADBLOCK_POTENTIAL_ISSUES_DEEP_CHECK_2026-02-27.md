# KakaoTalk 광고차단 구현 심층 점검 (조치 완료 업데이트)

작성일: 2026-02-27  
최종 갱신: 2026-02-28  
점검/반영 기준: `CLAUDE.md`, `README.md`, `kakao_adblocker/*`, `tests/*`

## 요약

- 초기 점검 문서의 P1~P3, 추가 권장 3개, 테스트 보강 5개를 모두 반영했다.
- 구현/문서/테스트를 동기화했고 회귀 테스트를 통과했다.
- 검증 결과: `pytest -q` 기준 `64 passed in 0.20s`.

## 조치 완료 항목

### P1-1. 한국어 리터럴 인코딩

- 완료: rules/UI 기본 문자열을 UTF-8 정상값 기준으로 유지하고, rules 문자열 무결성 self-check를 추가했다.
- 완료: `main_window_titles`, `aggressive_ad_tokens`에서 mojibake 시그니처/`�` 감지 시 load warning을 기록한다.
- 근거 파일: `kakao_adblocker/config.py`, `kakao_adblocker/ui.py`, `tests/test_config_v11.py`

### P1-2. `stop()` thread timeout 방어

- 완료: `stop_event/wake_event` 설정 후 watch thread `join(2.0)` 재검사 로직을 추가했다.
- 완료: timeout 시 `"stop: watch thread did not terminate within 2.0s"`를 상태(`last_error`)와 로그에 기록하고 종료 절차를 계속한다.
- 근거 파일: `kakao_adblocker/event_engine.py`, `tests/test_engine_v11.py`

### P1-3. 원복 스냅샷 선삭제 문제

- 완료: `_restore_hidden_windows()`를 성공 제거/실패 보존 방식으로 변경했다.
- 완료: 복원 실패 창은 스냅샷을 유지해 재시도 가능하게 했다.
- 완료: 복원 실패 상태를 `EngineState.restore_failures`, `EngineState.last_restore_error`로 노출한다.
- 근거 파일: `kakao_adblocker/event_engine.py`, `kakao_adblocker/ui.py`, `tests/test_engine_v11.py`, `tests/test_tray_controller_v11.py`

### P2-1. 설정 저장 예외 처리

- 완료: UI 공통 저장 helper를 도입해 `save()` 실패 시 값 롤백 + warning 로그 + 상태 갱신을 수행한다.
- 완료: 적용 대상은 `toggle_blocking`, `toggle_startup`, `toggle_aggressive_mode`, `_sync_startup_setting`.
- 완료: `toggle_blocking`은 저장 성공 후에만 `engine.set_enabled()`를 호출한다.
- 근거 파일: `kakao_adblocker/ui.py`, `tests/test_tray_controller_v11.py`

### P2-2. psutil 실패 시 PID 폴백

- 완료: psutil 초기화/루프 레벨 실패 시 `tasklist` 폴백으로 넘어가도록 변경했다.
- 완료: per-process 예외 격리(continue)는 유지했다.
- 근거 파일: `kakao_adblocker/services.py`, `tests/test_services_v11.py`

### P2-3. 에러 로그 맵 상한

- 완료: `_last_log` 키 상한을 추가했다.
- 정책: `MAX_ERROR_LOG_KEYS=512`, 초과 시 oldest 기준 prune로 `384`까지 축소.
- 근거 파일: `kakao_adblocker/event_engine.py`, `tests/test_engine_v11.py`

### P3-1. `_tick_status` 종료 경합

- 완료: `winfo_exists()` 체크 + `root.after(...)` 예외 방어를 추가했다.
- 근거 파일: `kakao_adblocker/ui.py`, `tests/test_tray_controller_v11.py`

## 추가 권장 항목 반영 결과

1. 원복 실패 상태 가시화: 완료 (`EngineState` 필드 추가 + 트레이 상태 문자열 노출).
2. rules 문자열 self-check: 완료 (load warning 연동).
3. broken 백업 정리 정책: 완료 (`30일 초과 삭제 + 최신 10개 유지`).

## 테스트 보강 반영 결과

1. `stop()` timeout 시나리오: 추가/통과.
2. 복원 실패 재시도 시나리오: 추가/통과.
3. `settings.save()` 예외 롤백 시나리오: 추가/통과.
4. psutil 실패 -> `tasklist` 폴백 시나리오: 추가/통과.
5. 한국어 핵심 토큰 무결성 시나리오: 추가/통과.

## 문서 동기화 반영

- `ADBLOCK_ALGORITHM_BASELINE_V11.md`: 신규 안전 규칙(stop-timeout, 복원 실패 상태 노출, broken 백업 혼합 정리, rules self-check) 반영.
- `README.md`: 사용자 관점 변경점(복원 실패 상태 표시, 설정 저장 실패 롤백, psutil 폴백, broken 백업 자동 정리, status tick 방어) 반영.
- `.spec` 점검 결과를 반영해 `kakaotalk_adblock.spec` hiddenimports에 `kakao_adblocker.logging_setup`, `kakao_adblocker.services`를 명시해 onefile 안정성을 보강.

## 잔여 리스크

- 현재 기준 필수 반영 항목은 없음.
- 운영 관점 확장 과제로는 장시간 실환경 성능 계측 자동화 정도가 남는다.
