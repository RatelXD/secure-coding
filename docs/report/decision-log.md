# Decision log

Decisions are append-only. Each ADR records status, context/Why, drivers, alternatives, decision, What changed, consequences, follow-ups, and AC/Policy/Threat/Test/PR/release links.

| ADR | Decision | Status | Gate |
|---|---|---|---|
| ADR-1 | same-origin Django ASGI; PostgreSQL authority; Redis fan-out | accepted for G2 | G2 |
| ADR-2 | client UUID + DB-accepted ACK + degraded/history resync; no outbox | accepted for G2 | G2 |
| ADR-3 | canonical DB-time effective moderation/status policies | accepted for G2 | G2 |
| ADR-4 | locked authoritative mock balance + immutable double-entry journal | analysis prohibited before G5 | G6 |
| ADR-5 | scoped permissions + reauth/reason/version + append-only admin audit | analysis prohibited before G5 | G6 |

No ADR weakens the approved local scope, policy oracle, Critical/High zero, real G5 chain, G8a-before-formal order, or user-only G8b boundary.

## GOV-DEC-001 — Temporary documented self-review for G1

- Status: user-approved supersession on 2026-07-16.
- Context: the separate `RatelAI` GitHub integration could inspect PR #1 but could not submit an official review because GitHub returned `403 Resource not accessible by integration`.
- Decision: G1 no longer requires an independent GitHub account, GitHub `APPROVED` state, or `prevent_self_review=true`. For the governance bootstrap PR, the authenticated repository owner may record review using the exact public marker `G1-GOVERNANCE-BOOTSTRAP-SELF-REVIEW: APPROVED head=<current PR SHA>`.
- Retained gates: the marker must match the current head; strict exact Actions checks must pass; admins remain subject to branch protection; linear history is required; force-push/delete protection stays enabled; the release environment requires the owner as reviewer and keeps admin bypass disabled.
- Consequence: GitHub cannot provide reviewer independence for this stage. Confirmation bias is an explicitly accepted residual risk, partially mitigated by automated checks, current-head binding, the normal code-review tool, and rejection of edited or inexact review comments.
- Scope: this supersedes only the independent-review clauses of G1 and release-environment self-review. The bootstrap marker approves PR #1 governance bytes only; it does not declare G1 complete or relax trusted-workflow, provenance, credential handling, Critical/High zero, G5, G8a-before-formal, or user-only G8b gates.
- Follow-up: restore an independent reviewer and `prevent_self_review=true` after the GitHub integration receives working Pull requests write permission.

## GOV-DEC-002 — Default-branch-trusted G1 governance

- Status: user-approved self-review implementation, pending final trusted-context PR receipt on 2026-07-16.
- Context: PR #1 could only bootstrap a PR-controlled workflow. PR #2 added a `pull_request_target` transition so the default branch, rather than proposed PR bytes, defines the enforcement program.
- Decision: remove the temporary `pull_request` trigger and require the distinct `governance-trusted` context from GitHub Actions app 15368. The trusted workflow may check out exact PR bytes with credentials disabled, but it must execute only pinned actions and inline logic loaded from the default branch; repository-controlled scripts, dependencies, gitleaks configuration, and ignore files are not executed or trusted.
- Self-review receipt: the authenticated repository owner must post the exact unedited marker `G1-GOVERNANCE-SELF-REVIEW: APPROVED head=<current PR SHA>` after the unique exact-head trusted check succeeds.
- Consequence: author-controlled changes cannot redefine the required check during the same PR. Independent human review remains temporarily superseded, so owner confirmation bias remains accepted under GOV-DEC-001.
- Scope: this closes SEC-2026-005 only after the finalization PR is merged and branch protection still requires `governance-trusted`; deterministic renderer toolchain evidence and all later gates remain independent blockers.

## GOV-DEC-003 — Manual report processing and local-only assignment context

- Status: user-approved supersession on 2026-07-16.
- Context: generated Markdown/Mermaid-to-PDF output was treated as a deterministic G1/G8a artifact, but the user will process the submission report manually. Assignment-source correction material is operational input for planning, implementation, and verification rather than repository documentation.
- Decision: PDF generation, renderer publication, OCI inventory, and byte-identical PDF receipts are removed from G1 and G8a. The already implemented renderer remains an optional helper and must not block product work or release. Public G8a validates the exact-RC repository, Pages, and release package without a generated PDF requirement.
- Local context: assignment-source material belongs only in ignored `.gjc/context/` files read at agent startup. README, public report pages, PR text, Actions artifacts, Pages, releases, and product output must not reproduce it.
- Consequence: Team does not generate or handle the user's final report/submission artifact. User-manual report processing and LMS submission remain outside Team scope.
- Retained gates: trusted governance, credential handling, test/security gates, real G5 maintenance, exact-RC G8a, same-SHA formal promotion, and user-only G8b remain mandatory.
## ADR-1 — Same-origin Django ASGI with one durable authority

