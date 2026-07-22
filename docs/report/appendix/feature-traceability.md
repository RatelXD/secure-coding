# 부록 A. 요구사항-설계-구현-테스트 추적표

첫 표는 기존 기능을, 두 번째 표는 검색·관리·모의 이체 정책의 구현과 자동 검증 연결을 기록합니다. 상태는 실제 코드와 2026-07-22 통합 matrix 및 실패 범위 보정 검증 근거가 있는 경우에만 갱신합니다.

| 요구사항 ID | 요구사항 | 설계 요소 | 구현 파일·모듈 | 테스트 근거 | 상태 | 비고 |
|---|---|---|---|---|---|---|
| `FR-USER-01` | 회원가입·로그인 | Django 인증·세션, 아이디 정규화, DB 제한 | `apps/accounts` model/form/service/view | 계정 HTTP·병렬 제한 테스트 | PASS | 계정·IP 임계값과 일반 오류 확인 |
| `FR-USER-02` | 공개 사용자 조회 | 공개 필드 allowlist | `accounts/views.py`, 사용자 목록·상세 template | 민감 필드 비노출·XSS 테스트 | PASS | 아이디·소개글만 공개 |
| `FR-USER-03` | 본인 소개글·비밀번호 변경 | 세션 행위자·변경 필드 allowlist | `accounts/forms.py`, `views.py` | 본인 변경·IDOR·CSRF·세션 테스트 | PASS | 본인 세션에서만 변경 |
| `FR-PRODUCT-01` | 상품 등록 | 소유자 관계·안전 이미지 파이프라인 | `catalog/models.py`, `forms.py`, `services.py`, `views.py` | 가격·이미지·우회 입력 테스트 | PASS | 가격은 필수이며 이미지는 선택 사항, 제출한 이미지는 안전 처리 |
| `FR-PRODUCT-02` | 본인 상품 관리 | 객체 소유권·버전 확인 | `catalog/views.py` | IDOR·CSRF·버전 충돌 테스트 | PASS | 잠금 안에서 소유자 재확인 |
| `FR-PRODUCT-03` | 목록·상세 조회 | DB 시각 공개 여부 정책 | `catalog/views.py`, `moderation/services.py` | 공개·비노출·만료 조회 테스트 | PASS | 활성 제재 상품은 404 |
| `FR-CHAT-01` | 전체 채팅 | ASGI·인증·Origin·DB 수락 | `chat/consumers.py`, `services.py`, `views.py` | 입력·재전송·속도·장애 테스트 | PASS | DB 저장 뒤 전달·ACK |
| `FR-CHAT-02` | 1대1 채팅 | 방 참여자·현재 상태 검증 | `Room`, `RoomParticipant`, chat service/consumer | 제3자·휴면 수신 차단 테스트 | PASS | 정확히 두 참여자 |
| `FR-REPORT-01` | 사용자·상품 신고 | 유효 신고 조건·고유 제약 | `moderation/forms.py`, `views.py`, `services.py` | 자기·중복·가입기간·CSRF 테스트 | PASS | 신고 사유 필수 |
| `FR-REPORT-02` | 가역 제재 | DB 시각·트랜잭션·감사 | moderation model/service/middleware | 임계값·동시성·만료 테스트 | PASS | 7일 뒤 DB 시각 기준 해제 |
| `SR-AUTH-01` | 비밀번호 안전 저장 | Django hash·validator·세션 epoch | `apps/accounts` | 해시·NUL·로그·세션 음성 테스트 | PASS | 12~128자와 Django 검증기 |
| `SR-AUTHZ-01` | 서버 측 권한 확인 | 세션 행위자·소유권·참여자 검사 | 각 기능 form/view/service/consumer | IDOR·비인증·제3자 음성 테스트 | PASS | 모든 1차 진입점 적용 |
| `SR-UPLOAD-01` | 안전한 이미지 제한 | 디코딩·재인코딩·UUID | `catalog/forms.py`, `services.py` | 변조 이미지 corpus·메타데이터 테스트 | PASS | JPEG·PNG·WebP만 허용 |
| `SR-SESSION-01` | 세션·CSRF·Host·HTTPS | Django 보안 설정·epoch·프록시 제한 | config settings/middleware와 accounts/chat | CSRF·Origin·epoch·`check --deploy` | PASS | 실제 프록시 값은 배포 환경에서 별도 확인 필요 |
| `SR-CHAT-01` | WebSocket 보안 | 인증·정확 Origin·방 권한·속도·재수신 권한 | chat consumer/service | Origin·참여자·속도·재전송·휴면 테스트 | PASS | Redis 장애 시 DB 이력 수렴 |
| `SR-REPORT-02` | 원자적 제재 | 대상 잠금·신고 소비·단일 감사·멱등성 | moderation model/service | 동시 다섯 신고·만료 테스트 | PASS | 제재와 audit 한 건 |

