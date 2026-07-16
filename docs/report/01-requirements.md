# 01 — Requirements analysis

## Scope and gate

Cycle 1 covers username/password membership, profile self-service, one-image products, authenticated global and direct chat, user/product reports, and seven-day reversible moderation. Cycle 2 capabilities are outside this design packet and MUST remain absent until their later gate opens.

Only username and password are collected. Email, phone, address, payment data, password recovery, token/CORS APIs, permanent moderation deletion, and Redis persistence are out of scope.

This document closes requirements ambiguity only. Every Cycle 1 feature remains unimplemented until its feature gate and tests pass.

## Actors and preconditions

| Actor | Preconditions | Permitted boundary |
|---|---|---|
| Anonymous visitor | Valid Host; no authenticated session | Registration, login, public visible product list/detail, health liveness |
| Active member | Valid same-origin session and CSRF for unsafe HTTP | Own profile/password, own products, chat rooms in which they participate, reports |
| Product owner | Active member and product owner | Create/update own product and inspect its moderation status |
| Moderator service | Database transaction and canonical policy services | Consume qualifying reports and create reversible actions/audit records |
| Operator | Deployment authority, not application content authority | Read readiness/liveness; operate PostgreSQL/Redis without bypassing policy |

A dormant user is not an active member. A hidden product is not publicly visible even when its stored product row is otherwise active.

## Acceptance criteria

### Identity and authentication

- **AC-C1-ID-001 — Canonical username.** Given a proposed username, when registration validates it, then trim and lowercase produce one ASCII canonical value matching `^[a-z0-9_]{4,30}$`, and the database rejects canonical duplicates.
- **AC-C1-ID-002 — Password safety.** Given a proposed password, when registration or password change validates it, then 12–128 Unicode code points, Django similarity/common/numeric/minimum validators, and NUL rejection all apply; plaintext and derived hashes never enter logs.
- **AC-C1-AUTH-001 — Generic throttled login.** Given known or unknown credentials, when authentication fails, then the response does not disclose account existence; account and keyed-IP limits are enforced atomically at their exact boundaries.
- **AC-C1-PROFILE-001 — Profile self-service.** Given an active authenticated member, when profile data or password is changed, then only the member's own allowed fields change; password change rotates the session and does not expose credentials.

### Catalog

- **AC-C1-CAT-001 — Product ownership.** Given an active member, when creating or changing a product, then ownership is server-derived and only the owner can mutate the product.
- **AC-C1-CAT-002 — Safe single image.** Given one JPEG, PNG, or WebP image no larger than 5 MiB or 4096×4096, when uploaded, then full decode succeeds, a new safe representation strips metadata, a generated non-executable name is used, and SVG/polyglot/decompression/path inputs fail closed.
- **AC-C1-CAT-003 — Effective visibility.** Given a product, when list/detail/link resolution runs, then the canonical database-time visibility service decides exposure; active hiding returns public not-found without deleting content.

### Chat

- **AC-C1-CHAT-001 — Authorized rooms.** Given an authenticated active member, when opening HTTP history or a WebSocket, then global-chat membership or both direct-chat participants are checked server-side; room identifiers never grant access.
- **AC-C1-CHAT-002 — Valid bounded text.** Given a chat submission, when validated, then trimmed UTF-8 content is 1–2000 bytes, NUL and C0 controls other than newline are rejected, stored text remains text, and output is escaped.
- **AC-C1-CHAT-003 — Durable acceptance.** Given an authorized rate-compliant message with UUIDv4 client ID, when its PostgreSQL transaction commits, then and only then it is accepted and acknowledged with its stable server ID.
- **AC-C1-CHAT-004 — Idempotent replay.** Given `(room, sender, client_message_id)`, when an identical payload is retried, then the prior accepted result is returned without another row or fan-out; a different payload receives conflict.
- **AC-C1-CHAT-005 — Honest degradation.** Given a committed message, when Redis publish fails, then acceptance is retained, the ACK reports `delivery=degraded`, and clients resynchronize history after their last server cursor. Redis failure never rewrites history.

### Reporting and moderation

- **AC-C1-MOD-001 — Valid reports.** Given an active account at least seven days old, when reporting a non-self target with an allowed context, then lifetime reporter-target uniqueness is enforced and inactive/self/under-age/duplicate reports fail.
- **AC-C1-MOD-002 — Context thresholds.** Given independent unconsumed reports, when a product reaches five reporters or a user reaches reports in two distinct allowed contexts, then exactly one seven-day reversible action and one audit event are created atomically.
- **AC-C1-MOD-003 — No report reuse.** Given reports consumed by an action, when another threshold is evaluated, then those reports cannot extend, duplicate, or create another action. After expiry, only new unconsumed reports qualify.
- **AC-C1-MOD-004 — Database-time expiry.** Given an action whose `expires_at` is at or before database time, when any entrypoint checks status, then it is ineffective immediately without a scheduler or destructive update.
- **AC-C1-MOD-005 — Dormancy transition.** Given a newly effective user action, when committed, then `auth_epoch` increments; the next HTTP request flushes the session and denies access, and each socket is notified and closed with 4403 or closes with 4403 on its next frame even if Redis is unavailable.

## Policy oracle and executable Test-ID contracts

All limits are inclusive at the accepted edge. “DB time” means the time obtained inside the authoritative PostgreSQL operation, not application-host time. Each listed Test-ID is a mandatory Given/When/Then contract; feature implementation may add, but may not weaken, cases.

