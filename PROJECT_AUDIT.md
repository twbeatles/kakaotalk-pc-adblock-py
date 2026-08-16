# Project Audit

## 1. Executive Summary

이 프로젝트는 Windows 전용 KakaoTalk 레이아웃 광고 차단기이며, 설정/규칙을 `%APPDATA%`에 보관하고 백그라운드 엔진과 트레이 UI로 동작한다. 최근 추가된 GitHub Releases 업데이트 기능은 Ed25519 서명과 SHA-256 검증을 사용하므로 다운로드 전 검증의 기본 방향은 적절하다.

전체 위험도는 **Medium-High**다. 가장 중요한 문제는 업데이트 설치 도우미의 실제 적용 결과를 앱이 알 수 없다는 점과, 다운로드 후 설치 전 사이에 검증된 EXE가 교체될 수 있다는 점이다. 기존 엔진에도 종료 시 watch thread가 멈추지 않을 때 복원과 늦은 창 변경이 경쟁할 수 있는 경로가 남아 있다. 설정 저장/복구, 일반 트레이 콜백 디스패치, 단일 인스턴스 방어는 비교적 잘 구현되고 테스트도 존재한다.

감사는 `README.md`, `CLAUDE.md`, CodeGraph의 활성 v11 호출 관계를 기반으로 수행했다. `legacy/`는 문서상 보관 코드이므로 평가 범위에서 제외했다. 코드 변경은 하지 않았으며 이 리포트만 추가했다.

### Remediation Status (follow-up)

후속 구현에서 3.1, 3.2, 3.4의 권장 수정은 반영되었다. 설치 도우미는 교체 직전 재검증하고 결과 JSON을 남기며, 다음 시작 시 UI가 결과를 표시한다. 매니페스트에는 tag/만료 시각을 포함하고, 릴리스 asset 업로드는 멱등화 및 게시 후 서명 검증을 수행한다. 엔진은 종료 시작 시 즉시 `enabled=false`로 전환해 기존 `_can_mutate_windows()` guard가 늦은 mutation을 차단하도록 보강했다. Authenticode 서명 운영은 별도의 인증서가 필요한 선택 사항으로 남아 있다.

## 2. Project Understanding

### 목적과 실행 흐름

- 엔트리포인트 `kakaotalk_layout_adblock_v11.py`는 `kakao_adblocker.app.main()`으로 진입한다.
- 앱은 Windows named mutex로 일반 UI 실행을 단일 인스턴스로 제한하고, 런타임 설정/규칙/로그를 `%APPDATA%\KakaoTalkAdBlockerLayout`에서 준비한다.
- `LayoutOnlyEngine`은 KakaoTalk PID와 Win32 창을 스캔하고, 규칙에 맞는 광고 창 숨김/닫기 및 레이아웃 조정을 수행한다. `TrayController`는 UI 상태, 설정 토글, 시작프로그램 등록, 트레이 수명주기를 조정한다.
- 설정/규칙 JSON은 `config.storage._atomic_write_text()`의 임시 파일 + `os.replace()`로 저장한다. 파싱 실패 시 원본을 `*.broken-*`으로 백업하고 기본값으로 self-heal한다.

### 업데이트 흐름

`TrayController.check_for_updates()`가 daemon worker를 시작하고, `UpdateService.check_for_update()`가 latest release의 `update.json`을 가져온다. 내장된 Ed25519 공개키로 매니페스트를 검증한 뒤 `download_update()`가 EXE의 크기와 SHA-256을 확인한다. 사용자가 승인하면 `launch_installer()`가 별도 PowerShell 프로세스를 시작하고 앱을 종료한다. PowerShell은 부모 PID가 끝난 뒤 기존 EXE를 `.bak`으로 옮기고 staged EXE를 원래 경로로 이동한 후 재시작한다.

릴리스 워크플로는 `v*` 태그에서 Windows 빌드 후, `KAKAO_UPDATE_PRIVATE_KEY_B64` 시크릿으로 매니페스트를 서명하고 `gh release create`로 EXE와 `update.json`을 업로드한다.

