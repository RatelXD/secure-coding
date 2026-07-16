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
| 2026-07-16 | 채팅 잠금·Origin·휴면 수신 집중 회귀 | PASS | 발견 결함 3건 수정 확인 |
| 2026-07-16 | 계정·IP 로그인 제한 병렬 테스트 | 2 tests PASS | 행 잠금 직렬화와 임계값 |
| 2026-07-16 | `pytest -q` 통합 재실행 | 154 tests, 210 subtests PASS | 1차 사용자·상품·채팅·신고 전체 자동 검증 |

채팅 수락의 PostgreSQL 행 잠금, Host authority Origin, 휴면 뒤 기존 소켓 수신 결함과 계정 제한 저장 증폭·세션 epoch 결함을 수정했습니다. 집중 회귀와 전체 통합 스위트가 통과해 1차 자동 검증은 PASS입니다. 실제 프록시·백업 복원·브라우저 흐름은 종합 검증 근거로 분리하며, 검색·관리자·모의 이체는 2차 범위로 아직 구현하지 않았습니다.
