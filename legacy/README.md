# Legacy Archive

이 디렉터리는 v11 전면 재설계 과정에서 분리된 구버전 코드 보관소입니다.

## 구성

- `kakao_adblocker/legacy.py`
  - v10 단일 모놀리식 구현 원본
- `backup/`
  - v4 ~ v9 스냅샷 스크립트
- `tools/`
  - `ad_sniffer.py`, `window_inspector.py`
- `configs/`
  - `ad_patterns.json`, `adblock_settings.json`, `blocked_domains.txt`, `adblock.log`
- `scripts/`
  - `카카오톡 광고제거 v8.0.py`
- `specs/`
  - `kakaotalk_adblock_v10.spec`

## 정책

- v11 런타임은 이 폴더를 참조하지 않습니다.
- 신규 기능/버그 수정은 `kakao_adblocker/`의 v11 코드에만 반영합니다.
