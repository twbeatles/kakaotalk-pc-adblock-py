# KakaoTalk Layout AdBlocker v11

Windows용 카카오톡 광고 레이아웃 정리 도구입니다.

## 핵심 변경점

- `hosts/DNS/AdFit` 기능을 완전히 제거했습니다.
- `blurfx/KakaoTalkAdBlock` 방식에 맞춰 `100ms` 폴링 기반 레이아웃 엔진으로 재설계했습니다.
- 기본 동작은 트레이 중심이며, 설정 창은 필요 시 열 수 있습니다.

## 실행

```bash
python kakaotalk_layout_adblock_v11.py
python kakaotalk_layout_adblock_v11.py --minimized
python kakaotalk_layout_adblock_v11.py --dump-tree
python kakaotalk_layout_adblock_v11.py --dump-tree --dump-dir "C:\temp"
```

## 설정/로그 경로

- `%APPDATA%\KakaoTalkAdBlockerLayout\layout_settings_v11.json`
- `%APPDATA%\KakaoTalkAdBlockerLayout\layout_rules_v11.json`
- `%APPDATA%\KakaoTalkAdBlockerLayout\layout_adblock.log`

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
- 시작프로그램 등록
- 창 열기
- 로그 폴더 열기
- 릴리스 페이지 열기(수동)
- 종료

## 빌드

```bash
pyinstaller kakaotalk_adblock.spec
```

`uac_admin`은 제거되어 관리자 권한 없이 실행됩니다.

## 이전 hosts 수정 이슈 수동 복구

v11은 hosts를 자동 수정하지 않습니다. 이전 버전으로 hosts가 남아 로그인 문제가 있으면 직접 정리하세요.

1. 관리자 권한 메모장으로 `C:\Windows\System32\drivers\etc\hosts` 열기
2. `# [KakaoTalk AdBlock Start]` ~ `# [KakaoTalk AdBlock End]` 블록 삭제
3. 저장 후 카카오톡 재시작

## 참고

- 참고 구현: https://github.com/blurfx/KakaoTalkAdBlock
