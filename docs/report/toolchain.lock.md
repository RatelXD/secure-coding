# Report toolchain lock

The final generic report is rendered offline with fixed inputs. Floating versions and network rendering are forbidden.

| Component | Required version | Accepted evidence |
|---|---:|---|
| Pandoc | 3.6.4 | executable byte SHA-256 and version output from the accepted image |
| WeasyPrint | 66.0 | installed-distribution SHA-256 and version output from the accepted image |
| Mermaid CLI | 11.4.2 | package-tree SHA-256, bundled Chromium version, and local render receipt |
| Noto Sans CJK KR | 2.004 | exact font-file SHA-256 and embedded-font receipt |
| Noto Sans Mono CJK KR | 2.004 | exact font-file SHA-256 and embedded-font receipt |
| qpdf | 12.0.0 | executable byte SHA-256 and version output from the accepted image |
| Poppler `pdfinfo`/`pdffonts`/`pdftotext` | fixed by accepted image | executable byte SHA-256 and version output |

## Accepted lock-line format

An accepted renderer adds exactly these two lines, replacing the bracketed values with measured values:

```text
- Renderer OCI image (linux/amd64): `<pullable-name>@sha256:<64 lowercase hex>`
- Renderer inventory SHA-256: `<64 lowercase hex>`
```

The inventory hash covers a canonical UTF-8 manifest containing the image platform, every required version, every executable/package/font byte hash, the bundled Chromium version, and the renderer entrypoint byte hash. A tag, manifest-list digest without a fixed platform manifest, local image ID, placeholder, or unverified 64-hex value is not accepted.

## Checked-in build and publish path

`report/renderer/Dockerfile` builds one linux/amd64 image from the platform-specific Pandoc base digest recorded below. Alpine packages are exact-version constrained, the qpdf 12.0.0 source archive is SHA-256 verified, Python dependencies are fully version constrained in `report/renderer/requirements.txt`, and Mermaid's complete npm dependency graph and registry integrities are fixed by `report/renderer/npm/package-lock.json`.

The image generates `/renderer/inventory.json` and `/renderer/inventory.sha256` from canonical JSON. The inventory covers platform, tool versions, executable bytes, both dependency locks, every Noto CJK font file, Chromium, and all renderer entrypoint/configuration bytes.

`.github/workflows/report-renderer-image.yml` builds and publishes only from trusted `main` or manual dispatch on `main`. It grants `packages: write` and `contents: read`, does not persist checkout credentials, and publishes an exact commit-SHA tag. The workflow output digest must be independently resolved to the linux/amd64 platform manifest before adding accepted lock lines.

## Candidate audit

No pullable candidate is accepted yet.

- Base: `pandoc/extra` linux/amd64 digest `sha256:a1fcbb4ef0ff0433fdfaf9f19fcbd3440c4f53379327985d5107ac76227c5f1d`, containing Pandoc 3.6.4.
- Rejected standalone candidate: `letiemble/weasyprint` linux/amd64 digest `sha256:1adbb827d4293db4a0ddaddfbb2c1adc49dff00429885f3c6eaaed7392a5a1ac`; WeasyPrint 66.0 fails to load `libgobject-2.0` and the remaining inventory is absent.
- Local combined-image smoke build: inventory SHA-256 `c10e85a98d55cdc8cf3d15a8639345167eab0e63b360a659f4c6528c4aad62b4`; Pandoc 3.6.4, WeasyPrint 66.0, Mermaid CLI 11.4.2 with Chromium 136.0.7103.113, Noto Sans/Mono CJK font revision 2.004, qpdf 12.0.0, and Poppler 24.02.0.
- Local offline smoke receipt: two independent renders produced identical PDF SHA-256 `a9fa7f742af630a4fbd4ee63003a1ddc9465a48d7a7e337416c0248ef5f92056`, 13 pages, embedded/subset Noto Sans and Noto Sans Mono CJK KR, no prohibited metadata, and no HTTP(S) or local-file URI actions.

The local smoke receipt proves the checked-in implementation path, not registry availability or the final RC. A local image ID, hypothetical name, or unverified digest must not satisfy governance tests.

## Fail-closed contract

`scripts/render-report.sh` accepts only a clean exact RC checkout with one RC tag at `HEAD`, the fixed generic output path, a locally preloaded image whose repository digest exactly equals the accepted linux/amd64 lock line, and a normalized metadata template. Before invoking Docker it rejects tracked private/runtime paths, stages only regular tracked `docs/report/*.md`, `report/metadata.yaml`, and `report/pdf.css` files into a temporary allowlist tree, and mounts only that tree. It uses `--pull=never`, `--network none`, a read-only filesystem, no capabilities, no-new-privileges, an arbitrary non-root UID, fixed locale/timezone/epoch and Python hash seed, and read-only source input.

The accepted image must implement `/renderer/render` and `/renderer/inspect`. Rendering must verify the inventory hash, render Mermaid locally, canonicalize Mermaid IDs/metadata and PDF metadata/ID, embed both pinned Noto fonts, reject external URI schemes, and write atomically. Two independent clean invocations from the same RC must produce byte-identical PDF SHA-256 and page count.

`report/metadata.yaml` uses the literal `RELEASE_SHA` placeholder and the fixed date `1970-01-01`; the renderer replaces the placeholder only with the validated 40-hex RC SHA. No workstation path or identity value may enter the image, metadata, logs, or PDF.

**Gate status:** BLOCKED. The checked-in build/publish path and local deterministic smoke receipt exist, but G1 cannot pass until the leader publishes the trusted-main image, records its pullable linux/amd64 digest and measured inventory in both accepted lock lines, and independent verification repeats the offline renders from the accepted digest.