### CodeGraph 기반 영향 범위

- `LayoutOnlyEngine.stop()` → `_restore_hidden_windows()` → `restore_hidden_windows()`는 창 변경/복원에 직접 영향이 있다.
- `TrayController.shutdown()`은 트레이 중지, 엔진 중지, Tk 종료를 순서대로 호출한다.
- `UpdateService.download_update()`의 유일한 호출자는 `TrayController.check_for_updates()`이며, `launch_installer()`도 UI 승인 경로에서만 호출된다.
- CodeGraph는 `UpdateService`의 매니페스트 검증 테스트는 찾았지만 `download_update()` 및 `launch_installer()`의 직접 테스트는 찾지 못했다.

## 3. High-Risk Issues

### 3.1 업데이트 설치 실패가 사용자에게 전달되지 않음

* 위치: `kakao_adblocker/services.py:571-589`, `kakao_adblocker/ui.py:417-423`
* 문제: `launch_installer()`는 PowerShell 도우미를 시작한 직후 성공으로 간주한다. 도우미가 부모 종료 뒤 EXE 이동/재시작에 실패해도 결과 파일, 로그, 다음 시작 시 알림이 없다. UI는 “설치를 위해 종료합니다”를 표시하고 종료한다.
* 영향: EXE가 백신/동기화 도구/다른 프로세스에 잠겨 있거나 대상 폴더에 쓰기 권한이 없으면 업데이트가 적용되지 않을 수 있다. 사용자는 성공으로 오인하고, `.bak` 또는 staged 파일만 남을 수 있다.
* 근거: 도우미 스크립트는 `catch`에서 복원을 시도한 후 throw하지만, 호출 프로세스는 이미 종료되어 해당 종료 코드나 stderr를 수집하지 않는다. `launch_installer()` 관련 테스트도 없다.
* 권장 수정 방향: 결과 JSON을 앱 데이터 폴더에 원자적으로 기록하고 다음 시작 시 소비/표시한다. 도우미의 실패/복원/재시작 실패를 기록하고, 경로 권한 및 target lock을 설치 전 점검한다.
* 우선순위: High

### 3.2 무결성 검증 후 설치 전 staged EXE의 TOCTOU 취약점

* 위치: `kakao_adblocker/services.py:538-568`, `kakao_adblocker/services.py:571-587`
* 문제: `download_update()`는 staged 파일을 해시 검증하지만, `launch_installer()`는 이후 `staged.is_file()`만 검사하고 해시/크기/파일 ID를 다시 확인하지 않는다. staged 파일은 사용자 쓰기 가능한 `%APPDATA%\...\updates`에 있다.
* 영향: 동일 사용자 권한의 다른 프로세스가 확인 이후 파일을 바꾸면 검증되지 않은 EXE가 기존 설치 파일을 대체할 수 있다. 특히 EXE가 더 높은 신뢰 경로에 설치된 경우 보안 영향이 커진다.
* 근거: 매니페스트의 `sha256`/`size`는 UI가 `launch_installer()`에 전달하지 않으며, PowerShell 스크립트도 staged 파일을 재검증하지 않는다.
* 권장 수정 방향: 업데이트 세션 객체에 manifest hash/size를 보존하고, 설치 도우미가 교체 직전에 다시 SHA-256과 크기를 확인하게 한다. 가능하면 사용자 전용 권한 ACL의 staging 디렉터리와 고유 파일명을 사용하고, 검증 후 파일 핸들을 유지하거나 권한을 제한한다.
* 우선순위: High

### 3.3 엔진 종료 timeout 경로에서 복원과 늦은 창 변경이 경쟁할 수 있음

