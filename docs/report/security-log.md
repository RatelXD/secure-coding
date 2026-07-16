# Security log

Entries are append-only and use IDs `SEC-YYYY-NNN`.

## Entry schema

- ID / date / cycle / discovery stage / severity
- Related AC / Policy / Threat / Test / Evidence / PR / release
- Asset and trust boundary
- Weakness and exploitability
- **Why**
- **Before**
- **What changed**
- **After**
- Verification, including negative/regression tests and exact result
- Residual risk
- Owner and independent security signer

## Open gate concern

### SEC-2026-001 — Independent review unavailable

- Stage: G1 governance preflight
- Severity: release blocker (not a product vulnerability)
- Evidence: `G1-GH-20260716`
- Why: protected review must be independent of the feature author and release actor.
- Before: collaborator inventory contains only `RatelXD`; `main` is unprotected; the protected `release` environment has `prevent_self_review=true` but only that same account as reviewer.
- What changed: Pages and fail-closed release environment exist; no independent collaborator was fabricated or bypassed.
- After: G1 remains BLOCK and product work is prohibited.
- Verification: verified GitHub REST inspection; see [verification log](verification-log.md).
- Residual risk: deadline risk until an independent reviewer is invited and protections/checks can be proven.

### SEC-2026-002 — Independent review path established; required checks pending

- Stage: G1 governance preflight
- Severity: release blocker (not a product vulnerability)
- Evidence: `G1-GH-20260716-R2`
- Why: branch and release gates must name an independent reviewer and use the exact successful Actions contexts rather than guessed or weakened checks.
- Before: `SEC-2026-001` recorded no independent collaborator and incomplete branch protection.
- What changed: collaborator `RatelAI` is available; strict `main` review rules are active; the protected `release` environment requires `RatelAI`, prevents self-review, and disables admin bypass.
- After: the independent-review path is fail-closed. GitHub governance remains BLOCK because no required status check is configured until the governance workflows are pushed and run.
- Verification: `scripts/verify_g1.py` confirmed every GitHub governance predicate except `required_status_checks`; see [verification log](verification-log.md).
- Residual risk: a PR must produce the exact check contexts, those contexts must be configured with strict mode, and `RatelAI` must independently approve before merge. The repository owner must not self-approve or bypass the gate.

### SEC-2026-003 — SDK credential material entered PR history

- Stage: G1 independent PR review
- Severity: Critical until every exposed SDK credential is revoked and replaced
- Evidence: independent `RatelAI` review finding on PR #1; no credential value or runtime-state filename is copied into public evidence.
- Why: project-local GJC runtime state is private operational data and must never enter Git, PRs, Actions artifacts, Pages, or releases.
- Before: Team auto-checkpoint commits added five `.gjc/state/sdk/*.json` runtime records before the ignore rule existed.
- What changed: approval polling and workers were stopped; the governance branch was rebuilt from `origin/main` using only intentional commits; CI and regression tests now reject every tracked `.gjc/**` file outside `.gjc/skills/**`.
- After: the sanitized branch contains no `.gjc/state/**` path. The exposed credentials remain untrusted until provider-side revocation and replacement are confirmed.
- Verification: `git log --all -- .gjc/state/sdk` and the PR diff must show no path on the sanitized branch; governance tests and CI must pass after the forced branch update.
- Residual risk: force-pushing removes the files from the active PR history but cannot guarantee immediate deletion from GitHub caches, forks, clones, logs, or provider telemetry. Credential rotation is mandatory.

### SEC-2026-004 — Independent G1 review temporarily superseded

- Stage: G1 governance recovery
- Severity: accepted governance risk; all technical security gates remain blocking
- Evidence: `GOV-DEC-001` and exact-head self-review receipt on PR #1
- Why: the separate reviewer integration can inspect repository content but cannot submit GitHub reviews or comments with its current app permissions.
- Before: G1 required a distinct collaborator approval and `prevent_self_review=true`, leaving the project blocked on integration permissions.
- What changed: the user explicitly authorized documented self-review. Branch-required approvals are removed, while strict exact CI, admin enforcement, linear history, no force-push/delete, credential remediation, and current-head review binding remain mandatory.
- After: governance bootstrap PR #1 may be self-reviewed only when the repository owner posts `G1-GOVERNANCE-BOOTSTRAP-SELF-REVIEW: APPROVED head=<current PR SHA>` and every required check succeeds; this receipt does not complete G1.
- Residual risk: reviewer independence and protection from confirmation bias are absent until the independent integration is repaired. The user accepted this temporary risk.

