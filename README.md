# Tiny Second-hand Shopping Platform

Django 기반 중고거래 플랫폼을 대상으로 요구사항 분석부터 보안 설계, 구현, 테스트, 유지보수까지 수행하는 시큐어 코딩 과제 저장소입니다.

## 현재 상태

공개 `main`에는 보고서와 저장소 검증 도구만 반영되어 있습니다. 애플리케이션 모델과 실행 설정은 개발 브랜치에서 구현 중이며 아직 공개 `main`에서 실행할 수 없습니다. 따라서 존재하지 않는 설치·실행 명령이나 완료되지 않은 기능을 이 문서에서 안내하지 않습니다.

| 영역 | 상태 |
|---|---|
| 한국어 과제 보고서 | 작성 중 |
| Django 애플리케이션 골격 | 구현 중, `main` 통합 전 |
| 사용자·상품·채팅·신고 기능 | 구현 예정 또는 일부 골격 구현 중 |
| 검색·관리자·모의 잔액 이체 | 구현 예정 |
| 제품 기능·보안 종합 테스트 | 미검증 |

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
| 백엔드 | Python 3.12, Django 5.2 LTS, ASGI | 구현 중 |
| 실시간 통신 | Django Channels, Redis fan-out | 구현 중 |
| 데이터베이스 | PostgreSQL | 구현 중 |
| 화면 | Django Templates, vanilla JavaScript | 구현 예정 |
| 로컬 환경 | Docker Compose | 구현 중, `main` 통합 전 |
| 문서 | Markdown, Mermaid, GitHub Pages | 작성 중 |

## 사전 요구사항과 실행 방법

### 현재 `main`에서 가능한 작업

- Python 3.12 이상
- Git

저장소 문서·경계 테스트는 다음 명령으로 실행합니다.

```bash
python3 -m unittest discover -s tests/governance -v
```

2026-07-16 기준 위 명령으로 26개 테스트가 통과했습니다. 이 결과는 문서와 저장소 경계를 확인한 것이며, 제품 기능이 동작한다는 뜻은 아닙니다.

### 애플리케이션 실행

현재 공개 `main`에는 `pyproject.toml`, `.env.example`, `compose.yaml`, `src/`가 아직 없습니다. 아래 예시는 개발 브랜치의 설정 이름을 문서화한 것이며, 통합 뒤 실제 실행으로 다시 검증해야 합니다.

```dotenv
APP_ENV=development
DJANGO_DEBUG=true
DJANGO_SECRET_KEY=<개발용으로 새로 생성한 충분히 긴 값>
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:8000
POSTGRES_DB=marketplace
POSTGRES_USER=marketplace
POSTGRES_PASSWORD=<로컬 전용 비밀번호>
POSTGRES_HOST=db
POSTGRES_PORT=5432
REDIS_URL=redis://redis:6379/0
```

실제 값이나 토큰은 Git에 저장하지 않습니다. 관련 파일이 공개 `main`에 통합된 뒤 의존성 설치, 마이그레이션, Docker Compose 실행·중지, 제품 테스트, 서비스 상태 확인 명령을 실제로 실행하고 이 절을 갱신합니다.

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
