# v1.0.0 최종 보고서

이 문서는 Tiny Second-hand Shopping Platform의 요구사항, 설계, 구현, 검증, 유지보수와 보안 약점을 한 번에 확인할 수 있도록 요약한 문서입니다. 기준 버전은 **v1.0.0**, 기준 main은 `48912530c846d200af461217d6b0034b942a8b04`입니다. 기존 상세 보고서가 추적하는 역사적 기준 `1467092302f789f802114f62d4d3dcfcf1b13be8`과 그 이후 변경은 구분해 적었습니다. `PASS`는 실제 실행 근거가 있는 경우에만 사용하고, 구현되었지만 세부 재검증이 필요한 항목과 배포 환경에서 아직 확인하지 않은 항목은 따로 표시합니다.

## 1. 요구사항 분석

비회원은 공개 상품을 조회하고, 일반 회원은 가입·로그인·프로필 변경·상품 관리·채팅·신고를 수행합니다. 관리자는 부여된 범위 안에서 신고와 가역 제재를 처리합니다. 수집 개인정보는 아이디와 비밀번호로 제한하며 이메일·전화번호·주소·결제정보는 범위에 넣지 않았습니다.

1차 범위는 사용자·상품·선택적 이미지(상품당 0~4장)·전체 및 상품 기반 1대1 채팅·신고·기간제 제재입니다. 2차 범위는 공개 상품 검색·정렬·페이지, 제한된 관리자 기능, 실제 결제와 분리된 모의 내부 잔액 이체입니다. 은행·PG 결제, 환불·정산, 이메일 인증·비밀번호 복구, 토큰 기반 별도 SPA, 영구 삭제 제재와 운영급 SRE는 제외했습니다. 상세 기능과 정책 식별자는 [요구사항 분석](01-requirements.md)에 있습니다.

핵심 보안 요구는 서버 권한 재검사, 입력·파일 경계 검증, 세션·CSRF·Origin 보호, 메시지 재전송 멱등성, 신고·제재 원자성, 오류·로그의 민감정보 비노출, 잔액·원장 불변성입니다. 2차 기능의 검색·관리·이체 수락 기준도 같은 문서에 보존되어 있습니다.

## 2. 시스템 설계

애플리케이션은 브라우저와 같은 출처를 사용하는 단일 Django ASGI 서비스입니다. PostgreSQL이 사용자·상품·채팅·신고·거래·감사 상태의 영속 권위이며, Redis는 채팅 fan-out과 presence를 위한 재구축 가능한 전달 계층입니다. 이미지 업로드는 크기·형식·해상도를 먼저 제한하고 완전 디코딩 후 새 파일로 재인코딩합니다. 설계와 신뢰 경계는 [시스템 설계](02-system-design.md)를 기준으로 합니다.

- HTTP 요청은 세션·CSRF·Host와 객체 소유권을 확인하고, WebSocket은 인증·정확한 Origin·방 참여자·현재 계정 상태를 연결과 frame에서 다시 확인합니다.
- 채팅 수락은 PostgreSQL 커밋을 기준으로 하며 Redis 전달 실패는 `degraded`로 남깁니다. 동일 client UUID는 중복 저장·재발행하지 않습니다.
- 신고와 제재는 유효 신고 판정, 대상 잠금, 신고 소비, 제재, 감사와 `auth_epoch` 변경을 하나의 트랜잭션으로 묶고, 제재는 정확히 7일인 가역 상태입니다.
- 모의 이체는 세션 사용자를 발신자로 고정하고 safety shared lock → 멱등성 lock → 계정 PK 순서로 잠급니다. 모든 journal은 두 entry와 합계 0을 커밋 시점에 검증하며 원장 변경·삭제는 DB에서 거부합니다.
- 검색은 공개 범위를 먼저 적용하고 NFC 정규화, allowlist, `q` 0~100자, `page` 1~500과 결정적 정렬을 적용합니다. 관리자 작업은 codename·대상 grant·재인증·CSRF·version과 append-only 감사를 함께 요구합니다.

## 3. 구현 내용

`src/apps` 아래에 `accounts`, `catalog`, `chat`, `moderation`, `trades`, `transfers` 경계를 두고 `config`에서 설정·URL·ASGI·상태 확인을 관리합니다. 실제 URL·서비스·마이그레이션·화면의 구현 범위는 [구현 내용](03-implementation.md)에 정리되어 있습니다.

