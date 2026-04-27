# AI Context: KakaoTalk Layout AdBlocker v11

## 개요

- 목적: 카카오톡 Windows 클라이언트의 광고 영역을 레이아웃 조정으로 제거
- 버전: `11.x`
- 특징: `hosts/DNS/AdFit` 제거, 트레이 중심 UX, 적응형 폴링 엔진(active 50ms / idle 200ms 기본)
- 실행 정책: Windows 전용(비Windows에서는 fail-fast 종료 코드 `2`)

## 광고차단 알고리즘 고정 규칙

- v11 광고차단 알고리즘은 고정 계약으로 취급한다. 임의 리팩터링, 휴리스틱 완화/강화, 범용화 시도를 하지 않는다.
- 기본 전략은 항상 `layout-only`다. `hosts/DNS/레지스트리/네트워크 차단` 계열 기능을 다시 추가하지 않는다.
- 기본 알고리즘 의미는 `blurfx/KakaoTalkAdBlock` 계열과 일치시킨다:
  - 메인 윈도우 식별
  - legacy signature 기반 top-level candidate hide
  - subtree token 기반 aggressive hide
  - guarded popup dismiss
  - confirmed ad signal 기반 empty `EVA_ChildWindow` close
- empty `EVA_ChildWindow` close의 custom scroll guard는 메인 윈도우 전체가 아니라 해당 candidate child subtree 기준으로 유지한다.
- token 없는 하단 `Chrome_WidgetWin_*` geometry-only hide는 기본값에서 금지하고, rules opt-in(`hide_bottom_banner_without_token=true`)일 때만 허용한다.
- non-empty popup host title은 기본값에서 allowlist(`popup_host_text_contains`)에 맞지 않으면 dismiss하지 않는다.
- popup class 탐색은 direct child만 보지 않고 `popup_search_depth` 범위의 descendant까지 허용하되, 기본값은 `2`를 넘기지 않는다.
- 알고리즘 자체를 바꾸려면 반드시 실제 `--dump-tree`/`--dump-tree-series` 근거, fixture 또는 회귀 테스트, 관련 문서 갱신을 함께 남긴다.
- 가능하면 rules/fixture/test를 조정하고, 엔진 로직 변경은 실제 회귀가 확인된 경우로 제한한다.

## 엔트리포인트

- 실행: `kakaotalk_layout_adblock_v11.py`
- 기존 `카카오톡 광고제거 v10.0.py`는 루트에서 제거되었고, `legacy/카카오톡 광고제거 v10.0.py`에서 사용중단 안내만 출력
- 패키지 `kakao_adblocker`는 lazy export(`__getattr__`)를 사용해 초기 import 비용을 줄임
- 정적 분석 기준선은 루트 `pyrightconfig.json`으로 고정되며 활성 범위는 `kakao_adblocker`, `tests`, `kakaotalk_layout_adblock_v11.py`
- 권장 로컬 검증 명령은 `.\scripts\dev_check.ps1`이며 필요 시 `-SkipTests`로 타입 검사만 수행

## 핵심 모듈

- `kakao_adblocker/app/`
  - `main`, CLI parser, self-check, startup trace helper
  - package facade는 기존 `kakao_adblocker.app` import surface와 test monkeypatch 지점을 유지
  - 내부 구현은 `cli.py`, `self_check.py`, `startup.py`로 분리
- `kakao_adblocker/config/`
  - `LayoutSettingsV11`, `LayoutRulesV11`
  - `%APPDATA%\KakaoTalkAdBlockerLayout` 경로 관리
  - 성능 설정: `idle_poll_interval_ms`, `pid_scan_interval_ms`, `cache_cleanup_interval_ms`
  - 신규 성능 설정: `burst_scan_iterations`, `burst_scan_interval_ms`
  - 신규 필드 누락 시 기본값 자동 보완(무중단 호환)
  - 신규 rules 플래그: `hide_bottom_banner_without_token=false`, `close_empty_eva_child_requires_ad_signal=true`
  - 신규 rules 튜닝값: `weak_signal_confirm_ticks=2`, `hidden_restore_grace_ms=250`
  - 신규 rules 키: `popup_ad_classes=["AdFitWebView"]`, `popup_search_depth=2`, `popup_host_text_contains=[]`, `popup_host_require_empty_text=true`
  - rules 로드 시 `ad_candidate_classes`가 누락/비정상이면 `main_window_classes`로 폴백
  - JSON 파손(파싱 실패/최상위 타입 불일치) 시 `*.broken-YYYYMMDD-HHMMSS` 백업 생성 후 기본값 JSON으로 self-heal
  - rules 로드 시 `banner_min_height_px > banner_max_height_px` 역전값을 자동 교정(swap)하고 경고 기록
  - `*.broken-*` 백업 자동 정리(30일 초과 삭제 + 최신 10개 유지)를 로드 시마다 적용
  - settings/rules 저장은 원자적 교체(`os.replace`)로 파일 파손 리스크 완화
  - 첫 실행 runtime bootstrap(settings/rules/log)은 create-if-missing 방식으로 처리해 기존 파일 덮어쓰기를 방지
  - rules 문자열 무결성 self-check(mojibake 시그니처/`�`) 경고
  - 앱 계층 전달용 `consume_load_warnings()` 제공
