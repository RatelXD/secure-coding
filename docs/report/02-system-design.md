# 02 — System design

Design is gated and has not started. The approved architecture baseline is a same-origin Django 5.2 LTS ASGI application with server templates and vanilla JavaScript. PostgreSQL is the sole durable authority; Redis is non-durable Channels fan-out.

The design packet must define actor/precondition/Given-When-Then acceptance statements, DFD/ERD/state/sequence diagrams, assets and trust boundaries, entrypoint/permission matrices, the complete Policy-ID oracle, image and exact ngrok ingress contracts, migration/rollback, and Test-ID mappings.

ADRs are append-only in the [decision log](decision-log.md). ADR-1 through ADR-3 must close G2 before Cycle 1 implementation. ADR-4 and ADR-5 cannot be analyzed or approved before the real G5 chain closes, and must close G6 before Cycle 2 implementation.
