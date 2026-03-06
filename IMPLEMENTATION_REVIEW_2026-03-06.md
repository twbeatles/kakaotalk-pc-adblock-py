# 기능 구현 점검 메모

작성일: 2026-03-06
최종 업데이트: 2026-03-06

## 검토 범위

- `CLAUDE.md`
- `GEMINI.md`
- `README.md`
- `kakaotalk_adblock.spec`
- `kakao_adblocker/app.py`
- `kakao_adblocker/event_engine.py`
- `kakao_adblocker/ui.py`
- `tests/*`

## 반영 완료 항목

### 1. 시작 경고 유지

- `app.py`에서 우선순위 시작 경고를 `engine.start()` 이후에 반영하도록 순서를 조정함
- 결과적으로 시작 경고 1건이 실제 상태 문자열(`last_error`)에도 유지됨

### 2. 공격 모드 OFF 즉시 복구

- `event_engine.py`에 hide reason(`legacy`/`aggressive`) 추적을 추가함
- `ui.py`의 aggressive mode 토글은 저장 성공 후 엔진에 즉시 전달됨
- aggressive mode를 끄면 aggressive hide 창을 즉시 복구하고 바로 재스캔/재적용함

### 3. stale hide 자동 복구

- 숨김 창이 이후 aggressive/legacy 시그니처에 더 이상 매치되지 않으면 자동으로 복구되도록 엔진 로직을 추가함
- "한 번 숨기면 차단 OFF/종료 전까지 유지"되는 문제를 제거함

### 4. 상태 문자열 라벨 정리

- UI 상태 문자열에서 누적 카운터 의미가 분명하도록 `누적 숨김`, `누적 리사이즈` 라벨로 명시함

### 5. 회귀 테스트 보강

- 시작 경고 적용 순서 검증 추가
- aggressive mode OFF 즉시 복구 검증 추가
- stale legacy hide 자동 복구 검증 추가
- aggressive mode 토글이 엔진에 즉시 전달되는지 검증 추가

## 문서/패키징 정합성 반영

- `README.md`: 새 동작 반영
- `CLAUDE.md`: 엔진/UI 컨텍스트 반영
- `GEMINI.md`: 엔진/UI/패키징 메모 반영
- `kakaotalk_adblock.spec`: hidden import 변경 불필요함을 주석으로 명시
- `.gitignore`: `*.egg-info/`, `pip-wheel-metadata/` 추가

## 검증 결과

- `pytest -q` 실행 결과: `107 passed`

## 현재 결론

이번 점검에서 제안했던 핵심 구현 이슈는 코드와 테스트 기준으로 모두 반영 완료 상태다. 남은 작업은 별도 기능 확장이나 배포 절차 정리 수준이며, 현재 런타임/문서/패키징 정합성은 맞춰진 상태다.
