# Tiny Second-hand Shopping Platform (중고 거래 플랫폼)

Django 기반 중고거래 플랫폼을 대상으로 요구사항 분석부터 보안 설계, 구현, 테스트, 유지보수까지 수행하는 시큐어 코딩 과제 Repository입니다.

## 현재 상태

현재 저장소에는 Django 5.2 기반 동일 출처 ASGI 애플리케이션과 PostgreSQL·Redis 로컬 실행 구성이 있습니다. 1차 범위의 사용자·상품·채팅·신고·가역 제재 종단 기능과 독립 보안 회귀 테스트를 구현했으며, 전체 변경을 합친 종합 검증은 진행 중입니다. 검색·관리자·모의 잔액 이체는 2차 범위로 남겨 두었습니다.

| 영역 | 상태 |
|---|---|
| 한국어 과제 보고서 | 작성 중 |
| Django 애플리케이션 | 1차 구현 |
| 사용자·상품·채팅·신고 기능 | 1차 종단 기능 구현, 종합 재검증 필요 |
| 검색·관리자·모의 잔액 이체 | 2차 범위, 미구현 |
| 골격·보안 설정 자동 테스트 | PASS |
| 1차 독립 보안 회귀 테스트 | 추가 완료, 통합 실행 전 |

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
| 문서 | Markdown, Mermaid, GitHub Pages | 작성 중 |

## 사전 요구사항

- Git
- Docker Engine과 Docker Compose 플러그인
- 전체 자동 테스트를 직접 실행할 때는 Python 3.12와 `uv`

## 환경 변수

`.env` 파일은 선택 사항입니다. 파일이 없어도 Docker Compose가 로컬 전용 기본값을 적용하므로 아래 실행 절차가 동작합니다. 값을 바꿀 때만 `.env.example`을 `.env`로 복사해 사용하며, 비밀값이나 토큰은 Git에 저장하지 않습니다.

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

전체 자동 테스트는 잠금 파일의 테스트 의존성을 설치하고, 테스트 전용 PostgreSQL에 연결한 상태에서 실행합니다.

```bash
uv sync --frozen --group test
APP_ENV=test \
POSTGRES_DB=marketplace \
POSTGRES_USER=marketplace \
POSTGRES_PASSWORD="${TEST_DB_PASSWORD:?set TEST_DB_PASSWORD}" \
POSTGRES_HOST="${TEST_DB_HOST:-127.0.0.1}" \
POSTGRES_PORT=5432 \
POSTGRES_SSLMODE=disable \
REDIS_URL=redis://127.0.0.1:6379/0 \
uv run pytest -q
```

2026-07-16 기준 골격 검증 65개와 하위 사례 131개가 통과했습니다. 이후 1차 기능용 독립 HTTP·업로드·채팅·동시성·마이그레이션 회귀 테스트를 추가했지만, 전체 변경을 합친 실행 결과는 아직 기록하지 않았으므로 1차 기능 전체를 PASS로 표시하지 않습니다. `.env` 파일 없이 Compose 빌드·마이그레이션·서비스 기동과 healthy 상태는 별도로 확인했습니다.

## 보안 설계 요약

- 가입 정보는 아이디와 비밀번호로 최소화합니다.
- 비밀번호는 Django 인증 체계의 해시와 검증기를 사용하도록 설계합니다.
- 프로필과 상품 변경은 서버에서 본인·소유자 권한을 다시 확인합니다.
- 상품 이미지는 형식·크기·해상도를 제한하고 디코딩 후 새 파일로 재인코딩하도록 설계합니다.
- 채팅은 인증, Origin, 참여자 권한, 메시지 길이·속도, 재전송 중복을 확인합니다.
- 신고와 제재는 중복·자기 신고를 제외하고, 기간이 정해진 가역 상태로 처리하도록 설계합니다.
- 상세 적용 상태와 남은 위험은 [보안 약점과 개선 계획](docs/report/06-security-improvements.md)에 기록합니다.

## 문서

- [개발 전 과정 보고서](docs/report/index.md)
- [요구사항 분석](docs/report/01-requirements.md)
- [시스템 설계](docs/report/02-system-design.md)
- [구현 내용](docs/report/03-implementation.md)
- [체크리스트와 테스트](docs/report/04-checklist-and-testing.md)
- [유지보수](docs/report/05-maintenance.md)
- [보안 약점과 개선 계획](docs/report/06-security-improvements.md)
- [GitHub Pages](https://ratelxd.github.io/secure-coding/)

최종 PDF는 이 문서들을 바탕으로 사용자가 직접 편집합니다. 저장소의 선택적 렌더링 보조 도구는 사용할 수 있지만 필수 절차가 아닙니다.