## 2차 설계 추적표

상위 기능 `FR-TRANSFER-01`, `FR-SEARCH-01`, `FR-ADMIN-01`의 상세 정책 ID와 수락 기준은 [요구사항 분석의 2차 상세 정책](../01-requirements.md)에 있습니다.

| 정책 ID | 요구사항 | 설계 요소 | 구현 파일·모듈 | 검증 근거 | 상태 | 비고 |
|---|---|---|---|---|---|---|
| `이체-범위-01` | 현금과 분리된 `Decimal(12,2)` 모의 계정 | +100,000.00·`SEED_RESERVE` -100,000.00 합계 0 `SEED_ISSUE` | `apps/transfers/models.py`, `services.py`, `0001_initial.py` | `tests/unit/trades_transfer/test_authority.py` | 구현·자동 검증 수행 | 외부 결제 제외 |
| `이체-금액-01` | 0.01..99,999,999.99와 잔액 상한 | `Decimal`, DB CHECK, 서비스 재검사 | `apps/transfers/views.py`, `services.py` | transfer 경계·HTTP 테스트 | 구현·자동 검증 수행 | `Decimal(12,2)` |
| `이체-계정-01` | 소유자만 잔액 0 계정 종료 | CSRF·safety shared·계정 잠금 | `apps/transfers/views.py`, `services.py` | 계정 종료 권한·상태 테스트 | 구현·자동 검증 수행 | 원장·감사 보존 |
| `이체-대상-01` | 세션 발신자와 활성 수신자 | 서버 행위자·DB 현재 상태 | `apps/transfers/services.py` | 발신자 위조·자기·미존재 음성 테스트 | 구현·자동 검증 수행 | 양쪽 상태 검사 |
| `이체-잔액-01` | 부족 잔액 거부 | 잠긴 최신 잔액 검사 | `apps/transfers/services.py` | 거부 뒤 계정·원장 불변 테스트 | 구현·자동 검증 수행 | 성공 row 0 |
| `이체-원자성-01` | journal 두 항목·합계 0 | deferred trigger·journal/entry 불변 trigger | `apps/transfers/migrations/0001_initial.py` | 비정상 journal·변조 거부 테스트 | 구현·자동 검증 수행 | PostgreSQL 커밋 검증 |
| `이체-멱등-01` | UUID와 canonical payload | safety shared→stable digest lock·저장 응답 재현 | `apps/transfers/services.py` | 201/422 재현·payload 충돌 테스트 | 구현·자동 검증 수행 | 새 키만 OPEN 검사 |
| `이체-동시성-01` | 차단과 새 이체 직렬화 | safety shared→멱등→계정 PK 순서·`40001`/`40P01` 재시도 | `apps/transfers/services.py` | BLOCKED·병렬·재시도 테스트 | 구현·자동 검증 수행 | 전환 뒤 늦은 commit 금지 |
| `이체-보정-01` | 직접 원장 변경 금지 | journal/entry 불변 trigger·보정 원본 참조 | `apps/transfers/models.py`, migration | 직접 변경 음성 테스트 | 구현·자동 검증 수행 | 일반 관리자 진입점 없음 |
| `이체-대사-01` | 잔액·원장 일치 | exclusive lock·incident·maintainer 재검증 | `reconcile_mock_ledger` command | BLOCKED/재개·backup restore 검증 | 구현·자동 검증 수행 | Redis 비권위 |
| `검색-공개-01` | 공개 상품만 검색 | DB 시각 가시성 선적용 | `apps/catalog/search.py` | `test_catalog_engagement_search.py` | 구현·자동 검증 수행 | 관리 우회 없음 |
| `검색-입력-01` | NFC·q 0..100 | migration backfill·DB CHECK·정규화 | catalog model/search/service | NFC/NFD·100/101·C0/C1 테스트 | 구현·자동 검증 수행 | 빈 검색은 공개 전체 |
| `검색-필터-01` | 상태·가격 allowlist | AVAILABLE/SOLD·정수 가격·AND | `apps/catalog/search.py` | 필터 조합·잘못된 입력 테스트 | 구현·자동 검증 수행 | fail closed |
| `검색-정렬-01` | 세 정렬·ID 내림차순 동률 | allowlist·결정적 tie-break | `apps/catalog/search.py` | 반복 순서·임의 필드 거부 | 구현·자동 검증 수행 | newest 기본 |
| `검색-페이지-01` | `1..500`, 페이지당 20건 | count+slice·사전 범위 거부 | `apps/catalog/search.py` | 20/21·500/501·query budget | 구현·자동 검증 수행 | 마지막 이후 빈 목록 |
| `관리-최소권한-01` | staff+codename+grant | 정확 permission·meta-scope 분리 | `apps/moderation/management.py`, `services.py` | `test_management_review.py` | 구현·자동 검증 수행 | 기본 거부 |
| `관리-범위-01` | USER/PRODUCT 객체 범위 | `AdminScopeGrant`·version·세션 무효화 | moderation model/service/view | 범위 밖 404·중복 grant 테스트 | 구현·자동 검증 수행 | 민감값·잔액·원장 제외 |
| `관리-재인증-01` | 300초·NFC reason·CSRF·version | 서버 시각과 stale 검사 | moderation management/service | 299/300/301·10..500 테스트 | 구현·자동 검증 수행 | 모든 관리 write |
| `관리-가역성-01` | 7일 제재·조기 해제 | DB 시각·`SanctionRelease` | moderation model/service | 만료 경계·hide/restore 테스트 | 구현·자동 검증 수행 | 원본 보존 |
| `관리-감사-01` | append-only 민감값 없는 감사 | 업무와 단일 transaction·trigger | moderation model/migration/service | 감사 실패 rollback·변조 거부 | 구현·자동 검증 수행 | grant 포함 |
| `관리-중복-01` | 중복 제재·해제 안전성 | 활성 단일성·기존 결과 반환 | moderation service | 병렬 적용/해제·만료 충돌 테스트 | 구현·자동 검증 수행 | 기간 연장 없음 |