- `kakao_adblocker/event_engine/`
  - `LayoutOnlyEngine`, `EngineState`
  - 내부 구현은 `controller.py`, `scanner.py`, `signals.py`, `actions.py`, `dump.py`, `models.py`로 분리
  - 단일 watch+apply 루프(적응형 폴링), `main_window_classes` 기반 메인 윈도우 식별
  - 차단 OFF 상태에서는 watch/apply를 모두 일시중단하고 1.0초 저비용 대기
  - 광고 후보는 `ad_candidate_classes`(기본: `EVA_Window_Dblclk`, `EVA_Window`)와 레거시 시그니처(exact + substring)를 함께 사용해 필터링
  - 비메인 top-level KakaoTalk window의 descendant(depth<=`popup_search_depth`)가 `popup_ad_classes`와 매치되더라도, 기본값에서는 empty host title 또는 allowlist(`popup_host_text_contains`) 매치일 때만 host와 matched popup descendant만 정리
  - popup dismiss는 `SendMessageTimeoutW` 기반 `WM_CLOSE` timeout(기본 500ms)으로 보호하고, 실제 close/hide/zero-size 성공 여부를 검증하며 실패 시 상태(`last_error`)와 로그에 반영
  - popup dismiss 후 창이 살아 있어 hide/zero-size fallback이 적용되면 `popup` hide snapshot으로 추적해 OFF/stop 또는 popup 신호 소멸 시 복원
  - empty `EVA_ChildWindow` close의 custom-scroll guard는 메인 윈도우 전체가 아니라 candidate child subtree 기준으로 tick마다 재평가
  - 메인 윈도우 상태는 `candidate_main_window_count`(후보)와 `main_window_count`(확정)로 분리되며, 실제 apply는 확정 기준만 사용
  - 엔진 시작 시 enabled인 경우에만 동기 warm-up(scan+apply 1회)으로 초기 광고 깜빡임 완화
  - 빈 문자열 텍스트 캐시는 짧은 TTL로 재조회해 초기 UI 구성 구간 탐지 지연 완화
  - 메인 윈도우는 `top-level + main class + child signature`를 강한 가드로 유지하고, title이 비어있지 않아도 `main_window_titles` 불일치 시 자식 시그니처(`OnlineMainView`/`LockModeView`) fallback 탐지를 허용
  - 차단 OFF/공격 모드 OFF/엔진 종료 시 scan/apply/window mutation single-flight lock으로 숨김·이동 창 원복과 재은닉 경합을 방지
  - `stop()` 시작 이후에는 새 hide/close/apply 작업이 봉쇄되어, join timeout 이후에도 복원 직후 재은닉이 발생하지 않도록 정리
  - aggressive hide 창은 공격 모드 OFF 시 즉시 원복 후 재스캔/재적용
  - 숨김 창은 aggressive/legacy 시그니처에서 벗어나면 stale 상태로 남지 않고 자동 원복
  - `stop()` join timeout(2.0s) 시 상태/로그 경고 후 종료 절차 계속
  - 원복 실패 항목 스냅샷 보존으로 재시도 가능
  - `EngineState.restore_failures`, `EngineState.last_restore_error` 상태 노출
  - `reset_restore_failures()`로 복원 실패 상태 수동 초기화 지원
  - `WindowIdentity(hwnd,pid,class)` 기반 text/hidden-window 캐시로 HWND 재사용 오동작 방지
  - 숨김/후보 aggressive subtree는 stale non-empty 텍스트 캐시를 우회해 광고 토큰 소멸 후 복원 지연을 줄임
  - 스캔 경로는 경량 수집(`rect/visible` 미조회)으로 호출 부담 감소, `--dump-tree`만 상세 수집 사용
  - `--dump-tree-series`는 frame별 candidate decision preview를 함께 저장하며 popup dismiss host와 matched descendant를 모두 기록
  - PID 스캔/캐시 정리 주기 스로틀 적용
  - PID 스캔 경고(psutil 실패, tasklist fallback/실패)를 상태(`last_error`)와 로그에 반영
  - 기본 설정 기준 idle->active 복귀 목표 지연 약 200ms
  - `report_warning()`로 시작 시점 경고를 상태(`last_error`)에 반영하며, 엔진 시작 이후에도 우선순위 경고 1건 유지