* 위치: `kakao_adblocker/event_engine/controller.py:124-151`
* 문제: watch thread가 2초 안에 종료되지 않고 `_scan_apply_lock`도 1초 안에 확보되지 않으면, 코드가 lock 없이 `_restore_hidden_windows(reason="stop")`를 호출한다.
* 영향: 멈추지 않은 watch thread가 이후 hide/close/apply를 계속하면 복원 직후 창이 다시 변경될 수 있다. 종료 중 KakaoTalk 창의 최종 상태가 비결정적일 수 있다.
* 근거: 코드 주석도 lock 보유 thread가 stuck인 경우 unlocked restore로 fallback한다고 명시한다. README는 종료 시 새 hide/close/apply가 봉쇄되어 재은닉을 방지한다고 설명하므로, timeout fallback은 그 보장을 완전히 충족하지 못한다.
* 권장 수정 방향: 종료 세대(generation) 또는 cancellation token을 각 scan/apply의 commit 직전에 검증하고, timeout 후에는 어떤 창 변경도 수행하지 않도록 강제한다. lock 없이 복원해야 한다면 stale worker가 다시 변경하지 못하는 별도 상태를 먼저 원자적으로 설정한다.
* 우선순위: High

### 3.4 릴리스 워크플로 재시도/부분 성공을 복구할 수 없음

* 위치: `.github/workflows/release.yml:42-46`
* 문제: 워크플로는 무조건 `gh release create`를 실행한다. 릴리스 생성 후 asset 업로드 중 실패하거나 Actions를 재실행하면 기존 tag/release 때문에 create가 실패한다.
* 영향: 릴리스가 EXE 또는 `update.json` 하나만 가진 불완전 상태가 될 수 있고, 동일 태그로 자동 복구가 어렵다. 최신 릴리스를 참조하는 앱은 매니페스트 또는 artifact를 받지 못한다.
* 근거: `gh release create`에 기존 release를 확인/수정하는 분기가 없고, `gh release upload --clobber` 또는 재시도 로직도 없다.
* 권장 수정 방향: release 존재 여부를 검사해 생성 또는 upload를 분기하고, asset은 `--clobber`로 멱등 업로드한다. publish 전 두 asset의 존재와 매니페스트 검증을 확인한다.
* 우선순위: Medium

## 4. Potential Functional Gaps

- **추정:** 자동 업데이트는 onefile EXE에서만 지원되지만, UI의 “업데이트 확인”은 소스 실행에서도 노출된다. 이 경우 매니페스트를 정상 조회한 뒤 다운로드 단계에서 실패한다. 소스 실행에서는 버튼을 숨기거나 “배포 EXE에서만 가능”을 사전에 표시하는 편이 명확하다.
- **추정:** 업데이트 worker는 daemon thread이며 취소 토큰/진행률/연결 시간 제한 외의 읽기 제한이 없다. 앱 종료 후 콜백은 `_safe_after()`가 버리지만 다운로드는 프로세스 종료까지 진행할 수 있다. 대용량 또는 느린 네트워크에서 사용자 경험이 불명확하다.
- **추정:** 매니페스트에는 서명, 버전, URL, 해시, 크기만 있고 만료 시각/릴리스 태그/허용 호스트 정책이 없다. 서명 검증이 주 방어선이므로 즉시 취약점은 아니지만, 키 유출 또는 오래된 고버전 매니페스트 재배포에 대한 방어 심층화가 없다.
- **추정:** `download_update()`의 고정된 `KakaoTalkLayoutAdBlocker_v11-{version}.exe` 및 `.download` 경로에는 잠금/독점 생성이 없다. 단일 UI 인스턴스는 막지만, 비정상 종료 뒤 남은 파일, 향후 다중 채널/수동 실행 확장 시 충돌 처리가 필요할 수 있다.
- **문서 불일치:** `README.md:215-225`, `CLAUDE.md:105`의 트레이 메뉴 목록에는 새 `업데이트 확인` 항목이 없다. 같은 README의 자동 업데이트 절은 존재하므로 메뉴 문서만 갱신되지 않은 상태다.
- **추정:** 워크플로는 `-NoSign`으로 EXE를 빌드한다. 업데이트 매니페스트의 서명은 검증되지만 Windows Authenticode 서명은 별도다. 배포 신뢰/SmartScreen 요구가 있다면 release code-signing 구성과 운영 정책이 추가로 필요하다.

