# 04 — Checklist and testing

Independent L5 verification owns `tests/**`, sanitized artifacts, release/backup/restore verification scripts, and raw `.evidence-private/verification/**`. L4 records only public trace and provenance/redaction evidence.

Required lanes include unit, integration, E2E, security, concurrency, recovery, observability, evidence/Pages, and release/package checks. Each result links exact command, environment/tool version, result, failure and retest, immutable SHA, and Evidence-ID in the [verification log](verification-log.md).

Promotion requires unresolved Critical/High = 0 with no exception or severity manipulation. A default, tautology, skipped check, or missing raw evidence is not PASS.
