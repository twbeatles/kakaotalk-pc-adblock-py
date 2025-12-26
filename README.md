# KakaoTalk AdBlocker Pro v6.0

카카오톡 PC 버전의 배너 광고를 차단하고, 광고가 있던 자리에 남는 빈 공간(레이아웃)을 자동으로 제거해주는 프로그램입니다.

![Python](https://img.shields.io/badge/Python-3.8+-blue)
![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-lightgrey)
![License](https://img.shields.io/badge/License-MIT-green)

## ✨ 주요 기능

| 기능 | 설명 |
|------|------|
| **광고 레이아웃 제거** | Chrome 기반 광고 컨트롤(`Chrome_WidgetWin_`) 감지 및 숨김 |
| **Hosts 도메인 차단** | 광고 서버 통신 원천 차단 |
| **AdFit 레지스트리 차단** | 팝업 광고 원천 차단 |
| **HiDPI 지원** | 고해상도 모니터 완벽 지원 |
| **시스템 트레이** | 백그라운드 실행 및 트레이 최소화 |
| **자동 시작** | Windows 부팅 시 자동 실행 |

## 🚀 사용 방법

### 실행 파일 (권장)
1. [Releases](../../releases)에서 `KakaoTalkAdBlocker_v6.exe` 다운로드
2. **관리자 권한으로 실행**
3. **스마트 최적화** 클릭

### 소스코드 실행
```bash
# 의존성 설치
pip install pystray Pillow psutil

# 실행 (관리자 권한 필요)
python "카카오톡 광고제거 v6.0.py"
```

## ⚙️ 설정

| 옵션 | 설명 |
|------|------|
| Windows 시작 시 자동 실행 | 레지스트리에 시작프로그램 등록 |
| 닫을 때 트레이로 최소화 | X 버튼 → 트레이 아이콘으로 숨김 |
| 시작 시 트레이로 바로 최소화 | 시작 시 창 없이 트레이로 |
| 광고 레이아웃 자동 제거 | `EVA_Window_Dblclk` 윈도우 내 광고 숨김 |
| 팝업 광고 차단 | `SOFTWARE\Kakao\AdFit` 레지스트리 조작 |

## 🛠️ 빌드

```bash
# PyInstaller 설치
pip install pyinstaller

# 빌드
pyinstaller kakaotalk_adblock.spec

# 결과물: dist/KakaoTalkAdBlocker_v6.exe
```

## 📁 파일 구조

```
├── 카카오톡 광고제거 v6.0.py    # 메인 프로그램
├── kakaotalk_adblock.spec      # PyInstaller 빌드 설정
├── blocked_domains.txt         # 차단할 도메인 목록
├── adblock_settings.json       # 설정 파일 (자동 생성)
└── adblock.log                 # 로그 파일 (자동 생성)
```

## 📋 변경 이력

### v6.0.0 (2024-12-27)
- ✨ 광고 레이아웃 제거 완전 재설계 (`EVA_Window_Dblclk`, `Chrome_WidgetWin_`)
- ✨ HiDPI Per-Monitor DPI Awareness V2 지원
- ✨ AdFit 레지스트리 차단 기능
- ✨ 실시간 로그 뷰어
- ✨ Toast 알림 시스템
- 🔧 UI/UX 전면 개선

### v5.x
- 시스템 트레이 / 자동 시작 기능
- 모던 UI 적용

---

**Disclaimer**: 이 프로그램은 개인 용도로 개발되었으며, 카카오(Kakao Corp)와 관련이 없습니다.