2차 표는 구현 파일과 실행 테스트를 연결합니다. 새 SHA에서 검증하지 않은 결과를 PASS로 선기재하지 않으며 실패와 보정 명령을 검증 기록에 함께 남깁니다.
## G7A-1 상품 권위 구현 추적

이 표는 구현 파일과 검증 시나리오의 연결을 기록합니다. 2026-07-18 UTC에 집중 테스트 53건, 전체 `pytest` 224건과 하위 사례 346건, 데스크톱 브라우저 2건, 거버넌스 55건을 같은 작업 트리에서 확인했습니다.

| 정책 ID | 설계·위협 ID | 마이그레이션 ID | 구현 위치 | 테스트 ID | 한국어 시나리오와 기대값 | 상태 |
|---|---|---|---|---|---|---|
| `G7A-이미지-01` | `VULN-03`, 별도 byte 소유권 | `catalog.0003_catalog_authority_expand` | `apps/catalog/models.py`, catalog image service | `G7A-CAT-MIG-001`, `G7A-CAT-GUARD-002`, `G7A-CAT-GUARD-004` | 기존 source를 별도 migrated key로 복사하고 source/destination byte·checksum을 일치시킨다. reverse에서도 외부 byte를 파괴하지 않는다. | 통과 |
| `G7A-이미지-02` | `VULN-03`, gallery 경계 | `catalog.0003`, `0005`, `0006` | catalog form/service/view, `ProductImage`, 삭제 intent | `G7A-CAT-BOUNDARY-001`, `002`, lifecycle 집중 테스트 | 인증 사용자의 0·1·4장 입력 순서, 5장 거부, temp→owned 승격과 실패 재시도, legacy key 비공유를 확인한다. | 통과 |
| `G7A-분류지역-01` | 최소 지역정보·allowlist | `catalog.0003_catalog_authority_expand` | `Category`, `Region`, `Product.region_source`, catalog list | `G7A-CAT-REF-001`, `G7A-CAT-REGION-001`, `002` | 승인된 7개 분류, 기존 NULL 지역의 `LEGACY_UNSET`, 지역 생략·정확 선택·잘못된 코드의 fail-closed를 확인한다. | 통과 |
| `G7A-거래권위-01` | typed legacy SOLD·단일 read projector | `trades.0001_typed_trade_authority` | `apps/trades/models.py`, `apps/catalog/projectors.py` | `G7A-CAT-PROJECTOR-001`~`003`, `G7A-CAT-MIG-001` | SOLD 호환값을 buyer 없는 `LEGACY_SOLD/COMPLETED` Trade로 이관하고 `sale_state`를 읽기 권위로 사용하지 않는다. | 통과 |
| `G7A-동결-01` | mixed old/new write 금지 | `catalog.0004`, `0006` | DB trigger, owner field allowlist | `G7A-CAT-GUARD-001`~`004` | cutover 뒤 legacy 권위 변경과 Product hard DELETE, legacy/gallery shared key 직접 쓰기를 정확한 trigger로 거부한다. | 통과 |
| `G7A-권한회귀-01` | 세션 행위자·CSRF·소유권 | 해당 없음(기존 HTTP 경계 유지) | catalog form/view | `G7A-CAT-AUTHZ-001`, 기존 catalog HTTP 회귀 | 비인증 다중 이미지 요청은 상품과 이미지 row를 만들지 못하며 기존 소유자·CSRF 경계를 약화하지 않는다. | 통과 |
## G7A-2 회원 탈퇴 폐기 준비 추적

