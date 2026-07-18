# 부록 A. 요구사항-설계-구현-테스트 추적표

첫 표는 구현·검증을 마친 1차 범위를 연결합니다. 두 번째 표는 정책을 확정했지만 제품 코드와 검증은 아직 없는 2차 범위를 연결합니다. `PASS`는 실제 실행 근거가 있는 경우에만 사용하고, `설계 확정·미구현·미검증`은 구현 완료를 뜻하지 않습니다.

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

| 정책 ID | 요구사항 | 설계 요소 | 구현 파일·모듈 | 예정 검증 | 상태 | 비고 |
|---|---|---|---|---|---|---|
| `이체-범위-01` | 현금과 분리된 `Decimal(12,2)` 모의 계정 | 사용자 계정 +100,000.00·`SEED_RESERVE` -100,000.00의 단일 합계 0 `SEED_ISSUE`·SEED 전용 부분 고유 제약 | 없음(후속 구현) | 계정 단일성·균형 발행·다른 journal 허용·DB 중복 방지 테스트 | 설계 확정·미구현·미검증 | 충전·출금·환불·환전·외부 결제 제외 |
| `이체-금액-01` | 금액·잔액 경계 | 1회 0.01..99,999,999.99, 잔액 0.00..1,000,000,000.00 | 없음(후속 구현) | 소수 자릿수·0·음수·상하한 테스트 | 설계 확정·미구현·미검증 | `Decimal(12,2)` |
| `이체-계정-01` | 소유자만 안전하게 계정 종료 | CSRF POST·계정 행 잠금·잔액 0 재검사·종료 뒤 송수신 차단 | 없음(후속 구현) | 비소유자·종료/이체 양방향 경합·원장·감사 보존 테스트 | 설계 확정·미구현·미검증 | 휴면은 종료가 아니라 일시 동결 |
| `이체-대상-01` | 세션 발신자, 정확한 수신자, 양쪽 활성 | 서버 행위자 결정·DB 현재 시각 제재 상태 조회 | 없음(후속 구현) | 발신자 위조·자기·미존재·휴면 사용자 음성 테스트 | 설계 확정·미구현·미검증 | 발신자·수신자 모두 검사 |
| `이체-잔액-01` | 부족 잔액 거부 | 잠긴 최신 잔액 검사 | 없음(후속 구현) | 부족 잔액 뒤 계정·원장 불변 테스트 | 설계 확정·미구현·미검증 | 성공 이체 기록도 남기지 않음 |
| `이체-원자성-01` | 정확히 두 항목·합계 0 journal | deferred INSERT 검증·journal/entry UPDATE/DELETE trigger | 없음(후속 구현) | 0/1/2/3항목·합계 불일치·변경 거부 | 설계 확정·미구현·미검증 | PostgreSQL 커밋 시 검증 |
| `이체-멱등-01` | 발신자 UUID와 canonical payload | safety shared→stable digest lock·성공/업무 거부 status·body 영구 재사용·새 키만 OPEN 검사 | 없음(후속 구현) | 저장 201·422의 BLOCKED 순차/병렬 재현·동등 금액·payload 차이·롤백 키 재요청 | 설계 확정·미구현·미검증 | 시스템 실패만 같은 키 재처리 |
| `이체-동시성-01` | 차단 전환과 새 이체 직렬화 | safety shared→멱등→새 키 OPEN 검사→계정 잠금·대사 exclusive lock·`40001`/`40P01` 3회 | 없음(후속 구현) | BLOCKED 경합·저장 결과 재현·병렬 새 이체·총 4회 재시도 | 설계 확정·미구현·미검증 | 전환 뒤 새 이체 커밋 금지 |
| `이체-보정-01` | 원장·잔액 직접 변경 금지 | 원본 참조 보정 항목·휴면 시 계정 동결 | 없음(후속 구현) | 취소/조정 합계·원본 보존·휴면 복구 테스트 | 설계 확정·미구현·미검증 | 사용자·일반 관리자 보정 진입점 없음 |
| `이체-대사-01` | 시스템 전체 잔액과 원장 일치 | exclusive safety lock·incident·maintainer 전체 재검증 | 없음(후속 구현) | 전환 barrier·무권한/불완전 복구·재개 경합 | 설계 확정·미구현·미검증 | Redis는 잔액 권위가 아님 |
| `검색-공개-01` | 공개 상품만 검색 | 기존 DB 시각 상품 공개 정책 재사용 | 없음(후속 구현) | 비노출·만료 경계와 전체 건수 테스트 | 설계 확정·미구현·미검증 | 관리자도 일반 검색 우회 불가 |
| `검색-입력-01` | 저장값과 검색어 NFC | 기존 데이터 backfill·쓰기 정규화·DB CHECK·q 0..100 | 없음(후속 구현) | 저장/검색 NFC·NFD 조합·raw DB 거부·길이 | 설계 확정·미구현·미검증 | 빈 검색어는 공개 전체 |
| `검색-필터-01` | 상태·가격 필터 | AVAILABLE/SOLD allowlist·정수 가격 1..999,999,999,999·AND 결합 | 없음(후속 구현) | 잘못된 상태·가격·역전 범위 테스트 | 설계 확정·미구현·미검증 | 현재 상품 모델 경계와 일치 |
| `검색-정렬-01` | 허용 정렬과 결정적 동률 순서 | 최신/가격 오름/가격 내림 allowlist·ID 내림차순 tie-break | 없음(후속 구현) | 동률 반복 조회·임의 필드 거부 테스트 | 설계 확정·미구현·미검증 | 최신순이 기본 |
| `검색-페이지-01` | `1..500`의 20건 페이지 | 필터·정렬 뒤 제한된 OFFSET pagination·501 이상 사전 거부 | 없음(후속 구현) | 20/21건·500/501·매우 큰 페이지 테스트 | 설계 확정·미구현·미검증 | 500 이내 마지막 이후는 빈 목록 |
| `관리-최소권한-01` | 일반 작업 권한과 meta-scope 예외 | staff+codename+`AdminScopeGrant`, scope는 superuser+직접 `moderation.manage_admin_scope` | 없음(후속 구현) | 일반 grant·자동 우회·bootstrap 역할/0명 조건·advisory lock 병렬 실행 | 설계 확정·미구현·미검증 | scope만 대상 grant 예외 |
| `관리-범위-01` | 대상별 기본 거부와 최소 공개 | USER/PRODUCT FK 하나·grant version·302/403/404·세션 무효화 | 없음(후속 구현) | 무대상/양대상·활성 중복·범위·stale revoke | 설계 확정·미구현·미검증 | 민감 정보·잔액·원장 제외 |
| `관리-재인증-01` | 제재·scope 변경 공통 보호 | UTC 300초·NFC 10..500 reason·CSRF·staff/grant version | 없음(후속 구현) | 시간·사유·stale·자기 변경·bootstrap | 설계 확정·미구현·미검증 | 모든 관리 상태 변경 |
| `관리-가역성-01` | 7일 제재와 단일 조기 해제 | DB 시각 경계·원본 불변·별도 `SanctionRelease`·만료 뒤 409 충돌 감사 | 없음(후속 구현) | 병렬 적용/해제·만료 직전/정확/직후·해제 응답·기록 수 | 설계 확정·미구현·미검증 | 자연 만료 자체는 해제 기록 없음 |
| `관리-감사-01` | 추가 전용·민감값 없는 감사 | 업무와 단일 트랜잭션·SELECT/INSERT 전용 역할·DB trigger·실패 503 | 없음(후속 구현) | 성공/거부/충돌 1건·INSERT 실패 0건·변경 거부 | 설계 확정·미구현·미검증 | grant 변경도 감사 |
| `관리-중복-01` | 중복 제재·해제의 상태 안전성 | 활성 제재 단일성·기존 결과 반환·만료 뒤 `SanctionRelease` 금지 | 없음(후속 구현) | 순차/병렬 중복 적용·반복 해제·만료 뒤 해제 409 테스트 | 설계 확정·미구현·미검증 | 기간 연장과 성공 감사 중복 금지 |

2차 표의 `예정 검증`은 테스트 계약일 뿐 실행 근거가 아닙니다. 후속 구현에서 실제 파일, 명령, 결과를 확인한 뒤에만 구현·테스트 열과 상태를 갱신합니다.
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
## 추적표 갱신 규칙

1. 파일이 생겼다는 이유만으로 상태를 `통과`로 바꾸지 않습니다.
2. 현재 저장소에 반영된 코드와 실제 테스트 결과를 기준으로 갱신합니다.
3. 테스트 근거에는 명령, 결과, 대상 코드 상태를 함께 기록합니다.
4. 요구사항과 코드가 다르면 차이를 비고에 남기고 구현 또는 문서를 수정합니다.
