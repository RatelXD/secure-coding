# 부록 A. 요구사항-설계-구현-테스트 추적표

이 표는 요구사항이 설계와 코드, 테스트에 어떻게 연결되는지 보여줍니다. 현재 저장소의 코드와 실제 실행 결과를 기준으로 상태를 표시하고, 종단 기능이 없으면 골격 테스트가 통과해도 `구현 중` 또는 `구현 예정`으로 유지합니다.

| 요구사항 ID | 요구사항 | 설계 요소 | 구현 파일·모듈 | 테스트 근거 | 상태 | 비고 |
|---|---|---|---|---|---|---|
| `FR-USER-01` | 회원가입·로그인 | Django 인증·세션, 아이디 정규화 | `apps/accounts` | 아이디·비밀번호 저장 골격 테스트 PASS | 구현 중 | 로그인 URL·속도 제한 미구현 |
| `FR-USER-02` | 공개 사용자 조회 | 공개 필드 allowlist | `apps/accounts` 예정 | 없음 | 구현 예정 | 민감 필드 비노출 확인 필요 |
| `FR-USER-03` | 본인 소개글·비밀번호 변경 | 세션 행위자·변경 필드 allowlist | `accounts/services.py` 골격 | 타인 변경 음성 테스트 예정 | 구현 중 | HTTP 경로 미구현 |
| `FR-PRODUCT-01` | 상품 등록 | 소유자 관계·안전 이미지 파이프라인 | `apps/catalog` | 소유자·이미지 경계 골격 테스트 PASS | 구현 중 | 가격·재인코딩 확인 필요 |
| `FR-PRODUCT-02` | 본인 상품 관리 | 객체 소유권·버전 확인 | `catalog/services.py` 골격 | IDOR 음성 테스트 예정 | 구현 중 | 실제 서비스 미구현 |
| `FR-PRODUCT-03` | 목록·상세 조회 | 공개 여부 정책 | `apps/catalog` 예정 | 공개·비노출 조회 테스트 예정 | 구현 예정 | URL·화면 없음 |
| `FR-CHAT-01` | 전체 채팅 | ASGI·인증·Origin·DB 수락 | `apps/chat` 골격 | 입력 정책·WebSocket 테스트 예정 | 구현 중 | consumer 미완 |
| `FR-CHAT-02` | 1대1 채팅 | 방 참여자 검증 | `Room`, `RoomParticipant` 골격 | 제3자 접근 테스트 예정 | 구현 중 | 정확히 두 참여자 제약 확인 필요 |
| `FR-REPORT-01` | 사용자·상품 신고 | 유효 신고 조건·고유 제약 | `apps/moderation` 골격 | 자기·중복·가입기간 테스트 예정 | 구현 중 | 신고 사유 확인 필요 |
| `FR-REPORT-02` | 가역 제재 | DB 시각·트랜잭션·감사 | `ModerationAction`, `AuditEvent` 골격 | 임계값·동시성·만료 테스트 예정 | 구현 중 | 제재 생성 서비스 미구현 |
| `FR-SEARCH-01` | 검색·정렬·페이지 | 공개 상품 query policy | `apps/catalog/search.py` 예정 | 입력·자원·비노출 테스트 예정 | 구현 예정 | 2차 기능 |
| `FR-ADMIN-01` | 관리자 기능 | 작업별 권한·재인증·감사 | `apps/administration` 예정 | 일반 사용자 거부 테스트 예정 | 구현 예정 | 2차 기능 |
| `FR-TRANSFER-01` | 모의 잔액 이체 | 행 잠금·멱등성·이중 분개 | `apps/transfers` 예정 | 합계 보존·동시성 테스트 예정 | 구현 예정 | 실제 결제 아님 |
| `SR-AUTH-01` | 비밀번호 안전 저장 | Django hash·validator | `apps/accounts` | `ACCT-PASSWORD-001` PASS | 구현 중 | 가입 서비스·오류 로그 확인 필요 |
| `SR-AUTHZ-01` | 서버 측 권한 확인 | 세션 행위자·소유권·참여자 검사 | 각 기능 service/view/consumer | IDOR·권한 음성 테스트 예정 | 구현 중 | 진입점별 적용 필요 |
| `SR-UPLOAD-01` | 안전한 이미지 제한 | 디코딩·재인코딩·UUID | `catalog/services.py` Protocol | 변조 이미지 corpus 예정 | 구현 예정 | 확장자 검사만으로 불충분 |
| `SR-SESSION-01` | 세션·CSRF·Host·HTTPS | Django 보안 설정 | `config/settings.py`, `config/middleware.py` | `check --deploy`, 프록시 설정 음성 테스트 PASS | 구현 중 | 실제 CSRF 요청·배포 TLS 확인 필요 |
| `SR-CHAT-01` | WebSocket 보안 | 인증·Origin·방 권한·속도 | `apps/chat`, `config/routing.py` | Channels 음성 테스트 예정 | 구현 중 | 종단 경로 미완 |
| `SR-REPORT-02` | 원자적 제재 | 단일 트랜잭션·멱등성 | `apps/moderation` 예정 | 동시 신고 테스트 예정 | 구현 예정 | 모델 골격만 확인 |
| `SR-TRANSFER-01` | 이체 무결성 | 잠금·이중 분개·재시도 | `apps/transfers` 예정 | property·동시성 테스트 예정 | 구현 예정 | 2차 기능 |

## 추적표 갱신 규칙

1. 파일이 생겼다는 이유만으로 상태를 `PASS`로 바꾸지 않습니다.
2. 현재 저장소에 반영된 코드와 실제 테스트 결과를 기준으로 갱신합니다.
3. 테스트 근거에는 명령, 결과, 대상 코드 상태를 함께 기록합니다.
4. 요구사항과 코드가 다르면 차이를 비고에 남기고 구현 또는 문서를 수정합니다.
