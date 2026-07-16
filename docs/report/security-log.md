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
