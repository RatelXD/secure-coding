# Verification log

Public summaries are append-only. Raw verification evidence belongs only to L5 under `.evidence-private/verification/`; raw provenance belongs only to L4 provenance paths.

| Evidence-ID | Date (UTC) | Gate | Inspection or command | Result | Immutable subject |
|---|---|---|---|---|---|
| G1-SRC-PDF-20260716 | 2026-07-16 | G1-SRC | `pdfinfo`; `pdftotext -f 25/-f 35`; `sha256sum` | PASS: 36 pages; physical 25/35 quotes proven; 7,205,525 bytes; SHA recorded | SRC-PDF-001 |
| G1-SRC-PRT-20260716 | 2026-07-16 | G1-SRC/GOV | commit `?raw=1`, raw URL, Git Database blob API; strict RFC 4648 base64 decode | PASS: all 780 bytes and SHA `0cca…6798`; tree points to blob `8e4f…e18`; original sections present | commit `e1e524b…e5e5` |
| G1-SUP-HUM-20260716 | 2026-07-16 | G1-SRC | pinned checkout, license and selected-subtree file hash inventory | PASS: exact selected subtree installed; local-only executable audit | commit `14aeb52…9689` |
| G1-SUP-MMD-20260716 | 2026-07-16 | G1-SRC | pinned checkout, license and selected-subtree file hash inventory | PASS with enforced local-only policy: exact subtree installed; Kroki/network fallback disabled | commit `15d09cf…3f3b` |
| G1-GH-20260716 | 2026-07-16 | G1 | GitHub REST repository/collaborator/protection/Pages/environment inspection | **BLOCK**: sole collaborator; no independent approval; main unprotected. Pages and protected release environment exist. | `RatelXD/secure-coding` |
| G1-TOOL-20260716 | 2026-07-16 | G1 | renderer tool/version inventory | **BLOCK**: pinned renderer OCI digest/package/font hashes not established | report toolchain |
| G1-GH-20260716-R2 | 2026-07-16 | G1 | `python3 scripts/verify_g1.py --source-pdf <private source> --repository RatelXD/secure-coding`; GitHub REST inspection | **BLOCK** only within GitHub governance: `RatelAI` is an independent collaborator and required release reviewer; `prevent_self_review=true`; admin bypass disabled; strict review/linear-history/no-force-push/no-delete rules PASS; required status checks absent pending governance workflow run and exact-context configuration | `RatelXD/secure-coding` live configuration |
| G1-CRED-20260716 | 2026-07-16 | G1-SEC | non-secret repository-owner/provider-side revocation confirmation; full-history gitleaks and runtime-path CI | PASS: all five credentials from SEC-2026-003 revoked; no replacement credential generated or stored | SEC-2026-003/SEC-2026-006 credential set |

A row marked BLOCK cannot be converted to PASS by a different row. Product implementation remains prohibited until every G1 component passes.
