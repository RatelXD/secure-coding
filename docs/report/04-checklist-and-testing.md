# 04. 체크리스트와 테스트

## 4.1 상태 표기

- `PASS`: 실제 실행 결과와 근거가 있습니다.
- `FAIL`: 실제 실행 결과가 기대와 다릅니다.
- `미검증`: 테스트 방법은 정했지만 아직 실행하지 않았습니다.
- `구현 예정`: 테스트할 기능 자체가 아직 없습니다.
- `재검증 필요`: 코드나 환경이 바뀌어 이전 결과를 같은 조건에서 다시 확인해야 합니다.

## 4.2 기능 체크리스트

| 요구사항 ID | 점검 항목 | 테스트 방법 | 기대 결과 | 실제 결과 | 상태 | 근거 |
|---|---|---|---|---|---|---|
| `FR-USER-01` | 회원가입·로그인 | 정상·중복·잘못된 아이디와 비밀번호로 요청 | 유효한 사용자만 생성·로그인 | HTTP 흐름, 계정·IP 제한, 경합과 차단 뒤 저장 증폭 방지 테스트 통과 | PASS | `tests/unit/accounts_catalog/test_accounts_http.py`, `tests/integration/test_login_throttle_concurrency.py` |
| `FR-USER-03` | 본인 소개글·비밀번호 변경 | 본인과 다른 사용자 세션으로 변경 시도 | 본인만 허용 | 본인 전용 URL, 세션 epoch, IDOR·CSRF 테스트 통과 | PASS | 계정 HTTP·보안 테스트 |
| `FR-PRODUCT-01` | 상품 등록 | 정상·경계·잘못된 상품과 이미지 제출 | 유효한 상품만 저장 | 가격·판매 상태·재인코딩과 우회 입력 테스트 통과 | PASS | 상품 view·이미지·보안 테스트 |
| `FR-PRODUCT-02` | 본인 상품 관리 | 타인 상품 수정·삭제 시도 | 타인은 거부 | 소유자 재확인, 버전 충돌과 IDOR 테스트 통과 | PASS | `tests/unit/accounts_catalog/test_catalog_views.py` |
| `FR-PRODUCT-03` | 목록·상세 조회 | 비회원과 회원으로 공개·비노출 상품 조회 | 공개 상품만 노출 | DB 시각 기반 비노출 SQL 필터와 상세 404 테스트 통과 | PASS | 상품 view·보안·제재 테스트 |
| `FR-CHAT-01` | 전체 채팅 | 인증·비인증 사용자의 연결과 전송 | 인증 사용자만 허용 | 저장 후 전달·ACK, 속도 제한, 장애 이력 수렴 테스트 통과 | PASS | `tests/integration/test_chat_resilience.py` |
| `FR-CHAT-02` | 1대1 채팅 | 참여자와 제3자의 입장·이력 조회 | 두 참여자만 허용 | 정확히 두 참여자 방, 제3자 거부와 휴면 수신 차단 테스트 통과 | PASS | 채팅 unit·security 테스트 |
| `FR-REPORT-01` | 사용자·상품 신고 | 정상·자기·중복·기준 미달 신고 | 유효 신고만 집계 | 필수 사유, 대상·맥락·자격·중복 검증 테스트 통과 | PASS | 신고 HTTP·서비스 테스트 |
| `FR-REPORT-02` | 가역 제재 | 임계값 전후와 만료 시각 확인 | 한 번만 적용되고 만료 후 해제 | 동시 다섯 신고에서 제재·소비·감사 한 건과 DB 시각 만료 확인 | PASS | `tests/integration/test_moderation_concurrency.py` |

## 4.3 보안 체크리스트

