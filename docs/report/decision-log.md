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
