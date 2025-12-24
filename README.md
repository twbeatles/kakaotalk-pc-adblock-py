# 카카오톡 광고 차단기 Pro v4.0

<p align="center">
  <b>🛡️ 카카오톡 PC 버전의 광고를 완전히 차단하는 프로그램</b>
</p>

---

## ✨ 주요 기능

| 기능 | 설명 |
|------|------|
| 🛡️ **광고 도메인 차단** | hosts 파일 수정으로 광고 서버 접근 차단 |
| 🎯 **광고 레이아웃 제거** | Windows API로 광고 공간 자체를 숨김 (NEW!) |
| 🔔 **Toast 알림** | 비침투적 성공/오류 알림 시스템 |
| ⌨️ **키보드 단축키** | 빠른 작업 실행 |
| 🔄 **실시간 모니터링** | 차단 상태 변경 자동 감지 |
| 💾 **자동 백업** | hosts 파일 수정 전 자동 백업 |
| 🎨 **시스템 트레이** | 백그라운드 실행 지원 |

---

## 🚀 빠른 시작

### 1. 설치

```bash
# 필수 라이브러리 설치
pip install psutil pystray Pillow
```

### 2. 실행

```powershell
# 관리자 권한으로 PowerShell 열기
cd "프로그램 경로"
python "카카오톡 광고제거 v4.0.py"
```

> ⚠️ **관리자 권한 필수**: hosts 파일 수정을 위해 관리자 권한으로 실행해야 합니다.

### 3. 사용

1. **"🛡️ 광고 차단 시작"** 버튼 클릭
2. **"광고 레이아웃 숨기기"** 옵션 활성화 (선택)
3. **카카오톡 재시작**

---

## ⌨️ 키보드 단축키

| 단축키 | 기능 |
|--------|------|
| `Ctrl+B` | 광고 차단 시작 |
| `Ctrl+U` | 차단 해제 |
| `Ctrl+R` | 카카오톡 재시작 |
| `F5` | 상태 새로고침 |

---

## ⚙️ 옵션 설명

| 옵션 | 설명 | 기본값 |
|------|------|--------|
| 시스템 트레이 최소화 | 창 닫을 때 트레이로 최소화 | ✅ |
| 프로세스 모니터링 | 차단 상태 변경 감지 | ✅ |
| 광고 레이아웃 숨기기 | Windows API로 광고 공간 제거 | ✅ |

---

## 🔧 기술 상세

### 차단 방식

1. **hosts 파일 방식**
   - 광고 도메인을 `127.0.0.1`로 리다이렉트
   - 광고 콘텐츠 로딩 자체를 차단

2. **레이아웃 숨기기 방식** (NEW!)
   - Windows API (`EnumWindows`, `SetWindowPos`) 사용
   - `OnlineMainView`: 하단 31px 광고 영역 축소
   - `BannerAdView`, `AdView`: 완전히 숨김

### 차단 도메인 목록 (30+ 도메인)

```
# 핵심 광고 서버
display.ad.daum.net
ad.kakaocdn.net
ad.smart.kakao.com

# adimg 시리즈 (1-10)
adimg1.kakaocdn.net ~ adimg10.kakaocdn.net

# 트래킹/분석
track.tiara.kakao.com
stat.tiara.kakao.com
```

---

## 📦 빌드 (EXE 생성)

```bash
# PyInstaller 설치
pip install pyinstaller

# 빌드 실행
pyinstaller kakaotalk_adblock.spec
```

빌드된 파일: `dist/카카오톡 광고차단기 v4.0.exe`

---

## 📋 시스템 요구사항

- **OS**: Windows 10/11
- **Python**: 3.8+
- **권한**: 관리자 권한 필요

---

## ⚠️ 주의사항

1. 반드시 **관리자 권한**으로 실행
2. 광고 차단 후 **카카오톡 재시작** 필요
3. 레이아웃 숨기기는 **Windows 전용**
4. 카카오톡 업데이트 시 광고 구조 변경될 수 있음

---

## 📝 변경 로그

### v4.0.0 (2025-12)
- ✨ 광고 레이아웃 제거 기능 추가 (Windows API)
- ✨ Toast 알림 시스템 구현
- ✨ 키보드 단축키 추가 (Ctrl+B/U/R, F5)
- 🔧 광고 도메인 30개+ 추가 (2024-2025)
- 🐛 run_as_admin 경로 공백 버그 수정
- 🐛 모니터링 루프 상태 감지 추가

### v3.0.0
- 기본 hosts 파일 차단 기능
- 시스템 트레이 지원
- 자동 백업/복원

---

## 📄 라이선스

MIT License

---

## 🙏 크레딧

- 참고: [blurfx/KakaoTalkAdBlock](https://github.com/blurfx/KakaoTalkAdBlock)
