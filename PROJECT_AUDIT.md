# Project Audit

감사 일자: 2026-09-02  
대상: KakaoTalk Layout AdBlocker v11.1.0 (기본 구현 = Rust native `kakao-adblock-rs`)  
범위: 기능 구현·런타임 안정성. 코드는 수정하지 않음.

## 1. Executive Summary

이 프로젝트는 Windows 전용 카카오톡 **layout-only** 광고 차단기다. 현재 기본 런타임은 Rust 워크스페이스(`kakao-core` / `kakao-win32` / `kakao-app`)이고, Python v11은 `legacy/python-v11/`에 골든 패리티 참고 구현으로 남아 있다. 엔진의 강한 시그니처(owned `WS_POPUP` + Chrome Legacy, bottom banner + token)는 fixture/골든으로 고정되어 있고, 단일 인스턴스 뮤텍스 유지와 `SWP_NOMOVE` 리사이즈는 최근 수정되었다.

전체 위험도는 **Medium**. 데이터 유실/파괴나 네트워크 차단 계열 보안 문제는 없다. 설정 JSON과 카카오톡 HWND만 다루며 DB가 없다.

가장 중요한 문제:

1. **Weak-signal 판정이 tick 사이에 누적되지 않아** substring legacy hide, token-only Chrome hide, empty `EVA_ChildWindow` close가 런타임에서 사실상 적용되지 않는다.
2. **숨김 창 stale 원복이 없다.** 시그니처가 사라져도 disable/종료 전까지 숨긴 채로 남는다.
3. **트레이 “업데이트 확인”은 설치/재시작을 하지 않는다.** `download_and_verify`는 정의만 있고 호출자가 없다.
4. **GUI 서브시스템에서 파일 로그가 없다.** tracing은 stderr라 더블클릭 실행 시 운영 로그가 사실상 사라진다.
5. **적응형 50ms/200ms 폴링은 구현되어 있지 않다.** 훅이 실패하면 슬립 없이 tick이 돌 수 있다.

데이터 손상 가능성: **낮음**. 사용자 파일은 `%APPDATA%\KakaoTalkAdBlockerLayout` JSON뿐이고, 파손 시 broken 백업 + 기본값 heal이 있다. 카카오톡 창 좌표를 잘못 복원하면 UI가 깨질 수 있으나 최근 패치로 메인 뷰 리사이즈는 복원 스냅샷에서 제외했다.

가장 먼저 수정할 영역: `evaluate_graph`/`spawn_worker`의 candidate state 수명(weak confirm + stale restore), 그다음 트레이 업데이트 실제 적용, 파일 로그와 훅 실패 시 폴백 슬립.

## 2. Project Understanding

### 목적

카카오톡 Windows 클라이언트의 광고 영역을 hosts/DNS/레지스트리/패킷 차단 없이 Win32 레이아웃 조정·은닉으로 제거한다. UAC가 필요 없다. 알고리즘은 `blurfx/KakaoTalkAdBlock` 계열 계약을 따른다.

### 주요 entrypoint

- 기본: `rust/crates/kakao-app/src/main.rs` → `kakao_app::run_with_args` (`kakao-adblock-rs`, 배포명 `KakaoTalkLayoutAdBlocker_v11.exe`)
- 루트 `kakaotalk_layout_adblock_v11.py`: Rust EXE 안내만 출력하고 종료 코드 0
- Python 참고: `legacy/python-v11/kakaotalk_layout_adblock_v11.py`

### 핵심 모듈

| 크레이트/경로 | 역할 |
|---|---|
| `kakao-core` | 그래프 평가, 시그널, 레이아웃 공식, rules |
| `kakao-win32` | Real/Fake Win32, 프로세스 스냅샷, mutex, tray, WinEvent hook, Run 레지스트리 |
| `kakao-app` | CLI, 설정, 워커, 덤프, self-check, updater |
| `legacy/python-v11` | 골든/회귀 참고 구현 (`tests/`가 이 패키지를 import) |

### 데이터 저장

