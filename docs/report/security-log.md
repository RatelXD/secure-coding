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
