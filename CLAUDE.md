# AI Context: KakaoTalk Layout AdBlocker v11

## 개요

- 목적: 카카오톡 Windows 클라이언트의 광고 영역을 레이아웃 조정으로 제거
- 버전: `11.x`
- 특징: `hosts/DNS/AdFit` 제거, 트레이 중심 UX, 100ms 폴링 엔진

## 엔트리포인트

- 실행: `kakaotalk_layout_adblock_v11.py`
- 기존 `카카오톡 광고제거 v10.0.py`는 사용중단 안내만 출력

## 핵심 모듈

- `kakao_adblocker/config.py`
  - `LayoutSettingsV11`, `LayoutRulesV11`
  - `%APPDATA%\KakaoTalkAdBlockerLayout` 경로 관리
- `kakao_adblocker/event_engine.py`
  - `LayoutOnlyEngine`, `EngineState`
  - watch/apply 루프(100ms), `main_window_classes` 기반 메인 윈도우 식별
- `kakao_adblocker/layout_engine.py`
  - `OnlineMainView` / `LockModeView` 리사이즈 규칙
  - 공격적 배너 휴리스틱, 짧은 ad 토큰 단어 경계 매칭
- `kakao_adblocker/ui.py`
  - `TrayController`
  - 트레이 메뉴: 상태/OnOff/시작프로그램/창 열기/로그/릴리스/종료
  - 최소화 시작 시(`--minimized`/`start_minimized`) 시작 안내 팝업 생략
- `kakao_adblocker/services.py`
  - `ProcessInspector`, `StartupManager`, `ReleaseService`

## 동작 규칙

1. `kakaotalk.exe` PID 집합을 수집
2. 메인 윈도우(`EVA_Window_Dblclk`/`EVA_Window`) 식별
3. `OnlineMainView`: `width=parent-2`, `height=parent-31`
4. `LockModeView`: `width=parent-2`, `height=parent`
5. `Chrome Legacy Window` 하위 광고 서브윈도우 숨김
6. 공격 모드에서 `Chrome_WidgetWin_* + ad token`/하단 배너 후보 숨김
7. 시작프로그램 토글은 레지스트리 갱신 성공 시에만 설정 파일에 반영

## 설정 파일

- `%APPDATA%\KakaoTalkAdBlockerLayout\layout_settings_v11.json`
- `%APPDATA%\KakaoTalkAdBlockerLayout\layout_rules_v11.json`
- `%APPDATA%\KakaoTalkAdBlockerLayout\layout_adblock.log`

## 레거시 보관

- 구버전 자산은 `legacy/`로 이동됨
- 원본 모놀리식: `legacy/kakao_adblocker/legacy.py`
