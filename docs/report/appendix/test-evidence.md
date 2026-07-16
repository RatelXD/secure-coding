# 부록 B. 테스트 근거

## B.1 현재 저장소에서 확인한 결과

| 실행일 | 대상 | 명령 | 결과 | 판단 범위 |
|---|---|---|---|---|
| 2026-07-16 | 전체 자동 테스트 | `pytest -q` | 65 tests, 131 subtests PASS | 모델 제약, 정책 함수, 프록시 설정, 저장소 경계 |
| 2026-07-16 | 저장소 경계 | `python3 -m unittest discover -s tests/governance -p 'test_*.py'` | 40 tests PASS | 문서 도구, 공개 내용, 저장소 경계 |
| 2026-07-16 | Django 설정 | `python src/manage.py check` | PASS | 테스트 환경 설정 |
| 2026-07-16 | 운영 보안 설정 | `python src/manage.py check --deploy --fail-level WARNING` | PASS | 명시적 HTTPS·TLS·프록시 값 |
| 2026-07-16 | 마이그레이션 일치 | `python src/manage.py makemigrations --check --dry-run` | 변경 없음 | 현재 모델과 마이그레이션 |
| 2026-07-16 | PostgreSQL 마이그레이션 | `python src/manage.py migrate --noinput` | PASS | 실제 PostgreSQL 컨테이너 |
| 2026-07-16 | 컨테이너 정의·빌드 | `docker compose config --quiet`, `docker build --check .`, 이미지 build | PASS | Compose 구성과 애플리케이션 이미지 |
| 2026-07-16 | 서비스 상태 | Compose 실행 후 `/readyz/` 요청 | HTTP 200 | 애플리케이션과 PostgreSQL 연결 |
| 2026-07-16 | 비밀값 | 고정 digest의 전체 Git 이력 스캐너 | 누출 없음 | 현재 Git 이력 |
| 2026-07-16 | `.env` 없는 로컬 실행 | 임시 디렉터리 Compose config, `docker compose build app`, `migrate`, `up -d --wait` | PASS, 앱·DB·Redis healthy | `.env` 선택 사용과 Compose 로컬 기본값 |
| 2026-07-16 | 운영 설정 누락 | 환경 변수가 없는 앱 이미지에서 설정 import | 시작 거부 PASS | 운영 비밀 키 등 명시값 강제 |
| 2026-07-16 | 계정 HTTP 보안 | 독립 가입·해시·NUL·공개 필드·XSS·인증·CSRF·일반 오류 테스트 | 4 tests PASS | 계정 핵심 정상·음성 경계 |
| 2026-07-16 | 신고 동시성 | PostgreSQL에서 독립 동시 신고 테스트 | 1 test PASS | 동시 5건, 제재 1건, 소비 5건, 감사 1건, 정확히 7일 |
| 2026-07-16 | 신고 HTTP 보안 | 독립 인증·CSRF·필수 사유·자기 신고 일반 오류 테스트 | 1 test PASS | 신고 진입점 음성 경계 |
| 2026-07-16 | 범위·마이그레이션 | 독립 범위·leaf 테스트 | 2 tests PASS | 1차 앱별 단일 leaf, 2차 모듈 부재 |
| 2026-07-16 | 이미지 재인코딩 | 독립 메타데이터·UUID·SVG·polyglot·손상·경로 테스트 | 2 tests PASS | 안전한 새 이미지와 우회 입력 거부 |
| 2026-07-16 | 채팅 수락 | PostgreSQL에서 독립 재전송·장애·속도 테스트 | 3 errors | nullable join과 행 잠금 조합 결함, 수정·재검증 필요 |
| 2026-07-16 | WebSocket 정확 Origin | 형식이 잘못된 Host userinfo 독립 테스트 | FAIL | Host authority 검증 누락, 수정·재검증 필요 |
| 2026-07-16 | 채팅 결함 회귀 | nullable join 잠금, Host userinfo, 휴면 수신 차단 집중 테스트 | PASS | PostgreSQL 행 잠금 범위·Origin authority·outbound 권한 결함 수정 확인 |
| 2026-07-16 | 계정 제한 경합 | 동일 계정 5건과 동일 IP 10건 병렬 실패 | 2 tests PASS | 행 잠금 직렬화, 임계값 단일 적용 |
| 2026-07-16 | 1차 통합 스위트 | `pytest -q` | 154 tests, 210 subtests PASS | 사용자·상품·채팅·신고 정상·음성·경계·경합과 설정 |

