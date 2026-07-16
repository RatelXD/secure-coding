# 03. 구현 내용

## 3.1 작성 기준

이 장은 실제 코드 경로가 확인되는 내용과 앞으로 구현할 내용을 구분합니다. 2026-07-16 기준 1차 사용자·상품·채팅·신고·가역 제재의 URL, 화면, 서비스와 독립 보안 회귀 테스트를 구현했습니다. 전체 변경을 합친 자동 테스트 결과는 아직 기록하지 않았으므로 종합 상태는 `재검증 필요`로 표시합니다.

## 3.2 프로젝트 구조

개발 중인 애플리케이션은 다음 구조를 사용합니다.

```text
src/
├── manage.py
├── config/                 # Django 설정, URL, ASGI, 미들웨어, 상태 확인
└── apps/
    ├── accounts/           # 사용자와 프로필 경계
    ├── catalog/            # 상품과 이미지 경계
    ├── chat/               # 채팅방, 메시지, 전달 계약
    └── moderation/         # 신고, 제재, 감사, 현재 상태 계산
```

`transfers`, `administration`, 상품 검색 모듈은 아직 만들지 않았습니다.

## 3.3 환경과 공통 설정

| 항목 | 코드 위치 | 구현 내용 | 상태 |
|---|---|---|---|
| Django 설정 | `src/config/settings.py` | 환경별 설정, PostgreSQL, Redis Channels, 쿠키·보안 헤더 기준 | 구현 |
| ASGI | `src/config/asgi.py`, `src/config/routing.py` | HTTP와 WebSocket 프로토콜 라우팅 | 구현 |
| 사용자 상태 미들웨어 | `src/config/middleware.py` | 인증 사용자 요청에서 현재 휴면 상태 확인 | 구현 |
| 상태 확인 | `src/config/health.py`, `src/config/urls.py` | liveness와 PostgreSQL readiness 분리 | 구현 |
| 로컬 환경 | `Dockerfile`, `compose.yaml`, `.env.example` | 선택적 `.env`, 앱·PostgreSQL·Redis 기본 구성 | 실행 확인 |

`check --deploy`, 명시적 HTTPS CSRF 출처, 신뢰 프록시 IP 제한, Docker 이미지 빌드와 Compose 상태 확인을 실행했습니다. 실제 배포의 도메인·프록시 IP·TLS 종단 값은 배포 환경에서 별도로 확인해야 합니다.

## 3.4 사용자 기능

### 구현 내용

- `src/apps/accounts/models.py`, `validators.py`, `forms.py`
  - 정규 아이디와 `auth_epoch`, 12~128자·NUL 거부·Django 비밀번호 검증을 적용합니다.
- `src/apps/accounts/services.py`
  - 계정과 키드 HMAC IP 식별자별 로그인 실패를 PostgreSQL에서 제한하고 일반 오류를 반환합니다.
- `src/apps/accounts/views.py`, `urls.py`
  - 가입·로그인·POST 로그아웃, 공개 사용자 목록·상세, 본인 소개글·비밀번호 변경을 제공합니다.
  - 공개 응답은 아이디와 소개글만 사용하며 본인 변경 URL에는 로그인·CSRF 경계를 적용합니다.

### 검증 상태

비밀번호 해시·로그, 일반 로그인 오류, 공개 필드, XSS, 인증·CSRF 회귀 테스트를 추가했습니다. 전체 통합 실행 전까지 종합 상태는 `재검증 필요`입니다.

## 3.5 상품 기능

### 구현 내용

- `src/apps/catalog/models.py`, `forms.py`, `views.py`
  - 가격·판매 상태·버전을 포함한 상품을 정의하고 소유자만 등록·수정·삭제합니다.
  - 공개 목록·상세는 DB 시각 기반 제재 가시성을 사용하며 활성 비노출 상품은 404를 반환합니다.