### SEC-2026-005 — Governance workflow bootstrap trust gap

- Stage: G1 governance bootstrap
- Severity: release blocker after bootstrap merge
- Evidence: Architect review of PR #1 head `c0663a2f914a3db057ee2d33fa2885968bab82fc`
- Why: a `pull_request` workflow is loaded from the proposed revision, so the same PR can alter the code behind a required check while retaining its check name.
- Before: the first governance PR necessarily introduces the workflow because `main` has no trusted workflow to run.
- What changed: the owner identity, exact unedited marker, required GitHub Actions app ID, current head SHA, unique completed check run, full-history runtime-path guard, and pinned full-history secret scanner are verified.
- After: PR #1 can establish the governance baseline under explicit owner bootstrap review, but overall G1 remains BLOCK until a follow-up installs a default-branch-trusted `pull_request_target` governance check that never executes PR-controlled code and branch protection requires its distinct context.
- Verification: the bootstrap merge and the trusted-workflow follow-up must use separate PRs and receipts; product implementation remains prohibited between them.
- Residual risk: the bootstrap check is not an independent attestation. The exact-head owner review is the temporary compensating control.

### SEC-2026-006 — Exposed SDK credentials revoked

- Stage: G1 governance recovery
- Severity: closed Critical credential exposure; historical disclosure remains recorded
- Evidence: repository owner confirmation on 2026-07-16; no credential value, identifier, or provider response is stored
- Why: history sanitation prevents new access through active refs but does not invalidate credentials copied before sanitation.
- Before: SEC-2026-003 remained Critical because five exposed credentials were not yet confirmed invalid.
- What changed: the repository owner confirmed that all five exposed credentials were revoked at their providers. No replacement credentials have been generated.
- After: the exposed values are no longer valid credentials. Replacement is not required to neutralize the exposure; any future credential must remain outside Git, GJC runtime records, public evidence, Actions artifacts, Pages, and releases.
- Verification: non-secret owner/provider-side revocation confirmation plus the exact-head full-history gitleaks and runtime-path CI checks.
- Residual risk: historical bytes may persist in caches, clones, or provider telemetry, but they no longer grant access. Provider telemetry should be retained for incident follow-up without copying secrets into this repository.

### SEC-2026-007 — Trusted governance transition completed

- Stage: G1 governance recovery
- Severity: closed release blocker; historical self-review risk remains recorded
- Evidence: `G1-GH-20260716-R3`; merged PRs #1–#4
- Why: the bootstrap exception could not remain the permanent required-check trust model.
- Before: SEC-2026-004 and SEC-2026-005 recorded a documented owner self-review exception and a PR-controlled workflow trust gap.
- What changed: the repository established strict `governance-trusted` from GitHub Actions app `15368`; its default-branch `pull_request_target` workflow checks out exact PR bytes with persisted credentials disabled, runs no PR-controlled scripts or dependencies, and uses a digest-pinned scanner. The untrusted trigger was removed.
- After: the GitHub governance component of G1 passes. The historical bootstrap exception remains recorded, but it is not the current check path.
- Verification: merged PR history and current branch-protection configuration were reviewed; see [verification log](verification-log.md).
- Residual risk: exact-head documented owner self-review remains the approved human-review model until independent integration permissions are available. It does not weaken the trusted technical check.

### SEC-2026-008 — Deterministic renderer artifact unavailable

