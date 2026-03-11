# 기능 구현 점검 메모

작성일: 2026-03-10
최종 업데이트: 2026-03-11

## 이번 라운드 추가 반영

- upstream parity 기준으로 누락돼 있던 explicit popup ad 처리 경로를 반영함
- `LayoutRulesV11.popup_ad_classes` 기본값 `["AdFitWebView"]` 추가
- 비메인 top-level KakaoTalk window의 direct child가 `popup_ad_classes`와 매치되면 parent/child를 `WM_CLOSE + SW_HIDE + zero-size` 처리
- popup 제거는 restore cache에 넣지 않아 차단 OFF/stop 시 legacy/aggressive hide 복구 로직과 섞이지 않도록 분리
- non-main media/emoticon viewer 보호 회귀 테스트 추가
- synthetic dump-tree fixture 2종(`popup_adfit_webview.json`, `non_main_media_viewer.json`) 추가

## 문서 / 패키징 정합성 점검 결과

- `README.md`, `CLAUDE.md`, `GEMINI.md`에 popup parity와 `popup_ad_classes` 규칙을 반영함
- `kakaotalk_adblock.spec`는 hidden import 변경이 필요하지 않았고, 주석만 현재 구현 기준으로 보강함
- spec 기준 onefile 빌드는 그대로 성공했고, popup parity는 기존 `config.py` / `event_engine.py` 경로 내부 구현이라 추가 hook이 필요하지 않았음
- `.gitignore`는 실제 빌드 후 재점검 결과 `build/`, `dist/`, 캐시류를 이미 충분히 덮고 있어 추가 수정 불필요

## 검증 결과

- `pytest -q`: `132 passed`
- `pyright kakao_adblocker tests`: `0 errors, 0 warnings`
- `python kakaotalk_layout_adblock_v11.py --self-check`: `5/5 checks passed`
- `powershell -ExecutionPolicy Bypass -File .\scripts\build_release.ps1 -NoSign`: 성공
- `dist\KakaoTalkLayoutAdBlocker_v11.exe --self-check`: `5/5 checks passed`, exit code `0`

## 현재 결론

현재 코드베이스는 popup parity까지 포함해 런타임, 테스트, 문서, onefile 패키징이 서로 맞물리도록 정리된 상태다.  
남은 리스크는 기존 메모와 동일하게 최신 클라이언트의 blank-banner처럼 실제 `--dump-tree` 샘플이 없는 케이스이며, 해당 영역은 fixture 확보 전까지 production 휴리스틱을 추측으로 바꾸지 않는 방침이 맞다.
