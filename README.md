# KakaoTalk Layout AdBlocker v11

Windows용 카카오톡 광고 레이아웃 정리 도구입니다.

## 핵심 변경점

- `hosts/DNS/AdFit` 기능을 완전히 제거했습니다.
- `blurfx/KakaoTalkAdBlock` 방식에 맞춰 레이아웃 엔진으로 재설계했습니다.
- 폴링은 적응형으로 동작합니다: 활성 상태 `50ms`, 유휴 상태 `200ms`(기본값).
- 기본 동작은 트레이 중심이며, 설정 창은 필요 시 열 수 있습니다.

## 최근 안정성 개선 (v11.0.x)

- `--minimized` 또는 `start_minimized=true`로 시작할 때는 시작 안내 팝업을 띄우지 않습니다.
- 엔진이 `layout_rules_v11.json`의 `main_window_classes`를 실제 메인 윈도우 탐지에 반영합니다.
- 광고 후보 탐지는 `ad_candidate_classes`를 분리 적용하고, 최상위 후보는 `Chrome Legacy Window` 시그니처를 만족할 때만 처리합니다.
- 기본 광고 후보 클래스는 `EVA_Window_Dblclk`, `EVA_Window`이며, 구버전 rules에서 `ad_candidate_classes`가 누락/비정상이면 `main_window_classes`로 폴백합니다.
- 공격 모드에서 짧은 토큰(예: `Ad`)은 단어 경계 기준으로 매칭하여 오탐(`ReadLater`, `Header` 등)을 줄였습니다.
- 시작프로그램 토글 시 레지스트리 갱신 실패가 발생하면 설정 파일(`run_on_startup`)을 잘못 저장하지 않습니다.
- 앱 시작 시 `run_on_startup`은 레지스트리 상태를 기준으로 1회 동기화됩니다.
- 차단 OFF 전환 또는 앱 종료 시, 이전에 숨김/이동한 광고 창은 즉시 원복됩니다.
- 상태 표시에 마지막 오류(`last_error`)와 마지막 갱신 시각(`last_tick`)이 함께 표시됩니다.
- PID 스캔/캐시 정리는 주기 스로틀이 적용되어 유휴 상태 CPU 사용량을 줄였습니다.
- `--dump-tree` 경로는 UI/트레이 모듈을 지연 로딩하여 시작 오버헤드를 최소화합니다.
- 기본 설정(`idle_poll_interval_ms=200`) 기준으로 유휴 복귀 지연은 최대 약 200ms를 목표로 합니다.
- `layout_settings_v11.json`, `layout_rules_v11.json` 파손(파싱 실패/최상위 타입 오류) 시 `*.broken-YYYYMMDD-HHMMSS` 백업을 생성하고 경고를 상태/로그에 노출합니다.
- 엔진 내부 캐시/숨김 스냅샷 키를 `WindowIdentity(hwnd,pid,class)`로 강화해 HWND 재사용 시 오동작 가능성을 낮췄습니다.
- 스캔 경로는 경량 수집(`rect/visible` 미조회)으로 최적화되고, 상세 수집은 `--dump-tree` 경로에만 적용됩니다.
- 트레이 메뉴 콜백은 안전 스케줄링(`_safe_after`)으로 종료 경합 시 예외 전파를 막습니다.
- 엔진 시작 시 동기 warm-up(scan+apply 1회)을 먼저 수행해 초기 광고 깜빡임을 줄였습니다.
- 빈 텍스트 캐시는 짧은 TTL로 빠르게 재조회해 초기 UI 구성 구간의 탐지 지연을 줄였습니다.

## 실행

```bash
python kakaotalk_layout_adblock_v11.py
python kakaotalk_layout_adblock_v11.py --minimized
python kakaotalk_layout_adblock_v11.py --dump-tree
python kakaotalk_layout_adblock_v11.py --dump-tree --dump-dir "C:\temp"
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

## 트레이 메뉴

- 상태
- 차단 On/Off
- 공격 모드
- 시작프로그램 등록
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
- `.spec`는 lazy-import 경로(`kakao_adblocker.app`, `kakao_adblocker.config`, `kakao_adblocker.event_engine`, `kakao_adblocker.ui`, `pystray`, `PIL`)를 `hiddenimports`로 명시하고, `collect_submodules("pystray"|"PIL")`를 함께 사용해 onefile 패키징 누락을 방지합니다.

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