| 보안 요구사항 ID | 점검 항목 | 테스트 방법 | 기대 결과 | 실제 결과 | 상태 | 근거 |
|---|---|---|---|---|---|---|
| `SR-AUTH-01` | 비밀번호 평문 저장 여부 | 사용자 생성 뒤 저장값과 비밀번호 검증 확인 | 원문이 저장되지 않고 올바른 비밀번호만 검증 | Django 단방향 해시 저장 확인 | PASS | `ACCT-PASSWORD-001` |
| `SR-AUTH-02` | 로그인 무차별 대입 | 계정·IP 기준 경계와 병렬 실패 요청 | 기준 초과 시 일반화된 제한 응답 | DB 권위 제한, 병렬 직렬화, 오래된 상태 정리와 일반 오류 확인 | PASS | 계정 unit·동시성 테스트 |
| `SR-AUTHZ-01` | 인증 없는 보호 기능 접근 | 로그아웃 상태로 보호 URL/API 요청 | 로그인 또는 403으로 차단 | 계정·상품·신고 보호 URL 음성 테스트 통과 | PASS | `tests/security/test_cycle1_http_security.py` |
| `SR-AUTHZ-01` | 타인 프로필·상품·신고 수정 | 다른 사용자 객체 ID로 변경 요청 | 403 또는 존재를 숨긴 404 | 타인 상품 변경 404와 참여자 전용 채팅 테스트 통과 | PASS | HTTP·채팅 테스트 |
| `SR-INPUT-01` | SQL Injection | 로그인 입력에 SQL 형태 문자열 전달 | 입력을 데이터로 처리하고 인증·DB 상태가 변하지 않음 | 잘못된 아이디로 일반 거부되고 기존 사용자 행 유지 | PASS | `tests/security/test_cycle1_http_security.py` |
| `SR-INPUT-01` | XSS | 상품·소개글·채팅에 스크립트성 문자열 입력 | text로 저장되고 화면에서 escape | 템플릿 escape와 채팅 `textContent` 회귀 테스트 통과 | PASS | `tests/security/test_cycle1_http_security.py` |
| `SR-SESSION-01` | CSRF | 토큰 없는 상태 변경 요청과 위조 Origin 요청 | 403으로 차단 | 상태 변경 POST의 CSRF와 WebSocket 정확 Origin 테스트 통과 | PASS | 독립 보안 스위트 |
| `SR-UPLOAD-01` | 파일 업로드 우회 | 확장자/MIME 불일치, SVG, 손상·과대 파일 | 전부 거부하고 실행되지 않음 | 완전 디코딩·재인코딩, 메타데이터 제거와 우회 입력 거부 확인 | PASS | 상품 이미지·보안 테스트 |
| `SR-CHAT-01` | WebSocket 인증·Origin·방 권한 | 비인증, null/위조 Origin, 제3자 방 접근 | 연결 또는 frame 단계에서 차단 | 정확 Origin, 참여자·현재 상태 재검증과 휴면 수신 차단 확인 | PASS | 채팅 unit·security 테스트 |
| `SR-ERROR-01` | 내부 정보 노출 | 400·403·404·500 응답과 로그 확인 | 비밀값·내부 경로·상세 예외 없음 | 로그인·신고 일반 오류와 비밀번호 로그 음성 테스트 통과, 운영 500 화면은 별도 확인 필요 | 미검증 | 운영 오류 응답 수동 확인 필요 |

## 4.4 자동화 테스트와 수동 테스트

### 자동화 대상

- 모델 제약과 서비스 단위 테스트
- HTTP 인증·권한·CSRF·입력값 통합 테스트
- WebSocket 인증·Origin·참여자·재전송 테스트
- 신고 임계값과 동시성 테스트
- 마이그레이션 생성 여부와 `django check --deploy`
- 의존성·비밀값·정적 분석 점검

### 수동 대상

- 회원가입부터 상품·채팅·신고까지의 브라우저 흐름
- 오류 메시지와 화면 출력의 민감정보·XSS 여부
- 이미지 표시와 메타데이터 제거 결과
- 휴면·비노출 전후 화면과 만료 후 복구
- Docker Compose 시작·재시작·백업·복구

## 4.5 현재 실제 실행 결과

2026-07-16에 현재 1차 애플리케이션을 대상으로 다음 검증을 실행했습니다.

| 대상 | 명령 | 결과 | 판단 범위 |
|---|---|---|---|
| 전체 자동 테스트 | `pytest -q` | 159 tests, 214 subtests PASS | 사용자·상품·채팅·신고 정상·음성·경계·경합과 보안 설정 |
| Django 설정 | `python src/manage.py check` | PASS | 현재 테스트 설정 |
| 운영 보안 설정 | `python src/manage.py check --deploy --fail-level WARNING` | PASS | 명시적 운영 환경 변수 사용 |
| 마이그레이션 | `python src/manage.py makemigrations --check --dry-run` | 변경 없음 | 모델과 마이그레이션 일치 |
| PostgreSQL 적용 | `python src/manage.py migrate --noinput` | PASS | 실제 PostgreSQL 컨테이너 |
| 의존성 취약점 | 전체 의존성 그룹 점검 | pytest 9.0.3 적용 뒤 취약점 없음 | 개발·검증 의존성 |
| 비밀값 | 고정 버전 스캐너로 전체 Git 이력 점검 | 누출 없음 | 현재와 과거 Git 이력 |
| `.env` 없는 Compose | `docker compose config`, 이미지 빌드, 마이그레이션, `up -d --wait` | PASS | 선택적 `.env`, 로컬 기본값, 앱·DB·Redis healthy |
| 서비스 상태와 정적 자산 | Compose 실행 후 `/readyz/`, `/static/chat/chat.js` 요청 | 모두 HTTP 200, 채팅 자산은 `text/javascript` | 앱·PostgreSQL 연결과 DEBUG 정적 자산 제공 |
| 재시작과 복구 | 앱·DB·Redis 재시작, PostgreSQL 백업·복원 | 재시작 복구 PASS; 복원 뒤 사용자 1명, 상품 1개, 마이그레이션 24개 일치 | 컨테이너와 데이터 복구 |

전체 159개와 하위 사례 214개를 실제 PostgreSQL·Redis 컨테이너에 연결해 실행했습니다. 계정·IP 로그인 제한 경합, 인증·IDOR·CSRF·XSS, 이미지 우회, WebSocket Origin·참여자·재전송·휴면 수신 차단, Redis 장애 이력 수렴, 동시 제재·만료와 마이그레이션 일치를 확인했습니다. `.env` 파일 없이 Compose 설정 해석, 이미지 빌드, 마이그레이션, 서비스 healthy 상태, 재시작 복구와 백업·복원을 확인했습니다. 외부 터널 서비스는 실행하지 않았으므로 이 보고서의 검증 근거에 포함하지 않습니다.