- `%APPDATA%\KakaoTalkAdBlockerLayout\layout_settings_v11.json`
- `%APPDATA%\KakaoTalkAdBlockerLayout\layout_rules_v11.json`
- 로그 경로 상수는 `layout_adblock.log`이나 Rust는 이 파일에 쓰지 않음
- DB 없음. 숨김 스냅샷은 프로세스 메모리만

### 외부 의존성

- Win32 (`windows` crate)
- GitHub Releases (`ureq` + Ed25519 `update.json`)
- 시작프로그램: `HKCU\...\Run\KakaoTalkAdBlockerLayout`

### 핵심 실행 흐름

```
Explorer/Run 더블클릭
  → main.rs (windows_subsystem=windows, CLI면 AttachConsole)
  → run_with_args
  → load_settings/load_rules (%APPDATA%)
  → InstanceMutex::acquire()  [핸들을 함수 끝까지 유지]
  → spawn_worker (scan+evaluate+apply)
  → tray::run_loop (메시지 전용 HWND + Shell_NotifyIcon)
       ToggleEnabled → AtomicBool + save_settings + worker restore_all
       Exit → 루프 종료 → stopping=true → restore_all → join
```

엔진 tick:

```
kakaotalk_pids (ToolHelp)
  → build_graph (EnumWindows + EnumChildWindows + GetParent/owner)
  → evaluate_graph (메인 확정, legacy/aggressive/popup, set_pos)
  → apply_evaluation (WM_CLOSE / SW_HIDE / SetWindowPos)
```

실측 메인 배너(KakaoTalk 26.5): owned `WS_POPUP`을 `GetParent`→owner 경로로 후보 등록 후 legacy exact hide. 골든 `owned_popup_legacy_ad.json`으로 고정.

## 3. Audit Coverage & Limitations

### 확인한 모듈

- `rust/crates/kakao-app/src/{main.rs,lib.rs,engine.rs,config.rs,updater.rs,startup.rs,dump.rs,self_check.rs,graph_build.rs}`
- `rust/crates/kakao-win32/src/{real.rs,tray.rs,single_instance.rs,event_hook.rs,process.rs,api.rs}`
- `rust/crates/kakao-core/src/{evaluate.rs,signals.rs,rules.rs,layout.rs}`
- `legacy/python-v11` 중 restore/update/layout 대조
- `.github/workflows/{release.yml,windows-ci.yml}`, `scripts/build_release.ps1`
- `README.md`, `CLAUDE.md` (루트 `AGENTS.md`는 없음; `.agents/skills/speckit-*`만 존재)

### CodeGraph로 본 호출 관계

- `run_with_args` → `tick` → `apply_evaluation` / `evaluate_graph`
- `spawn_worker` → `EventHook` + `restore_all` (disable/stop만)
- `TrayCommand::CheckUpdate` → `updater::check_for_update`만 (download 없음)
- `download_and_verify` 호출자: **없음**
- `save_settings` 호출: 트레이 토글 경로
- Python `LayoutOnlyEngine.stop` / `UpdateService.launch_installer`는 레거시 전용

### 실행한 테스트

- `pytest -q --basetemp .pytest_tmp` → **242 passed** (`PYTHONPATH=legacy/python-v11`)
- `cargo test --workspace` (x86_64-pc-windows-msvc) → **통과** (kakao-app 6, scan_parity 3, golden_parity 1, kakao-win32 5, smoke 1)

실행하지 않음: 실기 KakaoTalk attach, 트레이 수동 클릭, 실제 GitHub 업데이트 다운로드, pyright(이번 감사 세션).

### 한계

- CodeGraph 인덱스가 `legacy/` 심볼을 함께 노출한다. 활성 판단은 `rust/` + `tests/` + 루트 엔트리로 좁혔다.
- 실기에서 재현된 하단 공백·이중 실행·검은 화면은 이전 세션에서 패치됨. 이 감사는 **현재 HEAD** 기준이다.
- `std::fs::rename`의 Windows 덮어쓰기 동작은 러스트 버전마다 다를 수 있어, 설정 저장 실패는 오류 무시(`let _ = save_settings`)만 Confirmed로 남긴다.

## 4. High-Risk Issues