- `src/apps/catalog/services.py`
  - JPEG·PNG·WebP만 5 MiB·4096×4096 안에서 완전 디코딩합니다.
  - 새 이미지로 인코딩해 메타데이터를 제거하고 UUIDv4 저장 이름을 생성합니다.
  - SVG, MIME·서명 불일치, polyglot, 손상·과대·경로 입력을 거부합니다.

### 검증 상태

소유자 IDOR·CSRF, 공개 XSS·판매자 필드, 활성·만료 비노출, 메타데이터·UUID와 우회 입력 테스트를 추가했습니다. 전체 통합 실행 전까지 종합 상태는 `재검증 필요`입니다.

## 3.6 채팅 기능

### 구현 내용

- `src/apps/chat/models.py`, `services.py`
  - 전체 방 하나와 정확히 두 참여자의 고유 1대1 방, PostgreSQL 권위 속도 제한과 UUIDv4 멱등 수락을 구현합니다.
  - 저장 커밋 뒤 ACK·Redis fan-out을 수행하며 같은 재전송은 재발행하지 않고 다른 내용은 충돌로 거부합니다.
  - Redis 장애는 저장을 유지한 `degraded` 결과로 반환하고 cursor 이력으로 수렴합니다.
- `src/apps/chat/consumers.py`, `routing.py`, `static/chat/chat.js`
  - 인증·현재 사용자 상태·정확 Origin·참여자 권한을 연결과 frame에서 확인합니다.
  - 화면은 신뢰하지 않는 사용자명과 본문을 `textContent`로 출력합니다.

### 검증 상태

Origin·참여자, 재전송·충돌, 10/10초 제한, 전달 장애·이력 수렴과 안전한 DOM 출력 테스트를 추가했습니다. 전체 통합 실행 전까지 종합 상태는 `재검증 필요`입니다.

## 3.7 신고와 제재

### 구현 내용

- `src/apps/moderation/models.py`, `forms.py`, `views.py`
  - 사유가 필요한 사용자·상품 신고 URL과 신고자-대상 평생 고유 제약을 제공합니다.
- `src/apps/moderation/services.py`
  - 자기·비활성·가입 7일 미만 신고를 제외하고 7일 안의 독립 신고자 다섯 명과 사용자 두 맥락 조건을 판정합니다.
  - 대상 잠금 아래 신고 소비, 정확히 7일 제재, 감사 한 건과 휴면 `auth_epoch` 증가를 한 트랜잭션으로 적용합니다.
  - 사용자 휴면과 상품 비노출 효력·만료를 DB 현재 시각으로 계산합니다.

### 검증 상태

필수 사유·자기 신고·CSRF, 동시 다섯 신고의 제재·소비·감사 단일성, 활성·만료 공개 동작 테스트를 추가했습니다. 전체 통합 실행 전까지 종합 상태는 `재검증 필요`입니다.

## 3.8 2차 기능

| 기능 | 구현 계획 | 현재 상태 |
|---|---|---|
| 상품 검색 | 공개 상품만 대상으로 검색·정렬·페이지 나누기 | 구현 예정 |
| 관리자 | 작업별 권한, 재인증, 사유, 버전 확인, 감사 기록 | 구현 예정 |
| 모의 잔액 이체 | PostgreSQL 행 잠금, 멱등성 키, 이중 분개, 합계 보존 | 구현 예정 |

실제 돈, 은행 계좌, PG 결제는 다루지 않습니다.

## 3.9 보안 구현 기록 방식

보안 기능은 다음 네 가지를 함께 남깁니다.

1. 어떤 오용이나 공격을 막으려는지
2. 어떤 코드·설정·데이터 제약을 적용했는지
3. 정상 테스트와 음성 테스트를 어떻게 수행했는지
4. 아직 남은 한계가 무엇인지

구체적인 위험과 후속 검증은 [보안 약점과 개선 계획](06-security-improvements.md), 실제 명령은 [테스트 근거](appendix/test-evidence.md)에 기록합니다.
