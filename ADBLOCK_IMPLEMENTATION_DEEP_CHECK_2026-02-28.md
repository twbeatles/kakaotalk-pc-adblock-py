# 광고차단 개선안 구현 완료 리포트 (2026-02-28)

작성일: 2026-02-28  
최종 갱신: 2026-02-28  
기준 문서: `README.md`, `CLAUDE.md`, `GEMINI.md`, `legacy/README.md`  
기준 코드: `kakao_adblocker/*`, `tests/*`, `kakaotalk_adblock.spec`

## 구현 요약

- P1~P3 제안사항을 코드/테스트/문서에 반영 완료.
- 요청한 정책 유지:
  - `ADBLOCK_POTENTIAL_ISSUES_DEEP_CHECK_2026-02-28.md` 삭제 상태 유지
  - 레거시 시그니처는 regex 없이 exact+substring
  - PID 실패 가시화는 엔진 상태(`last_error`) + 로그 중심 반영

## 반영 완료 항목

### 1) P1-1 트레이 비가용 시 접근 불가 문제

- 트레이 비가용이면 최소화 시작 요청(`--minimized`/`start_minimized`)을 무시하고 창을 강제 표시.
- 트레이 비가용 상태에서 창 닫기(X)는 숨김이 아니라 종료로 처리.
- 반영 파일:
  - `kakao_adblocker/app.py`
  - `kakao_adblocker/ui.py`

### 2) P2-1 Win32 시그니처 명시 + 실패 진단 보강

- user32 함수 `argtypes/restype` 명시:
  - `EnumWindows`, `EnumChildWindows`, `GetWindowThreadProcessId`, `GetClassNameW`, `GetWindowTextW`,
    `GetParent`, `GetWindowRect`, `GetClientRect`, `IsWindow`, `IsWindowVisible`, `ShowWindow`,
    `SetWindowPos`, `SendMessageW`, `UpdateWindow`
- `Win32API.get_last_error()` 추가.
- `show_window`/`set_window_pos` 실패 시 debug 로그에 win32 error 코드 기록.
- 반영 파일:
  - `kakao_adblocker/win32_api.py`
  - `kakao_adblocker/event_engine.py`

### 3) P2-2 self-check 레지스트리 접근 정합성

- `StartupManager.probe_access()`가 Run 레지스트리 `KEY_READ` + `KEY_SET_VALUE`를 모두 점검.
- self-check 라벨을 `Run 레지스트리 읽기/쓰기 접근`으로 수정.
- 반영 파일:
  - `kakao_adblocker/services.py`
  - `kakao_adblocker/app.py`

### 4) P2-3 PID 탐지 실패 원인 가시화

- `ProcessInspector`에 경고 버퍼 추가:
  - `ProcessInspector.consume_last_warning()`
- psutil 초기화/루프 실패, tasklist fallback/실패 원인을 경고로 저장.
- 엔진이 PID 스캔 시 경고를 소비해 `last_error`/로그에 반영.
- 반영 파일:
  - `kakao_adblocker/services.py`
  - `kakao_adblocker/event_engine.py`

### 5) P3-1 메인 윈도우 빈 타이틀 fallback

- 메인 후보에서 title 비었을 때 즉시 제외하지 않고,
  자식 뷰 시그니처(`OnlineMainView`/`LockModeView`)를 확인해 메인 윈도우로 판정.
- 반영 파일:
  - `kakao_adblocker/event_engine.py`

### 6) P3-2 레거시 후보 exact+substring 완충

- rules 필드 추가: `chrome_legacy_title_contains` (기본값 `["Chrome Legacy Window"]`)
- 레거시 후보 판별에서 exact(`chrome_legacy_title`) + substring(`chrome_legacy_title_contains`) 지원.
- 반영 파일:
  - `kakao_adblocker/config.py`
  - `kakao_adblocker/event_engine.py`

## .spec 점검 및 반영

- 점검 결과: 기존 .spec는 동작상 문제는 없었음.
- 안정성 보강 차원에서 hiddenimports를 명시 확장:
  - `kakao_adblocker.layout_engine`
  - `kakao_adblocker.win32_api`
- 반영 파일:
  - `kakaotalk_adblock.spec`

## 문서 정합성 반영

- 업데이트 완료 문서:
  - `README.md`
  - `CLAUDE.md`
  - `GEMINI.md`
- 반영 내용:
  - 트레이 비가용 시 최소화 무시/닫기 동작 변경
  - self-check read/write 점검
  - PID 경고 가시화
  - 레거시 exact+substring 규칙
  - .spec hiddenimports 보강 내용

## 테스트 반영

- 신규 테스트:
  - `tests/test_win32_api_v11.py`
- 확장/수정 테스트:
  - `tests/test_app_v11.py`
  - `tests/test_tray_controller_v11.py`
  - `tests/test_services_v11.py`
  - `tests/test_engine_v11.py`
  - `tests/test_config_v11.py`

## 검증 결과

- `pytest -q`: **92 passed**

## .gitignore 점검

- 현재 변경 기준으로 추가 ignore가 꼭 필요한 항목은 없음.
- 테스트/빌드 부산물(`__pycache__/`, `.pytest_cache/`, `build/`, `dist/`, `*.pyc`)은 이미 포함됨.