### [ISSUE-001] Weak-signal 확정이 tick마다 리셋되어 해당 액션이 적용되지 않음

* **위치:** `rust/crates/kakao-core/src/evaluate.rs` `apply_once` / `inspect_candidates`; `signals.rs` `update_candidate_state`; `engine.rs` `tick`
* **우선순위:** High
* **신뢰도:** Confirmed
* **문제:** `weak_signal_confirm_ticks` 기본값은 2다. `update_candidate_state`는 Strong이면 1틱에 확정, Weak는 `match_streak >= 2`가 필요하다. `apply_once`는 **호출마다 빈 `HashMap`**으로 상태를 만든다. `tick`도 이전 상태를 넘기지 않는다. 따라서 Weak는 영원히 streak=1에서 멈추고 hide/close가 나가지 않는다.
* **발생 조건:** 다음 판정이 Weak일 때 — `legacy_signature == "substring"`, Chrome_WidgetWin + ad token이면서 bottom-banner 기하가 아님, empty `EVA_ChildWindow` close(ad signal이 있어 close 결정이 난 경우).
* **영향:** 26.5 메인 owned-popup(exact/Strong)은 동작한다. substring 레거시, 토큰만 있는 위젯, empty child close 계약은 런타임에서 빠진다. Python 참고 구현은 `_candidate_states`를 프로세스 수명 동안 유지한다.
* **근거:** `apply_once` L512 `let mut states: HashMap<...> = HashMap::new();`, `update_candidate_state` L226–228, `empty_eva_close_decision`/`legacy_hide_decision("substring")`/`aggressive_hide_decision`의 Weak. 골든 `owned_popup_legacy_ad.json`은 Strong이라 단일 tick hide가 통과한다. 워크스페이스 테스트는 이 multi-tick 누적을 검증하지 않는다.
* **반증 확인:** Strong 경로는 1틱 확정이라 메인 배너는 보호된다. `ticks.max(1)`이어도 Weak는 2가 필요하다. 상위 caller가 상태를 넘기는지 확인했으나 `tick` → `evaluate_graph` 시그니처에 이전 state가 없다.
* **호출/영향 범위:** `spawn_worker` → `tick` → `evaluate_graph` → `apply_once` → `apply_evaluation`. dump-tree preview도 동일하게 1틱.
* **권장 수정 방향:** Python처럼 `HashMap<WindowIdentity, CandidateState>`를 워커에 두고 `evaluate_graph`에 왕복 전달. Weak 확정 후에만 mutate.
* **필요한 회귀 테스트:** 동일 fixture를 두 번 evaluate했을 때 2번째에 substring/empty-close가 action으로 승격되는지. 1틱만 보면 pending이어야 함.

### [ISSUE-002] 숨김 창이 시그니처 소멸 후에도 자동 원복되지 않음

* **위치:** `rust/crates/kakao-app/src/engine.rs` `spawn_worker`, `restore_all`
* **우선순위:** High
* **신뢰도:** Confirmed
* **문제:** 스냅샷 복원은 `enabled`가 true→false로 바뀌거나 워커가 `stopping`으로 끝날 때만 실행된다. Python `restore_no_longer_matched_hidden_windows`에 해당하는 tick 단위 stale 원복이 없다.
* **발생 조건:** aggressive/legacy로 숨긴 창의 텍스트/클래스가 더 이상 광고가 아닌 경우, 또는 오탐 숨김 후 사용자가 차단을 끄지 않는 경우.
* **영향:** CLAUDE.md 계약(“시그니처에서 벗어나면 stale로 남지 않고 자동 원복”)과 불일치. 잘못 숨긴 창이 세션 동안 유지될 수 있다.
* **근거:** `spawn_worker`에서 `restore_all` 호출은 disable 전환과 루프 종료 두 곳뿐. `evaluate_graph` actions.show는 apply_evaluation에서 쓰이지 않는다.
* **반증 확인:** disable/Exit 시 restore는 있다. HWND+pid+class identity 가드는 있다. 그러나 “신호 소멸” 경로는 없다. 최근 패치로 **리사이즈 스냅샷은 의도적으로 제외**했으므로, 숨김만의 stale 원복 부재는 별개다.
* **호출/영향 범위:** tray ToggleEnabled → flags.enabled → worker restore_all. 일반 tick은 hide만 누적.
* **권장 수정 방향:** 이번 tick의 matched identity 집합과 snapshots 키를 비교해 miss+grace 후 SW_SHOW. 자식 창 복원은 화면좌표 SetWindowPos를 쓰지 말 것(검은 화면 회귀).
* **필요한 회귀 테스트:** hide 후 동일 hwnd의 텍스트를 비광고로 바꾼 FakeWin32에서 다음 tick에 visible=true.

