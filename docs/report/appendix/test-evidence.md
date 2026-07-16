# 부록 B. 테스트 근거

## B.1 현재 확인한 결과

| 실행일 | 대상 | 명령 또는 절차 | 관찰 결과 | 상태 |
|---|---|---|---|---|
| 2026-07-16 | 최종 자동 테스트 | `pytest -q` | 168 tests, 216 subtests PASS | PASS |
| 2026-07-16 | 테스트 인프라 재현 | README의 테스트 전용 Compose 준비·전체 테스트·정리 절차 | loopback 전용 DB·Redis에서 168 tests, 216 subtests PASS; 별도 프로젝트·볼륨 정리 확인 | PASS |
| 2026-07-16 | 상품 이미지 지속성 | 깨끗한 Compose에서 유효 PNG 등록·미디어 GET·앱 재시작·재조회 | 등록 302, 미디어 HTTP 200 `image/png`, 재시작 후 파일·조회 유지 | PASS |
| 2026-07-16 | DB 중단 준비 상태 | PostgreSQL 중단 뒤 3초 제한 `/readyz/`, 재시작 뒤 재요청 | 0.271초에 JSON 503, 복구 후 HTTP 200 | PASS |
| 2026-07-16 | 릴리스 표현 | RC1·RC2 본문과 태그 대상 확인 | GitHub Release 객체와 태그/SHA 불변 규칙을 구분하고 기존 태그 대상 유지 | PASS |
| 2026-07-16 | Django 설정 | `python src/manage.py check` | PASS | PASS |
| 2026-07-16 | 운영 보안 설정 | `python src/manage.py check --deploy --fail-level WARNING` | PASS | PASS |
| 2026-07-16 | 마이그레이션 일치 | `python src/manage.py makemigrations --check --dry-run` | 변경 없음 | PASS |
| 2026-07-16 | PostgreSQL 마이그레이션 | `python src/manage.py migrate --noinput` | PASS | PASS |
| 2026-07-16 | 컨테이너 정의·빌드 | `docker compose config --quiet`, `docker build --check .`, 이미지 build | PASS | PASS |
| 2026-07-16 | `.env` 없는 로컬 실행 | `.env` 없이 Compose build·migrate·`up -d --wait` | 앱·PostgreSQL·Redis healthy | PASS |
| 2026-07-16 | 준비 상태 | Compose 실행 뒤 `/readyz/` 요청 | HTTP 200 | PASS |
| 2026-07-16 | 정적 채팅 자산 | Compose 실행 뒤 `/static/chat/chat.js` 요청 | HTTP 200, `Content-Type: text/javascript` | PASS |
| 2026-07-16 | 서비스 복구 | DB·Redis·앱 재시작 | 재시작 뒤 복구 확인 | PASS |
| 2026-07-16 | PostgreSQL 백업·복원 | PostgreSQL backup/restore | 복원 전후 `users=1`, `products=1`, migrations=24 일치 | PASS |
| 2026-07-16 | 의존성 감사 | pytest 9.0.3 업그레이드 후 all-groups `pip-audit` | 취약 의존성 없음 | PASS |
| 2026-07-16 | 비밀값 | 고정 버전 gitleaks의 전체 Git 이력 검사 | 62 commits 검사, 누출 없음 | PASS |
| 2026-07-16 | Pages 배포 | GitHub Pages 배포 확인 | `https://ratelxd.github.io/secure-coding/` 접근 가능 | PASS |
| 2026-07-16 | 외부 터널 | ngrok | 도구를 사용할 수 없어 실행하지 않음 | 미검증 |

## B.2 과거 발견·수정 근거

아래 결과는 결함을 발견하고 수정한 당시의 기록이며, 현재 실패 상태를 뜻하지 않습니다.

| 실행일 | 대상 | 당시 관찰 결과 | 후속 확인 |
|---|---|---|---|
| 2026-07-16 | 채팅 수락 PostgreSQL 독립 테스트 | nullable join과 행 잠금 조합으로 3 errors | 잠금·Origin·휴면 수신 집중 회귀 PASS |
| 2026-07-16 | WebSocket 정확 Origin 독립 테스트 | Host userinfo 검증 누락으로 FAIL | 집중 회귀 PASS |
| 2026-07-16 | 1차 통합 스위트 | 당시 `pytest -q`가 154 tests, 210 subtests PASS | 당시 수정본의 회귀 근거; 유지보수 수정 후 최종 168 tests, 216 subtests는 B.1에 기록 |
| 2026-07-16 | 정식 릴리스 `v0.1.0` README 테스트 절차 | 기본 Compose 실행 뒤 문서의 `127.0.0.1:5432` 연결이 거부됨 | [issue #20](https://github.com/RatelXD/secure-coding/issues/20) 기록; 테스트 오버레이와 구성 회귀 테스트 추가 후 전체 테스트 PASS |
| 2026-07-16 | 정식 릴리스 상품 이미지 등록 | 유효 PNG 제출이 `/app/media` 권한 오류로 HTTP 500 | [issue #21](https://github.com/RatelXD/secure-coding/issues/21) 기록; 앱 소유 디렉터리·영속 볼륨 추가 후 등록·재시작 회귀 PASS |
| 2026-07-16 | 정식 릴리스 DB 중단 준비 상태 | `/readyz/`가 JSON 503 대신 3초 제한 시간 초과 | [issue #22](https://github.com/RatelXD/secure-coding/issues/22) 기록; 제한된 해석과 다중 주소 단일 쿼리로 수정 후 0.271초 503·복구 200 |
| 2026-07-16 | 릴리스 불변성 표현 | GitHub API는 `immutable=false`인데 본문은 “불변 후보”로 표기 | [issue #23](https://github.com/RatelXD/secure-coding/issues/23) 기록; 태그/SHA 규칙과 Release 객체 상태를 구분하도록 본문 수정 |

## B.3 자동화·운영 확인 상태

| 영역 | 확인 내용 | 상태 |
|---|---|---|
| 사용자 | 회원가입·로그인, 일반 오류, 비밀번호 저장·로그, CSRF, 타인 변경 거부, 제한 경합 | PASS |
| 상품 | 가격 경계, 소유자 CRUD, 공개 여부, 재인코딩·메타데이터·우회 입력 | PASS |
| 채팅 | 인증·Origin·참여자, 재전송 충돌, 속도, Redis 장애·이력 동기화, 휴면 수신 차단 | PASS |
| 신고·제재 | 필수 사유, 자기 신고, 동시 임계값, 단일 감사, 정확한 만료 | PASS |
| 배포·복구 | `.env` 없는 Compose, 준비 상태, 정적 자산, 재시작, PostgreSQL 백업·복원 | PASS |
| 실제 프록시·TLS | 배포 환경의 종단 프록시와 TLS | 미검증 |
| ngrok 외부 터널 | 터널을 통한 외부 접속 | 미검증(도구 사용 불가) |

## B.4 보고서용 캡처 원칙

1. 자동화된 결과와 운영 확인은 위 표의 명령·관찰 결과로 인용합니다.
2. 캡처를 추가할 때는 사용자 실명, 비밀번호, 세션, 토큰, 로컬 절대 경로를 포함하지 않습니다.
3. 구현하지 않은 다음 단계 기능의 화면·캡처는 이 1차 근거에 포함하지 않습니다.
