# Tiny Second-hand Shopping Platform (중고 거래 플랫폼)

Django 기반 중고거래 플랫폼의 요구사항 분석부터 보안 설계, 구현, 테스트, 유지보수까지 다루는 시큐어 코딩 과제 저장소입니다.

## 현재 상태

현재 저장소에는 Django 5.2 기반 동일 출처 ASGI 애플리케이션과 PostgreSQL·Redis 로컬 실행 구성이 있습니다. 사용자·상품·검색·채팅·알림·거래·신고·관리·후기·회원 탈퇴와 모의 잔액 이체까지 제품 코드에 반영되어 있습니다. 최신 변경은 `1467092302f789f802114f62d4d3dcfcf1b13be8`이며, PR #43·#44에서 채팅 연결 상태·가로형 로고·정수 원화 표시·재연결 한도를 보정했습니다.

| 영역 | 상태 |
|---|---|
| 한국어 과제 보고서 | [GitHub Pages](https://ratelxd.github.io/secure-coding/) 공개 및 저장소 문서 완성 |
| Django 애플리케이션 | 통합 기능 구현 |
| 사용자·상품·검색·채팅·알림·거래·신고·관리·후기·탈퇴 | 통합 종단 기능 구현 |
| 모의 잔액 이체 | PostgreSQL 이중 분개·멱등·대사 권위 구현 |
| 골격·보안 설정 자동 테스트 | 통합 matrix 실행 및 보정 근거 기록 |
| 브라우저·접근성 | 두 viewport Playwright/axe 검증 |

## 주요 기능 범위

- 아이디와 비밀번호를 이용한 회원가입·로그인
- 사용자 조회와 본인 소개글·비밀번호 변경
- 상품 등록·관리·목록·상세 조회와 안전한 이미지 업로드
- 상품에서 시작하는 인증 회원 간 1대1 채팅, 대화 이력·알림·송금
- WebSocket 연결 상태 표시와 제한된 지수 백오프 재연결
- 전역 공통 가로형 `주거니 받거니` 브랜드 로고
- 정수 원화 송금 입력과 `100,000원` 형식의 화면 표시
- 사용자·상품 신고와 기간이 정해진 가역 제재
- 상품 검색, 관리자 기능, 모의 내부 잔액 이체

세부 상태는 [요구사항 분석](docs/report/01-requirements.md)과 [기능 추적표](docs/report/appendix/feature-traceability.md)에서 확인할 수 있습니다.

## 기술 스택

| 구분 | 기술 | 상태 |
|---|---|---|
| 백엔드 | Python 3.12, Django 5.2 LTS, ASGI | 1차 구현 |
| 실시간 통신 | Django Channels, Redis fan-out | consumer·저장·이력 수렴 구현 |
| 데이터베이스 | PostgreSQL | 권위 저장소·마이그레이션 구현 |
| 화면 | Django Templates, vanilla JavaScript | 1차 서버 렌더링 화면 구현 |
| 로컬 환경 | Docker Compose | 실행 확인 |
| 문서 | Markdown, Mermaid, GitHub Pages | 한국어 1차 과제 보고서 공개 |

## 사전 요구사항

- Git
- Docker Engine과 Docker Compose 플러그인
- 전체 자동 테스트를 직접 실행할 때는 Python 3.12와 `uv`

## 환경 변수

> **로컬 Docker Compose 실행에는 `.env` 파일이 필요하지 않습니다.**
>
> 저장소를 받은 뒤에는 `.env`를 만들지 않고도 아래의 빌드·마이그레이션·실행 명령을 그대로 실행할 수 있습니다. Compose가 `APP_ENV=development`, 개발용 Django 키, PostgreSQL 계정, Redis 주소 등 로컬 전용 기본값을 제공합니다.

`.env`는 **선택 사항**입니다. 필요한 경우에만 `.env.example`을 `.env`로 복사해 수정하며, 비밀값이나 토큰은 Git에 저장하지 않습니다. 아래 내용은 필수 파일이 아니라 설정 가능한 항목의 예시입니다.

```dotenv
APP_ENV=development
DJANGO_DEBUG=true
DJANGO_SECRET_KEY=<개발용으로 새로 생성한 충분히 긴 값>
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:8000
DJANGO_TRUST_PROXY_HEADERS=false
DJANGO_TRUSTED_PROXY_IPS=
POSTGRES_DB=marketplace
POSTGRES_USER=marketplace
POSTGRES_PASSWORD=<로컬 전용 비밀번호>
POSTGRES_HOST=db
POSTGRES_PORT=5432
POSTGRES_SSLMODE=disable
REDIS_URL=redis://redis:6379/0
```

프록시 헤더를 신뢰하는 배포에서는 `DJANGO_TRUST_PROXY_HEADERS=true`와 실제 프록시 IP 목록을 함께 지정해야 합니다. `APP_ENV=production`에서는 개발 기본값으로 대체하지 않으며, 충분히 긴 비밀 키, 명시적 호스트·HTTPS CSRF 출처, TLS PostgreSQL·Redis 연결값을 모두 외부에서 제공해야 시작됩니다.

운영 환경에서도 `.env`라는 **파일 형식 자체가 필수인 것은 아니지만**, 운영용 환경 변수 값은 반드시 셸·배포 플랫폼·비밀 저장소 등 외부 수단으로 제공해야 합니다. 개발 기본값으로 운영을 시작할 수 없도록 설정 검증을 구성했습니다.

## 설치와 실행

```bash
docker compose build app
docker compose run --rm app python manage.py migrate --noinput
docker compose up -d
docker compose ps
```

서비스가 준비되면 `http://localhost:8000/readyz/`에서 데이터베이스 연결 상태를 확인할 수 있습니다. 종료할 때는 다음 명령을 사용합니다.

```bash
docker compose down
```

## 테스트 실행

문서·저장소 경계 테스트는 Python 표준 라이브러리만으로 실행할 수 있습니다.

```bash
python3 -m unittest discover -s tests/governance -v
```

전체 자동 테스트는 잠금 파일의 테스트 의존성을 설치한 뒤, 테스트 전용 Compose 오버레이로 PostgreSQL과 Redis를 loopback에만 열어 실행합니다. 이 절차도 `.env` 파일이 필요하지 않으며 기본 애플리케이션 데이터와 별도 프로젝트·볼륨을 사용합니다.

```bash
uv sync --frozen --group test
docker compose -p secure-coding-test \
  -f compose.yaml -f compose.test.yaml \
  up -d --wait db redis

APP_ENV=test \
POSTGRES_DB=marketplace \
POSTGRES_USER=marketplace \
POSTGRES_PASSWORD="${TEST_DB_PASSWORD:-development-only-database-password}" \
POSTGRES_HOST=127.0.0.1 \
POSTGRES_PORT="${TEST_DB_PORT:-55432}" \
POSTGRES_SSLMODE=disable \
REDIS_URL="redis://127.0.0.1:${TEST_REDIS_PORT:-56379}/0" \
uv run pytest -q

docker compose -p secure-coding-test \
  -f compose.yaml -f compose.test.yaml \
  down -v
```

2026-07-22 통합 matrix의 전체 `pytest`는 307 PASS·4 FAIL·하위 사례 448 PASS였고, 실패 원인을 수정한 뒤 실패한 정확한 node 4개를 재실행해 4 PASS를 확인했습니다. 같은 matrix에서 Django check, migration drift와 전진 적용은 PASS였습니다. PostgreSQL backup→빈 DB restore는 확장 의존 비교 명령을 제거한 뒤 migration 39개와 public table 45개가 일치했고, 고정 Playwright container에서 toolchain contract와 데스크톱·모바일 browser/axe 4건이 PASS였습니다. 최초 전체 실행의 실패를 숨기거나 이를 단일 311 PASS 실행으로 바꾸어 기록하지 않습니다. 이후 PR #43의 필수 CI 6개와 PR #44의 필수 CI 6개도 각각 PASS했습니다.

## 보안 설계 요약

- 가입 정보는 아이디와 비밀번호로 최소화합니다.
- 비밀번호는 Django 인증 체계의 해시와 검증기를 사용하도록 설계합니다.
- 프로필과 상품 변경은 서버에서 본인·소유자 권한을 다시 확인합니다.
- 상품 이미지는 형식·크기·해상도를 제한하고 디코딩 후 새 파일로 재인코딩하도록 설계합니다.
- 채팅은 인증, Origin, 참여자 권한, 메시지 길이·속도, 재전송 중복을 확인합니다.
- 신고와 제재는 중복·자기 신고를 제외하고, 기간이 정해진 가역 상태로 처리하도록 설계합니다.
- 상세 적용 상태와 남은 위험은 [보안 약점과 개선 계획](docs/report/06-security-improvements.md)에 기록합니다.

## 문서

- [한국어 1차 과제 보고서](https://ratelxd.github.io/secure-coding/)
- [저장소 보고서 색인](docs/report/index.md)
- [요구사항 분석](docs/report/01-requirements.md)
- [시스템 설계](docs/report/02-system-design.md)
- [구현 내용](docs/report/03-implementation.md)
- [체크리스트와 테스트](docs/report/04-checklist-and-testing.md)
- [유지보수](docs/report/05-maintenance.md)
- [보안 약점과 개선 계획](docs/report/06-security-improvements.md)

최종 PDF는 이 문서들을 바탕으로 사용자가 직접 편집합니다. 저장소의 선택적 렌더링 보조 도구는 사용할 수 있지만 필수 절차가 아닙니다.