## 5. Recommended Fix Plan

### 1단계: 즉시 수정

1. 업데이트 도우미에 hash/size 재검증과 결과 파일을 추가하고, 다음 시작에서 성공/실패/복원 결과를 사용자에게 알린다.
2. `LayoutOnlyEngine`의 stop timeout 경로에 종료 세대 또는 cancellation commit guard를 도입해 lock 없는 복원 후 재은닉을 막는다.
3. release workflow를 멱등화하고, 생성된 release asset과 매니페스트 서명을 publish 직후 검증한다.

### 2단계: 안정성 개선

1. 업데이트 UI에 source-mode 사전 안내, 진행 상태, 취소/종료 정책, 남은 staged 파일 정리를 추가한다.
2. staging 파일을 고유한 세션 디렉터리에 두고 파일 권한과 cleanup 정책을 명시한다.
3. 매니페스트에 만료 시각과 tag/asset name을 포함하고, URL 구조와 release tag의 일치를 검증한다.

### 3단계: 구조 개선

1. `UpdateService`를 매니페스트 검증, 다운로드, 적용 결과, launcher로 분리하고 업데이트 세션 상태를 명시적 dataclass로 모델링한다.
2. PowerShell 인라인 문자열 대신 버전 관리되는 작은 updater helper 또는 well-tested native helper를 사용하고, 명확한 IPC/result contract를 둔다.
3. README/CLAUDE의 기능 목록을 테스트 또는 릴리스 체크리스트와 연계해 문서 드리프트를 줄인다.

## 6. Test Recommendations

1. `download_update()` 테스트: 정상 스트림, HTTPS가 아닌 최종 redirect, 초과 크기, 짧은 파일, 해시 불일치, 디스크 쓰기 실패, 기존 `.download`/destination 충돌을 mock HTTP와 임시 디렉터리로 검증한다.
2. `launch_installer()` 통합 테스트: 별도 테스트 EXE/텍스트 fixture를 대상으로 parent 종료 대기, 정상 교체/재시작, target lock 실패, staged 누락, backup 복원을 검증한다. 실제 설치 경로는 사용하지 않는다.
3. TOCTOU 회귀 테스트: 다운로드 검증 뒤 staged 파일을 바꾸고 installer가 재검증 실패해야 함을 확인한다.
4. UI 테스트: 중복 클릭이 worker 하나만 시작하는지, source mode 메시지, 다운로드 실패/취소/종료 중 콜백 폐기, 설치 결과의 다음 시작 알림을 확인한다.
5. 엔진 경쟁 테스트: watch thread가 `_scan_apply_lock`을 보유한 채 stop timeout이 나는 fixture에서, stop 이후 어떠한 hide/close가 다시 수행되지 않는지 검증한다.
6. workflow 계약 테스트: `VERSION`/tag 일치, 생성된 `update.json`이 embedded public key로 검증되는지, release asset URL과 tag가 일치하는지 검증한다. 가능하면 GitHub API를 mock한 멱등 publish 테스트도 추가한다.
7. 문서 테스트: README와 CLAUDE의 트레이 메뉴/업데이트 설명이 현재 UI 메뉴와 일치하는지 단순 문자열 또는 structured checklist로 확인한다.

## Verification Notes

- 기존 작업 상태에서 전체 pytest는 `229 passed`, Pyright는 `0 errors, 0 warnings`이었다.
- 이번 감사에서는 코드 변경이나 실행 중 EXE 교체를 수행하지 않았다. 이전 패키징 검증은 실행 중인 `dist/KakaoTalkLayoutAdBlocker_v11.exe`가 잠겨 마지막 교체 단계에서 실패한 상태였으며, 이는 업데이트 도우미 실패 통지 항목의 실제 운영 중요도를 뒷받침한다.