Phase 7A는 폐기 준비 경계만 추가하며 활성화는 Phase 7D에 맡깁니다. 2026-07-18 UTC에 계정·세션·폐기 task·채팅 종료 그룹·hard-OFF 경계를 포함한 집중 테스트 73건을 같은 작업 트리에서 통과시켰습니다.

| 정책 ID | 설계·위협 경계 | 구현·검증 위치 | 테스트 ID | 한국어 시나리오와 기대값 | 상태 |
|---|---|---|---|---|---|
| `G7A-탈퇴-OFF-01` | 공개 탈퇴 URL·폼 0개 | `apps/accounts/urls.py`, `forms.py`, `tests/unit/accounts_catalog/test_withdrawal_surface_contract.py` | `G7A-WITHDRAWAL-001`, `002` | accounts URL 이름·경로와 공개 form inventory에 withdraw/delete/deactivate 계열 진입점이 없음을 확인한다. | 통과 |
| `G7A-탈퇴-OFF-02` | 파괴적 사용자 변경 0건 | `tests/integration/test_withdrawal_no_mutation.py` | `G7A-WITHDRAWAL-003` | 인증 사용자가 예상 가능한 탈퇴·삭제 경로에 GET/POST해도 모두 404이고 accounts 소유 row 전체 snapshot이 바뀌지 않는다. | 통과 |
| `G7A-탈퇴-OFF-03` | 공개 내비게이션·동작 0개 | `src/templates/base.html`, 계정 template, `tests/security/accounts/test_withdrawal_navigation_security.py` | `G7A-WITHDRAWAL-004` | 홈·마이페이지·소개글·비밀번호 화면의 링크와 form action에 탈퇴 진입점이 없고 `회원 탈퇴` 문구도 노출되지 않는다. | 통과 |
| `G7A-탈퇴-준비-01` | 탈퇴 계정 fail-closed·공개 tombstone | `apps/accounts/services.py`, accounts·catalog·chat 공개 presenter와 template | 계정·상품·채팅 withdrawal 서비스 테스트 | `withdrawn_at` 계정은 HTTP·채팅 권위에서 거부하고 공개 화면과 이력에는 원래 아이디·소개 대신 `탈퇴한 회원`만 표시한다. | 통과 |
| `G7A-탈퇴-준비-02` | 인증 epoch·세션 폐기 인덱스 | `accounts.0004_withdrawal_preparation`, `UserSessionIndex`, `AccountSessionService` | `test_withdrawal_services.py`, `test_withdrawal_preparation_migration.py` | 로그인·가입·비밀번호 변경·로그아웃과 기존 유효 세션의 인덱스 생성·회전·폐기를 검증하고 epoch가 없거나 맞지 않으면 거부한다. | 통과 |
| `G7A-탈퇴-준비-03` | 내구성 있는 폐기 task·heartbeat | `RevocationTask`, `RevocationWorkerHeartbeat`, `prepare_withdrawal_revocation` | withdrawal model·service 테스트 | 비활성·사용 불가 비밀번호·탈퇴 시각·양의 epoch가 모두 맞을 때만 canonical event key의 task를 멱등 생성하고 상태·lease·heartbeat 제약을 적용한다. | 통과 |
| `G7A-탈퇴-준비-04` | 사용자별 WebSocket 종료 준비 | `apps/chat/services.py`, `ChatConsumer` | `tests/unit/chat/test_chat_delivery.py` | 연결마다 room 그룹과 사용자 종료 그룹을 함께 등록·해제하고 `user.close` 수신 시 4403으로 종료하며 그룹 등록 실패는 degraded로 노출한다. | 통과 |
| `G7A-탈퇴-OFF-04` | 활성화 hard OFF | `WITHDRAWAL_ACTIVATION_ENABLED = False`, withdrawal surface contract | hard-OFF 상수·URL·form·navigation 테스트 | 환경 변수로 켤 수 없는 코드 상수와 비노출 계약을 함께 확인하고 Phase 7D 전 공개 활성화를 금지한다. | 통과 |
## 추적표 갱신 규칙

1. 파일이 생겼다는 이유만으로 상태를 `통과`로 바꾸지 않습니다.
2. 현재 저장소에 반영된 코드와 실제 테스트 결과를 기준으로 갱신합니다.
3. 테스트 근거에는 명령, 결과, 대상 코드 상태를 함께 기록합니다.
4. 요구사항과 코드가 다르면 차이를 비고에 남기고 구현 또는 문서를 수정합니다.