- Status: accepted for G2 on 2026-07-16.
- Context / Why: Cycle 1 needs HTTP, WebSocket, session, CSRF, authorization, chat history, and reversible moderation to share consistent trust and transaction boundaries. Multiple APIs or persistent systems would introduce policy drift and ambiguous authority.
- Drivers: small auditable surface, same-origin controls, transactional integrity, explicit outage behavior, and deployable local composition.
- Alternatives: a layered monolith remains an implementation organization option inside the same boundary; a SPA/token API, split services, permissive CORS, or Redis as a ledger are rejected. A synchronous-only deployment is rejected because authenticated live chat is required.
- Decision: use Django 5.2 LTS Templates/vanilla JavaScript under one ASGI application. PostgreSQL is the only persistent authority and supplies policy time. Redis is disposable fan-out/rate support. Session, Host, CSRF, Origin, ownership, participation, and canonical status checks apply at both HTTP and WebSocket boundaries.
- What changed: the baseline is now specified by trust boundaries, entrypoint/failure tables, a status invocation matrix, production fail-closed settings, and health/readiness semantics in the system design.
- Consequences: Redis loss may degrade live delivery but cannot lose accepted history or alter status. PostgreSQL loss makes readiness fail. No independent token/CORS API may be added without a superseding ADR.
- Follow-ups: feature PRs must prove route-level invocation and transaction tests. Later-cycle architecture is excluded from this decision.
- Links: `AC-C1-*`, `POL-STATUS-001/002`, `THR-C1-001..004`, `T-STATUS-*`, diagrams `g2-trust-flow` and `g2-cycle1-erd`.

## ADR-2 — Database-accepted chat with cursor resynchronization

- Status: accepted for G2 on 2026-07-16.
- Context / Why: database commit, Redis publish, and sender ACK cannot be atomic. Reporting publish failure as message failure after commit causes duplicate retries; publishing before commit can expose messages that never become history.
- Drivers: exactly one durable row per client command, honest acceptance semantics, deterministic retries, bounded Cycle 1 operations, and convergence after fan-out gaps.
- Alternatives: a transactional outbox offers eventual rebroadcast but adds a worker, duplicate consumption, cleanup, and recovery surface; it is not selected. Publish-first and rollback-on-publish-failure are invalid because they contradict PostgreSQL authority.
- Decision: require UUIDv4 and unique `(room, sender, client_message_id)`. Recheck permission, canonical status, and database-authoritative rate budget in the insert transaction. Commit is acceptance. Publish a new row once after commit. Identical retry returns the stable server result without republishing; mismatched retry conflicts. Redis failure returns accepted/degraded and triggers history fetch after the last stable server cursor.
- What changed: HTTP/WS failure semantics now distinguish rejected, not-accepted, accepted/live, accepted/degraded, and ambiguous client transport outcomes.
- Consequences: clients must deduplicate by server ID and resynchronize on reconnect, visibility return, degraded ACK, or gap. Redis outage messages are not automatically replayed live. Metrics distinguish accepted, degraded, rejected, and cursor convergence.
- Follow-ups: `T-CHAT-006..009` must fault commit, publish, and ACK independently; any stronger delivery requirement needs a superseding ADR and migration/recovery review.
- Links: `AC-C1-CHAT-001..005`, `POL-CHAT-001..003`, `THR-C1-005..007`, diagram `g2-chat-acceptance`.

## ADR-3 — Database-time reversible moderation authority

- Status: accepted for G2 on 2026-07-16.
- Context / Why: stored flags, host clocks, scheduled reversal, and per-entrypoint checks can disagree at sanction and expiry boundaries. Such drift could expose hidden products or leave dormant users active.
- Drivers: one status answer at one instant, reversible seven-day actions, race-safe report consumption, immediate expiry semantics, and enforcement during Redis outage.
- Alternatives: cron-reversed flags are not selected because scheduler delay becomes authorization drift. Permanent deletion and Redis-cached authority are rejected. Reconciliation is retained only as audit/hint repair.
- Decision: immutable action start/expiry plus PostgreSQL `db_now` feed canonical `effective_user_status` and `effective_product_visibility` services. Middleware, query managers, consumers, chat/product/report/moderation services, and owner status views invoke them. Action creation, report consumption, audit creation, and user `auth_epoch` increment are atomic. An existing session invalidated by epoch change never revives after expiry.
- What changed: the system design includes the exhaustive invocation matrix, exact-expiry behavior, socket 4403 fallback, and moderation state machine.
- Consequences: stored state alone is never authoritative; raw queryset bypasses are security defects. Expiry requires no scheduler. Historical actions/reports remain auditable and are never physically deleted by policy.
- Follow-ups: concurrency tests must prove one action/audit at threshold and no consumed-report reuse. Static/review checks must reject status bypasses.
- Links: `AC-C1-MOD-001..005`, `POL-MOD-001/002`, `POL-STATUS-001/002`, `THR-C1-008..011`, diagrams `g2-moderation-state` and `g2-cycle1-erd`.
