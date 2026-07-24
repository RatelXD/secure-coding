# Phase 6R 확장 재합의 실행 계약

이 문서는 Phase 6R 이후 제품 PR이 따라야 할 실행 계약입니다. 현재 C1 동작과 승인된 C2 `이체-*`, `검색-*`, `관리-*` 정책은 약화하지 않습니다. 관련 권위·외래 키·잠금·사건·보존·호환성 코드는 main에 구현되어 있으며, 세부 경계 검증이 끝나지 않은 항목은 `PASS` gate로 올리지 않습니다. 현재 기준 main은 `1467092302f789f802114f62d4d3dcfcf1b13be8`입니다.

## 단일 권위와 FK 계약

| 엔터티/투영 | 영속 권위와 소유자 | 필수 FK·제약 | 읽기 투영 | feature gate |
|---|---|---|---|---|
| Product | catalog/Product | owner→User(PROTECT), category→Category(PROTECT), region→Region(PROTECT, nullable legacy) | `effective_product_state(product, db_now)` | `CATALOG_V2` |
| ProductImage | catalog/ProductImage | product→Product(CASCADE), 순서 0..3, 상품별 순서 UNIQUE | 0~4장 순서 gallery | `CATALOG_V2` |
| Trade | trades/Trade | product→Product(PROTECT), seller→User(PROTECT, NOT NULL), buyer→User(PROTECT; `LEGACY_SOLD` COMPLETED일 때만 NULL), `CHECK (((kind = 'LEGACY_SOLD' AND status = 'COMPLETED' AND buyer_id IS NULL) OR (kind <> 'LEGACY_SOLD' AND buyer_id IS NOT NULL)) IS TRUE)`, 상품별 non-cancelled RESERVED/COMPLETED 최대 1 | 상품 상태·완료 수·후기 자격 | `TRADE_AUTHORITY` |
| ProductConversation | chat/ProductConversation | room→Room(OneToOne, PROTECT), product/seller/buyer→각 권위(PROTECT), 조합 UNIQUE | 기존 Room/ChatMessage history | `PRODUCT_CHAT` |
| Favorite | catalog/Favorite | user→User(CASCADE), product→Product(CASCADE), 조합 UNIQUE | 본인 관심 목록·공개 관심 수 | `ENGAGEMENT` |
| ProductView | catalog/ProductView | product→Product(CASCADE), viewer session hash+UTC date 조합 UNIQUE | 공개 조회 수 | `ENGAGEMENT` |
| Presence | Redis TTL, PostgreSQL 사용자 상태가 우선 | user/room 식별자는 기존 권위 검증 후 TTL에 기록 | 허용된 1:1 상대의 online/offline | `PRESENCE` |
| Notification | notifications/Notification | recipient→User(CASCADE), `(recipient,event_key)` UNIQUE, DB trigger가 `expires_at = created_at + INTERVAL '90 days'`로 설정 | 본인 알림함 | `NOTIFICATIONS` |
| MockAccount/ledger | transfers의 PostgreSQL account/journal/entry | account→User(PROTECT), journal당 immutable entry 2개·합계 0 | 잔액·원장·대사 상태 | `TRANSFERS` |
| Review | trades/Review | trade→Trade(PROTECT), author/subject→User(PROTECT), 방향별 UNIQUE | 공개 후기·평균 | `REVIEWS` |
| ReviewVisibilityAction | trades/ReviewVisibilityAction | review/actor→권위(PROTECT), append-only | 최신 유효 HIDE/RESTORE | `REVIEWS` |
| AbuseReport/AdminScopeGrant | moderation 권위 | USER/PRODUCT/REVIEW FK 중 정확히 하나, 활성 scope 중복 금지 | 신고·관리 범위 | `REVIEW_MODERATION` |
| AccountWithdrawal | accounts의 User 상태+RevocationTask | user→User(OneToOne, PROTECT), task idempotency UNIQUE | tombstone·세션 폐기 상태 | 준비 `WITHDRAWAL_PREP`, 활성 `WITHDRAWAL` |

Product lifecycle의 새 write API는 `TradeService` 하나뿐입니다. cutover 뒤 `Product.sale_state`는 DB trigger가 UPDATE를 거부하는 동결 호환 필드이며 어떤 projector도 권위로 읽지 않습니다. ProductConversation은 별도 메시지 저장소를 만들지 않고 기존 RoomParticipant/ChatMessage send·ACK·history·rate·Origin 경로를 사용합니다. PostgreSQL이 모든 영속 상태의 기준이고 Redis는 복구 가능한 fan-out/presence에만 사용합니다.

## 잠금 순서 계약

