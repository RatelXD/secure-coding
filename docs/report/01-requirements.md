# 01 — Requirements analysis

## Inputs

- `SRC-PDF-001` and the physical-page correction in [`AC-SRC-001`](source-ledger.md)
- Approved Cycle 1 and Cycle 2 scope
- Policy oracle and security/release gates

## Cycle boundaries

Cycle 1 covers username/password membership, safe profile self-service, one-image products, global/direct authenticated chat, user/product reports, and seven-day reversible moderation. Cycle 2 is mandatory but cannot begin before a real Cycle 1 observation→issue→fix→negative/regression→PATCH RC→same-SHA formal→retrospective chain closes G5.

Only username and password are collected. Email, phone, address, payment data, real banking/PG, password recovery, SPA/CORS/token deployment, permanent moderation deletion, and Redis persistence are out of scope.

## Trace status

| AC family | Cycle | Status | Gate |
|---|---:|---|---|
| AC-SRC/REP/GOV | foundation | in progress | G1 BLOCK |
| AC-C1-* / AC-SEC-* | 1 | not started | prohibited before G1 |
| AC-MNT-001 | 1 maintenance | not started | G5, no substitute |
| AC-C2-* | 2 | not started | prohibited before G5/G6 |
| AC-SUB-001/002 | generic package | not started | G8a |
| AC-SUB-003/004 | user-private submission | Team forbidden | G8b user only |
