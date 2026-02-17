# AI Context: KakaoTalk PC AdBlocker Pro v10.0

> 이 문서는 AI 에이전트가 프로젝트를 이해하고 코드를 수정할 때 참고해야 할 핵심 정보입니다.

## 1. 프로젝트 개요

| 항목 | 내용 |
|:--|:--|
| **목적** | 카카오톡 PC 버전의 광고 차단 및 레이아웃 정리 |
| **언어** | Python 3.9+ |
| **GUI** | tkinter (Tk/Tcl) |
| **최신 버전** | v10.0 (Event-Driven Architecture) |
| **코드 규모** | 약 1,100줄, 15개 클래스 |

## 2. 핵심 아키텍처

### 3-Layer 광고 차단 시스템

```
┌─────────────────────────────────────────────────────────┐
│ Layer 1: Hosts 파일 차단                                │
│ → 광고 서버 도메인을 0.0.0.0으로 리다이렉트             │
│ → HostsManager 클래스                                   │
├─────────────────────────────────────────────────────────┤
│ Layer 2: Windows API 레이아웃 조작                      │
│ → SetWinEventHook으로 이벤트 감지                       │
│ → ShowWindow(SW_HIDE)로 광고 숨김                       │
│ → SetWindowPos로 메인 뷰 리사이징                       │
│ → 레이아웃 휴리스틱(하단 배너) 감지                     │
│ → EventDrivenAdBlocker 클래스                           │
├─────────────────────────────────────────────────────────┤
│ Layer 3: AdFit 레지스트리 차단                          │
│ → 팝업 광고 LUD 값 조작                                 │
│ → AdFitBlocker 클래스                                   │
└─────────────────────────────────────────────────────────┘
```

### 이벤트 기반 감지 흐름

```
SetWinEventHook ──► _win_event_callback ──► Queue ──► _process_events
       │                                                    │
       │                                                    ▼
       │                                        PatternMatcher.is_ad_window()
       │                                                    │
       ▼                                                    ▼
  Message Pump                                    ShowWindow(hwnd, SW_HIDE)
  (GetMessage loop)                                         │
                                                            ▼
                                                   _resize_view()
```

## 3. 핵심 클래스 설명

### 광고 차단 엔진

| 클래스 | 역할 | 주요 메서드 |
|:--|:--|:--|
| `EventDrivenAdBlocker` | 이벤트 기반 광고 감지/차단 엔진 | `start()`, `stop()`, `_win_event_callback()` |
| `PatternMatcher` | 외부 설정 기반 패턴 매칭 | `is_ad_window()`, `is_resize_target()` |
| `PatternConfig` | ad_patterns.json 로드/관리 | `_load_config()`, `_parse_patterns()` |

### Windows API 래퍼

| 클래스 | 역할 | 주요 메서드 |
|:--|:--|:--|
| `User32` | user32.dll 정적 래퍼 | `get_pid()`, `get_class()`, `get_text()`, `show_window()`, `set_window_pos()` |

### 시스템 관리

| 클래스 | 역할 | 주요 메서드 |
|:--|:--|:--|
| `HostsManager` | Hosts 파일 조작 | `block(domains)`, `get_status()` |
| `AdFitBlocker` | 레지스트리 팝업 차단 | `_update()` (LUD 값 조작) |
| `SystemManager` | 프로세스/DNS/권한 관리 | `is_admin()`, `flush_dns()`, `restart_process()` |
| `StartupManager` | 윈도우 시작프로그램 | `is_enabled()`, `set_enabled()` |

### UI 컴포넌트

| 클래스 | 역할 |
|:--|:--|
| `MainWindow` | 메인 GUI 윈도우 |
| `ModernButton` | 둥근 모서리 커스텀 버튼 |
| `StatusCard` | 상태 표시 카드 위젯 |
| `TrayManager` | 시스템 트레이 관리 |

**UI 설정:** 실시간 보호 토글, 테마(라이트/다크) 즉시 적용 지원

## 4. 중요 설정 파일

### ad_patterns.json (외부 패턴 설정)

```json
{
  "ad_patterns": {
    "hide": [
      {"type": "text_startswith", "value": "BannerAdView"},
      {"type": "text_startswith", "value": "AdView"}
    ]
  },
  "resize_patterns": {
    "targets": [
      {"type": "text_startswith", "value": "OnlineMainView"}
    ]
  },
  "layout_heuristics": {
    "enabled": true,
    "min_height_px": 80,
    "max_height_px": 170,
    "min_width_ratio": 0.85,
    "bottom_margin_px": 10
  },
  "timing": {
    "scan_interval_active_ms": 500,
    "scan_interval_idle_ms": 2000
  },
  "event_hook": {
    "enabled": true,
    "fallback_polling": true
  }
}
```

**지원하는 패턴 타입:**
- `text_startswith` - 윈도우 텍스트가 특정 문자열로 시작
- `text_contains` - 윈도우 텍스트에 특정 문자열 포함
- `text_equals` - 정확히 일치
- `text_regex` - 정규식 매칭
- `class_equals` - 클래스 이름 일치
- `class_startswith` - 클래스 이름 시작

### adblock_settings.json (사용자 설정)
- `realtime_protection`: 전체 차단 엔진 ON/OFF
- `theme`: `light`/`dark`

## 5. 핵심 규칙

1. **관리자 권한 필수**: Hosts 파일 수정에 필요
2. **외부 패턴 설정**: `ad_patterns.json`에서 광고 패턴 관리 (코드 수정 불필요)
3. **Thread-Safety**: 모든 윈도우 조작은 `RLock`으로 보호
4. **Event Hook 우선**: 이벤트 훅 실패 시에만 Polling 폴백 사용
5. **폴링 간격**: `timing.scan_interval_*` 설정으로 폴링 간격 조정

## 6. 디렉토리 구조

```
├── 카카오톡 광고제거 v10.0.py    # 메인 실행 파일 (1,087줄)
├── ad_patterns.json              # 광고 패턴 설정
├── adblock_settings.json         # 사용자 설정 (auto_start, minimize_to_tray 등)
├── blocked_domains.txt           # 차단할 도메인 목록 (약 30개)
├── window_inspector.py           # 윈도우 구조 분석 도구
├── kakaotalk_adblock.spec        # PyInstaller 빌드 스펙
├── CLAUDE.md / GEMINI.md         # AI 컨텍스트 파일
├── README.md                     # 사용자 문서
└── backup/                       # 이전 버전 보관 (v4.0~v9.0)
```

## 7. 빌드 및 실행

```bash
# Python으로 실행
python "카카오톡 광고제거 v10.0.py"

# PyInstaller 빌드
pyinstaller kakaotalk_adblock.spec
```

## 8. 주의사항

- 카카오톡 업데이트 시 윈도우 클래스/텍스트명이 변경될 수 있음
- `ad_patterns.json`만 수정하면 새 광고 유형 대응 가능
- `EVA_Window`는 카카오톡 메인 윈도우 클래스명

## 9. 의존성

| 패키지 | 필수 여부 | 용도 |
|:--|:--|:--|
| `tkinter` | 필수 | GUI 프레임워크 |
| `ctypes` | 필수 | Windows API 호출 |
| `psutil` | 선택 | 프로세스 감지 (없으면 tasklist 사용) |
| `pystray` | 선택 | 시스템 트레이 아이콘 |
| `PIL/Pillow` | 선택 | 트레이 아이콘 이미지 생성 |
