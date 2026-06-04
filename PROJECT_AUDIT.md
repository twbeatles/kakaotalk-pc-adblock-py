# Project Audit

## 1. Executive Summary

Overall residual risk after remediation: **Low to Medium**.

The original implementation audit found no Critical issue. The operational risks identified in the audit have been addressed: duplicate UI instances are blocked with a Windows named mutex, tray callbacks no longer touch Tk from tray/worker threads, Win32 text reads preserve known/truncated/error state, dump/report failures return clear exit codes, and Startup Run command repair preserves custom registrations.

Remaining risk is mostly operational: live KakaoTalk UI changes are still validated by manual dump/fixture review rather than fully automated CI, and restore-failure retry snapshots are intentionally process-local rather than persisted across restarts.

Latest validation:

```text
powershell -ExecutionPolicy Bypass -File .\scripts\dev_check.ps1
pyright: 0 errors, 0 warnings
pytest: 220 passed

powershell -ExecutionPolicy Bypass -File .\scripts\smoke_check.ps1
self-check: 7/7 checks passed (core_failed=0, optional_failed=0)
```

## 2. Project Understanding

Docs/specs reviewed for this implementation pass:

- `README.md`
- `CLAUDE.md`
- `GEMINI.md`
- `legacy/README.md`
- `kakaotalk_adblock.spec`
- `legacy/specs/kakaotalk_adblock_v10.spec`
- `.gitignore`

Project purpose:

- Windows KakaoTalk client ad-area cleanup tool.
- v11 contract is `layout-only`; hosts, DNS, packet/network blocking, and registry-based ad blocking are intentionally out of scope.
- Startup Run registry handling exists only for autostart.
- Default runtime is tray-focused with adaptive polling.

CodeGraph analysis note:

- Broad CodeGraph queries can surface `legacy/` symbols even though active `pyrightconfig.json` excludes `legacy`.
- Active v11 analysis should be narrowed to `kakao_adblocker/`, `tests/`, and `kakaotalk_layout_adblock_v11.py`.

Packaging understanding:

- Active build target is `kakaotalk_adblock.spec`.
- `legacy/specs/kakaotalk_adblock_v10.spec` is only a filename-compatibility shim that mirrors the active v11 hidden-import surface.
- The new mutex, dynamic text-result, and Startup Run command parsing code uses stdlib `ctypes` calls into `kernel32/user32/shell32`, so no new PyInstaller hidden imports are required.

## 3. High-Risk Issues

### 3.1 Duplicate Application Instances

* 위치: `kakao_adblocker/app/__init__.py::main`, `_acquire_single_instance_guard`
* 문제: 여러 UI/engine 인스턴스가 같은 KakaoTalk 창을 동시에 조작할 수 있었다.
* 영향: hide/restore/resize 경합과 tray 상태 혼동이 발생할 수 있었다.
* 근거: 일반 UI 실행 경로에 `Local\KakaoTalkLayoutAdBlocker_v11` named mutex가 추가되었다. 중복 실행은 Tk root, `TrayController`, engine start 없이 stderr 메시지 후 종료 코드 `0`으로 종료한다.
* 권장 수정 방향: 구현 완료. 기존 창 활성화 IPC는 향후 별도 기능으로 분리한다.
* 우선순위: High, **Implemented**

### 3.2 Tray Callback Thread Safety

* 위치: `kakao_adblocker/ui.py::_safe_after`, `_drain_ui_queue`
* 문제: tray thread에서 Tk/root 메서드를 호출할 수 있었다.
* 영향: 실제 Tk 환경에서 tray menu callback이 간헐적으로 드롭될 수 있었다.
* 근거: `_safe_after()`는 queue put만 수행하고, root 생존 여부와 callback 실행 가능 여부는 Tk main-thread drain에서만 확인한다.
* 권장 수정 방향: 구현 완료.
* 우선순위: High, **Implemented**

### 3.3 Win32 Text Retrieval Ambiguity

