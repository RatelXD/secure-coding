# Decision log

Decisions are append-only. Each ADR records status, context/Why, drivers, alternatives, decision, What changed, consequences, follow-ups, and AC/Policy/Threat/Test/PR/release links.

| ADR | Decision | Status | Gate |
|---|---|---|---|
| ADR-1 | same-origin Django ASGI; PostgreSQL authority; Redis fan-out | approved baseline, detailed design pending | G2 |
| ADR-2 | client UUID + DB-accepted ACK + degraded/history resync; no outbox | approved baseline, detailed design pending | G2 |
| ADR-3 | canonical DB-time effective moderation/status policies | approved baseline, detailed design pending | G2 |
| ADR-4 | locked authoritative mock balance + immutable double-entry journal | analysis prohibited before G5 | G6 |
| ADR-5 | scoped permissions + reauth/reason/version + append-only admin audit | analysis prohibited before G5 | G6 |

No ADR weakens the physical-page correction, policy oracle, Critical/High zero, real G5 chain, G8a-before-formal order, or user-only G8b boundary.

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
