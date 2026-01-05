# 🛡️ KakaoTalk AdBlocker Pro v10.0

카카오톡 PC 광고 차단기 - Advanced Window Sniffing Edition

## ✨ 주요 기능

- **고급 광고 스니핑** - 실시간 윈도우 계층 분석으로 광고 자동 감지
- **다중 전략 탐지** - 클래스명, 크기, 위치 기반 휴리스틱
- **팝업 광고 차단** - RichPopWnd 기반 팝업 자동 닫기
- **배너 자동 숨김** - Chrome 웹뷰 광고 및 배너 숨김 처리
- **Hosts 파일 차단** - 광고 도메인 네트워크 레벨 차단
- **실시간 통계** - 감지/차단 현황 대시보드

## 📦 필요 라이브러리

```bash
pip install PyQt6 psutil darkdetect
```

## 🚀 실행 방법

```bash
python "카카오톡 광고제거 v10.0.py"
```

## 📁 파일 구조

```
├── 카카오톡 광고제거 v10.0.py  # 메인 애플리케이션
├── ad_sniffer.py               # 광고 스니핑 엔진
├── window_inspector.py         # 디버그 도구
└── README.md
```

## 🔧 디버그 도구

```bash
# 윈도우 계층 분석
python window_inspector.py --json

# ad_sniffer 단독 테스트
python ad_sniffer.py --inspect
```

## 📦 빌드 (PyInstaller)

```bash
pyinstaller kakaotalk_adblock_v10.spec
```

## ⚠️ 주의사항

- Hosts 파일 수정은 **관리자 권한** 필요
- 카카오톡 업데이트 시 광고 패턴이 변경될 수 있음

## 📜 라이선스

MIT License
