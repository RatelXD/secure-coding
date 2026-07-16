# 02 — System design

## Architecture boundary

Cycle 1 is a same-origin Django 5.2 LTS ASGI application using server-rendered templates and vanilla JavaScript. HTTP and WebSocket traffic enter one origin and one Host allowlist. PostgreSQL is the only persistent authority. Redis provides disposable channel fan-out and rate-support hints; it is never history, a ledger, or a status authority.

The executable G2 deliverable is configuration, routing, model/service interfaces, migrations required by those interfaces, and focused architecture tests. UI and feature behavior remain outside the skeleton.

## Assets and trust boundaries

| Boundary | Untrusted side | Trusted side | Required controls |
|---|---|---|---|
| B1 Browser → ingress | Headers, cookies, form/body, file bytes, WS frames | Validated same-origin request | Host allowlist, TLS at ingress, Secure/HttpOnly/SameSite cookies, CSRF on unsafe HTTP, Origin on WS, size/time limits |
| B2 ASGI → policy/service | Route identifiers and actor claims | Canonical actor/object authorization | Server-derived ownership, room participation, canonical status invocation, generic denial |
| B3 Service → PostgreSQL | Concurrent commands and host clock | Committed durable state and DB time | Transactions, unique/check constraints, row locks where required, commit-before-success |
| B4 Service → Redis | Ephemeral publish/rate hints | Best-effort live fan-out | No durable facts; bounded timeout; failure maps to degraded delivery, never rollback of committed history |
| B5 Application → media | Uploaded hostile bytes | Re-encoded non-executable image | Full decode, dimension/size/MIME checks, metadata removal, generated name, separate media serving |
| B6 Operations → health | Network caller | Minimal liveness/readiness result | No secrets/config details; liveness process-only; readiness requires PostgreSQL, reports Redis degradation separately |

Protected assets are credentials, authenticated sessions/CSRF tokens, usernames/profile content, products/media, room membership and message history, reports, moderation actions/audits, and availability/rate budgets. Raw passwords, raw IP addresses, message bodies, cookies, and private operational data must not be logged.

See [the trust-flow diagram](../diagrams/g2-trust-flow.mmd) and [Cycle 1 ERD](../diagrams/g2-cycle1-erd.mmd).

## Entrypoints and uniform denial

| Entrypoint | Authentication | Authorization/status checks | Failure surface |
|---|---|---|---|
| Public HTTP GET | Optional session | Effective product visibility for object/list references | 404 for hidden or inaccessible product; never disclose existence |
| Authenticated HTTP GET | Valid session | `effective_user_status`; object owner/participant as applicable | Flush invalid epoch; 403 for authenticated policy denial, 404 where object concealment is required |
| Unsafe HTTP POST | Valid session + same-origin CSRF | User status, ownership/participant, input/rate policy inside service boundary | 400 malformed, 403 auth/policy/CSRF, 404 concealed object, 409 idempotency conflict, 429 throttled; no partial commit |
| WebSocket handshake | Valid session, allowed Host and Origin | User status and room participation before accept | Reject handshake with HTTP 403; do not reveal room existence |
| WebSocket frame | Accepted socket | Recheck auth epoch/status, participation, size/rate, command schema before durable command | Structured error for recoverable 400/409/429 class; close 4400 malformed protocol, 4401 unauthenticated, 4403 forbidden/dormant, 4408 policy timeout/rate abuse, 1011 internal failure |
| Health `/health/live/` | No content authority | Process event loop only | 200 `live`; 503 only when process cannot serve |
| Readiness `/health/ready/` | Restricted/minimal output | PostgreSQL required; Redis observed separately | 200 when PostgreSQL authoritative path works, including `redis=degraded`; 503 when PostgreSQL unavailable |

Error responses use stable codes and correlation IDs but no username, target existence, SQL/backend detail, stack trace, or submitted body. HTTP responses and WS errors describe whether a command was accepted; connection transport failure alone never implies acceptance.

## Canonical status invocation matrix

No view, consumer, query manager, or mutation service may inspect a stored status flag as its final decision. It must invoke the named service with database time in the authoritative operation.

| Operation | User service | Product service | Timing and required effect |
|---|---:|---:|---|
| Session-authenticated HTTP middleware | REQUIRED | — | Before protected view; epoch mismatch/dormancy flushes session and returns 403 |
| WebSocket connect | REQUIRED | — | Before `accept`; reject 403 when ineffective |
| Every WebSocket command | REQUIRED | When product linked | Before command transaction; close 4403 for dormant user |
| Chat history query/send | REQUIRED | When resolving product link | In query/send service; hidden link resolves as not-found |
| Product create/update/delete-like action | REQUIRED | REQUIRED for existing product | In mutation transaction; only effective owner and visible policy state permit mutation |
| Public product list/detail | — | REQUIRED | Query manager applies DB-time predicate; no post-filtering leak |
| Report creation | REQUIRED for reporter and user target | REQUIRED for product target | In report transaction before uniqueness/threshold calculation |
| Moderation threshold/action | REQUIRED for user target | REQUIRED for product target | One DB transaction; action `expires_at` and DB time determine effect |
| Owner moderation-status view | REQUIRED | REQUIRED | Owner sees status metadata; public representations remain 404 |
| Reconciliation job | REQUIRED | REQUIRED | Hint/audit repair only; never creates authority different from service result |

