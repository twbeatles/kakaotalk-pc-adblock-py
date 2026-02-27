# KakaoTalk Layout AdBlocker v11 광고차단 알고리즘 고정 사양

작성일: 2026-02-27  
최종 갱신: 2026-02-27  
목적: 현재 v11 광고차단 동작을 회귀 없이 유지하기 위한 기준선(Baseline) 정의

## 1) 고정 대상 범위

- 엔진: `kakao_adblocker/event_engine.py`, `kakao_adblocker/layout_engine.py`
- 설정/규칙: `layout_settings_v11.json`, `layout_rules_v11.json`
- 앱/상태 연동: `kakao_adblocker/app.py`, `kakao_adblocker/ui.py`
- 서비스: `kakao_adblocker/services.py`

## 2) 알고리즘 핵심 계약 (MUST)

### 2.1 프로세스/윈도우 식별

1. 대상 프로세스는 `kakaotalk.exe` PID 집합으로 한정한다.
2. 메인 윈도우는 `main_window_classes` + top-level(`parent=0`) + 텍스트 존재 조건으로 식별한다.
3. `EVA_Window`는 `main_window_titles` 토큰 조건을 추가로 만족해야 한다.
4. 광고 후보는 `ad_candidate_classes`를 사용하며, top-level 후보는 `Chrome Legacy Window` 시그니처를 만족해야 한다.

### 2.2 리사이즈 규칙

1. `OnlineMainView*`: `width = parent_width - layout_shadow_padding_px`, `height = parent_height - main_view_padding_px`
2. `LockModeView*`: `width = parent_width - layout_shadow_padding_px`, `height = parent_height`
3. 현재 크기가 동일하면 `set_window_pos` 호출을 생략한다.

### 2.3 공격 모드 규칙

1. 공격 모드는 `settings.aggressive_mode == True`일 때만 적용한다.
2. 짧은 ASCII 토큰(예: `Ad`)은 단어 경계로만 매칭한다.
3. 하단 배너 후보는 높이/폭비/하단 위치 조건을 모두 만족해야 한다.

### 2.4 캐시/원복 안정성 규칙

1. 엔진 캐시는 `WindowIdentity(hwnd,pid,class)` 키를 사용한다.
2. 숨김 스냅샷도 동일 식별자 키를 사용한다.
3. 빈 문자열 텍스트 캐시는 짧은 TTL로 재조회하여 초기 UI 구성 구간의 탐지 지연을 줄인다.
4. 원복 시 현재 `(pid,class)`가 스냅샷과 다르면 원복을 스킵한다(재사용 HWND 방어).
5. 차단 OFF 또는 엔진 stop 시 숨김 창 원복을 즉시 수행한다.

### 2.5 성능/루프 규칙

1. 루프 모델은 단일 `watch+apply` 루프를 유지한다.
2. 스캔 경로는 경량 수집을 사용한다(`rect/visible` 미조회).
3. 상세 geometry/visibility 수집은 `--dump-tree` 경로에서만 수행한다.
4. PID 스캔/캐시 정리는 스로틀을 유지한다.
5. 엔진 시작 시 watch/apply warm-up 1회를 동기 수행해 초기 깜빡임을 줄인다.
6. 기본 목표 지연: active 50ms, idle 200ms.

### 2.6 설정/경고 규칙

1. settings/rules JSON 파싱 실패 또는 top-level 타입 불일치 시:
   - 원본을 `*.broken-YYYYMMDD-HHMMSS`로 백업
   - 기본값으로 안전 복귀
   - load warning 큐에 경고 기록
2. `banner_min_height_px > banner_max_height_px`면 자동 교정(swap) 후 경고를 기록한다.
3. 앱 시작 시 load warning을 logger에 남기고, 첫 경고를 `engine.report_warning()`으로 상태에 노출한다.

### 2.7 UI/서비스 안전 규칙

1. 트레이 메뉴 콜백은 `_safe_after` 경유로 예약한다.
2. 종료 경합으로 `after`가 실패해도 예외를 전파하지 않는다.
3. `ProcessInspector.get_process_ids()` psutil 경로는 per-process 예외 격리로 일부 프로세스 오류가 전체 스캔 실패로 번지지 않게 한다.

## 3) 실행/UX 계약

1. 비Windows에서는 즉시 종료 코드 `2`를 반환한다.
2. `--dump-tree`는 UI 모듈 로딩 없이 실행/종료한다.
3. `--minimized` 또는 `start_minimized=true` 시작 시 안내 팝업을 띄우지 않는다.

## 4) 테스트 게이트 (변경 시 필수)

- 리사이즈 공식/공격 토큰: `tests/test_layout_engine_v11.py`
- 후보 시그니처/원복/스로틀/경량스캔/HWND 재사용 방어: `tests/test_engine_v11.py`
- 설정 fallback 백업/배너 역전 교정: `tests/test_config_v11.py`
- load warning -> `report_warning` 전달: `tests/test_app_v11.py`
- 트레이 `_safe_after` 레이스 방어: `tests/test_tray_controller_v11.py`
- psutil per-process 예외 격리: `tests/test_services_v11.py`

## 5) 변경 관리 규칙

1. MUST 계약 변경 시 `README.md`와 본 문서를 함께 갱신한다.
2. 동작 의미가 바뀌는 룰 튜닝은 테스트와 변경 사유를 반드시 남긴다.
3. 회귀 의심 시 `--dump-tree` 결과와 `layout_adblock.log`를 함께 수집해 분석한다.

## 6) 릴리즈 전 수동 스모크 체크리스트

1. 기본 채팅 목록에서 광고 영역 미노출 확인
2. 차단 OFF 즉시 원복 확인
3. 앱 종료 시 원복 확인
4. 공격 모드 ON/OFF 전환 시 오탐 여부 확인
5. 시작프로그램 토글 성공/실패 각각에서 설정 반영 여부 확인
6. `--dump-tree` 실행 시 UI 비기동 및 결과 파일 생성 확인
