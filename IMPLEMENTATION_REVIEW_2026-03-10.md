# 기능 구현 점검 메모

작성일: 2026-03-10

## 후속 반영 상태

- 아래 주요 권고사항은 현재 코드베이스에 반영 완료:
  - subtree token 기반 aggressive signal
  - token 없는 하단 `Chrome_WidgetWin_*` geometry-only hide 기본 비활성
  - empty `EVA_ChildWindow` close의 광고 신호 연동
  - `stop()` 시작 이후 hide/close/apply 봉쇄
  - `tkinter/Tk`를 포함한 `--self-check` 확장
  - 후보/확정 메인 윈도우 count 분리
  - synthetic `dump-tree` fixture 기반 회귀 테스트 추가
- 반영 후 재검증 결과:
  - `pytest -q`: `127 passed`
  - `python kakaotalk_layout_adblock_v11.py --self-check`: `5/5 checks passed`
  - `pyright`: `0 errors, 0 warnings`

## 검토 기준

- 문서: `CLAUDE.md`, `README.md`
- 런타임 코드: `kakao_adblocker/app.py`, `kakao_adblocker/config.py`, `kakao_adblocker/event_engine.py`, `kakao_adblocker/layout_engine.py`, `kakao_adblocker/ui.py`, `kakao_adblocker/services.py`, `kakao_adblocker/win32_api.py`
- 검증: `pytest -q`, `python kakaotalk_layout_adblock_v11.py --self-check`, `pyright`

## 현재 상태

- `pytest -q`: `107 passed`
- `--self-check`: `4/4 checks passed`
- `pyright`: `0 errors, 0 warnings`

현재 저장소는 테스트/타입체크 기준으로는 안정적이다. 다만 `CLAUDE.md`와 `README.md`가 설명하는 "트레이 중심", "적응형 엔진", "self-check 기반 진단"을 실제 사용자 환경까지 확장해서 보면, 아래 항목들은 기능적으로 잠재 리스크가 있거나 추가 구현 가치가 높은 부분이다.

## 주요 잠재 이슈

### 1. 기본 `aggressive_mode=true`와 하단 배너 휴리스틱이 정상 UI를 숨길 가능성

- 근거:
  - 기본값이 `aggressive_mode = True`다. `kakao_adblocker/config.py:251`
  - 하단 배너 판정은 `Chrome_WidgetWin_*` 이거나 ad token을 포함하면 참이 된다. 즉, 토큰이 없어도 하단의 넓은 `Chrome_WidgetWin_*` 패널이면 숨김 대상이 된다. `kakao_adblocker/layout_engine.py:78-95`
- 리스크:
  - 카카오톡이 추후 하단 공지, 실험 UI, 웹 기반 푸터를 `Chrome_WidgetWin_*`로 내리면 광고가 아니어도 첫 실행부터 숨길 수 있다.
  - 현재 테스트는 광고성 케이스만 검증하고, "광고가 아닌 하단 웹뷰는 남겨야 한다"는 부정 케이스가 없다. `tests/test_layout_engine_v11.py:68-89`
- 권장:
  - 신규 설치 기본값을 `aggressive_mode=false`로 낮추거나,
  - `geometry + token` 동시 만족으로 조건을 강화하거나,
  - 허용 리스트(`allowed_widget_text_contains`, `allowed_widget_classes`)를 rules에 추가하는 편이 안전하다.

### 2. 빈 `EVA_ChildWindow`에 대한 `WM_CLOSE`가 과하게 공격적임

- 근거:
  - 메인 윈도우 직계 자식이 `EVA_ChildWindow`이고 텍스트가 비어 있으며 custom scroll 시그니처가 없으면 바로 `WM_CLOSE`를 보낸다. `kakao_adblocker/event_engine.py:378-387`
  - 판정 함수도 사실상 같은 조건만 본다. `kakao_adblocker/layout_engine.py:43-55`
- 리스크:
  - 현재는 광고 placeholder를 닫는 용도로 보이지만, 카카오톡이 빈 bootstrap pane, skeleton view, lazy-loaded container를 추가하면 광고가 아닌 정상 UI도 닫을 수 있다.
  - `hide`가 아니라 `close`이므로 잘못 맞으면 회복 비용이 더 크다.
- 권장:
  - `WM_CLOSE`는 rules의 명시적 opt-in 플래그로 분리하거나,
  - legacy/ad 시그니처가 같이 있을 때만 닫고, 그 전에는 `hide` 또는 관찰 모드로 한 단계 낮추는 것이 좋다.

### 3. `stop()` join timeout 이후에도 재은닉이 발생할 수 있음

- 근거:
  - `stop()`은 watch thread가 2초 안에 끝나지 않아도 경고만 남기고 `_restore_hidden_windows()`를 실행한다. `kakao_adblocker/event_engine.py:137-150`
  - 실제 watch loop는 루프 경계에서만 stop flag를 확인한다. `kakao_adblocker/event_engine.py:267-282`
  - `_apply_once()` 내부에는 "종료 진행 중" 가드가 없다. `kakao_adblocker/event_engine.py:336-416`
  - 현재 테스트도 timeout 경고 기록만 확인하고, timeout 이후 재은닉이 없는지는 검증하지 않는다. `tests/test_engine_v11.py:239-262`
