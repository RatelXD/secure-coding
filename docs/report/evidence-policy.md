# Evidence policy

## Classification and ownership

| Class | Allowed location | Sole writer | Allowed content | Prohibited content |
|---|---|---|---|---|
| PUBLIC | Git, PR, Pages, Release, `dist/` | file owner | IDs, sanitized results, tools, immutable commit/tag/artifact hashes | absolute paths, identity, credentials, sessions, raw private payloads, ngrok/LMS data |
| SANITIZED | `artifacts/sanitized/` or public docs | L5 produces; L4 reviews redaction | pseudonyms, masked logs, payload category and hash, stripped screenshots | raw actor identifiers or metadata |
| TEAM-PRIVATE-PROVENANCE | `.evidence-private/source-manifest.md`, `.evidence-private/provenance/`, `.evidence-private/redaction/` | L4 | source paths and metadata, fetch/hash receipts, redaction work manifests | identity PDF/name, LMS receipt originals, credentials/sessions |
| TEAM-PRIVATE-VERIFICATION | `.evidence-private/verification/` | L5 | raw test/scanner/log/screenshot evidence and RC verification | identity PDF/name, LMS receipt originals, credentials/sessions |
| USER-PRIVATE | user-owned `private-submission/` | user only | identity copy and LMS originals | all Team access; all Git/CI/Pages/Release ingestion |

No other `.evidence-private/` path is allowed. L4 never writes `.evidence-private/verification/`; L5 never writes provenance/redaction paths. Every other lane is read/review-only for both private classes. The Team must not access `private-submission/`.

## Publication checklist

1. Assign an Evidence-ID and classification at creation.
2. Preserve immutable source/test metadata privately under the sole owner.
3. Replace people with stable pseudonyms; mask IPs, hosts, sessions, tokens, and payloads.
4. Strip screenshot/document metadata.
5. Have L4 and L5 independently review SANITIZED material.
6. Scan tracked history, workflow artifact globs, Pages output, and the public release package.
7. Publish only the minimum PUBLIC or SANITIZED representation and link its AC/Policy/Test/PR/release IDs.

A failed classification, ownership, scan, or redaction check blocks promotion. Schedule pressure does not lower classification.
