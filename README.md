# Tiny Second-hand Shopping Platform (중고 거래 플랫폼)

Django 기반 중고거래 플랫폼을 대상으로 요구사항 분석부터 보안 설계, 구현, 테스트, 유지보수까지 수행하는 시큐어 코딩 과제 Repository입니다.

## 현재 상태

현재 저장소에는 Django 5.2 기반 동일 출처 ASGI 애플리케이션과 PostgreSQL·Redis 로컬 실행 구성이 있습니다. 1차 범위의 사용자·상품·채팅·신고·가역 제재 종단 기능을 구현했고, 전체 변경을 합친 자동·보안·동시성 테스트가 통과했습니다. 검색·관리자·모의 잔액 이체는 2차 범위로 남겨 두었습니다.

| 영역 | 상태 |
|---|---|
| 한국어 과제 보고서 | [GitHub Pages](https://ratelxd.github.io/secure-coding/) 공개 및 저장소 문서 완성 |
| Django 애플리케이션 | 1차 구현 |
| 사용자·상품·채팅·신고 기능 | 1차 종단 기능 구현, 통합 자동 검증 PASS |
| 검색·관리자·모의 잔액 이체 | 2차 범위, 미구현 |
| 골격·보안 설정 자동 테스트 | PASS |
| 1차 독립 보안 회귀 테스트 | 통합 실행 PASS |

## 주요 기능 범위

- 아이디와 비밀번호를 이용한 회원가입·로그인
- 사용자 조회와 본인 소개글·비밀번호 변경
- 상품 등록·관리·목록·상세 조회와 안전한 이미지 업로드
- 인증 사용자의 전체 채팅과 참여자 전용 1대1 채팅
- 사용자·상품 신고와 기간이 정해진 가역 제재
- 2차 개발 범위인 상품 검색, 관리자 기능, 모의 내부 잔액 이체

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
> 저장소를 받은 뒤 `.env`를 만들지 않고도 아래의 빌드·마이그레이션·실행 명령을 그대로 사용할 수 있습니다. Compose가 `APP_ENV=development`, 개발용 Django 키, PostgreSQL 계정, Redis 주소 등 로컬 전용 기본값을 제공합니다.

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

운영 환경에서도 `.env`라는 **파일 형식 자체가 필수인 것은 아니지만**, 운영용 환경 변수 값은 반드시 셸·배포 플랫폼·비밀 저장소 등 외부 수단으로 제공해야 합니다. 개발 기본값으로 운영을 시작하면 설정 검증이 실패하도록 구성했습니다.

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

2026-07-18 UTC 기준 전체 자동 테스트 224개와 하위 사례 346개가 통과했습니다. 이 결과에는 계정·IP 로그인 제한 경합, 인증·IDOR·CSRF·XSS, 이미지 우회, 다중 이미지 저장 수명주기와 지역 필터, WebSocket Origin·권한·재전송, Redis 장애 이력 수렴, 동시 신고·제재, 테스트 인프라의 loopback 격리, 미디어 지속성, 준비 상태 전체 제한 시간·다중 주소 대체, 마이그레이션 검증과 2차 상세 정책 구조 검사가 포함됩니다. `.env` 파일 없이 Compose 설정 해석, 이미지 빌드, 마이그레이션, 서비스 기동과 healthy 상태도 확인했습니다.

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
