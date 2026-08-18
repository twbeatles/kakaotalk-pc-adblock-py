# 💬 KakaoTalk Layout AdBlocker v11

Windows PC용 카카오톡 레이아웃 기반 무해한 광고 차단 도구입니다.

hosts 파일 수정, DNS 변경, 레지스트리 변조, 네트워크 패킷 차단 없이 **순수 Win32 윈도우 레이아웃 조정 및 광고 창 은닉**만으로 동작합니다. 관리자 권한(UAC)이 필요하지 않으며, 카카오톡 업데이트나 시스템 환경에 안전합니다.

---

## 📑 목차

- [✨ 주요 특징 (Key Features)](#-주요-특징-key-features)
- [🚀 빠른 시작 (설치 및 실행)](#-빠른-시작-설치-및-실행)
  - [방법 1: 실행 파일(EXE)로 바로 사용하기 (권장)](#방법-1-실행-파일exe로-바로-사용하기-권장)
  - [방법 2: 소스 코드에서 실행하기](#방법-2-소스-코드에서-실행하기)
- [🖥️ 사용 방법 및 UI / 트레이 가이드](#️-사용-방법-및-ui--트레이-가이드)
  - [1. 시스템 트레이 메뉴](#1-시스템-트레이-메뉴)
  - [2. GUI 설정 창](#2-gui-설정-창)
  - [3. 실시간 상태 표시 읽는 법](#3-실시간-상태-표시-읽는-법)
  - [4. 부팅 시 자동 시작 (시작프로그램)](#4-부팅-시-자동-시작-시작프로그램)
  - [5. 원클릭 자동 업데이트](#5-원클릭-자동-업데이트)
- [⌨️ CLI 명령줄 옵션 및 진단 도구](#️-cli-명령줄-옵션-및-진단-도구)
- [⚙️ 설정 및 규칙 커스터마이징](#️-설정-및-규칙-커스터마이징)
  - [설정 파일 위치](#설정-파일-위치)
  - [layout\_settings\_v11.json (동작 및 성능 설정)](#layout_settings_v11json-동작-및-성능-설정)
  - [layout\_rules\_v11.json (광고 필터링 규칙)](#layout_rules_v11json-광고-필터링-규칙)
  - [설정 파일 자동 복구(Self-Healing) 및 백업](#설정-파일-자동-복구self-healing-및-백업)
- [❓ 자주 묻는 질문 및 문제 해결 (FAQ)](#-자주-묻는-질문-및-문제-해결-faq)
- [🛠️ 개발 및 빌드 가이드 (For Developers)](#️-개발-및-빌드-가이드-for-developers)
  - [개발 환경 구축](#개발-환경-구축)
  - [정적 분석 및 테스트](#정적-분석-및-테스트)
  - [PyInstaller 단일 파일(Onefile) 빌드](#pyinstaller-단일-파일onefile-빌드)
  - [스모크 체크 및 릴리스 서명](#스모크-체크-및-릴리스-서명)
- [📜 라이선스 및 참고 프로젝트](#-라이선스-및-참고-프로젝트)

---

## ✨ 주요 특징 (Key Features)

- 🛡️ **안전한 순수 레이아웃 차단 (Layout-Only)**
  - `hosts`, DNS 캐시, AdFit 레지스트리를 전혀 건드리지 않아 PC 네트워크나 시스템 보안에 부작용이 없습니다.
  - 관리자 권한(UAC) 없이 일반 사용자 권한으로 안전하게 동작합니다.
- ⚡ **적응형 저전력 폴링 (Adaptive Polling)**
  - 카카오톡 활성 상태에서는 `50ms`, 유휴 상태에서는 `200ms`로 자동 전환되어 CPU 점유율을 최소화합니다.
- 🔄 **완벽한 상태 복원 (Clean Restoration)**
  - 차단을 끄거나(OFF) 프로그램을 종료할 때 이전에 숨겨지거나 리사이즈된 카카오톡 창을 즉시 원래 상태로 원복합니다.
- 🎯 **최신 카카오톡 UI 완벽 지원 (2025+ 및 26.x+)**
  - 친구 목록 하단 배너 광고(Owned Popup 구조), 피드 배너, 잠금 모드 뷰 등을 완벽히 감지하여 차단합니다.
- 🔔 **시스템 트레이 백그라운드 상주**
  - 작업표시줄 트레이 아이콘으로 조용히 백그라운드에서 동작하며, 필요 시 언제든 GUI 설정창을 열 수 있습니다.
- 🚀 **안정적인 부팅 자동 실행 & 트레이 자동 복구**
  - Windows 로그인 시 백그라운드로 자동 실행되며, 탐색기/트레이 충돌 시 최대 3회 자동 복구를 시도합니다.
- 🔒 **보안이 검증된 원클릭 자동 업데이트**
  - Ed25519 전자 서명과 SHA-256 무결성 검증을 거친 공식 릴리스만 안전하게 다운로드하여 업데이트합니다.
- 🛠️ **정밀 진단 및 커스텀 룰 지원**
  - 카카오톡 창 구조 덤프(`--dump-tree`, `--dump-tree-series`)와 사용자 맞춤형 JSON 규칙 설정을 지원합니다.

---

## 🚀 빠른 시작 (설치 및 실행)

> [!NOTE]
> 본 프로그램은 **Windows 10 / 11 (64-bit)** 전용 도구입니다.

### 방법 1: 실행 파일(EXE)로 바로 사용하기 (권장)

1. [GitHub Releases](https://github.com/twbeatles/kakaotalk-pc-adblock-py/releases) 페이지에서 최신 버전의 **`KakaoTalkLayoutAdBlocker_v11.exe`**를 다운로드합니다.
2. 다운로드한 파일을 원하는 로컬 폴더(예: `C:\Apps\KakaoTalkAdBlocker\` 또는 `D:\Tools\`)에 넣고 실행합니다.
   - *바탕화면(OneDrive 연동 폴더)보다는 로컬 드라이브 일반 폴더를 권장합니다.*
3. 실행 즉시 시스템 트레이(시계 옆)에 노란색 쉴드 아이콘이 표시되며 백그라운드에서 광고 차단이 시작됩니다.

### 방법 2: 소스 코드에서 실행하기

Python 3.9 이상이 설치된 환경에서 직접 구동할 수 있습니다.

```bash
# 1. 저장소 클론
git clone https://github.com/twbeatles/kakaotalk-pc-adblock-py.git
cd kakaotalk-pc-adblock-py

# 2. 필수 의존성 패키지 설치
pip install -r requirements.txt

# 3. 프로그램 실행
python kakaotalk_layout_adblock_v11.py
```

---

## 🖥️ 사용 방법 및 UI / 트레이 가이드

### 1. 시스템 트레이 메뉴

작업표시줄 알림 영역(트레이)의 노란색 쉴드 아이콘을 **우클릭**하면 편리한 제어 메뉴가 나타납니다.

```
[ 상태: ON | PID 1 | 메인윈도우 1 | 누적 숨김 1 | ... ]  (실시간 상태)
-------------------------------------------------------
차단 끄기 / 차단 켜기    (원클릭 광고 차단 토글)
✓ 공격 모드             (서브트리 토큰 검사 및 심화 차단)
✓ 시작프로그램 등록      (Windows 시작 시 자동 실행)
복원 실패 초기화        (창 원복 실패 카운터 리셋)
창 열기                 (GUI 제어창 표시)
로그 폴더 열기          (설정 및 로그 저장소 폴더 열기)
GitHub 릴리스 열기      (최신 릴리스 웹페이지 열기)
업데이트 확인           (최신 버전 확인 및 자동 업데이트)
종료                    (광고창 정상 원복 후 프로그램 종료)
```

- **차단 켜기 / 차단 끄기**: 차단을 끄면 숨겨져 있던 광고 영역이 즉시 원래대로 나타납니다.
- **공격 모드 (Aggressive Mode)**: 기본 시그니처 외에 광고 관련 토큰(`Ad`, `AdFit`, `광고` 등)이 포함된 하부 요소까지 확장하여 차단합니다. (기본값: 활성화)
- **창 열기**: 숨겨진 메인 GUI 창을 화면에 표시합니다.

---

### 2. GUI 설정 창

트레이 메뉴에서 **[창 열기]**를 누르면 메인 GUI 창이 열립니다.

- 상단에 **실시간 차단 상태 정보**가 표시됩니다.
- 버튼을 통해 `차단 On/Off`, `시작프로그램 토글`, `공격 모드 토글`, `로그 폴더 열기`, `업데이트 확인`, `종료`를 간편하게 조작할 수 있습니다.
- 창 우측 상단의 **닫기(X) 버튼**을 누르면 프로그램이 종료되지 않고 **시스템 트레이로 최소화(숨김)**됩니다. (완전히 종료하려면 [종료] 버튼 또는 트레이 메뉴의 [종료]를 사용하세요.)

---

### 3. 실시간 상태 표시 읽는 법

GUI 및 트레이 메뉴 상단에 실시간으로 엔진 상태가 표시됩니다.

```text
상태: ON | PID 1 | 메인윈도우 1 | 누적 숨김 3 | 누적 닫힘 1 | 누적 리사이즈 1 | 마지막 갱신 11:26:40
```

| 표시 항목 | 설명 |
| :--- | :--- |
| **상태: ON / OFF** | 현재 광고 차단 엔진의 활성화 여부 |
| **PID N** | 탐지된 카카오톡 프로세스(`KakaoTalk.exe`) 수 |
| **메인윈도우 N** | 현재 확인된 카카오톡 메인 창 수 |
| **후보 N** | 메인 창 후보로 검토 중인 창 수 (확정 수보다 많을 때만 표시) |
| **광고후보 N** | 감지된 광고 후보 창 수 |
| **광고후보 N(미차단?)** | 광고 후보가 감지되었으나 아직 숨김/닫힘이 적용되지 않은 상태를 경고 |
| **누적 숨김 N** | 현재 실행 세션 동안 숨김 처리(Hide)한 광고 창의 총 횟수 |
| **누적 닫힘 N** | 정상 종료 처리(Close)한 불필요한 빈 광고 자식 창의 총 횟수 |
| **누적 리사이즈 N** | 채팅/친구 목록 뷰의 높이를 정상화한 총 횟수 |
| **popup 닫기/숨김/제로** | 팝업 형태 광고 창의 처리 결과 카운터 |
| **복원실패 N** | 차단 해제 또는 종료 시 창 원복이 실패한 횟수 (있을 경우 표시) |
| **마지막 갱신 HH:MM:SS** | 엔진이 마지막으로 상태를 갱신한 시각 |

---

### 4. 부팅 시 자동 시작 (시작프로그램)

트레이 메뉴의 **[시작프로그램 등록]**을 체크하거나 GUI의 **[시작프로그램 토글]** 버튼을 누르면 Windows 레지스트리(`HKCU\...\Run`)에 등록되어 PC 부팅 시 백그라운드에서 자동으로 조용히 실행됩니다.

- 부팅 시에는 `--startup-launch --minimized` 인자로 시작되어 안내 팝업 없이 트레이로 바로 진입합니다.
- Windows 탐색기(Shell)가 완전히 준비될 때까지 기다린 후 트레이 아이콘을 등록하므로 로그인 직후 아이콘 누락을 방지합니다.

---

### 5. 원클릭 자동 업데이트

배포된 EXE 실행 파일 환경에서는 트레이 메뉴 또는 GUI의 **[업데이트 확인]**을 통해 최신 버전을 쉽게 적용할 수 있습니다.

1. **[업데이트 확인]** 클릭 시 GitHub 최신 릴리스의 서명 파일(`update.json`)을 조회합니다.
2. 내장된 **Ed25519 공개키**로 서명을 검증하고 파일의 **SHA-256 해시**와 크기를 대조합니다.
3. 새 버전이 확인되면 업데이트 설치 확인 대화상자가 나타납니다.
4. 승인 시 안전하게 이전 버전을 백업하고 새 실행 파일로 교체한 후 프로그램을 재시작합니다.
5. 이전 업데이트 설치 결과는 다음 프로그램 실행 시 안내됩니다.

---

## ⌨️ CLI 명령줄 옵션 및 진단 도구

명령 프롬프트(CMD) 또는 PowerShell에서 다양한 옵션을 지정하여 실행하거나 진단을 수행할 수 있습니다.

```bash
# 기본 실행 (GUI 창과 함께 시작)
KakaoTalkLayoutAdBlocker_v11.exe

# 트레이로 최소화하여 백그라운드 시작
KakaoTalkLayoutAdBlocker_v11.exe --minimized

# 환경 자가 진단 실행 (GUI 없이 시스템/레지스트리/Tk 상태 점검 후 결과 출력)
KakaoTalkLayoutAdBlocker_v11.exe --self-check

# 자가 진단 결과를 JSON 포맷으로 출력
KakaoTalkLayoutAdBlocker_v11.exe --self-check --json

# 현재 카카오톡 창 계층 구조 덤프 (JSON 저장)
KakaoTalkLayoutAdBlocker_v11.exe --dump-tree

# 덤프 파일 저장 경로 지정
KakaoTalkLayoutAdBlocker_v11.exe --dump-tree --dump-dir "C:\temp"

# 카카오톡 창 변화를 시간축으로 연속 덤프 (광고 탐지 판정 포함)
KakaoTalkLayoutAdBlocker_v11.exe --dump-tree-series --dump-series-duration-ms 2000 --dump-series-interval-ms 50
```

### CLI 옵션 요약표

| 옵션 | 설명 |
| :--- | :--- |
| `--minimized` | 화면에 메인 GUI 창을 띄우지 않고 시스템 트레이로 바로 시작합니다. |
| `--self-check` | 엔진을 띄우지 않고 레지스트리 권한, Tkinter 가용성, 프로세스 스캔 등 환경을 진단합니다. |
| `--json` | `--self-check` 등의 진단 결과를 JSON 형태로 표준 출력(stdout)에 반환합니다. |
| `--dump-tree` | 현재 카카오톡 윈도우 핸들(HWND) 트리 구조를 수집하여 JSON 파일로 저장합니다. |
| `--dump-tree-series` | 지정된 시간 동안 연속으로 윈도우 프레임과 광고 후보 판정(`candidates[]`)을 기록합니다. |
| `--dump-dir <path>` | 덤프 파일이 저장될 디렉터리 경로를 지정합니다. |
| `--dump-series-duration-ms <ms>` | 연속 덤프 수집 총 시간(ms)을 설정합니다. (기본값: 1000, 최대: 10000) |
| `--dump-series-interval-ms <ms>` | 연속 덤프 수집 간격(ms)을 설정합니다. (기본값: 100, 최소: 10) |

> [!TIP]
> `--self-check`, `--dump-tree`, `--dump-tree-series` 진단 명령은 단일 인스턴스 락(Mutex)을 요구하지 않으므로, 이미 프로그램이 백그라운드에서 동작 중이더라도 언제든지 병렬로 실행할 수 있습니다.

---

## ⚙️ 설정 및 규칙 커스터마이징

### 설정 파일 위치

프로그램 설정과 규칙, 로그 파일은 사용자의 `AppData` 폴더에 안전하게 보관됩니다.

- 📁 **설정 폴더**: `%APPDATA%\KakaoTalkAdBlockerLayout\`
  - `layout_settings_v11.json` : 프로그램 동작 및 성능 설정
  - `layout_rules_v11.json` : 광고 윈도우 탐지 및 크기 조절 규칙
  - `layout_adblock.log` : 프로그램 동작 로그 파일

트레이 메뉴의 **[로그 폴더 열기]**를 누르면 해당 폴더가 파일 탐색기로 바로 열립니다.

---

### layout_settings_v11.json (동작 및 성능 설정)

```json
{
  "enabled": true,
  "run_on_startup": false,
  "start_minimized": true,
  "poll_interval_ms": 50,
  "idle_poll_interval_ms": 200,
  "pid_scan_interval_ms": 200,
  "cache_cleanup_interval_ms": 1000,
  "burst_scan_iterations": 3,
  "burst_scan_interval_ms": 20,
  "aggressive_mode": true,
  "log_level": "INFO"
}
```

- `enabled`: 차단 활성화 여부 (`true`/`false`)
- `run_on_startup`: 부팅 시 시작프로그램 등록 여부
- `start_minimized`: 시작 시 트레이로 최소화 실행 여부
- `poll_interval_ms`: 카카오톡 활성 상태에서의 탐지 주기 (기본값: `50` ms)
- `idle_poll_interval_ms`: 카카오톡 유휴 상태에서의 탐지 주기 (기본값: `200` ms)
- `aggressive_mode`: 광고 키워드 토큰 기반 심화 탐지 모드 사용 여부
- `log_level`: 로그 상세도 (`"INFO"`, `"DEBUG"`, `"WARNING"`, `"ERROR"`)

---

### layout_rules_v11.json (광고 필터링 규칙)

카카오톡의 윈도우 클래스 구조가 변경되었을 때, 소스 코드 수정 없이 규칙 파일만 수정하여 대응할 수 있습니다.

```json
{
  "main_window_classes": ["EVA_Window_Dblclk", "EVA_Window"],
  "ad_candidate_classes": ["EVA_Window_Dblclk", "EVA_Window"],
  "main_window_titles": ["카카오톡", "KakaoTalk"],
  "main_view_prefix": "OnlineMainView",
  "lock_view_prefix": "LockModeView",
  "eva_child_class": "EVA_ChildWindow",
  "custom_scroll_prefix": "_EVA_",
  "chrome_legacy_title": "Chrome Legacy Window",
  "chrome_legacy_title_contains": ["Chrome Legacy Window"],
  "chrome_widget_prefixes": ["Chrome_WidgetWin_"],
  "popup_ad_classes": ["AdFitWebView"],
  "popup_search_depth": 2,
  "popup_host_text_contains": [],
  "popup_host_require_empty_text": true,
  "aggressive_ad_tokens": ["Ad", "AdFit", "Advertisement", "광고"],
  "banner_min_height_px": 40,
  "banner_max_height_px": 260,
  "banner_min_width_ratio": 0.75,
  "banner_bottom_margin_px": 40,
  "hide_bottom_banner_without_token": false,
  "close_empty_eva_child_requires_ad_signal": true,
  "layout_shadow_padding_px": 2,
  "main_view_padding_px": 31,
  "weak_signal_confirm_ticks": 2,
  "hidden_restore_grace_ms": 250,
  "cache_ttl_seconds": 8.0,
  "log_rate_limit_seconds": 8.0
}
```

- `aggressive_ad_tokens`: 공격 모드에서 광고로 식별할 문자열 토큰 목록
- `popup_ad_classes`: 독립 팝업 형태로 뜨는 광고 웹뷰 클래스명
- `banner_min_height_px` / `banner_max_height_px`: 하단 배너 광고의 유효 높이 범위
- `hide_bottom_banner_without_token`: 토큰 없는 하단 패널을 크기만으로 숨길지 여부 (기본값: `false`)

---

### 설정 파일 자동 복구(Self-Healing) 및 백업

- JSON 설정 파일을 직접 수정하다가 오타나 문법 오류가 발생하더라도 프로그램이 비정상 종료되지 않습니다.
- 손상된 파일은 `*.broken-YYYYMMDD-HHMMSS` 형태로 자동 백업되고, 기본값으로 안전하게 자체 복구(Self-Heal)됩니다.
- 생성된 백업 파일은 30일 경과 시 자동 정리되며 최신 10개까지만 유지됩니다.

---

## ❓ 자주 묻는 질문 및 문제 해결 (FAQ)

### Q1. `PermissionError: [Errno 13] Permission denied` 오류가 발생해요.

- **원인**: 실행 파일이 OneDrive 동기화 폴더(바탕화면, 문서 등)에 있거나 백신 소프트웨어가 파일을 일시 잠금한 경우 발생합니다.
- **해결 방법**:
  1. 실행 파일을 OneDrive 경로가 아닌 로컬 폴더(예: `C:\Apps\KakaoTalkAdBlocker\`)로 이동합니다.
  2. 다운로드한 EXE 파일을 우클릭 → **속성** → 하단 보안 항목의 **[차단 해제]**가 있다면 체크 후 적용합니다.
  3. Windows Defender나 백신 프로그램의 실시간 감시 예외 폴더에 추가합니다.

### Q2. 트레이 아이콘이 보이지 않거나 사라져요.

- **원인**: Windows 작업표시줄 설정에서 아이콘이 숨겨져 있거나 그래픽/셸 재시작으로 트레이 핸들이 갱신된 경우입니다.
- **해결 방법**:
  1. 작업표시줄의 `^` (숨겨진 아이콘 표시) 버튼을 눌러 노란색 쉴드 아이콘이 있는지 확인하고 작업표시줄로 드래그합니다.
  2. 프로그램 내부적으로 트레이 충돌 발생 시 3초 간격으로 최대 3회 자동 복구를 시도하며, 복구 실패 시 사용자가 제어할 수 있도록 GUI 창을 화면에 자동으로 띄워줍니다.

### Q3. 광고가 사라지지 않거나 상태에 `(미차단?)` 문구가 떠요.

- **원인**: 카카오톡이 대규모 업데이트를 통해 내부 윈도우 클래스 구조나 렌더링 방식을 변경했을 가능성이 있습니다.
- **진단 및 대처**:
  1. 광고가 노출된 상태에서 명령 프롬프트를 열고 `--dump-tree-series` 진단을 실행합니다.
     ```bash
     KakaoTalkLayoutAdBlocker_v11.exe --dump-tree-series
     ```
  2. 생성된 `window_dump_series_*.json` 파일을 첨부하여 [GitHub Issues](https://github.com/twbeatles/kakaotalk-pc-adblock-py/issues)에 제보해 주시면 신속하게 규칙 업데이트가 이루어집니다.

### Q4. 프로그램을 여러 번 실행하면 어떻게 되나요?

- Windows Named Mutex(`Local\KakaoTalkLayoutAdBlocker_v11`)를 통해 **단일 인스턴스 실행**이 엄격히 보장됩니다.
- 이미 실행 중인 상태에서 추가로 실행하면 중복 실행되지 않고 정상 종료 코드(`0`)로 안전하게 종료됩니다.

---

## 🛠️ 개발 및 빌드 가이드 (For Developers)

### 개발 환경 구축

Python 3.9 이상의 환경에서 개발 의존성을 포함하여 설치합니다.

```bash
# 개발/테스트 의존성 설치
pip install -r requirements-dev.txt
```

---

### 정적 분석 및 테스트

Pyright 정적 타입 분석과 Pytest 단위 테스트를 수행합니다.

```powershell
# PowerShell 전용 종합 검사 스크립트 실행
.\scripts\dev_check.ps1

# 또는 개별 도구 실행
python -m pyright
pytest -q --basetemp .pytest_tmp
```

- `pyrightconfig.json` 기준 활성 분석 범위: `kakao_adblocker`, `tests`, `kakaotalk_layout_adblock_v11.py`

---

### PyInstaller 단일 파일(Onefile) 빌드

```powershell
# Spec 파일을 사용한 빌드
pyinstaller kakaotalk_adblock.spec
```

- 빌드가 완료되면 `dist/KakaoTalkLayoutAdBlocker_v11.exe` 단일 실행 파일이 생성됩니다.
- 관리자 권한을 요구하지 않는 non-UAC 실행 파일로 패키징됩니다.

---

### 스모크 체크 및 릴리스 서명

```powershell
# 1. 빌드 전/후 스모크 테스트
powershell -ExecutionPolicy Bypass -File .\scripts\smoke_check.ps1 -RunTests

# 2. 릴리스 빌드 파이프라인 (무서명 빌드)
powershell -ExecutionPolicy Bypass -File .\scripts\build_release.ps1 -NoSign

# 3. 인증서 서명을 포함한 릴리스 빌드 (선택 사항)
$env:SIGN_CERT_SHA1="YOUR_CERT_THUMBPRINT"
powershell -ExecutionPolicy Bypass -File .\scripts\build_release.ps1
```

---

## 📜 라이선스 및 참고 프로젝트

- **License**: 본 프로젝트의 라이선스는 저장소 루트의 `LICENSE` 파일을 따릅니다.
- **Reference**: 본 도구의 윈도우 레이아웃 차단 방식은 [blurfx/KakaoTalkAdBlock](https://github.com/blurfx/KakaoTalkAdBlock)의 레이아웃 알고리즘 개념을 참고하여 Python 및 Win32 API로 최적화 및 확장 재설계되었습니다.
