# KakaoTalk Layout AdBlocker v11

Windows용 카카오톡 광고 레이아웃 정리 도구입니다.

## 핵심 변경점

- `hosts/DNS/AdFit` 기능을 완전히 제거했습니다.
- `blurfx/KakaoTalkAdBlock` 방식에 맞춰 레이아웃 엔진으로 재설계했습니다.
- 폴링은 적응형으로 동작합니다: 활성 상태 `50ms`, 유휴 상태 `200ms`(기본값).
- 기본 동작은 트레이 중심이며, 설정 창은 필요 시 열 수 있습니다.

## 최근 안정성 개선 (v11.0.x)

- `--minimized` 또는 `start_minimized=true`로 시작할 때는 시작 안내 팝업을 띄우지 않습니다.
- 트레이(pystray/Pillow) 모듈을 사용할 수 없는 환경에서는 `--minimized`/`start_minimized` 요청을 무시하고 창을 강제로 표시합니다.
- 트레이를 사용할 수 없는 상태에서 창 닫기(X)는 숨김이 아니라 앱 종료로 동작합니다.
- 엔진이 `layout_rules_v11.json`의 `main_window_classes`를 실제 메인 윈도우 탐지에 반영합니다.
- 광고 후보 탐지는 `ad_candidate_classes`를 분리 적용하고, 최상위 후보는 `Chrome Legacy Window` 시그니처를 만족할 때만 처리합니다.
- 레거시 광고 시그니처는 exact(`chrome_legacy_title`)와 substring(`chrome_legacy_title_contains`)을 함께 지원합니다.
- 기본 광고 후보 클래스는 `EVA_Window_Dblclk`, `EVA_Window`이며, 구버전 rules에서 `ad_candidate_classes`가 누락/비정상이면 `main_window_classes`로 폴백합니다.
- 공격 모드에서 짧은 토큰(예: `Ad`)은 단어 경계 기준으로 매칭하여 오탐(`ReadLater`, `Header` 등)을 줄였습니다.
- 시작프로그램 토글 시 레지스트리 갱신 실패가 발생하면 설정 파일(`run_on_startup`)을 잘못 저장하지 않습니다.
- 설정 파일 저장 실패가 발생하면 토글 값(`enabled`/`run_on_startup`/`aggressive_mode`)을 즉시 롤백해 UI 동작을 계속 유지합니다.
- 시작프로그램 토글에서 레지스트리 변경 후 설정 저장이 실패하면 레지스트리도 즉시 역롤백해 상태 불일치를 줄입니다.
- 앱 시작 시 `run_on_startup`은 레지스트리 상태를 기준으로 1회 동기화됩니다.
- 시작 시 `run_on_startup` 동기화 저장이 실패해도 값 롤백 후 예외 없이 계속 동작합니다.
- 차단 OFF 전환 또는 앱 종료 시, 이전에 숨김/이동한 광고 창은 즉시 원복됩니다.
- 원복 실패 창은 스냅샷을 유지해 재시도하며, 상태 문자열에 `복원실패 N` 및 마지막 실패 사유를 노출합니다.
- 트레이 메뉴에서 `복원 실패 초기화`를 실행해 `restore_failures` 상태를 수동 초기화할 수 있습니다.
- `stop()`에서 watch thread join timeout(2초) 발생 시 경고를 상태/로그에 기록하고 종료 절차를 계속 진행합니다.
- 상태 표시에 마지막 오류(`last_error`)와 마지막 갱신 시각(`last_tick`)이 함께 표시됩니다.
- PID 스캔/캐시 정리는 주기 스로틀이 적용되어 유휴 상태 CPU 사용량을 줄였습니다.
- psutil 스캔 초기화/루프 실패 시 `tasklist` 폴백 경로로 PID 탐지를 이어갑니다.
- PID 탐지 경고(예: psutil 실패, tasklist fallback/실패)는 상태 문자열(`last_error`)과 로그에 반영됩니다.
- `--dump-tree` 경로는 UI/트레이 모듈을 지연 로딩하여 시작 오버헤드를 최소화합니다.
- `--self-check` 경로는 UI/엔진을 기동하지 않고 환경 진단(APPDATA, tasklist, 레지스트리, 트레이 모듈 import)만 수행합니다.
- `--self-check`의 시작프로그램 진단은 Run 레지스트리 `읽기/쓰기` 접근을 함께 점검합니다.
- UI 실행 경로는 `try/finally` cleanup으로 예외 발생 시에도 `stop_tray()/engine.stop()`를 보장합니다.
- 기본 설정(`idle_poll_interval_ms=200`) 기준으로 유휴 복귀 지연은 최대 약 200ms를 목표로 합니다.
- `layout_settings_v11.json`, `layout_rules_v11.json` 파손(파싱 실패/최상위 타입 오류) 시 `*.broken-YYYYMMDD-HHMMSS` 백업을 생성하고 경고를 상태/로그에 노출합니다.
- `*.broken-*` 백업은 자동 정리 정책(30일 초과 삭제 + 최신 10개 유지)을 적용해 누적을 제어합니다.
- `layout_settings_v11.json`, `layout_rules_v11.json` 저장은 원자적 교체(`os.replace`) 방식으로 처리해 파손 가능성을 낮췄습니다.
- rules 문자열(`main_window_titles`, `aggressive_ad_tokens`)에 인코딩 이상 징후(mojibake/`�`)가 있으면 시작 시 경고를 기록합니다.
- 엔진 내부 캐시/숨김 스냅샷 키를 `WindowIdentity(hwnd,pid,class)`로 강화해 HWND 재사용 시 오동작 가능성을 낮췄습니다.
- 스캔 경로는 경량 수집(`rect/visible` 미조회)으로 최적화되고, 상세 수집은 `--dump-tree` 경로에만 적용됩니다.
- 트레이 메뉴 콜백은 큐 디스패치(`_safe_after` -> main-thread drain)로 처리해 스레드 경합을 줄입니다.
- 트레이 모듈 import 실패 시 즉시 재시도하지 않고 TTL(기본 30초) 경과 후 자동 재시도합니다.
- 상태 갱신 타이머(`_tick_status`)도 종료 경합에서 스케줄링 실패 예외를 전파하지 않습니다.
- 엔진 시작 시 동기 warm-up(scan+apply 1회)을 먼저 수행해 초기 광고 깜빡임을 줄였습니다.
- 빈 텍스트 캐시는 짧은 TTL로 빠르게 재조회해 초기 UI 구성 구간의 탐지 지연을 줄였습니다.