An action becomes effective on commit. User actions increment `auth_epoch` in the same transaction. Fan-out notification is best effort; middleware and next-frame checks independently enforce the committed transition. Expiry is computed, not scheduled: at `db_now >= expires_at`, the action is ineffective. Existing sessions invalidated by an epoch change are not resurrected; a fresh login is required.

## Chat command and failure protocol

The client supplies UUIDv4 `client_message_id`. The server canonicalizes and validates text, then enters one PostgreSQL transaction:

1. Re-evaluate effective user status, room participation, and database-authoritative rate budget.
2. Insert a message protected by unique `(room_id, sender_id, client_message_id)`.
3. If that key exists, compare the canonical payload: identical returns the stored result; different returns conflict.
4. Commit. Commit is the only acceptance point.
5. Attempt Redis publish once for a new row. Never publish a replay.
6. ACK the sender with `{status: "accepted", delivery: "live"|"degraded", server_id, client_message_id, cursor}`.

| Failure point | Stored? | Publish? | Sender result | Recovery |
|---|---:|---:|---|---|
| Auth/status/participation/input/rate denial | No | No | Rejected 400/403/404/429 class | Correct request or wait |
| Database insert/commit failure | No | No | Not accepted; retriable internal/unavailable result | Retry same client ID; server resolves actual DB state first |
| Commit succeeds, Redis publish succeeds | Yes once | Once | Accepted/live | Receiver server-ID dedupe |
| Commit succeeds, Redis publish fails | Yes once | Attempted once | Accepted/degraded | Cursor history sync |
| Commit succeeds, ACK is lost | Yes once | Once | Client sees ambiguity | Identical retry returns same server ID without republish |
| Retry payload differs | Original remains | No new publish | 409 conflict | Generate a new client ID for a new command |

History is ordered by a stable server cursor with deterministic tie-breaking. Reconnect, tab visibility return, degraded ACK, or cursor gap triggers fetch-after-cursor until exhausted. Clients deduplicate by server ID. The system does not promise automatic live rebroadcast after a Redis outage.

See [chat acceptance sequence](../diagrams/g2-chat-acceptance.mmd).

## Moderation state machine

Reports are append-only facts with lifetime reporter-target uniqueness. A threshold transaction locks/rechecks eligible unconsumed reports and the active-action state. It creates at most one immutable seven-day action, marks exactly its contributing reports consumed, increments user `auth_epoch` when applicable, and appends one audit event. Additional reports never extend an active action.

States are derived:

- `VISIBLE/ACTIVE`: no unexpired action at DB time.
- `HIDDEN/DORMANT`: one action with `starts_at <= db_now < expires_at`.
- `EXPIRED`: historical action remains, but effective state returns to visible/active.

At exact expiry, new unconsumed reports may form a later action; consumed reports never qualify again. Concurrent threshold and expiry transactions must serialize or retry so they cannot overlap actions or consume one report twice. Permanent deletion and scheduler-controlled reversal are prohibited.

See [moderation state diagram](../diagrams/g2-moderation-state.mmd).

## Skeleton data contracts

- `accounts.User`: canonical username, password hash through Django auth, profile field boundary, monotonic `auth_epoch`, timestamps.
- `catalog.Product`: immutable owner relation, bounded content and image reference; effective visibility comes from moderation policy, not a duplicated Boolean authority.
- `chat.Room` and participation relation: global/direct kind with database constraints; direct access derives from participation.
- `chat.ChatMessage`: room, sender, UUIDv4 client ID, canonical text, stable server ID/cursor, committed timestamp, unique idempotency key.
- `moderation.AbuseReport`: reporter, typed target/context, created/consumed relation, lifetime reporter-target uniqueness.
- `moderation.ModerationAction`: typed target, immutable start/expiry, contributing reports; non-overlap enforced transactionally.
- `moderation.AuditEvent`: append-only action creation/expiry observation metadata without raw report or chat bodies.

Cross-target integrity that cannot be represented by a simple database constraint is enforced in a single canonical service and covered by transaction/concurrency tests. Redis contains none of these durable records.

## Security defaults and deployment

Production configuration fails closed when secret key, PostgreSQL authority, allowed hosts, trusted same-origin HTTPS origin, or secure proxy settings are absent or malformed. Debug is off. Cookies are Secure, HttpOnly where applicable, and SameSite=Lax; CSRF uses Secure and trusted-origin allowlisting; HSTS and secure redirect are enabled behind an explicitly trusted single proxy. Forwarded host/proto headers are ignored unless that proxy contract is configured.

The ASGI router applies allowed-host/origin and session authentication controls to WebSockets before application consumers. No permissive CORS layer or token API exists. PostgreSQL readiness gates traffic. Redis outage must be observable but must not silently become persistence or make liveness fail.

Migrations are forward/backward reviewed before feature rollout. Rollback must not drop accepted history, reports, actions, or audit facts; destructive schema changes require a later explicit migration plan. Backups cover PostgreSQL and validated media, not Redis.

## G2 review checklist

- Every policy and Test-ID in [requirements](01-requirements.md) has one canonical implementation boundary.
- HTTP and WebSocket authentication, Host/Origin, denial, close-code, and acceptance semantics are explicit.
- PostgreSQL is the only durable authority; Redis fault behavior is honest and recoverable.
- Status and expiry calls cover every Cycle 1 entrypoint without raw-status bypass.
- Race controls exist for idempotency, rate boundaries, report consumption, and action overlap.
- No Cycle 2 package, route, model, migration, permission, or design contract is introduced.
- Open Critical and High findings are zero before G2 can pass.