* 위치: `kakao_adblocker/win32_api.py::get_window_text_result`, `kakao_adblocker/protocols.py::WindowTextResult`
* 문제: 고정 512자 buffer와 string-only 반환으로 empty/failure/truncation을 구분하지 못했다.
* 영향: popup host text read failure가 empty-title allow처럼 처리될 수 있었다.
* 근거: `WindowTextResult(text, known, truncated, error_code)`가 추가되었고, `Win32API`는 `GetWindowTextLengthW` 기반 동적 버퍼를 사용한다. unknown popup host는 guard blocked로 처리된다.
* 권장 수정 방향: 구현 완료.
* 우선순위: Medium, **Implemented**

### 3.4 Diagnostic Output Validation

* 위치: `kakao_adblocker/app/__init__.py`, `kakaotalk_layout_adblock_v11.py::_write_bootstrap_report`
* 문제: dump/report/startup trace write 실패와 과도한 dump duration 입력이 명확히 정리되지 않았다.
* 영향: traceback 노출 또는 장시간 dump 점유가 가능했다.
* 근거: write 실패는 stderr와 종료 코드 `1`, duration 상한 초과는 종료 코드 `2`로 처리된다. `--dump-series-duration-ms` 상한은 `10000`, interval 하한은 `10`이다.
* 권장 수정 방향: 구현 완료.
* 우선순위: Medium, **Implemented**

### 3.5 Startup Run Command Repair

* 위치: `kakao_adblocker/services.py::StartupManager`
* 문제: custom/wrapper Run command가 자동 sync로 덮어써질 수 있었다.
* 영향: 사용자가 의도적으로 구성한 autostart command가 표준 command로 교체될 수 있었다.
* 근거: Run command parsing은 `CommandLineToArgvW`와 환경변수 확장을 우선 사용한다. exact expected command와 source-mode compatible packaged EXE는 healthy이며, unknown/custom command는 `custom command left unchanged`로 보존된다.
* 권장 수정 방향: 구현 완료.
* 우선순위: Low, **Implemented**

## 4. Potential Functional Gaps

* 추정: 실제 KakaoTalk UI 변경에 대한 live smoke는 CI에서 강제되지 않는다. 릴리스 전 `--dump-tree` 또는 `--dump-tree-series`를 실제 UI에서 저장하고 fixture/test 필요 여부를 확인해야 한다.
* 추정: restore failure retry는 현재 프로세스 한정 정책이다. 프로세스 종료 이후 cross-process snapshot persistence는 구현하지 않았다.
* 추정: CodeGraph 인덱스는 `legacy/`를 포함할 수 있으므로 broad architecture query 결과를 active implementation으로 바로 해석하면 혼동이 생길 수 있다.

## 5. Recommended Fix Plan

1단계: 즉시 수정해야 할 문제

1. 중복 실행 방지 named mutex: **완료**
2. tray callback bridge main-thread drain: **완료**

2단계: 안정성 개선

1. Win32 text retrieval 동적 버퍼와 unknown 상태 처리: **완료**
2. dump/report 입력 검증과 종료 코드 정리: **완료**
3. Startup Run command parser와 custom command 보존: **완료**

3단계: 구조/문서 개선

1. README/CLAUDE/GEMINI/legacy README에 새 정책 문서화: **완료**
2. active/legacy spec의 hidden import 정합성 확인 및 주석 보강: **완료**
3. `.gitignore`에 `.codegraph/` 로컬 인덱스 제외 추가: **완료**

## 6. Test Recommendations

Covered by automated tests:

* duplicate UI launch mutex behavior
* self-check/dump mutex bypass
* tray `_safe_after()` worker-thread safety
* dynamic Win32 text and unknown popup host guard
* dump/report/startup trace write failure exit codes
* Startup Run command parsing and custom command preservation

Remaining manual checks:

* 릴리스 전 실제 KakaoTalk UI에서 `--dump-tree-series`를 저장해 popup/legacy/aggressive candidate가 기대대로 잡히는지 확인한다.
* PyInstaller release build는 `scripts/build_release.ps1 -NoSign` 또는 서명 환경이 있는 경우 서명 포함 build로 검증한다.