### [ISSUE-003] 트레이 업데이트 확인이 설치·재시작을 수행하지 않음

* **위치:** `rust/crates/kakao-app/src/lib.rs` `TrayCommand::CheckUpdate`; `updater.rs` `check_for_update`, `download_and_verify`
* **우선순위:** High
* **신뢰도:** Confirmed
* **문제:** 메뉴 “업데이트 확인”과 README의 “원클릭으로 안전하게 업데이트 및 재시작”이 불일치한다. 구현은 매니페스트 GET + 서명 검증 후 `tracing` 로그만 남긴다. `download_and_verify`는 크레이트 내 정의만 있고 호출자가 없다(grep 1건 = 정의).
* **발생 조건:** 사용자가 트레이에서 업데이트 확인을 누를 때. GUI라 로그도 안 보인다.
* **영향:** 새 릴리스가 있어도 바이너리가 바뀌지 않는다. 사용자는 성공/실패를 알 수 없다.
* **근거:** `CheckUpdate` 분기 L265–271. CLI `--check-update`도 println 후 종료. Python `UpdateService.launch_installer`는 레거시에만 존재.
* **반증 확인:** 매니페스트 검증 자체(Ed25519, URL pin, size, sha256, is_newer)는 구현되어 있다. 설치 파이프라인만 단절. `expires_at`은 Rust가 강제하지 않음(ISSUE-007).
* **호출/영향 범위:** tray wnd_proc → on_command → check_for_update. ureq는 이 콜백 스레드(메시지 루프)에서 동기 실행.
* **권장 수정 방향:** Python과 같이 staged 다운로드 → 재검증 → 프로세스 종료 후 교체 스크립트. 트레이에서는 백그라운드 스레드 + 사용자 가시 결과(트레이 팁/메시지).
* **필요한 회귀 테스트:** CheckUpdate가 download_and_verify를 호출하는지의 단위 테스트; 설치 도우미의 sha256 재검증.

### [ISSUE-004] WinEvent 훅 실패 시 슬립 없는 tick 루프

* **위치:** `rust/crates/kakao-app/src/engine.rs` `spawn_worker` L244–270; `event_hook.rs` `EventHook::install`
* **우선순위:** High
* **신뢰도:** Likely (훅 실패는 환경 의존, 루프 구조는 코드로 확인)
* **문제:** `idle_poll_interval_ms.max(2000)`이 reconciliation 하한이다. `poll_interval_ms`(문서상 50ms)는 워커에서 **읽히지 않는다**. 훅이 `Some`이면 이벤트 없을 때 80ms wait. 훅이 `None`이면 wait 분기가 빠져 **슬립 없이 tick**이 반복된다. `last_full`을 매 tick 갱신하므로 due_recon도 다시 안 뜬다.
* **발생 조건:** `SetWinEventHook` 실패(세션/권한/데스크톱). 일반 대화형 세션에서는 성공하는 경우가 많다.
* **영향:** CPU 100%에 가까운 스핀, 카카오톡 Win32 호출 폭주. 문서의 50ms/200ms 적응형 폴링은 구현과 다르다(이벤트 구동 + 최소 2s recon).
* **근거:** `if let Some(hook) = hook.as_ref() { wait; continue; }` 뒤에 Windows용 else-sleep이 없다. `poll_interval_ms` grep은 config 필드 정의뿐.
* **반증 확인:** 훅 성공 시 busy loop는 아니다. burst 구간에만 `burst_scan_interval_ms` sleep. 첫 iteration은 `last_full`을 10초 전으로 둬 즉시 1회 tick(워밍업 유사).
* **호출/영향 범위:** 워커 전용. 트레이 루프와 별도 스레드.
* **권장 수정 방향:** 훅 None이면 `poll_interval_ms`/`idle_poll_interval_ms`로 sleep. 훅 Some이면 recon 주기를 idle(200ms)에 맞출지 문서와 합의.
* **필요한 회귀 테스트:** hook 없는 워커가 한 루프에서 sleep을 호출하는지 또는 시간 하한이 있는지(테스트 더블).

