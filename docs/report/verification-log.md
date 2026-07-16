# 검증 기록 안내

실제 실행한 검증과 실행하지 못한 항목은 [부록 B. 테스트 근거](appendix/test-evidence.md)에 통합했습니다.

## 확인 상태 요약

| 구분 | 결과 | 상태 |
|---|---|---|
| Django 점검·마이그레이션·컨테이너 정의 | 설정 점검 PASS, 마이그레이션 변경 없음, 컨테이너 정의·이미지 build PASS | PASS |
| `.env` 없는 Compose | build·migrate·`up -d --wait` 후 앱·DB·Redis healthy | PASS |
| HTTP 확인 | `/readyz/`는 HTTP 200, `/static/chat/chat.js`는 HTTP 200과 `text/javascript` | PASS |
| 복구·보존 | DB·Redis·앱 재시작 복구 확인; PostgreSQL backup/restore 뒤 `users=1`, `products=1`, migrations=24 일치 | PASS |
| 공급망·이력 | pytest 9.0.3 업그레이드 뒤 all-groups `pip-audit` clean; 고정 버전 gitleaks 전체 이력 검사에서 누출 없음 | PASS |
| 공개 문서 | GitHub Pages `https://ratelxd.github.io/secure-coding/` 접근 확인 | PASS |
| 최종 자동 테스트 건수 | `pytest -q`: 159 tests, 215 subtests PASS | PASS |
| ngrok | 사용할 수 없어 외부 터널 검증을 실행하지 않음 | 미검증 |

과거 채팅 수락의 PostgreSQL 행 잠금 및 Origin 검증 실패는 발견 당시의 근거이며, 현재 실패 상태가 아닙니다. 수정 후 집중 회귀와 당시 통합 스위트(154 tests, 210 subtests PASS)를 확인했으며, 최종 통합 스위트에서는 159 tests, 215 subtests가 통과했습니다.
