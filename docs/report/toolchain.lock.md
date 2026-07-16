# Report toolchain lock

The final generic report is rendered offline with fixed inputs. Floating versions and network rendering are forbidden.

| Component | Required version | Current Phase 1 status |
|---|---:|---|
| Pandoc | 3.6.4 | required; workstation 3.1.3 is not accepted |
| WeasyPrint | 66.0 | required; absent on workstation |
| Mermaid CLI | 11.4.2 | required; absent on workstation; local bundled Chromium only |
| Noto Sans CJK KR | 2.004 | required; exact font bytes/hash pending renderer image |
| Noto Sans Mono CJK KR | 2.004 | required; exact font bytes/hash pending renderer image |
| qpdf | 12.0.0 | required; absent on workstation |
| Poppler `pdfinfo`/`pdffonts`/`pdftotext` | pinned renderer version | workstation 24.02.0 is provenance-only, not the final renderer |

## Fail-closed contract

The renderer OCI image digest, package hashes, and font hashes must be added here before G1 can pass. `TZ=UTC`, `LC_ALL=C.UTF-8`, and `SOURCE_DATE_EPOCH` equal to the candidate RC commit timestamp are mandatory. Rendering has no network. Mermaid SVG volatile IDs/metadata and PDF metadata/ID are canonicalized.

`scripts/render-report.sh --release-sha <RC_SHA> --output dist/secure-coding-report-generic.pdf` must reject a dirty tree, a different `HEAD`, a tag that does not target `HEAD`, missing pinned tools/fonts, or any external fetch. Two runs from the same checkout/container/environment must have identical SHA-256 and page count.

**Gate status:** BLOCKED until the digest and package/font hashes are proven. This is independent of the documented self-review and credential-remediation gates and must not be bypassed with workstation tools.