- 계정은 Django 비밀번호 해시, 계정·비식별 HMAC IP별 로그인 제한, 세션 epoch 무효화, 본인 전용 변경 URL을 사용합니다.
- 상품은 소유자 재확인, 판매 수명주기에서 파생되는 상태, JPEG·PNG·WebP 재인코딩, UUIDv4 파일명과 메타데이터 제거를 적용합니다.
- 채팅은 저장 후 ACK와 Redis 전달을 분리하고, 연결 상태·최대 5회 지수 백오프·10초 안정 연결 뒤 재시도 카운터 초기화를 구현했습니다. 송금·알림은 정수 원화 표시를 사용합니다.
- 신고·제재는 자기·중복·자격 미달 신고를 제외하고 대상 잠금 아래에서 임계값과 만료를 DB 현재 시각으로 판단합니다.
- 2차 이체·검색·관리 기능은 제품 코드와 마이그레이션에 반영되어 있습니다. 이체는 멱등 payload와 이중 분개, 검색은 NFC·공개 필터·페이지 제한, 관리는 최소 권한과 감사 불변성을 중심으로 구현했습니다.

## 4. 체크리스트와 검증 결과

상태 정의와 Test-ID별 계약은 [체크리스트와 테스트](04-checklist-and-testing.md), 실행 명령·환경·관찰값은 [검증 기록](verification-log.md)과 [부록 테스트 근거](appendix/test-evidence.md)에 있습니다.

| 근거 | 실제 관찰 | 해석 |
|---|---|---|
| 2026-07-16 `pytest -q` | 170 tests, 217 subtests PASS | 당시 1차·보안·2차 구조 검증 |
| 2026-07-18 `uv run pytest -q` | 224 tests, 346 subtests PASS | 부록에 기록된 후속 실행 |
| 2026-07-22 통합 matrix | 최초 307 PASS, 4 FAIL, subtest 448 PASS; 실패한 정확한 4개 node 재실행은 4 PASS | 실패를 숨기거나 단일 `311 PASS` 실행으로 합산하지 않음 |
| Django·migration·복구 | `check`, drift, `migrate`, backup→빈 DB restore, 고정 browser toolchain과 desktop/mobile Playwright·axe가 기록된 범위에서 PASS | 실행 근거가 있는 범위만 확인 |
| PR #43·#44 CI | 필수 CI 6개가 각 PR head에서 PASS ([#43](https://github.com/RatelXD/secure-coding/pull/43), [#44](https://github.com/RatelXD/secure-coding/pull/44)) | 후속 UI·채팅 보정의 원격 CI 근거 |
| 미검증 범위 | ngrok, 실제 배포 프록시·TLS 종단, 운영 500 화면·로그 표본, 로컬 WebSocket 끊김 캡처, 2차 세부 장애·경합 계약 일부 | PASS로 표시하지 않음 |

`.env` 없는 Compose healthy 상태, `/readyz/` 200, 정적 채팅 자산 200/`text/javascript`, 재시작 복구와 PostgreSQL 백업·복원도 기록되어 있습니다. 2026-07-22 전체 matrix의 실패 보정은 실패 범위만 재실행했으므로 전체 matrix를 새로 한 번에 통과했다고 해석하지 않습니다.

## 5. 유지보수와 보정

[유지보수 기록](05-maintenance.md)은 배포 전 점검과 릴리스 관찰 후 수정을 구분합니다.

- `MNT-01`: 기본 Compose와 호스트 테스트 네트워크가 달랐던 문제를 테스트 전용 loopback DB `55432`·Redis `56379` 오버레이로 수정했습니다.
- `MNT-02`: 앱 사용자 소유 `/app/media`와 영속 볼륨을 추가해 이미지 등록·재시작 보존을 확인했습니다.
- `MNT-03`: DNS 0.25초와 PostgreSQL 전체 1.5초 제한으로 DB 중단 시 `/readyz/`가 0.271초 JSON 503을 반환하고 복구 후 200이 되도록 했습니다.
- `MNT-04`: GitHub Release 객체의 편집 가능 여부와 태그·SHA를 이동하지 않는 프로젝트 규칙을 구분해 문구를 바로잡았습니다.
- `MNT-05`: 상품 채팅 연결 상태, 재연결 상한·안정 연결 기준, 가로형 로고와 정수 원화 표시를 PR #43·#44에서 보정했습니다.

이후에는 인증 제한, 상품 공개 경계, Redis 장애·재전송, 신고 임계값·만료, 백업·복구를 관찰하고 문제마다 재현 조건·최소 수정·음성·회귀 테스트·잔여 위험을 함께 기록합니다.

## 6. VULN-01~VULN-11 통제 현황

상세 발견 당시 상태와 잔여 위험은 [보안 약점과 개선 계획](06-security-improvements.md), 간결한 확인 결과는 [보안 기록](security-log.md)에 있습니다. 아래 상태는 그 문서의 실행 근거를 그대로 구분한 것입니다.

