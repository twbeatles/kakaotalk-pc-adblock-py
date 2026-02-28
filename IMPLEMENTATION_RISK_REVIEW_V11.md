# KakaoTalk Layout AdBlocker v11 구현 리스크 점검 (최신)

작성일: 2026-02-27  
최종 갱신: 2026-02-28  
기준: 현재 코드베이스(`kakao_adblocker/*`, `tests/*`, `kakaotalk_adblock.spec`, `README.md`)

## 1) 반영 완료 항목

### P1-1. HWND 재사용 오동작 방어

- 조치: `WindowIdentity(hwnd,pid,class)` 기반 캐시/숨김 스냅샷 키 적용 유지
- 조치: 원복 시 `(pid,class)` 불일치면 원복 스킵
- 근거 파일: `kakao_adblocker/event_engine.py`
- 검증 테스트: `tests/test_engine_v11.py` 재사용 HWND 원복 스킵 케이스

### P1-2. stop timeout 방어

- 조치: `stop()`에서 watch thread `join(timeout=2.0)` 후 생존 여부 재검사
- 조치: timeout 시 고정 메시지(`stop: watch thread did not terminate within 2.0s`)를 상태/로그에 반영
- 조치: timeout이어도 종료 절차(원복/running=False)는 계속 진행
- 근거 파일: `kakao_adblocker/event_engine.py`
- 검증 테스트: `tests/test_engine_v11.py` stop timeout 경고 케이스

### P1-3. 원복 스냅샷 재시도 가능화

- 조치: `_restore_hidden_windows()`를 선삭제 방식에서 성공 제거/실패 보존 방식으로 변경
- 조치: 복원 실패 상태 누적(`restore_failures`, `last_restore_error`) 노출
- 근거 파일: `kakao_adblocker/event_engine.py`, `kakao_adblocker/ui.py`
- 검증 테스트: `tests/test_engine_v11.py` 원복 실패 재시도 케이스, `tests/test_tray_controller_v11.py` 상태 문자열 노출 케이스

### P2-1. 설정 저장 실패 롤백

- 조치: UI 설정 저장 공통 helper 도입(`_save_setting_attr`)
- 조치: `toggle_blocking`, `toggle_startup`, `toggle_aggressive_mode`, `_sync_startup_setting`에 롤백 적용
- 조치: `toggle_blocking`은 저장 성공 시에만 `engine.set_enabled` 수행
- 근거 파일: `kakao_adblocker/ui.py`
- 검증 테스트: `tests/test_tray_controller_v11.py` 저장 실패 롤백 케이스

### P2-2. JSON fallback + 백업 정리

- 조치: JSON 파손 시 `*.broken-YYYYMMDD-HHMMSS` 백업/경고 유지
- 조치: 백업 자동 정리 정책 반영(30일 초과 삭제 + 최신 10개 유지)
- 조치: rules 문자열 무결성 self-check(mojibake/`�`) 경고 추가
- 근거 파일: `kakao_adblocker/config.py`
- 검증 테스트: `tests/test_config_v11.py` 백업 정리/문자열 무결성 케이스

### P2-3. PID 스캔 폴백

- 조치: psutil 초기화/루프 실패 시 `tasklist` 폴백
- 조치: psutil per-process 예외 격리 유지
- 근거 파일: `kakao_adblocker/services.py`
- 검증 테스트: `tests/test_services_v11.py` 폴백 케이스

### P2-4. 에러 로그 맵 상한

- 조치: `_last_log` 크기 상한 도입(`MAX_ERROR_LOG_KEYS=512`, prune target `384`)
- 근거 파일: `kakao_adblocker/event_engine.py`
- 검증 테스트: `tests/test_engine_v11.py` 로그맵 prune 케이스

### P3-1. 상태 tick 종료 레이스 방어

- 조치: `_tick_status`의 `root.after` 스케줄링에 `winfo_exists` 체크/예외 흡수 적용
- 근거 파일: `kakao_adblocker/ui.py`
- 검증 테스트: `tests/test_tray_controller_v11.py` tick 예외 비전파 케이스

## 2) .spec/문서 정합성 반영

- `kakaotalk_adblock.spec` hiddenimports 보강:
  - `kakao_adblocker.logging_setup`
  - `kakao_adblocker.services`
- `README.md`, `CLAUDE.md`, `GEMINI.md`, `ADBLOCK_ALGORITHM_BASELINE_V11.md`를 최신 코드 동작 기준으로 동기화
- `ADBLOCK_POTENTIAL_ISSUES_DEEP_CHECK_2026-02-27.md`를 조치 완료 문서로 갱신

## 3) 현재 잔여 리스크

1. 장시간 실환경 성능(메모리/CPU) 자동 벤치마크 체계는 별도 과제
2. 카카오톡 UI 구조 급변 시 rules 튜닝 필요성은 상시 존재

## 4) 회귀 방지 가이드

1. 엔진 캐시/숨김 스냅샷 키를 hwnd 단일 키로 되돌리지 않는다.
2. `_restore_hidden_windows`를 선삭제 방식으로 되돌리지 않는다.
3. stop timeout 경고 정책(경고 후 종료 계속)을 변경할 때는 테스트를 함께 갱신한다.
4. 백업 정리 정책(30일/10개) 변경 시 README 및 baseline 문서를 동시 갱신한다.
