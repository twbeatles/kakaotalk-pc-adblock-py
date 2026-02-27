# AI Context: KakaoTalk Layout AdBlocker v11

## 개요

- 목적: 카카오톡 Windows 클라이언트의 광고 영역을 레이아웃 조정으로 제거
- 버전: `11.x`
- 특징: `hosts/DNS/AdFit` 제거, 트레이 중심 UX, 적응형 폴링 엔진(active 50ms / idle 500ms 기본)
- 실행 정책: Windows 전용(비Windows에서는 fail-fast 종료 코드 `2`)

## 엔트리포인트

- 실행: `kakaotalk_layout_adblock_v11.py`
- 기존 `카카오톡 광고제거 v10.0.py`는 사용중단 안내만 출력
- 패키지 `kakao_adblocker`는 lazy export(`__getattr__`)를 사용해 초기 import 비용을 줄임

## 핵심 모듈

- `kakao_adblocker/config.py`
  - `LayoutSettingsV11`, `LayoutRulesV11`
  - `%APPDATA%\KakaoTalkAdBlockerLayout` 경로 관리
  - 성능 설정: `idle_poll_interval_ms`, `pid_scan_interval_ms`, `cache_cleanup_interval_ms`
  - 신규 필드 누락 시 기본값 자동 보완(무중단 호환)
  - rules 로드 시 `ad_candidate_classes`가 누락/비정상이면 `main_window_classes`로 폴백
  - JSON 파손(파싱 실패/최상위 타입 불일치) 시 `*.broken-YYYYMMDD-HHMMSS` 백업 생성 후 경고 큐에 기록
  - rules 로드 시 `banner_min_height_px > banner_max_height_px` 역전값을 자동 교정(swap)하고 경고 기록
  - 앱 계층 전달용 `consume_load_warnings()` 제공
- `kakao_adblocker/event_engine.py`
  - `LayoutOnlyEngine`, `EngineState`
  - 단일 watch+apply 루프(적응형 폴링), `main_window_classes` 기반 메인 윈도우 식별
  - 광고 후보는 `ad_candidate_classes`(기본: `EVA_Window_Dblclk`, `EVA_Window`)와 레거시 시그니처(`Chrome Legacy Window`)를 함께 사용해 필터링
  - 차단 OFF/엔진 종료 시 숨김·이동 창 원복
  - `WindowIdentity(hwnd,pid,class)` 기반 text/custom-scroll/hidden-window 캐시로 HWND 재사용 오동작 방지
  - 스캔 경로는 경량 수집(`rect/visible` 미조회)으로 호출 부담 감소, `--dump-tree`만 상세 수집 사용
  - PID 스캔/캐시 정리 주기 스로틀 적용
  - 기본 설정 기준 idle->active 복귀 목표 지연 약 500ms
  - `report_warning()`로 시작 시점 경고를 상태(`last_error`)에 반영 가능
- `kakao_adblocker/layout_engine.py`
  - `OnlineMainView` / `LockModeView` 리사이즈 규칙
  - 공격적 배너 휴리스틱, 짧은 ad 토큰 단어 경계 매칭
- `kakao_adblocker/ui.py`
  - `TrayController`
  - 트레이 메뉴: 상태/OnOff/공격 모드/시작프로그램/창 열기/로그/릴리스/종료
  - 최소화 시작 시(`--minimized`/`start_minimized`) 시작 안내 팝업 생략
  - 시작 시 `run_on_startup` 값을 레지스트리 상태로 1회 동기화
  - 상태 문자열에 마지막 오류/갱신시각 표시
  - pystray/Pillow 지연 로딩 및 상태 텍스트 중복 갱신 억제
  - 트레이 콜백은 `_safe_after`를 통해 종료 경합 시 예외를 전파하지 않음
- `kakao_adblocker/services.py`
  - `ProcessInspector`, `StartupManager`, `ReleaseService`
  - `ProcessInspector.get_process_ids()`는 psutil 경로에서 per-process 예외 격리 처리

## 빌드 메모

- `kakaotalk_adblock.spec`는 lazy-import 모듈(`kakao_adblocker.app`, `kakao_adblocker.ui`, `pystray`, `PIL`)을 `hiddenimports`로 명시해 onefile 누락을 방지

## 동작 규칙

1. `kakaotalk.exe` PID 집합을 수집
2. 메인 윈도우(`EVA_Window_Dblclk`/`EVA_Window`) 식별
3. `OnlineMainView`: `width=parent-2`, `height=parent-31`
4. `LockModeView`: `width=parent-2`, `height=parent`
5. `Chrome Legacy Window` 하위 광고 서브윈도우 숨김
6. 공격 모드에서 `Chrome_WidgetWin_* + ad token`/하단 배너 후보 숨김
7. 시작프로그램 토글은 레지스트리 갱신 성공 시에만 설정 파일에 반영
8. `--dump-tree`는 UI 모듈을 로딩하지 않는 경량 경로로 동작

## 설정 파일

- `%APPDATA%\KakaoTalkAdBlockerLayout\layout_settings_v11.json`
- `%APPDATA%\KakaoTalkAdBlockerLayout\layout_rules_v11.json`
- `%APPDATA%\KakaoTalkAdBlockerLayout\layout_adblock.log`

## 레거시 보관

- 구버전 자산은 `legacy/`로 이동됨
- 원본 모놀리식: `legacy/kakao_adblocker/legacy.py`
