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

## Candidate audit

No candidate is accepted yet.

- `pandoc/extra` platform digest `sha256:a1fcbb4ef0ff0433fdfaf9f19fcbd3440c4f53379327985d5107ac76227c5f1d` contains Pandoc 3.6.4 but does not contain the required WeasyPrint, Mermaid CLI, qpdf, Poppler, Noto CJK fonts, or `/renderer/render` contract.
- `letiemble/weasyprint` platform digest `sha256:1adbb827d4293db4a0ddaddfbb2c1adc49dff00429885f3c6eaaed7392a5a1ac` is rejected because its WeasyPrint 66.0 executable fails to load `libgobject-2.0`, and it lacks the remaining required inventory.
- A hypothetical name, local-only custom image, or image lacking a checked-in reproducible build/publish path is rejected.

These digest observations identify rejected artifacts only. They are not renderer pins and must not satisfy governance tests.

## Fail-closed contract

`scripts/render-report.sh` accepts only a clean exact RC checkout with one RC tag at `HEAD`, the fixed generic output path, a locally preloaded image whose repository digest exactly equals the accepted linux/amd64 lock line, and a normalized metadata template. It uses `--pull=never`, `--network none`, a read-only filesystem, no capabilities, no-new-privileges, an arbitrary non-root UID, fixed locale/timezone/epoch, and read-only source input.

The accepted image must implement `/renderer/render` and `/renderer/inspect`. Rendering must verify the inventory hash, render Mermaid locally, canonicalize Mermaid IDs/metadata and PDF metadata/ID, embed both pinned Noto fonts, reject external URI schemes, and write atomically. Two independent clean invocations from the same RC must produce byte-identical PDF SHA-256 and page count.

`report/metadata.yaml` uses the literal `RELEASE_SHA` placeholder and the fixed date `1970-01-01`; the renderer replaces the placeholder only with the validated 40-hex RC SHA. No workstation path or identity value may enter the image, metadata, logs, or PDF.

**Gate status:** BLOCKED. G1 cannot pass until a pullable, platform-specific renderer digest or checked-in reproducible build/publish path supplies the measured inventory, both accepted lock lines are present, and independent offline repeat renders pass.
