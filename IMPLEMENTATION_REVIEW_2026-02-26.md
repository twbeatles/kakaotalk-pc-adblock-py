# KakaoTalk Layout AdBlocker v11 기능 구현 점검 보고서

작성일: 2026-02-26  
참조 문서: `README.md`, `CLAUDE.md`

## 1) 점검 범위

- 핵심 엔진: `kakao_adblocker/event_engine.py`, `kakao_adblocker/layout_engine.py`
- UI/설정: `kakao_adblocker/ui.py`, `kakao_adblocker/config.py`, `kakao_adblocker/app.py`
- 플랫폼/API 경계: `kakao_adblocker/win32_api.py`
- 빌드/문서 정합: `kakaotalk_adblock.spec`, `README.md`, `CLAUDE.md`, `GEMINI.md`
- 테스트 상태: `pytest -q` 기준 19 passed

## 2) 요약 결론

- 문서에 정의된 v11 아키텍처(레이아웃 기반 차단, 100ms 폴링, 트레이 중심 UX)는 코드에 대체로 반영되어 있습니다.
- 최근 반영된 안정화 항목(짧은 `Ad` 오탐 완화, 최소화 시작 팝업 정책, startup 토글 실패 처리, `.spec` 경로 보강)도 구현/문서 정합성이 맞습니다.
- 다만 기능 품질 측면에서 **실사용 중 문제가 될 수 있는 잠재 이슈 5개(High 2, Medium 3)** 와 **추가 권장 개선 3개(Low)** 가 확인되었습니다.

## 3) 잠재 이슈 상세

### High-1: 차단 OFF 시 기존 숨김/이동된 창 원복 부재

- 근거
  - `set_enabled`는 플래그만 변경: `kakao_adblocker/event_engine.py:107`
  - 비활성화 시 apply 루프 즉시 return: `kakao_adblocker/event_engine.py:176`
  - 숨김 처리/오프스크린 이동 수행: `kakao_adblocker/event_engine.py:305`, `kakao_adblocker/event_engine.py:311`
  - `_hidden_hwnds`는 정리만 수행하고 복원 로직 없음: `kakao_adblocker/event_engine.py:351`
- 영향
  - 사용자가 UI에서 차단을 OFF로 바꿔도 이미 숨겨진 광고/서브윈도우가 즉시 복원되지 않아 “OFF가 체감되지 않는” 문제 가능
- 권장 개선
  - 숨김 시점에 원래 상태(visible 여부, rect)를 저장하고, OFF 전환 시 복원 루틴 실행
  - 복원이 실패한 핸들은 로그에 남기고 캐시에서 제거

### High-2: 캐시 딕셔너리의 동시 접근(Watch/Apply 스레드) 잠재 경쟁 상태

- 근거
  - watch/apply 두 개 스레드 동시 구동: `kakao_adblocker/event_engine.py:91`, `kakao_adblocker/event_engine.py:92`
  - `_get_cached`에서 딕셔너리 갱신: `kakao_adblocker/event_engine.py:328`, `kakao_adblocker/event_engine.py:334`
  - `_cleanup_caches`에서 같은 딕셔너리 순회/삭제: `kakao_adblocker/event_engine.py:343`, `kakao_adblocker/event_engine.py:347`, `kakao_adblocker/event_engine.py:349`
- 영향
  - 드물게 캐시 일관성 깨짐 또는 예외(log spam) 가능
  - 장시간 실행 시 불안정성으로 이어질 수 있음
- 권장 개선
  - `_text_cache`, `_class_cache`, `_custom_scroll_cache`에 공용 lock 도입
  - 또는 watch/apply를 단일 루프로 통합해 캐시 접근 직렬화

### Medium-1: 비Windows 환경에서 명시적 실패(fail-fast) 부재

- 근거
  - Win32 사용 가능 여부는 내부 플래그로만 처리: `kakao_adblocker/win32_api.py:19`
  - 앱 시작 시 플랫폼 체크 없이 Tk/UI 실행: `kakao_adblocker/app.py:22`, `kakao_adblocker/app.py:40`
- 영향
  - Linux/macOS 등에서 “실행은 되는데 실제 기능은 동작하지 않는” 모호한 상태 발생 가능
- 권장 개선
  - `app.main()` 초기에 `os.name != "nt"`이면 명시 메시지와 종료 코드 반환

### Medium-2: 광고 후보 창 탐지 조건이 과포괄될 여지

- 근거
  - 후보 선정 시 `parent==0`인 빈 텍스트 윈도우도 포함: `kakao_adblocker/event_engine.py:157` ~ `kakao_adblocker/event_engine.py:161`
  - `main_window_classes`를 확장 설정한 경우 과탐지 가능성 증가
- 영향
  - 사용자 커스텀 규칙 적용 시 의도하지 않은 창이 광고 후보로 분류될 가능성
- 권장 개선
  - 후보 탐지용 클래스를 분리(`ad_candidate_classes`)하거나
  - “main window 하위 관계 확인 + 추가 시그니처(text/class)”를 동시에 만족할 때만 후보 처리

### Medium-3: `run_on_startup` 설정값과 실제 레지스트리 상태의 초기 동기화 부재

- 근거
  - 설정은 JSON에서 로드: `kakao_adblocker/config.py:100`
  - UI 체크 상태는 레지스트리 직접 조회: `kakao_adblocker/ui.py:145`
  - 앱 시작 시 파일값과 레지스트리를 맞추는 동기화 루틴 없음
- 영향
  - 설정 파일과 실제 시스템 상태가 어긋나 사용자 혼란 가능
- 권장 개선
  - 앱 시작 시 1회 동기화(레지스트리 기준 또는 정책 기준) 후 저장

## 4) 추가 권장 개선 항목 (Low)

### Low-1: UI에서 `aggressive_mode` 토글 미노출

- 근거: 설정 필드는 존재(`kakao_adblocker/config.py:87`)하지만 UI에는 차단 ON/OFF와 startup만 노출(`kakao_adblocker/ui.py:62`, `kakao_adblocker/ui.py:63`)
- 권장: 트레이 메뉴/설정창에 `공격 모드` 토글 추가

### Low-2: 상태 표시에 오류 컨텍스트 노출 부족

- 근거: 상태 텍스트는 카운트 중심, `last_error` 미노출 (`kakao_adblocker/ui.py:88`)
- 권장: 마지막 오류 시각/메시지를 축약 노출해 사용자 디버깅 용이성 확보

### Low-3: 통합 테스트 갭

- 현재 단위 테스트는 강하지만(19개), 다음 시나리오가 직접 검증되지 않음
  - OFF 전환 시 원복 시나리오
  - 멀티스레드 캐시 안정성(stress)
  - 비Windows 실행 시 기대 종료 동작
  - `main_window_classes` 확장 시 오탐 방지 시나리오

## 5) 우선순위 실행 제안

1. High-1(OFF 원복) + 테스트 추가
2. High-2(캐시 접근 직렬화) + 스트레스 테스트
3. Medium-1(플랫폼 fail-fast) + 앱 엔트리 테스트
4. Medium-2/3(후보 탐지 정밀화, startup 동기화)
5. Low 항목(aggressive_mode UI, 상태 가시성) 순차 반영

## 6) 참고

- 현재 회귀 기준: `pytest -q` → 19 passed
- 문서 정합 대상: `README.md`, `CLAUDE.md`, `GEMINI.md`