- 리스크:
  - thread가 Win32 호출에서 늦게 복귀하면, 복원 직후 다시 창을 숨긴 뒤 종료될 수 있다.
  - 문서상 "차단 OFF/종료 시 즉시 원복" 보장을 가장 흔들 수 있는 부분이다.
- 권장:
  - `_stopping` 같은 별도 플래그를 두고 `_apply_once()`와 `_hide_window()`에서 즉시 중단시키거나,
  - timeout 시에는 restore보다 먼저 추가 hide/apply를 봉쇄하는 쪽으로 순서를 강화해야 한다.

### 4. `self-check`가 실제 UI 부팅 실패를 잡아주지 못함

- 근거:
  - `self-check`는 APPDATA, `tasklist`, Run 레지스트리, tray import만 본다. `kakao_adblocker/app.py:63-77`
  - 실제 실행 경로는 이후 `tkinter` import와 `tk.Tk()` 생성에 의존한다. `kakao_adblocker/app.py:120-122`
- 리스크:
  - PyInstaller/Tcl-Tk 패키징 문제, 손상된 Python/Tk 환경, GUI 세션 이슈는 `--self-check`에서 통과하고 실제 실행에서만 죽을 수 있다.
  - README/CLAUDE 기준으로 보면 self-check의 신뢰 범위가 현재보다 좁다.
- 권장:
  - `tkinter import`와 `Tk()` 생성/파괴를 짧게 검증하는 항목을 `--self-check`에 추가하는 편이 낫다.
  - 가능하면 tray도 "import 가능"이 아니라 "아이콘 초기화 가능"까지 경량 확인하는 옵션이 있으면 좋다.

### 5. 스캔 단계의 메인 윈도우 판정과 적용 단계의 판정이 일치하지 않음

- 근거:
  - `_watch_once()`는 top-level `EVA_Window_Dblclk`가 비어 있지 않은 제목만 가지면 title 검증 없이 메인 후보로 넣는다. `kakao_adblocker/event_engine.py:294-305`
  - 반면 `_apply_once()`는 다시 자식 트리를 보고 `_is_main_window(children)`로 재검증한다. `kakao_adblocker/event_engine.py:365-367`
- 리스크:
  - 상태 문자열의 `메인윈도우 N` 값이 실제 조정 대상보다 크게 잡힐 수 있다.
  - popup/dialog가 섞이면 후보 집합과 로그 노이즈가 늘어난다.
- 권장:
  - scan 단계에서도 apply 단계와 같은 "확정 메인 윈도우" 기준을 쓰거나,
  - 상태용 카운터를 `candidate_main_window_count`와 `confirmed_main_window_count`로 분리하는 것이 낫다.

## 추가 구현 권장 사항

### 1. 실제 카카오톡 버전 변화에 대한 회귀 장치가 더 필요함

- 현재 자동 검증은 단위 테스트와 환경 self-check 중심이다.
- `scripts/smoke_check.ps1:26-30`도 최종 단계는 수동 체크리스트다.
- 권장:
  - `--dump-tree` 결과를 버전별 fixture로 남기고,
  - `main_window_classes`, `main_view_prefix`, `Chrome_WidgetWin_*` 패턴이 바뀌었을 때 diff를 감지하는 회귀 테스트를 추가하는 편이 좋다.

### 2. rules에 "강도 조절용 스위치"가 더 필요함

- 현재는 `aggressive_mode`가 사실상 큰 스위치 하나다.
- 권장:
  - `close_empty_eva_child`
  - `hide_bottom_banner_without_token`
  - `require_legacy_signature_for_hide`
  - 같은 개별 플래그를 `layout_rules_v11.json`에 두면 현장 대응이 빨라진다.

### 3. 사용자에게 보이는 진단 정보가 조금 더 직접적이면 좋음

- tray 미가용, startup 롤백 실패, restore 실패 누적 등은 대부분 로그 중심이다.
- 권장:
  - 상태 문자열 또는 별도 진단 창에서
  - "현재 tray 비가용 사유"
  - "마지막 registry rollback 결과"
  - "최근 5회 restore 실패 hwnd/class"
  - 정도를 바로 보여주면 현장 디버깅 시간이 줄어든다.

## 우선순위 제안

1. `aggressive_mode` 오탐 완화
2. `WM_CLOSE` 조건 완화 또는 rules opt-in화
3. `stop()` timeout 이후 재은닉 방지
4. `self-check`에 `tkinter/Tk` 검증 추가
5. dump-tree 기반 회귀 테스트 도입

## 결론

현재 코드는 테스트 기준으로는 깨지지 않는다. 다만 실제 사용자 환경에서 문제를 만들 가능성이 가장 큰 곳은 "공격적 휴리스틱의 오탐", "빈 child window를 닫는 로직", "종료 경합", "self-check의 진단 범위 부족"이다. 다음 수정 라운드에서는 새 기능을 늘리기보다 이 네 축을 먼저 다듬는 편이 전체 신뢰도를 더 크게 올린다.