- `kakao_adblocker/layout_engine.py`
  - `OnlineMainView` / `LockModeView` 리사이즈 규칙
  - 공격적 배너 휴리스틱은 token 판정과 geometry 판정을 분리하고, 짧은 ad 토큰은 단어 경계 기준으로 매칭
  - 기본값에서는 token 없는 하단 `Chrome_WidgetWin_*` 패널을 geometry만으로 숨기지 않으며, subtree token도 aggressive signal로 사용
- `kakao_adblocker/protocols.py`
  - Win32 API/Joinable Thread/UI Root/Engine 상태에 대한 구조적 타입 프로토콜 정의
  - 테스트 더블(`tests/*`)과 런타임 모듈의 타입 경계를 분리
- `kakao_adblocker/ui.py`
  - `TrayController`
  - 트레이 메뉴: 상태/OnOff/공격 모드/시작프로그램/복원실패초기화/창 열기/로그/릴리스/종료
  - 최소화 시작 시(`--minimized`/`start_minimized`) 시작 안내 팝업 생략
  - 트레이 비가용 시 최소화 시작 요청을 무시하고 창을 강제 표시
  - 트레이 시작은 준비 신호 기반으로 판정하며 시작 타임아웃(1.5초) 시 비활성화
  - 트레이 런타임 비정상 종료 시 트레이를 비활성화하고 메인 창 복구
  - 트레이 시작 실패/런타임 중단 후 3초 간격 최대 3회 재시도, startup fallback 중 성공 시 자동 재은닉
  - 트레이 비가용 시 창 닫기(X)는 숨김이 아니라 종료로 처리
  - 시작 시 `run_on_startup` 값을 레지스트리 상태로 1회 동기화
  - 시작 시 Run 등록이 enabled면 등록 명령 stale/missing 여부를 함께 검사하고 자동 복구를 시도
  - 상태 문자열에 마지막 오류/갱신시각 표시
  - 엔진 오류가 없을 때는 tray unavailable/startup rollback 같은 UI 계층 경고를 상태 문자열에 짧게 노출
  - 상태 문자열의 `메인윈도우`는 확정 count이며, 후보가 더 많을 때만 `후보 N`을 추가 표기
  - 상태 문자열의 `누적 숨김`/`누적 닫힘`/`누적 리사이즈` 라벨로 누적 카운터 의미를 명시
  - pystray/Pillow 지연 로딩 + 실패 TTL(30초) 자동 재시도
  - 트레이 콜백은 queue 디스패치(`_safe_after` -> main-thread drain)로 처리
  - 설정 저장 실패 시 토글 값 롤백(`enabled`/`run_on_startup`/`aggressive_mode`)
  - startup 토글에서 저장 실패 시 레지스트리 역롤백
  - aggressive mode 토글은 저장 성공 후 엔진에 즉시 반영
  - `_tick_status` 스케줄링(`root.after`)도 종료 경합 예외 비전파
  - `로그 폴더 열기` / `GitHub 릴리스 열기` 실패도 상태 문자열 경고로 노출
- `kakao_adblocker/services.py`
  - `ProcessInspector`, `StartupManager`, `ReleaseService`
  - `ProcessInspector.get_process_ids()`는 psutil 경로에서 per-process 예외 격리 처리
  - psutil 초기화/루프 실패 시 `tasklist` 폴백
  - `ProcessInspector.consume_last_warning()`로 PID 탐지 경고를 엔진 계층에서 소비 가능
  - `StartupManager.probe_access()`는 Run 레지스트리 읽기/쓰기 접근을 함께 점검
  - 진단용 `ProcessInspector.probe_tasklist()`, `StartupManager.probe_access()` 제공

## 빌드 메모