| 순번 | 잠금 | 적용 작업 | 획득 뒤 재검사 |
|---:|---|---|---|
| 1 | 관련 User PK 오름차순 | reserve/cancel/complete, 상품 대화, 후기 관리, withdrawal | 활성·행위자·당사자 권한 |
| 2 | Product PK | lifecycle, room 생성/쓰기, hide, withdrawal | 공개·보관·effective state |
| 3 | non-cancelled Trade row 또는 상품 advisory key | reserve/cancel/complete, withdrawal | 상대·terminal·단일 active 제약 |
| 4 | ProductConversation PK | room 생성/메시지 accept | product/seller/buyer 일치 |
| 5 | Room PK | 메시지 accept, complete/hide barrier | participant·쓰기 가능 상태 |
| 6 | MockAccount PK 오름차순 | withdrawal 잔액 확인 | 계정 open·balance=0.00 |
| 7 | 사건 결과 row | 멱등 응답·Notification·revocation | event key·저장 결과 |

승인된 이체 경로의 순서는 `TransferSafetyState shared lock → idempotency row → MockAccount PK 오름차순`으로 유지하며 User row를 잠그지 않습니다. account lock 안에서 DB 사용자 상태를 다시 읽습니다. withdrawal은 User/Product/Trade 뒤 MockAccount를 잡으므로 이체와 순환 대기가 없습니다. complete/hide와 message accept barrier에서는 상태 변경 뒤 늦은 메시지 commit을 허용하지 않습니다.

## 도메인 사건과 보존 계약

| 사건 | 결정적 event key | 생성 결과 | 보존·삭제 계약 |
|---|---|---|---|
| 상품 메시지 | `chat.message:<chat_message_id>` | 수신자 Notification 최대 1 | ChatMessage와 완료/비노출 room history 물리 삭제 금지 |
| 예약/취소/완료 | `trade.<event>:<trade_id>:<version>` | 당사자 Notification 최대 1 | 취소·완료 Trade 이력 영구 보존 |
| 후기 작성 | `review.created:<review_id>` | 피후기자 Notification 최대 1 | 본문·평점·작성자·trade 수정/삭제 금지 |
| 후기 HIDE/RESTORE | `review.visibility:<action_id>` | action+AdminAudit 같은 transaction | action/audit append-only, 반복 요청은 새 row 0 |
| 신고·제재 결과 | `moderation.<event>:<audit_id>` | 신고자 Notification 최대 1 | 신고·제재·감사 보존, 감사 UPDATE/DELETE 금지 |
| 탈퇴 | `account.withdrawn:<user_id>:<auth_epoch>` | RevocationTask 최대 1 | username 내부 tombstone·거래·채팅·후기·신고·감사 보존; Favorite/Notification 삭제 |
| 데모 bootstrap | `demo.catalog:<manifest_version>` | owner/17 products/media 멱등 설치 | manifest checksum과 소유 key 보존 |

Notification 생성 migration은 DB trigger가 DB time으로 `created_at`와 `expires_at = created_at + INTERVAL '90 days'`를 함께 설정하게 하며, 기존 row도 DB interval로 backfill한 뒤 NULL 0건과 각 row의 정확한 90일 차이를 검증하고 `expires_at`를 NOT NULL로 cutover합니다. migration test는 fake DB clock에서 생성 시각과 정확히 90일 뒤 만료값을 검증하고, purger 경계는 `expires_at < DB now()`인 row만 UTC 일일 삭제합니다(동일 시각 row는 보존). batch는 PK cursor 500개, singleton advisory lock, bounded retry를 사용합니다. 마지막 성공 뒤 expired row가 24시간을 넘거나 heartbeat가 26시간 없으면 release blocker입니다. test 환경은 scheduler 기동을 거부하고 fake DB clock으로 command를 직접 검증합니다. Redis TTL은 보존 근거가 아니며 탈퇴한 사용자는 TTL이 남아도 offline으로 투영합니다.

## 마이그레이션·호환성·되돌리기 계약

