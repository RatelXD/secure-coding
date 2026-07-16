# Report toolchain lock

This file documents an optional offline report-rendering utility. Generated PDF output, renderer publication, OCI attestations, and renderer receipts are not G1 or G8a requirements and do not gate product work or release.

| Component | Utility version | Local provenance evidence |
|---|---:|---|
| Pandoc | 3.6.4 | executable byte SHA-256 and version output |
| WeasyPrint | 66.0 | installed-distribution tree SHA-256 and version output |
| Mermaid CLI | 11.4.2 | complete package-tree SHA-256 and bundled Chromium version |
| Noto Sans CJK KR | 2.004 | family, revision, exact font-file SHA-256, and embedded-font receipt |
| Noto Sans Mono CJK KR | 2.004 | family, revision, exact font-file SHA-256, and embedded-font receipt |
| qpdf | 12.0.0 | executable byte SHA-256 and version output |
| Poppler `pdfinfo`/`pdffonts`/`pdftotext` | 24.02.0 | executable byte SHA-256 and version output |

## Optional published-image format

An operator who independently publishes the utility may record these optional provenance lines:

```text
- Renderer OCI image (linux/amd64): `<pullable-name>@sha256:<64 lowercase hex>`
- Renderer inventory SHA-256: `<64 lowercase hex>`
```

The inventory hash covers canonical UTF-8 JSON containing platform and tool versions, executable bytes, hash-locked dependency inputs, installed Python distribution trees, the complete Mermaid package tree, explicit Noto family/revision/file evidence, Chromium, and renderer entrypoint bytes. A local image ID is not a pullable repository digest.

## Checked-in local build path

`report/renderer/Dockerfile` builds one linux/amd64 utility image from the platform-specific Pandoc base digest recorded below. Alpine packages are exact-version constrained, the qpdf 12.0.0 source archive is SHA-256 verified, Python wheels are enforced with pip `--require-hashes`, and Mermaid's complete npm dependency graph and registry integrities are fixed by `report/renderer/npm/package-lock.json`.

The image generates `/renderer/inventory.json` and `/renderer/inventory.sha256` from canonical JSON. No repository workflow publishes this optional utility and no package permission or attestation is required.

## Local implementation audit

No image publication is required or currently configured.

- Base: `pandoc/extra` linux/amd64 digest `sha256:a1fcbb4ef0ff0433fdfaf9f19fcbd3440c4f53379327985d5107ac76227c5f1d`, containing Pandoc 3.6.4.
- Rejected standalone candidate: `letiemble/weasyprint` linux/amd64 digest `sha256:1adbb827d4293db4a0ddaddfbb2c1adc49dff00429885f3c6eaaed7392a5a1ac`; WeasyPrint 66.0 fails to load `libgobject-2.0` and the remaining inventory is absent.
- Local combined-image smoke build after supply-chain fixes: inventory SHA-256 `cd6028cddb3e196edd928e18cf6d7ca1831e97aa4a4338f86bb7b4de05151ae2`; 15 installed Python distribution trees are hashed, the 24,732-entry Mermaid package tree SHA-256 is `64d324ffae99a4ac48f693492aecffa1eb3d3602141489345a68ba5f18f0e72f`, both required font families report revision 2.004, and the two Noto Sans CJK TTC SHA-256 values are `faa5f3656a78b2e2d450d27fe8382c778bc2b6bb5ea29c986664a6a435056ceb` and `b76b0433203017ca80401b2ee0dd69350349871c4b19d504c34dbdd80541690a`.
- Local offline smoke receipt after supply-chain fixes: two independent renders produced identical PDF SHA-256 `1110801444a4d1210effb3c4efddbfdc50120b1eadb5cee795f8147d12a3a4b9`, 13 pages, embedded/subset Noto Sans and Noto Sans Mono CJK KR, no prohibited metadata, and no HTTP(S) or local-file URI actions.

The local smoke receipts verify only optional utility behavior. They are not G1/G8a evidence.

## Fail-closed contract

`scripts/render-report.sh` is an optional strict wrapper. It accepts only a clean exact RC checkout with one RC tag at `HEAD`, a fixed generic output path, a preloaded image matching optional provenance lines, and normalized metadata. It rejects tracked private/runtime paths, stages only regular tracked report inputs, creates the host output file before binding it, and mounts only the staging tree and output file. It uses `--pull=never`, `--network none`, a read-only filesystem, no capabilities, no-new-privileges, an arbitrary non-root UID, and fixed locale/timezone/epoch/hash seed.

The utility image implements `/renderer/render` and `/renderer/inspect`, verifies its inventory hash, renders Mermaid locally, canonicalizes Mermaid/PDF variability, embeds both Noto families, rejects external URI schemes, and writes atomically. Repeated invocations from unchanged inputs are expected to be byte-identical.

`report/metadata.yaml` uses the literal `RELEASE_SHA` placeholder and the fixed date `1970-01-01`; the renderer replaces the placeholder only with the validated 40-hex RC SHA. No workstation path or identity value may enter the image, metadata, logs, or PDF.

**Status:** OPTIONAL / NON-GATING. PDF generation, image publication, repository digests, inventory receipts, and repeat renders are not required for G1 or G8a.