## 5. Potential Functional Gaps

- **Confirmed Gap:** 프로덕션 EXE는 `layout_adblock.log`에 쓰지 않는다. `init_tracing`은 stderr fmt subscriber. `windows_subsystem = "windows"`라 더블클릭 시 로그가 없다. README/트레이 “로그 폴더 열기”는 폴더는 열리지만 로그 파일이 비거나 없음.
- **Confirmed Gap:** 중복 실행 시 `eprintln!("already running")` 후 0 종료. GUI라 사용자에게 메시지가 없다.
- **Confirmed Gap:** `download_and_verify` 미연결(ISSUE-003). `expires_at` 미검증 — Python `UpdateService`는 만료를 거부한다. Rust는 payload에 필드가 있어도 만료 검사를 하지 않는다.
- **Confirmed Gap:** self-check가 Python만큼의 레지스트리/tasklist/트레이 import 진단을 하지 않는다. `self_check.rs`는 APPDATA 존재 + windows cfg + settings load 수준.
- **Confirmed Gap:** 시작 시 Run 등록 health/stale 복구가 없다. Python은 1회 동기화. Rust는 트레이 토글 때만 레지스트리를 만진다.
- **Likely Gap:** `ShowWindow` 반환값은 “이전 가시성”이라, 숨겼던 창을 성공적으로 다시 보여도 FALSE다. `restore_all`은 이를 실패로 센다. 복원 자체는 될 수 있으나 실패 카운터가 왜곡된다.
- **Likely Gap:** 트레이 CheckUpdate/OpenLogs가 UI 스레드에서 동기 HTTP/셸을 호출한다. 네트워크 지연 시 메뉴가 멈춘다(ureq 기본 타임아웃 의존).
- **Likely Gap:** `save_settings` 실패를 무시하고 enabled/aggressive 메모리는 이미 뒤집힌다. 재시작 시 디스크 값으로 되돌아간다. Python은 저장 실패 시 토글 롤백.
- **추정:** EventHook 채널 `bounded(1024)` + `try_send` 드롭. 생성 폭주 시 이벤트 유실, 다음 recon(≥2s)까지 지연. 치명적이진 않음.
- **추정:** `EventHook`의 `OnceLock<Sender>`는 프로세스당 1회. 테스트에서 install을 두 번 하면 두 번째 rx는 이벤트를 못 받을 수 있다. 프로덕션은 1회.
- **추정 아님(명시):** 메인 배너 owned-popup 경로는 골든으로 고정되어 있고, 이번 세션의 하단 공백(SWP_NOMOVE) / 뮤텍스 드롭 / 검은 화면(자식 화면좌표 복원)은 HEAD에서 수정된 상태로 본다.

## 6. Documentation Mismatches

다음이 구현과 다르다.

| 문서 | 주장 | 실제 |
|---|---|---|
| README | 차단 OFF/종료 시 숨김 **및 리사이즈** 100% 원복 | 숨김/zero-size만 복원. OnlineMainView 리사이즈는 스냅샷하지 않음(검은 화면 방지). |
| README | 원클릭 업데이트 다운로드·검증·재시작 | 매니페스트 확인 + 로그만 |
| README | 적응형 폴링 50ms/200ms | `poll_interval_ms` 미사용. 이벤트 + recon 하한 2s + wait 80ms |
| README | 로그 파일 `layout_adblock.log` | tracing stderr, 파일 append 없음 |
| README | 시작 즉시 광고 제거 | 워커 첫 tick은 있으나 훅/ recon에 의존. 동기 warm-up 함수는 Python만 문서화 |
| CLAUDE.md | 핵심 모듈이 `kakao_adblocker/app` 등 Python 패키지 | 활성 런타임은 `rust/crates/*`. CLAUDE 상단은 Rust로 갱신됐지만 모듈 목록 대부분은 Python 계약 설명 |
| CLAUDE.md | 숨김 창 시그니처 소멸 시 자동 원복 | Rust 워커에 stale restore 없음 |
| CLAUDE.md | `--dump-tree` windows 트리가 owned popup 누락 | Rust dump는 top-level owner를 `owned_popups`로 분리 기록 |
| 루트 AGENTS.md | 감사 지시에서 읽으라 함 | 파일 없음 |
| 구 PROJECT_AUDIT.md | Python `launch_installer` TOCTOU 등 | 그 코드는 레거시. 현재 Rust 기본 경로와 불일치 |

