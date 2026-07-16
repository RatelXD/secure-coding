# 검증 기록 안내

실제 실행한 테스트와 앞으로 필요한 검증은 [부록 B. 테스트 근거](appendix/test-evidence.md)에 통합했습니다.

## 현재 확인된 결과

| 실행일 | 명령 | 결과 | 범위 |
|---|---|---|---|
| 2026-07-16 | `pytest -q` | 65 tests, 131 subtests PASS | 모델 제약, 정책 함수, 보안 설정, 저장소 경계 |
| 2026-07-16 | `python src/manage.py check --deploy --fail-level WARNING` | PASS | 명시적 운영 설정 |
| 2026-07-16 | 마이그레이션 생성 점검·PostgreSQL 적용 | PASS | 현재 모델과 마이그레이션 |
| 2026-07-16 | 컨테이너 정의·빌드·`/readyz/` | PASS, HTTP 200 | 애플리케이션 골격과 PostgreSQL 연결 |
| 2026-07-16 | `.env` 없이 Compose config·build·migrate·`up -d --wait` | PASS, 앱·DB·Redis healthy | 선택적 `.env`와 로컬 기본값 |
| 2026-07-16 | 운영 환경값 없이 설정 import | 시작 거부 PASS | 운영 설정 fail-closed |
| 2026-07-16 | PostgreSQL 동시 신고 독립 테스트 | 1 test PASS | 제재·신고 소비·감사 단일성 |
| 2026-07-16 | PostgreSQL 채팅 수락 독립 테스트 | 3 errors | nullable join 행 잠금 결함, 수정 필요 |

기존 골격·정책 결과와 신고 동시성 결과는 PASS입니다. 채팅 수락의 PostgreSQL 행 잠금 결함을 수정하고 독립 테스트와 전체 통합 스위트를 다시 통과하기 전에는 1차 전체를 PASS로 해석하지 않습니다. 검색·관리자·모의 이체는 2차 범위이며 아직 없습니다.
