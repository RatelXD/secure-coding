# 부록 A. 요구사항-설계-구현-테스트 추적표

이 표는 요구사항이 설계와 코드, 테스트에 어떻게 연결되는지 보여줍니다. 현재 저장소의 코드와 실제 실행 결과를 기준으로 상태를 표시하고, 종단 기능이 없으면 골격 테스트가 통과해도 `구현 중` 또는 `구현 예정`으로 유지합니다.

| 요구사항 ID | 요구사항 | 설계 요소 | 구현 파일·모듈 | 테스트 근거 | 상태 | 비고 |
|---|---|---|---|---|---|---|
| `FR-USER-01` | 회원가입·로그인 | Django 인증·세션, 아이디 정규화, DB 제한 | `apps/accounts` model/form/service/view | 계정 HTTP·병렬 제한 테스트 PASS | PASS | 계정·IP 임계값과 일반 오류 확인 |
| `FR-USER-02` | 공개 사용자 조회 | 공개 필드 allowlist | `accounts/views.py`, 사용자 목록·상세 template | 민감 필드 비노출·XSS 테스트 PASS | PASS | 아이디·소개글만 공개 |
| `FR-USER-03` | 본인 소개글·비밀번호 변경 | 세션 행위자·변경 필드 allowlist | `accounts/forms.py`, `views.py` | 본인 변경·IDOR·CSRF·세션 테스트 PASS | PASS | 본인 세션에서만 변경 |
| `FR-PRODUCT-01` | 상품 등록 | 소유자 관계·안전 이미지 파이프라인 | `catalog/models.py`, `forms.py`, `services.py`, `views.py` | 가격·이미지·우회 입력 테스트 PASS | PASS | 가격과 안전한 이미지 필수 |
| `FR-PRODUCT-02` | 본인 상품 관리 | 객체 소유권·버전 확인 | `catalog/views.py` | IDOR·CSRF·버전 충돌 테스트 PASS | PASS | 잠금 안에서 소유자 재확인 |
| `FR-PRODUCT-03` | 목록·상세 조회 | DB 시각 공개 여부 정책 | `catalog/views.py`, `moderation/services.py` | 공개·비노출·만료 조회 테스트 PASS | PASS | 활성 제재 상품은 404 |
| `FR-CHAT-01` | 전체 채팅 | ASGI·인증·Origin·DB 수락 | `chat/consumers.py`, `services.py`, `views.py` | 입력·재전송·속도·장애 테스트 PASS | PASS | DB 저장 뒤 전달·ACK |
| `FR-CHAT-02` | 1대1 채팅 | 방 참여자·현재 상태 검증 | `Room`, `RoomParticipant`, chat service/consumer | 제3자·휴면 수신 차단 테스트 PASS | PASS | 정확히 두 참여자 |
| `FR-REPORT-01` | 사용자·상품 신고 | 유효 신고 조건·고유 제약 | `moderation/forms.py`, `views.py`, `services.py` | 자기·중복·가입기간·CSRF 테스트 PASS | PASS | 신고 사유 필수 |
| `FR-REPORT-02` | 가역 제재 | DB 시각·트랜잭션·감사 | moderation model/service/middleware | 임계값·동시성·만료 테스트 PASS | PASS | 7일 뒤 DB 시각 기준 해제 |
| `FR-SEARCH-01` | 검색·정렬·페이지 | 공개 상품 query policy | `apps/catalog/search.py` 예정 | 입력·자원·비노출 테스트 예정 | 구현 예정 | 2차 기능 |
| `FR-ADMIN-01` | 관리자 기능 | 작업별 권한·재인증·감사 | `apps/administration` 예정 | 일반 사용자 거부 테스트 예정 | 구현 예정 | 2차 기능 |
| `FR-TRANSFER-01` | 모의 잔액 이체 | 행 잠금·멱등성·이중 분개 | `apps/transfers` 예정 | 합계 보존·동시성 테스트 예정 | 구현 예정 | 실제 결제 아님 |
| `SR-AUTH-01` | 비밀번호 안전 저장 | Django hash·validator·세션 epoch | `apps/accounts` | 해시·NUL·로그·세션 음성 테스트 PASS | PASS | 12~128자와 Django 검증기 |
| `SR-AUTHZ-01` | 서버 측 권한 확인 | 세션 행위자·소유권·참여자 검사 | 각 기능 form/view/service/consumer | IDOR·비인증·제3자 음성 테스트 PASS | PASS | 모든 1차 진입점 적용 |
| `SR-UPLOAD-01` | 안전한 이미지 제한 | 디코딩·재인코딩·UUID | `catalog/forms.py`, `services.py` | 변조 이미지 corpus·메타데이터 테스트 PASS | PASS | JPEG·PNG·WebP만 허용 |
| `SR-SESSION-01` | 세션·CSRF·Host·HTTPS | Django 보안 설정·epoch·프록시 제한 | config settings/middleware와 accounts/chat | CSRF·Origin·epoch·`check --deploy` PASS | PASS | 실제 배포 프록시 값은 별도 확인 |
| `SR-CHAT-01` | WebSocket 보안 | 인증·정확 Origin·방 권한·속도·재수신 권한 | chat consumer/service | Origin·참여자·속도·재전송·휴면 테스트 PASS | PASS | Redis 장애 시 DB 이력 수렴 |
| `SR-REPORT-02` | 원자적 제재 | 대상 잠금·신고 소비·단일 감사·멱등성 | moderation model/service | 동시 다섯 신고·만료 테스트 PASS | PASS | 제재와 audit 한 건 |
| `SR-TRANSFER-01` | 이체 무결성 | 잠금·이중 분개·재시도 | `apps/transfers` 예정 | property·동시성 테스트 예정 | 구현 예정 | 2차 기능 |

## 추적표 갱신 규칙

1. 파일이 생겼다는 이유만으로 상태를 `PASS`로 바꾸지 않습니다.
2. 현재 저장소에 반영된 코드와 실제 테스트 결과를 기준으로 갱신합니다.
3. 테스트 근거에는 명령, 결과, 대상 코드 상태를 함께 기록합니다.
4. 요구사항과 코드가 다르면 차이를 비고에 남기고 구현 또는 문서를 수정합니다.
