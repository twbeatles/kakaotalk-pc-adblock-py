# KakaoTalk Layout AdBlocker v11 구현 리스크 점검 (업데이트)

작성일: 2026-02-27  
최종 갱신: 2026-02-27  
기준: 현재 코드베이스(`kakao_adblocker/*`, `tests/*`, `kakaotalk_adblock.spec`, `README.md`)

## 1) 반영 완료 항목

### P1-1. HWND 재사용 오동작 방어

- 조치: `WindowIdentity(hwnd,pid,class)` 기반 캐시/숨김 스냅샷 키 적용
- 조치: 원복 시 `(pid,class)` 불일치면 원복 스킵
- 근거 파일: `kakao_adblocker/event_engine.py`
- 검증 테스트: `tests/test_engine_v11.py`의 캐시 식별자/재사용 HWND 원복 스킵 케이스

### P1-2. 스캔 경로 경량화

- 조치: watch 스캔 경로에서 `rect/visible` 미조회
- 조치: 상세 수집은 `dump_window_tree` 경로에서만 수행
- 근거 파일: `kakao_adblocker/event_engine.py`
- 검증 테스트: `tests/test_engine_v11.py`의 scan 경량화 호출 횟수 검증

### P1-3. 초기 광고 깜빡임 완화

- 조치: 엔진 시작 시 background thread 기동 전 동기 warm-up(`watch_once + apply_once`) 수행
- 조치: 시작 직후 active 구간 진입을 위해 `last_activity`를 현재 시각으로 초기화
- 조치: 빈 문자열 텍스트 캐시는 짧은 TTL로 재조회하도록 보정
- 조치: `Chrome Legacy Window` 시그니처 판별은 실시간 `get_window_text` 경로 사용
- 근거 파일: `kakao_adblocker/event_engine.py`
- 검증 테스트: `tests/test_engine_v11.py`의 warm-up 선적용/빈 텍스트 캐시 재조회 케이스

### P2-1. JSON fallback 가시화

- 조치: settings/rules JSON 파손 시 `*.broken-YYYYMMDD-HHMMSS` 백업 생성
- 조치: 경고 큐 기록 + 앱 시작 시 logger 출력 + 첫 경고 상태 노출(`report_warning`)
- 근거 파일: `kakao_adblocker/config.py`, `kakao_adblocker/app.py`, `kakao_adblocker/event_engine.py`
- 검증 테스트: `tests/test_config_v11.py`, `tests/test_app_v11.py`

### P2-2. 배너 규칙 일관성

- 조치: `banner_min_height_px > banner_max_height_px` 자동 교정(swap)
- 조치: 교정 경고 큐 기록
- 근거 파일: `kakao_adblocker/config.py`
- 검증 테스트: `tests/test_config_v11.py`

### P2-3. PID 스캔 예외 격리

- 조치: psutil 경로를 per-process 예외 처리로 분리
- 근거 파일: `kakao_adblocker/services.py`
- 검증 테스트: `tests/test_services_v11.py`

### P3-1. 미사용 apply thread 경로 정리

- 조치: `_apply_thread`/`_apply_loop` 제거
- 조치: 단일 watch+apply 루프 모델 고정
- 근거 파일: `kakao_adblocker/event_engine.py`
- 검증 테스트: 기존 watch+apply same-cycle 테스트 유지

### P3-2. 트레이 종료 레이스 완화

- 조치: `_safe_after` 도입, 모든 트레이 콜백 적용
- 조치: 종료/after 실패 예외 비전파(debug 로그)
- 근거 파일: `kakao_adblocker/ui.py`
- 검증 테스트: `tests/test_tray_controller_v11.py`

## 2) 문서/빌드 정합성 반영

- `README.md` 안정성 항목 갱신(파손 백업/경고 노출, identity 캐시, 스캔 경량화, safe-after)
- `README.md`에 warm-up/빈 텍스트 캐시 갱신 및 spec hiddenimports 설명 최신화 반영
- `CLAUDE.md`, `GEMINI.md`를 현재 코드 동작(active 50ms 포함) 기준으로 갱신
- `ADBLOCK_ALGORITHM_BASELINE_V11.md`를 최신 알고리즘 계약 기준으로 재정리
- `kakaotalk_adblock.spec` hiddenimports 보강(`kakao_adblocker.config`, `kakao_adblocker.event_engine`)

## 3) 현재 잔여 리스크

1. 실환경 장시간 성능 지표(CPU 상한)는 단위테스트로 대체되어 있으며, 정량 벤치마크 자동화는 별도 과제
2. `*.broken-*` 백업 누적 정리 정책(보존 개수/기간)은 아직 미정

## 4) 회귀 방지 가이드

1. 엔진 캐시 키를 다시 hwnd 단일 키로 되돌리지 않는다.
2. watch 스캔 경로에 geometry/visibility 조회를 다시 추가하지 않는다(필요 시 dump-tree 경로로 분리).
3. 설정 로더 fallback은 반드시 "백업 + 경고 기록"을 유지한다.
4. 트레이 콜백은 `_safe_after`를 우회하지 않는다.
