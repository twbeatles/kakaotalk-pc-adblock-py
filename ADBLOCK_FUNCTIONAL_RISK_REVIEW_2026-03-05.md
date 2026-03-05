# KakaoTalk AdBlocker v11 기능 구현 리스크 점검 (2026-03-05)

## 점검 범위
- 기준 문서: `CLAUDE.md`, `README.md`
- 기준 코드: `kakao_adblocker/*.py`, `layout_rules_v11.json`, `scripts/build_release.ps1`
- 검증: `pytest -q` 실행 결과 `92 passed`

## 총평
- 현재 코드베이스는 문서와 대체로 정합하며, 기본 기능은 테스트 기준으로 안정적입니다.
- 다만 실사용 환경에서 장애/운영비용으로 이어질 수 있는 잠재 리스크가 일부 존재합니다.

## 우선순위 이슈

### P1-1. 트레이 가용성 판단이 런타임 실패를 반영하지 못함
- 근거:
  - `kakao_adblocker/ui.py:286`에서 `self._tray_running = True`를 먼저 설정한 뒤 스레드를 시작합니다.
  - `kakao_adblocker/ui.py:105`에서 `self._tray_available = bool(self._tray_running)`로 즉시 가용 판정을 확정합니다.
  - 트레이 스레드 내부(`self.icon.run`) 실패를 감시/반영하는 경로가 없습니다.
- 영향:
  - 트레이 스레드가 시작 직후 실패해도 앱은 트레이 사용 가능으로 오판할 수 있습니다.
  - 이 경우 창 닫기(X) 동작이 숨김으로 남아 사용자 복귀 경로가 사라질 위험이 있습니다.
- 권장:
  - 트레이 스레드 시작 후 ready/fail 신호(`Event` 또는 콜백)를 받아 `_tray_available`을 확정.
  - 스레드 예외 시 `_tray_available=False`로 내리고 창을 강제 표시하도록 폴백.

### P1-2. JSON 파손 파일 자동 복구가 없어 경고/백업이 반복될 수 있음
- 근거:
  - `kakao_adblocker/config.py:218-223`에서 파손 JSON을 감지하면 `None` 반환으로 기본값만 메모리 로드.
  - `kakao_adblocker/config.py:125-139`는 백업만 수행하고 원본 파손 파일 자체는 교체하지 않습니다.
  - `kakao_adblocker/config.py:364-378`는 파일이 "없을 때만" 템플릿 생성합니다.
- 영향:
  - 파손 파일이 그대로 남아 재시작마다 동일 경고와 `.broken-*` 백업 생성이 반복될 수 있습니다.
- 권장:
  - 파손 감지 후 백업 성공 시 기본값 JSON으로 원본을 원자적 재생성(`_atomic_write_text`)하는 self-heal 경로 추가.

### P2-1. `*.broken-*` 정리 로직이 파손 감지 시점에만 동작함
- 근거:
  - `kakao_adblocker/config.py:139`에서 `_cleanup_broken_backups()` 호출.
  - 해당 호출은 `_backup_broken_json()` 내부에만 존재합니다.
- 영향:
  - 문서상 "자동 정리" 기대와 달리, 이후 파손 이벤트가 없으면 오래된 백업이 장기간 남을 수 있습니다.
- 권장:
  - 앱 시작 시(또는 `load()` 시) 가볍게 1회 정리 루틴을 수행하도록 분리.

### P2-2. 차단 OFF 상태에서도 스캔 루프가 계속 동작함
- 근거:
  - `kakao_adblocker/event_engine.py:247-259`에서 watch/apply 루프는 항상 실행.
  - `kakao_adblocker/event_engine.py:314-315`에서 OFF일 때 `apply`만 스킵되고 `watch`는 계속 수행.
- 영향:
  - 사용자가 OFF를 선택해도 PID/윈도우 스캔 비용이 유지됩니다.
  - 저사양/배터리 환경에서 체감 자원 낭비가 될 수 있습니다.
- 권장:
  - OFF 상태에서는 watch 스캔도 스킵하고 긴 interval 대기 또는 루프 일시중단 모드 제공.

### P2-3. 기본 rules 템플릿에 `chrome_legacy_title_contains` 키가 없음
- 근거:
  - 코드 기본값에는 있음: `kakao_adblocker/config.py:290`
  - 루트 템플릿에는 누락: `layout_rules_v11.json`
- 영향:
  - 기능은 동작하지만, 사용자 입장에서 substring 시그니처를 발견/조정하기 어렵습니다.
- 권장:
  - `layout_rules_v11.json` 기본 템플릿에 키를 명시해 설정 가시성 확보.

### P3-1. `ShowWindow` 반환값을 성공/실패로 해석해 디버그 로그가 왜곡될 수 있음
- 근거:
  - `kakao_adblocker/win32_api.py:185-189`는 `ShowWindow` 반환을 bool로 전달.
  - `kakao_adblocker/event_engine.py:548-550`, `631`에서 `False`를 실패처럼 로깅.
- 영향:
  - Win32 API 의미(이전 표시 상태 반환)와 로그 해석이 어긋나 원인 분석이 어려워질 수 있습니다.
- 권장:
  - `ShowWindow` 호출 결과는 참고용으로만 취급하고, 실제 성공 판단은 `is_window_visible` 후속 상태 기준으로 일관화.

## 추가 구현 권장 사항

### A1. 테스트 공백 보완 (실환경 스모크)
- 현재 테스트는 Fake API 중심이라 실제 Win32/Tk/pystray 경합을 직접 검증하지 못합니다.
- 최소한 CI 외 수동 스모크 스크립트로 아래를 정례화 권장:
  - `--self-check`
  - `--minimized` + 트레이 실패 시 폴백 동작
  - OFF/ON 반복 시 자원 사용량 및 복원 동작

### A2. 설정 손상 복구 이벤트를 UI 상태에 명시
- 현재는 로그/`last_error` 반영 중심입니다.
- 설정 파일 자동 복구가 들어가면, 상태창에도 "복구됨/복구 실패"를 짧게 노출하면 사용자 지원 비용이 줄어듭니다.

### A3. 배포 의존성 분리
- `requirements.txt`에 `pytest`가 포함되어 있어 사용자 설치 시 불필요 패키지까지 같이 설치됩니다.
- 런타임/개발 의존성(`requirements.txt`, `requirements-dev.txt`) 분리를 권장합니다.

## 결론
- 즉시 대응 우선순위는 `P1-1`, `P1-2`입니다.
- 이후 `P2` 항목을 반영하면 장기 운영 안정성과 사용자 체감 품질이 개선됩니다.