- `kakaotalk_adblock.spec`는 런타임 핵심 모듈(`kakao_adblocker.app`, `kakao_adblocker.config`, `kakao_adblocker.event_engine`, `kakao_adblocker.layout_engine`, `kakao_adblocker.logging_setup`, `kakao_adblocker.services`, `kakao_adblocker.ui`, `kakao_adblocker.win32_api`, `pystray`, `PIL`, `tkinter`)을 `hiddenimports`로 명시하고 `collect_submodules("pystray"|"PIL")` 및 packageized `app/config/event_engine` 하위 모듈 수집을 함께 사용해 onefile 누락을 방지
- 타입 경계 모듈 `kakao_adblocker.protocols`도 `hiddenimports`에 포함되어 onefile 모듈 누락 가능성을 줄임
- 패키지 루트 `kakao_adblocker`도 `hiddenimports`에 포함되어 lazy export 패키지 접근 경로를 고정
- `pywinauto`, `comtypes`는 active v11 런타임 바깥의 legacy/UIA 의존성이므로 `.spec`의 `excludes`로 유지
- popup parity(`popup_ad_classes` / `AdFitWebView`), `SendMessageTimeoutW` close timeout, popup fallback 복원 추적은 기존 `config/event_engine/win32_api` 내부 구현이라 추가 PyInstaller hook 없이 현재 spec으로 포장 가능
- empty `EVA_ChildWindow` subtree custom-scroll guard는 tick-local `event_engine` 내부 구현이라 추가 hidden import 없이 현재 spec으로 유지
- `scripts/build_release.ps1`는 빌드 시작 시 `VERSION`과 `packaging/windows_version_info.txt` 동기화를 검증하고, 기본값으로 built EXE에 `--self-check --strict-self-check --json` packaged smoke를 1회 수행하며, core failure만 빌드 실패로 취급한다. 필요 시 `-SkipSmokeCheck`로 비활성화 가능
- interactive shell이 감지되면 built EXE에 `--startup-launch --minimized --startup-trace ... --exit-after-startup-ms ...` startup smoke를 추가 수행하고, 비interactive 환경에서는 skip 기록만 남기고 계속 진행한다
- `-StrictStartupSmoke`는 interactive startup smoke가 실제 수행된 경우에만 tray unavailable / tray start warning을 빌드 실패로 승격한다
- GitHub Actions workflow `.github/workflows/windows-ci.yml`는 hosted Windows에서 pyright, pytest, self-check JSON, no-sign packaging build만 검증하고, interactive tray/startup smoke는 강제하지 않는다

## 동작 규칙

1. `kakaotalk.exe` PID 집합을 수집
2. 메인 윈도우(`EVA_Window_Dblclk`/`EVA_Window`) 식별
3. `OnlineMainView`: `width=parent-2`, `height=parent-31`
4. `LockModeView`: `width=parent-2`, `height=parent`
5. `Chrome Legacy Window` 하위 광고 서브윈도우 숨김
6. 공격 모드에서 `Chrome_WidgetWin_* + ad token` 또는 subtree token이 확인된 하단 배너 후보만 숨기고, geometry-only hide는 rules opt-in일 때만 허용
7. 비메인 top-level 창의 descendant(depth<=`popup_search_depth`)가 `AdFitWebView` 등 `popup_ad_classes`에 매치되더라도 기본값에서는 empty host title 또는 allowlist match일 때만 host와 matched popup descendant만 close/hide/zero-size 처리
8. 시작프로그램 토글은 레지스트리 갱신 성공 시에만 설정 파일에 반영
9. `--dump-tree`는 UI 모듈을 로딩하지 않는 경량 경로로 동작
10. `--self-check`는 UI/엔진을 기동하지 않고 APPDATA/logging bootstrap/tasklist/레지스트리/Run 등록 명령/`tkinter/Tk`/트레이 import 환경 진단만 수행하며, 기본 모드의 트레이 import 실패는 optional이고 `--strict-self-check`에서는 core로 취급
11. 시작 경고 상태 반영은 `복구 실패 > 자동 복구 > 기타` 우선순위로 1건 노출

## 설정 파일

- `%APPDATA%\KakaoTalkAdBlockerLayout\layout_settings_v11.json`
- `%APPDATA%\KakaoTalkAdBlockerLayout\layout_rules_v11.json`
- `%APPDATA%\KakaoTalkAdBlockerLayout\layout_adblock.log`

## 레거시 보관

- 구버전 자산은 `legacy/`로 이동됨
- 원본 모놀리식: `legacy/kakao_adblocker/legacy.py`
- deprecated 엔트리포인트: `legacy/카카오톡 광고제거 v10.0.py`
- 레거시 스크립트는 보관 자산이며 활성 repo-wide `pyright` 범위에서는 제외; 기존 파일 상단 지시문은 개별 유지보수 시 참고용으로 유지