## 실행

```bash
python kakaotalk_layout_adblock_v11.py
python kakaotalk_layout_adblock_v11.py --minimized
python kakaotalk_layout_adblock_v11.py --dump-tree
python kakaotalk_layout_adblock_v11.py --dump-tree --dump-dir "C:\temp"
python kakaotalk_layout_adblock_v11.py --self-check
```

- 이 도구는 Windows 전용입니다. 비Windows 환경에서는 `This application only supports Windows.` 메시지와 함께 종료 코드 `2`로 종료됩니다.

## 설정/로그 경로

- `%APPDATA%\KakaoTalkAdBlockerLayout\layout_settings_v11.json`
- `%APPDATA%\KakaoTalkAdBlockerLayout\layout_rules_v11.json`
- `%APPDATA%\KakaoTalkAdBlockerLayout\layout_adblock.log`

`layout_settings_v11.json` 고급 성능 설정(기본값):

- `idle_poll_interval_ms`: `200`
- `pid_scan_interval_ms`: `200`
- `cache_cleanup_interval_ms`: `1000`

신규 성능 필드가 없는 구버전 설정 파일도 기본값으로 자동 보완되어 그대로 동작합니다.
구버전 rules 파일에서 `ad_candidate_classes` 키가 없거나 타입이 잘못된 경우에도 `main_window_classes` 기반 폴백으로 무중단 호환됩니다.

기존 `adblock_settings.json`, `ad_patterns.json`, `blocked_domains.txt`는 읽지 않습니다.

## 레거시 코드 보관 경로

구버전 자산은 루트가 아니라 `legacy/` 아래로 이동되었습니다.

- `legacy/kakao_adblocker/legacy.py` (v10 모놀리식 엔진 원본)
- `legacy/backup/*` (v4~v9 스냅샷)
- `legacy/tools/ad_sniffer.py`, `legacy/tools/window_inspector.py`
- `legacy/configs/*` (구버전 설정/도메인/로그)
- `legacy/scripts/카카오톡 광고제거 v8.0.py`
- `legacy/카카오톡 광고제거 v10.0.py` (v11 엔트리포인트 안내용 deprecated 스크립트)

## 트레이 메뉴

- 상태
- 차단 On/Off
- 공격 모드
- 시작프로그램 등록
- 복원 실패 초기화
- 창 열기
- 로그 폴더 열기
- GitHub 리포 열기(수동)
- 종료

## 빌드

```bash
pyinstaller kakaotalk_adblock.spec
```

`kakaotalk_adblock.spec`는 **onefile** 빌드 설정이며, 결과물은 `dist/KakaoTalkLayoutAdBlocker_v11.exe`로 생성됩니다.
- `.spec`는 프로젝트 루트 기준 절대 경로를 사용하도록 보강되어, 빌드 실행 위치에 덜 민감합니다.
- `.spec`는 런타임 핵심 모듈(`kakao_adblocker.app`, `kakao_adblocker.config`, `kakao_adblocker.event_engine`, `kakao_adblocker.logging_setup`, `kakao_adblocker.services`, `kakao_adblocker.ui`, `pystray`, `PIL`)를 `hiddenimports`로 명시하고, `collect_submodules("pystray"|"PIL")`를 함께 사용해 onefile 패키징 누락을 방지합니다.
- `.spec`는 레이아웃/Win32 핵심 모듈(`kakao_adblocker.layout_engine`, `kakao_adblocker.win32_api`)도 `hiddenimports`에 명시해 패키징 안정성을 보강했습니다.
- `--self-check` 진단 경로도 동일 hiddenimports 집합으로 별도 수정 없이 동작합니다.

`uac_admin`은 제거되어 관리자 권한 없이 실행됩니다.

## 패키징 실행 오류 대응

아래 오류가 보이면:

```text
PermissionError: [Errno 13] Permission denied: '...KakaoTalkLayoutAdBlocker_v11.exe'
```

대부분 관리자 권한 문제가 아니라, OneDrive/보안 솔루션이 EXE 파일 자체 접근을 잠시 잠그는 케이스입니다.

권장 조치:

1. EXE를 OneDrive 바탕화면이 아닌 `C:\Apps\KakaoTalkLayoutAdBlocker` 같은 로컬 폴더로 이동
2. 파일 우클릭 → 속성 → `차단 해제`가 보이면 체크 후 적용
3. OneDrive에서 `항상 이 장치에 유지`로 고정
4. Windows 보안(랜섬웨어 보호/실시간 보호) 예외에 EXE 추가

## 참고

- 참고 구현: https://github.com/blurfx/KakaoTalkAdBlock
