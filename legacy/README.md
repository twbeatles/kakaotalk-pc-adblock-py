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
- `카카오톡 광고제거 v10.0.py`
  - v11 엔트리포인트(`kakaotalk_layout_adblock_v11.py`)로 마이그레이션 안내만 출력
- `specs/`
  - `kakaotalk_adblock_v10.spec`

## 정책

- v11 런타임은 이 폴더를 참조하지 않습니다.
- 신규 기능/버그 수정은 `kakao_adblocker/`의 v11 코드에만 반영합니다.
- 루트 `pyrightconfig.json`의 활성 범위에서는 이 폴더를 제외합니다. 기존 파일 상단 `pyright` 지시문은 개별 유지보수 시 참고용으로만 남겨둡니다.
- GitHub Actions/windows-ci와 active packaging build도 이 폴더를 대상으로 하지 않으며, 현재 품질 게이트는 v11 런타임만 검증합니다.
- 레거시 파일은 동작 보존이 목적이므로, 타입/린트 수정을 하더라도 런타임 의미 변경은 금지합니다.
