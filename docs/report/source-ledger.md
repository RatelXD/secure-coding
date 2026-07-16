# Source ledger

This PUBLIC ledger intentionally contains no workstation path, username, identity, credential, or private evidence locator. Its schema is fixed by `AC-SRC-001`.

| source_id | basename | byte_size | sha256 | physical_page | printed_page_label | text_anchor | exact_quote | tool_and_version | supersedes |
|---|---|---:|---|---:|---|---|---|---|---|
| SRC-PDF-001 | secure-coding-slide.v2.pdf | 7205525 | e9266692538e00287fbc336c1c310d94f41d89e58a2bfb090f13ff7b5c782b90 | 35 | 35 | 마무리 - 과제 / 플랫폼 요구사항 | `시스템 설계는, 24page에서 명세한 것을 모두 포함할 것` | `pdfinfo 24.02.0; pdftotext 24.02.0; sha256sum 9.4` | — |
| SRC-PDF-001 | secure-coding-slide.v2.pdf | 7205525 | e9266692538e00287fbc336c1c310d94f41d89e58a2bfb090f13ff7b5c782b90 | 25 | 25 | 소프트웨어 개발 실습 / 시스템 설계 | `사람들이 플랫폼에 가입할 수 있어야 함`; `상품들을 올리고 볼 수 있어야 함.`; `플랫폼 사용자들끼리 소통이 가능해야함.`; `악성 유저나 상품을 차단 해야 함` | `pdfinfo 24.02.0; pdftotext 24.02.0; sha256sum 9.4` | PDF physical page 35's erroneous `24page` reference |
| SRC-PRT-001 | pull_request_template.md | 780 | 0cca0ae7ca6eb10a5da12fb97c93440d68c6197ef4f6cbd1f149abe191176798 | — | — | commit `e1e524bcff217999044ca6db3da65eedf990e5e5`; blob `8e4fed1229b1a12d7090c23222230917db738e18` | `## Why`; `## What changed`; `## Docs consulted`; `## Docs updated`; `## Tests / validation`; `## Migration / rollback`; `## Screenshots (UI only)`; `## Open questions / follow-ups` | `Python 3 urllib; RFC 4648 base64; SHA-256; GitHub Git Database API` | — |

## Interpretation rule

The physical-page 35 phrase `24page` is an error. Every requirement, design, implementation, test, maintenance, and release trace interprets it as **physical page 25**. Cycle 1 therefore includes membership, product publication and management, global/direct chat, reporting, reversible product hiding, and reversible user dormancy. Transfer, search, and administration remain mandatory Cycle 2 scope.