- Stage: G1 report toolchain
- Severity: release blocker (not a product vulnerability)
- Evidence: `G1-TOOL-20260716-R2`
- Why: an immutable digest is meaningful only when it identifies a pullable platform artifact whose measured contents satisfy the full renderer and font inventory.
- Before: the toolchain ledger named required versions but had no accepted renderer image, canonical inventory hash, or repeat-render receipt.
- What changed: candidate platform digests were audited and rejected when incomplete or broken. The renderer draft enforces immutable-image, offline, read-only, and metadata controls; no placeholder digest, mutable tag, local-only image, or network fallback was accepted.
- After: G1 remains BLOCK. A pullable linux/amd64 image or checked-in reproducible build/publish path must supply the complete measured inventory before independent real-container repeat rendering can establish PASS. The renderer must also stage or mount only explicit public inputs: its current whole-worktree mount exposes ignored private directories and `.git` to the container, and its root `.gjc/_session-*` guard is incomplete.
- Verification: public candidate audit, lock semantics, renderer invocation controls, mount scope, and forbidden-path predicates were inspected; see [toolchain lock](toolchain.lock.md) and [verification log](verification-log.md).
- Residual risk: accepting an arbitrary public image, invented inventory hash, mocked render receipt, or a container-visible private workspace would create a false supply-chain/privacy attestation. Product and G2 work remain prohibited.

### SEC-2026-009 — Local renderer proven; publication and provenance remain blocked

- Stage: G1 report toolchain
- Severity: release blocker (not a product vulnerability)
- Evidence: `G1-TOOL-LOCAL-20260716`, `G1-TOOL-LOCAL-20260716-R2`
- Why: a deterministic local image is necessary but cannot substitute for an accepted pullable platform digest and complete measured supply-chain inventory.
- Before: SEC-2026-008 recorded no combined build path, unsafe whole-worktree exposure, and no real-container repeat receipt.
- What changed: commit `5084386…` adds a trusted-main publication workflow, an allowlisted staging tree that excludes `.git` and private/runtime paths, a local-only combined renderer, and canonical metadata/PDF handling. Delivery and independent direct-container checks each produced byte-identical 13-page PDFs for their lane-local subjects.
- After: the prior whole-worktree and root session-path defects are closed. G1 remains BLOCK because the wrapper binds a nonexistent host output path as a file, Python/APK inputs lack complete immutable hash/snapshot enforcement, the inventory omits installed Python/Mermaid tree and explicit font family/revision proof, and no accepted pullable repository digest exists.
- Verification: independent local image ID/inventory inspection, focused governance tests, two real offline render/inspect runs, and Docker missing-bind behavior were checked without publishing private paths.
- Residual risk: local tags and image IDs are not registry attestations. Only a trusted-main linux/amd64 repository digest with complete inventory and independent digest-based repeat renders can close this gate.

### SEC-2026-010 — Report rendering removed from release gates

- Stage: G1/G8a scope reconciliation
- Severity: closed process blocker; optional utility risk only
- Evidence: `G1-REPORT-SCOPE-20260716`
- Why: generated PDF processing is a user-manual activity and must not be represented as an automated repository gate.
- Before: SEC-2026-008 and SEC-2026-009 treated renderer publication, provenance, and repeat-render receipts as release blockers.
- What changed: the user superseded that gate. The retained offline renderer is explicitly optional and non-gating; its publication workflow was removed, its wrapper correctness was repaired, and focused helper tests passed.
- After: renderer image publication, repository digest, inventory receipt, generated PDF, and repeat-render evidence do not block G1, G8a, product work, or release. Manual report processing remains outside automated promotion evidence.
- Verification: optional-helper tests explicitly enforce non-gating status and absence of a publication workflow; see [verification log](verification-log.md).
- Residual risk: the optional helper still requires ordinary maintenance if used, but failures cannot be promoted back into release blockers without a new explicit scope decision.
## Cycle 1 G2 threat model