| 대상 | expand/copy/backfill | validate/cutover | 호환성·rollback/비가역 경계 |
|---|---|---|---|
| ProductImage | 기존 정제 bytes를 `product-images/migrated/<product_id>/<sha256>.<ext>` 별도 key로 복사, source/destination checksum 동일 | 상품별 0~4·순서 UNIQUE 확인 뒤 gallery read/write gate | legacy key 동결 보존. 첫 gallery write 뒤 old app rollback 금지, G10까지 GC 금지 |
| Product category | nullable `category_id`와 canonical Category `기타`를 먼저 설치하고, backfill 시작 전 기존 Product 수 N을 고정하여 모든 기존 Product의 category를 결정적으로 `기타`로 설정 | `category_id IS NULL` 0건, `기타`를 가리키는 기존 Product 수 N, FK 위반 0건을 대조한 뒤 mandatory Category FK | mandatory FK 전 rollback은 gate OFF와 nullable application path 복구만 허용하고 이미 쓴 `기타` 참조와 Category row는 보존; cutover 뒤 forward fix만 허용 |
| legacy SOLD | SOLD마다 seller NOT NULL, buyer=NULL `LEGACY_SOLD` COMPLETED Trade 1개, completed_at=기존 updated_at; `CHECK (((kind = 'LEGACY_SOLD' AND status = 'COMPLETED' AND buyer_id IS NULL) OR (kind <> 'LEGACY_SOLD' AND buyer_id IS NOT NULL)) IS TRUE)`로 buyer NULL을 그 typed 상태에만 결박 | AVAILABLE/Trade 없음·SOLD/typed Trade count 전수 대조 뒤 sale_state trigger | `sale_state` write/read authority 복귀 금지; forward fix만 허용 |
| Notification expiry | DB trigger와 nullable `expires_at`를 expand하고 DB time의 `created_at + INTERVAL '90 days'`로 기존 row를 backfill | fake DB clock migration test에서 생성값과 90일 만료값, purger의 `< DB now()` 경계를 확인한 뒤 `expires_at` NOT NULL | NOT NULL cutover 전에는 trigger와 backfill을 유지한 채 gate OFF로 rollback 가능; cutover 뒤 만료값 추정·application clock fallback 금지 |
| legacy region | NULL은 `LEGACY_UNSET`, region=NULL로 명시 | 특정 region filter에서 제외, filter 생략 시 포함 | buyer/지역 추정 금지; legacy row 보존 |
| ProductConversation | Room kind PRODUCT와 metadata만 확장 | 기존 GLOBAL/DIRECT Room/participant/message ID·count·payload 동일성 확인 | 별도 message pipeline 금지, 기존 history로 rollback 가능한 동안 gate OFF |
| Withdrawal | fields/tombstone/session index/revocation task만 준비, URL/navigation hard OFF | 모든 authority table·active Trade 0·balance 0.00을 잠금 안 확인한 뒤 별도 PR에서 활성 | 첫 성공 뒤 이전 SHA rollback 금지; route OFF+durable retry+forward fix |
| Review 신고 | target CHECK와 REVIEW scope를 expand | 무신고 hide 404/action 0, reported action/audit 원자성 확인 | Review/action/audit mutable 경로 금지 |
| Notification purge | command/heartbeat/service를 먼저 설치 | scheduler singleton·재시작·24h SLO 검증 뒤 필수 service | scheduler 제거로 rollback 금지; 실패는 남은 cursor 재개 |
| Demo catalog | test/prod hard OFF, dev migrate 뒤 bootstrap | 17개 row/media/checksum과 재실행 변화 0 확인 | checksum 다른 final key overwrite 금지, 실패 시 전체 bootstrap 실패 |

모든 데이터 변경은 `expand → copy/backfill → validate → cutover` 순서를 지킵니다. DB와 media backup은 같은 snapshot ID와 restore proof를 가져야 합니다. mixed old/new write, missing authority를 false/zero/empty로 처리하는 fallback, legacy/ProductImage 공유 key는 병합 차단 사유입니다.

## Test-ID와 한국어 추적 스키마

각 제품 PR은 다음 필드를 한 행에 모두 기록합니다. 빈 값과 실행하지 않은 `PASS`는 허용하지 않습니다.

| 필드 | 형식과 의미 |
|---|---|
| `Policy-ID` | 기존 C1/C2 또는 신규 한국어 정책 ID. 예: `검색-공개-01`, `G6R-권위-01` |
| `Design/Threat-ID` | ADR·위협 식별자. 예: `DEC-07`, `VULN-11` |
| `Migration-ID` | migration 이름 또는 `해당 없음(근거)` |
| `Code owner/path` | 단일 권위 구현 owner와 저장소 상대 경로 |
| `Test-ID` | `G<phase>-<DOMAIN>-<TYPE>-<NNN>`; 예: `G6R-GOV-TITLE-001` |
| 한국어 시나리오 | 행위자·경계값·선행 상태·실행 절차 |
| 한국어 기대값/실제값 | 상태 코드, row 수, 불변식, 실패 분류를 분리 기록 |
| 검증 환경 | 대상 SHA, migration leaf, Python/Node/uv/browser 버전, 시작·종료 UTC |
| 증거 | 명령, exit code, 비밀값 제거 artifact checksum |
| `PR/RC receipt` | PR 번호와 외부 immutable receipt ID; RC 전에는 `RC 전(사유)` |

필수 최소 Test-ID 묶음은 권위/FK `G6R-GOV-AUTH-001`, 잠금 순서 `G6R-GOV-LOCK-001`, 사건/보존 `G6R-GOV-RET-001`, 마이그레이션/호환성 `G6R-GOV-COMPAT-001`, 제목 parser `G6R-GOV-TITLE-001`, Stitch manifest `G6R-STITCH-MAP-001`, fork-safe CI `G6R-CI-FORK-001`, pinned browser/axe `G6R-TOOL-PIN-001`입니다. 이후 PR은 자기 기능의 positive·negative·경계·경합/장애 Test-ID와 관련 C1/C2 회귀 ID를 함께 기록합니다.

제목 검사는 `scripts/verify_pr_title.py`의 production parser 하나를 사용합니다. 계획된 정확한 18개 제목도 예외 allowlist가 아니라 같은 parser의 positive vector입니다. PR branch는 commit 1개이고 HEAD subject, PR title, squash된 main subject가 모두 같아야 합니다. parser는 NFC `<type>(<scope>): <본문>`, U+0020 단일 구분, 한글 token 1개 이상, 승인된 숫자/버전·ASCII token만 허용합니다.