위 결과는 실제로 실행했습니다. 채팅 수락의 PostgreSQL nullable join 잠금 오류와 Host userinfo Origin 검증 누락을 먼저 재현한 뒤 잠금 대상을 방 행으로 제한하고 Host authority를 엄격히 검사했습니다. 휴면 사용자의 기존 WebSocket 수신과 누락된 세션 epoch도 독립 검토에서 확인해 차단했습니다. 수정 후 집중 회귀 테스트와 전체 154개·하위 사례 210개가 통과했습니다. 검색·관리자·모의 이체는 2차 범위이며 구현하지 않았습니다.

## B.2 결과 해석

기존 자동 테스트와 새 통합 테스트는 아이디 정규화, 비밀번호 단방향 해시 저장, 계정·IP 제한과 경합, 세션 무효화, 상품 소유자 권한, 이미지 재인코딩, 채팅 Origin·참여자·재전송·휴면 수신 차단, Redis 장애 수렴, 신고 임계값·동시성, 프록시 설정과 저장소 경계를 확인합니다. 1차 자동 검증은 PASS이며 실제 프록시·백업 복원·브라우저 흐름은 종합 검증 근거로 분리합니다.

## B.3 자동화 테스트 상태

| 영역 | 필요한 테스트 | 상태 |
|---|---|---|
| 사용자 | 회원가입·로그인, 일반 오류, 비밀번호 저장·로그, CSRF, 타인 변경 거부, 제한 경합 | 통합 PASS |
| 상품 | 가격 경계, 소유자 CRUD, 공개 여부, 재인코딩·메타데이터·우회 입력 | 통합 PASS |
| 채팅 | 인증·Origin·참여자, 재전송 충돌, 속도, Redis 장애·이력 동기화, 휴면 수신 차단 | 통합 PASS |
| 신고·제재 | 필수 사유, 자기 신고, 동시 임계값, 단일 감사, 정확한 만료 | 통합 PASS |
| 검색 | 입력 길이, 정렬·페이지, 비노출 제외, 자원 제한 | 구현 예정 |
| 관리자 | 역할·권한·재인증·CSRF·버전·감사 | 구현 예정 |
| 모의 이체 | 금액 경계, 잔액 부족, 멱등성, 동시성, 합계 보존, 실패 롤백 | 구현 예정 |
| 배포·복구 | 실제 프록시·TLS, 백업·복원, 서비스 재시작 | 미검증 |

## B.4 최종 PDF에 넣을 캡처 목록

### 실행 환경

- `docker compose up` 뒤 앱·PostgreSQL·Redis 상태
- Django 마이그레이션과 시스템 점검 결과
- 사용한 Python·Django·PostgreSQL·Redis 버전

### 기능 화면

- 회원가입·로그인·마이페이지
- 상품 등록·목록·상세·수정
- 전체 채팅·1대1 채팅
- 신고 접수와 제재 전후
- 검색·관리자·모의 잔액 이체

### 보안 테스트

- 비인증 보호 기능 접근 차단
- 타인 프로필·상품 변경 차단
- 일반 사용자 관리자 기능 접근 차단
- CSRF 토큰 없는 변경 요청 차단
- XSS 문자열이 실행되지 않는 화면
- 위장·과대·손상 이미지 거부
- 잘못된 WebSocket Origin·타인 방 연결 거부
- 오류 응답과 로그의 민감정보 비노출

### 유지보수

- 실제 문제의 수정 전 재현 결과
- 수정 후 음성·회귀 테스트 결과
- 관련 코드 변경과 사용자 화면 변화

캡처에는 사용자 실명, 비밀번호, 세션, 토큰, 로컬 절대 경로가 보이지 않아야 합니다.