알고리즘 freeze 문구(owned popup, token 없는 geometry hide 금지, popup depth 2)는 `kakao-core`와 골든이 대체로 일치한다.

## 7. Recommended Fix Plan

### Phase 1 — Immediate

1. 워커에 `CandidateState` 맵을 유지해 Weak 2틱 확정과 골든 단일-tick preview를 분리한다 (ISSUE-001).
2. matched identity 기준 stale hide 원복. 자식 창은 SW_SHOW만 또는 SWP_NOMOVE 크기 복원. 화면좌표 SetWindowPos 금지 (ISSUE-002, 검은 화면 회귀 방지).
3. 트레이/CLI 업데이트를 `download_and_verify` + 교체 도우미에 연결하거나, 메뉴 문구를 “확인만”으로 낮춘다 (ISSUE-003). 기능을 남기려면 설치 직전 해시 재검증과 결과 JSON이 필요하다.

### Phase 2 — Stability

- 훅 실패 시 `poll_interval_ms`/`idle` sleep. 문서와 recon 주기 합의 (ISSUE-004).
- tracing을 `layout_adblock.log`에 파일 append. GUI에서도 진단 가능.
- CheckUpdate/HTTP를 워커 스레드로. 트레이에 결과 표시.
- `save_settings` 실패 시 토글 롤백. `expires_at` 검증.
- `restore_all`은 `is_window_visible`로 성공 판정.
- 시작 시 Run 등록 health(커스텀 명령은 덮지 않음).

### Phase 3 — Structural

- CLAUDE/README를 Rust 런타임 기준으로 재정렬. Python 절은 `legacy/python-v11`로 한정.
- evaluate의 preview(덤프)와 apply(상태ful) API 분리.
- 골든에 weak 2-tick / stale restore fixture 추가. Python pytest는 참고 구현 회귀로 유지하되 “기본 런타임”과 혼동되지 않게 표시.

실제 코드는 이 감사에서 수정하지 않았다.

## 8. Test Recommendations

| 종류 | 시나리오 | 기대 |
|---|---|---|
| Unit | Weak substring legacy fixture를 `evaluate` 1회 | action pending 또는 hide 없음, match_streak=1 |
| Unit | 동일 상태를 2회 누적 evaluate | 2회째 hide 포함 |
| Unit | empty EVA + ad_signal, ticks=2 누적 | 2회째 close |
| Integration | FakeWin32 hide 후 텍스트를 비광고로 변경, 다음 tick | 창 visible, snapshots에서 제거 |
| Integration | FakeWin32 OnlineMainView y=38 리사이즈 후 restore_all | left/top 유지, 리사이즈 hwnd가 snapshot에 없음 (이미 scan_parity에 있음 — 유지) |
| Unit | `download_and_verify`를 트레이/CLI 경로에서 호출하도록 연결한 뒤, 잘못된 sha256이면 원본 EXE 불변 | |
| Concurrency | mutex acquire 중 두 번째 acquire 실패, drop 후 성공 (이미 `single_instance` 테스트 — 유지) | |
| Regression | owned_popup_legacy_ad hide 527936 (이미 있음) | |
| Platform | GUI EXE `--self-check`는 report 파일로 성공; 인자 없이 두 번째 실행은 0 종료이며 워커 미기동 | 콘솔 없는 already-running |
| E2E | 훅 더블이 None일 때 1초 동안 tick 횟수 상한 | busy loop 없음 |
| Unit | `save_settings`가 기존 파일을 덮어쓰는지 Windows에서 확인 | 토글 후 파일 enabled 값 변경 |

