# KakaoTalk AdBlocker Pro v10.0

<div align="center">

**카카오톡 PC 광고 차단 및 레이아웃 정리 도구**

![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)
![Platform](https://img.shields.io/badge/Platform-Windows-blue.svg)
![License](https://img.shields.io/badge/License-Personal_Use-green.svg)

</div>

---

카카오톡 PC 버전에서 배너 광고를 차단하고, 광고가 있던 빈 공간을 자동으로 제거하여 깔끔한 화면을 제공하는 프로그램입니다.

**v10.0은 `SetWinEventHook` 기반 이벤트 아키텍처를 도입하여 CPU 사용률을 획기적으로 낮춘 대규모 업데이트입니다.**

## 🚀 v10.0 주요 변경사항

| 항목 | v8.0 이전 | v10.0 |
|:--|:--|:--|
| **감지 방식** | Polling (1.5초마다) | SetWinEventHook (이벤트 즉시) |
| **CPU 유휴 시** | 주기적 사용 | **0%** |
| **패턴 관리** | 하드코딩 | 외부 JSON 설정 |
| **확장성** | 코드 수정 필요 | 설정 파일만 수정 |

### 새로운 기능

- ⚡ **Event-Driven Engine**: Windows 접근성 훅으로 윈도우 생성 이벤트를 실시간 감지
- 📝 **External Pattern Config**: `ad_patterns.json`에서 광고 패턴을 외부 관리
- 🔄 **Hybrid Architecture**: 이벤트 감지 + Fallback 폴링으로 안정성 확보
- 📊 **Real-time Stats**: 차단된 광고 수, 처리된 이벤트 수 실시간 표시
- 🎛️ **실시간 보호 토글**: 엔진 전체 ON/OFF 제어
- 🎨 **테마 전환**: 라이트/다크 테마 즉시 적용

---

## ✨ 주요 기능

### 1. 광고 원천 차단 (Hosts)
Windows hosts 파일을 수정하여 광고 서버와의 통신을 차단합니다.
```
0.0.0.0 display.ad.daum.net
0.0.0.0 ad.kakao.com
...
```

### 2. 레이아웃 자동 정리 (Windows API)
광고 배너가 숨겨진 후 남은 빈 공간을 자동으로 채워 채팅 목록이 꽉 차게 표시됩니다.

### 3. 원클릭 최적화
[스마트 최적화] 버튼 클릭 한 번으로:
- ✅ 광고 도메인 차단
- ✅ DNS 캐시 초기화
- ✅ 카카오톡 자동 재시작

### 4. 팝업 광고 차단 (AdFit)
레지스트리 조작을 통해 팝업 광고를 차단합니다.

### 5. 백그라운드 모드
시스템 트레이에서 실행되어 방해 없이 작동합니다.

---

## 📥 설치 및 실행

### 요구사항
- **OS**: Windows 10/11
- **Python**: 3.9+ (또는 빌드된 exe 사용)
- **권한**: 관리자 권한 필수 (Hosts 파일 수정)

### Python으로 실행
```bash
# 관리자 권한으로 실행
python "카카오톡 광고제거 v10.0.py"
```

### 데이터/설정 저장 위치 (v10.x)
설정/패턴/도메인/로그 파일은 실행 폴더가 아니라 아래 경로에 저장됩니다.

- `%APPDATA%\\KakaoTalkAdBlockerPro`
  - `adblock_settings.json`
  - `ad_patterns.json`
  - `blocked_domains.txt`
  - `adblock.log`

처음 실행 시, EXE에 포함된 기본 설정 파일(리소스)을 AppData로 복사한 뒤 사용합니다.

### 진단 덤프(윈도우 트리)
배너가 안 잡히거나 레이아웃 복구가 실패할 때, 아래 방법으로 진단 덤프를 생성할 수 있습니다.

- GUI: 하단 `🧪 덤프` 버튼
- CLI:
```bash
python "카카오톡 광고제거 v10.0.py" --dump-tree
python "카카오톡 광고제거 v10.0.py" --dump-tree --dump-dir "C:\\temp"
```

덤프 파일은 `window_dump_*.json` 형태로 저장됩니다(기본: `%APPDATA%\\KakaoTalkAdBlockerPro`).

### EXE 빌드
```bash
# PyInstaller로 빌드
pyinstaller kakaotalk_adblock.spec
```

---

## 📁 프로젝트 구조

```
├── 카카오톡 광고제거 v10.0.py    # 메인 실행 파일
├── ad_patterns.json              # 광고 패턴 설정 ⭐
├── blocked_domains.txt           # 차단 도메인 목록
├── adblock_settings.json         # 사용자 설정
├── window_inspector.py           # 윈도우 분석 도구
├── kakaotalk_adblock.spec        # PyInstaller 스펙
├── CLAUDE.md / GEMINI.md         # AI 컨텍스트
├── README.md                     # 이 문서
└── backup/                       # 이전 버전 (v4.0~v9.0)
```

---

## ⚙️ 설정 가이드

### ad_patterns.json
광고 패턴을 외부에서 관리합니다. 카카오톡 업데이트로 광고 형식이 바뀌면 이 파일만 수정하세요.

```json
{
  "ad_patterns": {
    "hide": [
      {"type": "text_startswith", "value": "BannerAdView", "description": "하단 배너"},
      {"type": "text_startswith", "value": "AdView", "description": "일반 광고"}
    ]
  },
  "layout_heuristics": {
    "enabled": true,
    "min_height_px": 80,
    "max_height_px": 170,
    "min_width_ratio": 0.85,
    "bottom_margin_px": 10
  },
  "resize_patterns": {
    "targets": [
      {"type": "text_startswith", "value": "OnlineMainView"}
    ]
  },
  "timing": {
    "scan_interval_active_ms": 500,
    "scan_interval_idle_ms": 2000
  }
}
```

**지원하는 패턴 타입:**
| 타입 | 설명 | 예시 |
|:--|:--|:--|
| `text_startswith` | 텍스트가 특정 문자열로 시작 | `"BannerAdView"` |
| `text_contains` | 텍스트에 문자열 포함 | `"Ad"` |
| `text_equals` | 텍스트 정확히 일치 | `"광고"` |
| `text_regex` | 정규식 매칭 | `"Ad.*View"` |
| `class_equals` | 클래스명 일치 | `"EVA_Window"` |

### 프로그램 설정
| 옵션 | 설명 |
|:--|:--|
| 윈도우 시작 시 자동 실행 | PC 부팅 시 자동 시작 |
| 닫을 때 트레이로 최소화 | X 버튼 클릭 시 트레이로 숨김 |
| 실시간 보호 | 광고 차단 엔진 전체 ON/OFF |
| 광고 레이아웃 자동 제거 | 빈 공간 자동 채움 |
| 팝업 광고 차단 (AdFit) | 레지스트리 기반 팝업 차단 |
| 테마 | 라이트/다크 테마 선택 |

---

## 🛠️ 기술 스택

| 기술 | 용도 |
|:--|:--|
| `ctypes` | Windows API 호출 (user32.dll) |
| `SetWinEventHook` | 이벤트 기반 윈도우 감지 |
| `tkinter` | GUI 프레임워크 |
| `psutil` (선택) | 프로세스 감지 |
| `pystray` (선택) | 시스템 트레이 |

---

## 🔍 문제 해결

### 광고가 계속 보여요
1. **관리자 권한**으로 실행했는지 확인
2. [스마트 최적화] 버튼 클릭
3. 카카오톡을 완전히 종료 후 재시작

### 카카오톡이 업데이트되어 작동하지 않아요
1. `window_inspector.py` 실행하여 새 윈도우 이름 확인
2. `ad_patterns.json` 파일에 새 패턴 추가

### 프로그램이 실행되지 않아요
```bash
# 의존성 설치
pip install -r requirements.txt
```

> v10.x EXE 빌드는 UIA(pywinauto) 보조 스캔을 포함하도록 설정되어 있습니다.

---

## ⚠️ 라이선스 및 고지사항

이 프로그램은 **개인의 학습 및 연구 목적**으로 개발되었습니다.

- (주)카카오와 어떠한 관련도 없습니다.
- 이 프로그램을 사용하여 발생하는 모든 책임은 사용자 본인에게 있습니다.
- 상업적 사용은 금지됩니다.

---

## 📜 버전 히스토리

| 버전 | 주요 변경사항 |
|:--|:--|
| v10.0 | SetWinEventHook 이벤트 기반 아키텍처, 외부 패턴 설정 |
| v9.0 | PatternMatcher 클래스 도입 |
| v8.0 | Smart PID 타겟팅, Modern Flat UI |
| v5.0~v6.1 | 레이아웃 최적화 개선 |
| v4.0 | 초기 버전, Hosts + Layout 숨김 |
