# 검증 기록 안내

실제 실행한 테스트와 앞으로 필요한 검증은 [부록 B. 테스트 근거](appendix/test-evidence.md)에 통합했습니다.

## 현재 확인된 결과

| 실행일 | 명령 | 결과 | 범위 |
|---|---|---|---|
| 2026-07-16 | `pytest -q` | 65 tests, 131 subtests PASS | 모델 제약, 정책 함수, 보안 설정, 저장소 경계 |
| 2026-07-16 | `python src/manage.py check --deploy --fail-level WARNING` | PASS | 명시적 운영 설정 |
| 2026-07-16 | 마이그레이션 생성 점검·PostgreSQL 적용 | PASS | 현재 모델과 마이그레이션 |
| 2026-07-16 | 컨테이너 정의·빌드·`/readyz/` | PASS, HTTP 200 | 애플리케이션 골격과 PostgreSQL 연결 |

이 결과는 현재 골격과 정책 계약의 검증입니다. 아직 없는 사용자 화면, 상품 CRUD, WebSocket consumer, 신고 생성 서비스, 검색, 관리자, 모의 이체의 종단 기능 결과로 해석하지 않습니다.