| Policy ID | Exact policy | Required Given/When/Then Test-IDs |
|---|---|---|
| `POL-ID-001` | Trim + lowercase; ASCII `^[a-z0-9_]{4,30}$`; canonical database uniqueness | `T-ID-001`: Given `Ab_c`, when normalized, then `ab_c`; `T-ID-002`: Given case collision, Unicode, whitespace, 3 or 31 chars, when persisted, then reject with no row |
| `POL-PW-001` | 12–128 code points; Django similarity/common/numeric/minimum checks; NUL rejected; no password/hash logging | `T-PW-001`: Given valid boundary lengths 12/128, then accept; `T-PW-002`: Given 11/129, common, numeric, similar, or NUL input, then reject and sanitized logs contain none of it |
| `POL-AUTH-001` | Per-account 5 failures/15 min → 15 min cooldown; keyed-HMAC IP 20/15 min → 30 min; generic result; success resets account only | `T-AUTH-001`: Given 4/5/expiry attempts, then only the fifth enters cooldown; `T-AUTH-002`: Given 19/20 and parallel attempts, then twentieth atomically enters IP cooldown; `T-AUTH-003`: Given known/unknown users, then equivalent response shape/timing class; `T-AUTH-004`: Given success, then account counter resets and IP counter does not |
| `POL-CHAT-001` | Trimmed UTF-8 1–2000 bytes; NUL/C0 except newline rejected; escape on output | `T-CHAT-001`: Given multibyte payloads of 2000/2001 bytes, then accept/reject respectively; `T-CHAT-002`: Given blank/NUL/C0/script text, then invalid controls reject and script is rendered as text |
| `POL-CHAT-002` | Per-user 10/10 s burst and 60/60 s; per-connection 10/10 s; PostgreSQL-authoritative; reject without storing and include bounded retry-after | `T-CHAT-003`: Given 10/11 and 60/61 sends, then only excess rejects with no row; `T-CHAT-004`: Given multiple sockets, then aggregate user limit still holds; `T-CHAT-005`: Given concurrent boundary sends, then committed accepted count never exceeds the limit |
| `POL-CHAT-003` | UUIDv4; unique room/sender/client ID; commit-before-ACK; replay same result/no republish; mismatch conflict; degraded cursor sync | `T-CHAT-006`: Given publish fault after commit, then ACK is accepted/degraded and history contains one row; `T-CHAT-007`: Given ACK loss and identical retry, then same server ID, one row, one publish attempt; `T-CHAT-008`: Given mismatched replay, then conflict; `T-CHAT-009`: Given reconnect at cursor N, then ordered history converges with no gaps/duplicates |
| `POL-MOD-001` | Product context `PRODUCT`; user contexts `PROFILE`, `PRODUCT_INTERACTION`, `GLOBAL_CHAT`, `DIRECT_CHAT`; lifetime reporter-target unique; no self, under-seven-day, or inactive reporter; thresholds product=5 reporters, user=2 distinct contexts | `T-MOD-001`: Given invalid enum/self/young/inactive/duplicate, then reject; `T-MOD-002`: Given 4/5/6 independent product reports, then action count is 0/1/1; `T-MOD-003`: Given one/two distinct user contexts, then action count is 0/1 |
| `POL-MOD-002` | Action lasts seven days; no overlapping extension/duplicate; reports consumed once; only post-expiry new reports qualify | `T-MOD-004`: Given simultaneous threshold-crossing transactions, then exactly one action/audit and each report consumed at most once; `T-MOD-005`: Given active action and more reports, then no extension; `T-MOD-006`: Given exact expiry and new reports, then old reports remain consumed and one new action may form |
| `POL-STATUS-001` | `effective_user_status(db_now)` is the sole authority for HTTP, WebSocket, chat, product mutation, report, and moderation paths | `T-STATUS-001`: Given one user/time, then every invocation cell returns the same state; `T-STATUS-002`: Given transition, then auth epoch/session/socket semantics hold; `T-STATUS-003`: Given Redis outage, then the next request/frame still denies; `T-STATUS-004`: Given exact expiry, then old session stays invalid and a new login may succeed |
| `POL-STATUS-002` | Canonical effective product visibility; hidden public references are 404; owner can inspect status; expiry restores visibility; no physical deletion | `T-STATUS-005`: Given list/detail/chat-link and the same DB time, then all hide; `T-STATUS-006`: Given owner status view, then status is visible without exposing publicly; `T-STATUS-007`: Given exact expiry, then all public query paths restore visibility |

## Trace and G2 exit

| Acceptance family | Policies | Required test families |
|---|---|---|
| Identity/auth/profile | `POL-ID-001`, `POL-PW-001`, `POL-AUTH-001`, `POL-STATUS-001` | `T-ID-*`, `T-PW-*`, `T-AUTH-*`, `T-STATUS-001..004` |
| Catalog | `POL-STATUS-001`, `POL-STATUS-002` | catalog ownership/image tests plus `T-STATUS-*` |
| Chat | `POL-CHAT-001..003`, `POL-STATUS-001` | `T-CHAT-*`, `T-STATUS-001..004` |
| Moderation | `POL-MOD-001..002`, `POL-STATUS-001..002` | `T-MOD-*`, `T-STATUS-*` |

G2 passes only when every Cycle 1 policy has an approved Given/When/Then Test-ID, trust and failure semantics are unambiguous, and independent review records zero open Critical or High design findings. Skeleton tests demonstrate contract placement, not feature completion.