단순히 “테스트 추가”가 아니라, Weak는 **1틱 vs 2틱 누적**을 나눠야 한다. 현재 골든은 1틱 Strong 위주라 ISSUE-001을 놓친다.

## 9. Final Assessment

| 항목 | 평가 | 근거 |
|---|---|---|
| Functional Correctness | **Acceptable** | 26.5 owned-popup/Strong hide·메인 뷰 리사이즈는 동작. Weak/stale/업데이트 설치는 빠짐 |
| Runtime Stability | **Acceptable** | mutex 유지, stop 시 stopping 플래그, 훅 실패 시 스핀 위험 |
| Data Integrity | **Good** | JSON heal/backup, 카카오톡 프로세스 메모리만 변경, DB 없음 |
| Error Resilience | **Needs Work** | 저장/ShowWindow/업데이트 실패가 사용자에게 안 보임, 파일 로그 없음 |
| Cross-platform Robustness | **Good** | Windows 전용 fail-fast(코드 2)가 명시적. 비Windows는 지원 대상 아님 |
| Test Confidence | **Acceptable** | Python 242 + Rust 골든/scan_parity는 Strong 경로에 강함. multi-tick·트레이·업데이트 설치는 약함 |

**실제로 먼저 수정할 문제 3개**

1. **ISSUE-001** — candidate state를 워커에 유지해 Weak 확정이 살아나게 한다.
2. **ISSUE-002** — 시그니처가 사라진 숨김 창을 tick마다 원복한다(화면좌표 자식 SetWindowPos 금지).
3. **ISSUE-003** — 업데이트를 실제로 적용하거나, 문서/메뉴에서 “확인만”이라고 정정한다.

## 10. Audit Remediation Status (감사 지적사항 조치 완료 현황)

- [x] **ISSUE-001 조치 완료**: `evaluate_graph_with_states`를 통해 워커에서 `states: HashMap<WindowIdentity, CandidateState>`를 프로세스 수명 동안 유지. Weak 시그널 1틱(pending) vs 2틱(confirmed hide/close) 누적 확정 동작 검증 완료 (`tests/evaluate_weak_parity.rs` 통과).
- [x] **ISSUE-002 조치 완료**: `engine.rs`에 `restore_stale_hidden` 구현. 시그니처가 소멸된 창은 2틱 유예(threshold=2) 후 안전하게 `SW_SHOW` 복원. 자식 창은 `SWP_NOMOVE`를 유지하여 검은 화면 회귀 방지 (`tests/restore_regression.rs` 통과).
- [x] **ISSUE-003 조치 완료**: `crates/kakao-updater` 전용 헬퍼 바이너리 신설. 매니페스트 `expires_at` 검증, SHA-256 검증, 프로세스 종료 대기, 교체 및 자동 재실행, 실패 시 롤백 구현. 트레이 `CheckUpdate` 비동기 스레드 및 네이티브 `MessageBox` 연동 완료 (`updater_tests.rs` 통과).
- [x] **ISSUE-004 조치 완료**: 훅 실패/비대화형 시 `idle_ms`(200ms) / `active_ms`(50ms) 기반 sleep 적용으로 busy loop 및 CPU 스핀 방지. 차단 비활성화 시 1000ms 슬립 적용.
- [x] **파일 로깅 조치 완료**: `%APPDATA%\KakaoTalkAdBlockerLayout\layout_adblock.log`에 tracing 파일 append 레이어 연동.
- [x] **중복 실행 UI 안내 완료**: 콘솔이 없는 GUI 더블클릭 중복 실행 시 알림 대화상자 노출 후 안전 종료.
- [x] **설정 저장 실패 롤백 완료**: 트레이 토글에서 `save_settings` 실패 시 상태 롤백.
- [x] **ShowWindow 복원 판정 정상화**: `restore_all`에서 `is_window_visible`로 복원 성공 여부 정확하게 판정.