| Threat ID | Asset / boundary | Threat and exploit path | Required control | Verification contract | Residual risk |
|---|---|---|---|---|---|
| `THR-C1-001` | Session and B1 | Stolen/fixed session or missing CSRF performs unsafe HTTP actions | Django session rotation, Secure/HttpOnly/SameSite cookies, CSRF, generic auth responses, `auth_epoch` | `T-AUTH-*`, `T-STATUS-002/004`, CSRF negative tests | Browser or endpoint compromise is outside application control |
| `THR-C1-002` | HTTP/WS B1 | Spoofed Host/Origin or untrusted forwarded headers bypass same-origin policy | Exact Host/origin allowlists, WS validation before accept, proxy trust configured fail-closed | handshake Host/Origin/forwarded-header matrix | A compromised trusted ingress can still spoof its asserted metadata |
| `THR-C1-003` | Objects and B2 | IDOR/mass assignment changes another profile/product or enters a direct room | Server-derived actor/owner/participants and concealed 404 decisions | ownership/participant negative tests on every entrypoint | Authorization defects in new entrypoints require continued review |
| `THR-C1-004` | Availability and B1/B3 | Concurrent brute force or request bursts exceed an in-memory limiter | PostgreSQL-authoritative exact account/IP/message boundaries; keyed-HMAC IP identifier; generic 429 | `T-AUTH-001..004`, `T-CHAT-003..005` concurrency cases | Distributed low-rate/Sybil abuse is reduced, not eliminated |
| `THR-C1-005` | Chat history B3/B4 | Publish-before-commit creates ghost message; publish failure followed by retry duplicates history | Commit-only acceptance, unique client UUID key, payload conflict, publish-once new row | `T-CHAT-006..009` commit/publish/ACK fault injection | No automatic live replay during Redis outage; history converges |
| `THR-C1-006` | Direct chat B2 | Guessed room/server cursor discloses private history | Participant check on handshake, each frame, and history query; opaque identifiers are not authority | room-ID and cursor IDOR tests | Participant endpoint compromise remains out of scope |
| `THR-C1-007` | Chat content B1 | Oversize/control/XSS payload consumes resources or executes in another browser | UTF-8 byte limit, control rejection, text storage, template/DOM escaping, frame limits | `T-CHAT-001/002`, WS oversize and stored-XSS tests | Unicode confusables may enable social engineering |
| `THR-C1-008` | Reports/actions B3 | Duplicate or concurrent threshold requests create overlapping sanctions | Lifetime uniqueness, locked threshold recheck, consumed-once reports, one active action/audit | `T-MOD-001..006` including concurrent 5/6 and expiry races | Coordinated independent Sybil reporters remain possible |
| `THR-C1-009` | User/product visibility B2/B3 | Stored flag, host clock, or query bypass disagrees with effective sanction | Canonical DB-time services and exhaustive invocation matrix | `T-STATUS-001..007`, raw-query review rule | Future entrypoints can regress unless matrix tests are maintained |
| `THR-C1-010` | Dormant sessions/sockets B1/B4 | Redis outage prevents revocation notification and leaves socket active | Atomic epoch increment, HTTP epoch check, every-frame status check, 4403 close | `T-STATUS-002/003`, Redis outage socket test | An idle socket may remain connected until notification or next frame but cannot execute a command |
| `THR-C1-011` | Moderation history B3 | Permanent deletion or report reuse destroys auditability or extends punishment | Immutable seven-day actions, append-only audit, consumed-report relation, computed expiry | `T-MOD-004..006`, migration/rollback review | Authorized database operators remain privileged and separately audited |
| `THR-C1-012` | Product media B1/B5 | Polyglot, SVG/script, decompression bomb, metadata/path payload reaches users/server | Allowlisted raster formats, size/dimension cap, full decode and new encode, generated name, isolated serving | image MIME/signature/polyglot/bomb/path/metadata tests | Decoder vulnerabilities require dependency scanning and patching |
| `THR-C1-013` | Secrets/privacy and all boundaries | Logs or errors expose password, raw IP, username, chat/report body, cookie, or backend detail | Structured allowlisted logging, keyed IP, generic errors, production debug off, secret scanning | capture negative logs/errors and secret/SAST scans | Operators with database access can see application content within their role |

Threat review is limited to Cycle 1. No later-cycle subsystem, route, permission, or data model is analyzed here.

### SEC-2026-011 — Ambiguous chat acceptance could duplicate durable messages

- Stage: G2 architecture review
- Severity: High design finding, closed in the G2 design packet
- Related: `AC-C1-CHAT-003..005`, `POL-CHAT-003`, `THR-C1-005`, `T-CHAT-006..009`, ADR-2
- Asset and trust boundary: authenticated message history across PostgreSQL/Redis boundary B3/B4.
- Why: treating Redis publish or ACK as the acceptance point makes a committed message appear failed and encourages duplicate client retries.
- Before: the baseline named PostgreSQL history and Redis fan-out but did not define every commit/publish/ACK interleaving.
- What changed: ADR-2 makes commit the only acceptance point, adds the unique client UUID/payload rule, prohibits replay republish, and requires degraded ACK plus cursor resynchronization.
- After: no Critical/High chat-acceptance design ambiguity remains; implementation remains blocked until fault tests pass.
- Verification: inspect the failure matrix and execute `T-CHAT-006..009` during the feature gate.
- Residual risk: outage messages are not automatically live-rebroadcast; convergence is explicit through history.
- Owner / security signer: architecture owner / independent G2 verifier.

