# 광고차단 개선안 구현 리포트 (2026-03-05)

작성일: 2026-03-05  
기준: `ADBLOCK_FUNCTIONAL_RISK_REVIEW_2026-03-05.md`

## 구현 범위
- P1~P3 + A1~A3 전체 반영
- 코드/테스트/문서/스크립트/의존성 분리 포함

## 반영 요약
- 트레이 시작 가용성 판정을 준비 신호 기반으로 전환하고, 시작 타임아웃 및 런타임 비정상 종료 시 창 접근 경로를 복구하도록 강화
- 설정/rules JSON 파손 시 `*.broken-*` 백업 후 기본값 JSON으로 self-heal 처리
- `*.broken-*` 백업 정리를 손상 이벤트 전용이 아니라 로드 시마다 수행
- 시작 경고 상태 반영 우선순위를 `복구 실패 > 자동 복구 > 기타`로 고정
- 엔진 OFF 시 watch/apply를 완전 일시중단하고 ON 전환 시 즉시 wake
- `ShowWindow` 반환값 해석을 제거하고, 후속 가시성 상태 기반으로 로그/판정을 통일
- `layout_rules_v11.json` 기본 템플릿에 `chrome_legacy_title_contains` 키 명시
- 운영 스모크 스크립트(`scripts/smoke_check.ps1`) 추가
- 의존성 분리: `requirements.txt`(런타임), `requirements-dev.txt`(개발/테스트/빌드)

## 정합성 반영
- 코드와 문서 동기화:
  - `README.md`
  - `CLAUDE.md`
  - `GEMINI.md`
- 빌드 스펙 점검:
  - `kakaotalk_adblock.spec`의 hiddenimports 집합이 최신 코드 경로와 정합
  - 트레이/자체복구 변경은 stdlib 중심이라 추가 hiddenimports 불필요

## .gitignore 점검
- Python 개발/테스트 캐시 및 IDE 산출물 패턴 보강:
  - `.venv/`, `venv/`, `env/`
  - `.mypy_cache/`, `.ruff_cache/`, `.tox/`, `.nox/`
  - `.coverage*`, `htmlcov/`
  - `.idea/`, `.vscode/`

## 검증 결과
- `pytest -q`: **105 passed**
- `powershell -ExecutionPolicy Bypass -File .\scripts\smoke_check.ps1`: **self-check 4/4 passed**