| ID | 위험 | 구현된 완화 | 현재 근거와 남은 확인 |
|---|---|---|---|
| `VULN-01` | 로그인 무차별 대입·계정 존재 노출 | 계정·HMAC IP별 실패 제한, 냉각·상태 정리, 세션 epoch 검증, 아이디와 무관한 일반 오류 | 경계·병렬·알 수 없는 계정 음성 테스트 PASS |
| `VULN-02` | 타인 객체 접근·대량 할당 | 세션 행위자 고정, 소유자·참여자 재확인, Form allowlist, 타인 객체 404 | IDOR·CSRF·객체 권한 음성 테스트 PASS |
| `VULN-03` | 위험한 이미지 업로드 | JPEG·PNG·WebP 완전 디코딩·재인코딩, 5MiB·4096² 제한, UUIDv4 이름·메타데이터 제거 | MIME·서명·polyglot·손상·과대·경로 우회 테스트 PASS |
| `VULN-04` | 채팅 권한 우회·XSS·중복 메시지 | 인증·Origin·참여자·현재 상태 재검증, `textContent`, UUID 멱등 저장, Redis `degraded` 수렴 | 수정 후 집중 회귀 PASS; 실제 프록시 close code·수동 끊김 캡처는 미검증 |
| `VULN-05` | 신고 조작·동시 제재 경합 | 활성·가입 기간·자기·중복·독립 신고자 조건, 대상 잠금, 신고 소비·7일 제재·감사 원자 처리 | 임계값·동시 신고·만료·단일 감사 테스트 PASS |
| `VULN-06` | 오류·로그의 민감정보 노출 | 일반화된 응답, 비밀번호·세션·토큰·원문 IP·채팅 본문 미기록, 운영 DEBUG 거부 | 자동 오류·로그 음성 테스트 PASS; 운영 500 화면·배포 로그 표본은 미검증 |
| `VULN-07` | 신뢰되지 않은 프록시 헤더 | 전달 Host 미신뢰, 명시적 프록시 IP allowlist, 단일 `https` 주장만 수용, 나머지 헤더 제거 | proxy header 테스트와 `check --deploy` PASS; 실제 프록시 종단은 미검증 |
| `VULN-08` | 운영 DB TLS 하향 | 운영 `sslmode`를 `require`·`verify-ca`·`verify-full`로 제한하고 `disable/allow/prefer` 거부 | 설정 음성 테스트 PASS; 실제 운영 CA·호스트명 검증은 확인 필요 |
| `VULN-09` | 모의 이체 중복·부분 처리·잔액 불일치 | 세션 발신자, 계정 잠금, canonical 멱등 payload, 두 entry·합계 0 journal, 불변 trigger, BLOCKED 대사·재개 | 구현 및 PR #43 CI 근거 있음; 세부 장애·경합·복구 계약은 재검증 필요 |
| `VULN-10` | 검색을 통한 비노출 유출·자원 고갈 | 저장·검색 NFC, 공개 범위 선적용, query allowlist, `q` 100자·페이지 1~500, 결정적 정렬 | 구현 및 PR #43 CI 근거 있음; query budget·세부 경계는 재검증 필요 |
| `VULN-11` | 관리자 권한 상승·감사 훼손 | codename+대상 grant, superuser+직접 permission meta-scope, 300초 재인증·version·CSRF, append-only 감사와 bootstrap lock | 구현 및 PR #43 CI 근거 있음; 전체 HTTP·감사 장애·경합은 재검증 필요 |

`VULN-09`~`VULN-11`은 제품 코드와 마이그레이션이 구현된 상태를 기록한 것이며, 설계 표나 CI 통과만으로 모든 세부 수락 시나리오가 완료되었다고 주장하지 않습니다. 남은 검증과 잔여 위험은 위 표와 [06장](06-security-improvements.md)의 계획을 따릅니다.

## 7. 근거 문서

- [요구사항 분석](01-requirements.md)
- [시스템 설계](02-system-design.md)
- [구현 내용](03-implementation.md)
- [체크리스트와 테스트](04-checklist-and-testing.md)
- [유지보수](05-maintenance.md)
- [보안 약점과 개선 계획](06-security-improvements.md)
- [검증 기록](verification-log.md)
- [보안 기록](security-log.md)
- [부록 테스트 근거](appendix/test-evidence.md)

이 보고서는 공개 문서에서 비밀값·세션·개인정보·로컬 절대 경로를 제외한다는 [근거 작성 원칙](evidence-policy.md)을 따릅니다.