### SEC-2026-012 — Status checks could drift across HTTP, WebSocket, and queries

- Stage: G2 architecture review
- Severity: High design finding, closed in the G2 design packet
- Related: `AC-C1-CAT-003`, `AC-C1-MOD-004/005`, `POL-STATUS-001/002`, `THR-C1-009/010`, `T-STATUS-*`, ADR-3
- Asset and trust boundary: account authorization and product visibility at B2/B3.
- Why: stored flags, application-host clocks, or entrypoint-local logic can expose a hidden product or authorize a dormant account at transition/expiry.
- Before: canonical status was a baseline principle without an exhaustive invocation/transition matrix.
- What changed: the matrix now requires DB-time services in middleware, handshake/frame, chat, catalog, report, moderation, owner-view, and reconciliation paths; epoch and Redis-outage fallback semantics are exact.
- After: no Critical/High status-authority design gap remains; raw query/status bypass is classified as a security defect.
- Verification: matrix inspection plus `T-STATUS-001..007`, including exact expiry and Redis outage.
- Residual risk: future entrypoints must extend the matrix and tests.
- Owner / security signer: architecture owner / independent G2 verifier.

### SEC-2026-013 — WebSocket controls could be weaker than same-origin HTTP

- Stage: G2 architecture review
- Severity: High design finding, closed in the G2 design packet
- Related: `AC-C1-CHAT-001`, `THR-C1-002/003/006`, ADR-1
- Asset and trust boundary: session-authenticated WebSocket at browser boundary B1.
- Why: cookies are sent during WebSocket handshakes; without explicit Host, Origin, session, room, and per-frame status checks, cross-site or stale-session access is possible.
- Before: same-origin ASGI was selected but handshake rejection and close behavior were unspecified.
- What changed: the entrypoint table requires Host/Origin/session/status/participant checks before accept, rechecks commands, and fixes 4400/4401/4403/4408/1011 close semantics.
- After: no Critical/High HTTP/WS parity ambiguity remains; consumer implementation must use the configured middleware stack.
- Verification: negative handshake/frame tests for Host, Origin, authentication, participation, epoch, and dormant status.
- Residual risk: trusted ingress compromise is outside application enforcement.
- Owner / security signer: architecture owner / independent G2 verifier.

### SEC-2026-014 — Concurrent moderation could duplicate or extend sanctions

- Stage: G2 architecture review
- Severity: High design finding, closed in the G2 design packet
- Related: `AC-C1-MOD-001..005`, `POL-MOD-001/002`, `THR-C1-008/011`, `T-MOD-*`, ADR-3
- Asset and trust boundary: report/action/audit integrity in PostgreSQL boundary B3.
- Why: count-then-create without locks and consumed-report authority can create two actions, reuse reports, or extend a sanction at the expiry boundary.
- Before: reversible seven-day moderation lacked a complete transactional state machine.
- What changed: threshold evaluation locks and rechecks eligibility, consumes contributing reports once, creates one immutable action/audit, never extends an active action, and uses DB-time expiry.
- After: no Critical/High moderation-race design gap remains; the design does not claim complete Sybil prevention.
- Verification: `T-MOD-002..006`, especially simultaneous threshold and exact-expiry/new-report barriers.
- Residual risk: independent coordinated reporters may reach a threshold; account age/rate/pattern alerts, reversibility, and review mitigate but do not eliminate it.
- Owner / security signer: architecture owner / independent G2 verifier.

## G2 design-review disposition

| Severity | Open | Closed by this packet | Gate rule |
|---|---:|---:|---|
| Critical | 0 | 0 | Any open finding blocks G2 |
| High | 0 | 4 | Each closure requires its linked contract and independent verification |
| Medium/Low | 0 | 0 | Record when discovered; do not silently accept |

This is a design-review disposition, not a product-security pass. G2 remains blocked if independent verification finds a missing invocation, failure branch, threat control, or executable Test-ID. Feature gates remain responsible for proving implementation and keeping Critical/High findings at zero.
