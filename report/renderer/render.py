#!/opt/renderer-venv/bin/python3
import argparse
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
from contextlib import contextmanager

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, NameObject
from weasyprint import HTML


def run(*args: str) -> None:
    subprocess.run(args, check=True, env={**os.environ, "HOME": "/tmp"})


@contextmanager
def fixed_workdir():
    path = Path("/tmp/report-render")
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(mode=0o700)
    try:
        yield str(path)
    finally:
        shutil.rmtree(path, ignore_errors=True)


def canonicalize_svg(svg: str) -> str:
    svg = re.sub(r"<metadata[\s\S]*?</metadata>", "", svg)
    ids = sorted(set(re.findall(r'\bid="([^"]+)"', svg)))
    for index, old in enumerate(ids):
        new = f"m{index:04d}"
        svg = svg.replace(f'id="{old}"', f'id="{new}"')
        svg = svg.replace(f"url(#{old})", f"url(#{new})")
        svg = svg.replace(f'href="#{old}"', f'href="#{new}"')
        svg = svg.replace(f'xlink:href="#{old}"', f'xlink:href="#{new}"')
    return svg.strip() + "\n"


def render_mermaid(markdown: str, work: Path) -> str:
    pattern = re.compile(r"```mermaid\s*\n(.*?)```", re.DOTALL)
    parts: list[str] = []
    offset = 0
    for index, match in enumerate(pattern.finditer(markdown)):
        parts.append(markdown[offset:match.start()])
        source = match.group(1).strip() + "\n"
        source_path = work / f"mermaid-{index:04d}.mmd"
        svg_path = work / f"mermaid-{index:04d}.svg"
        source_path.write_text(source, encoding="utf-8")
        run(
            "mmdc", "-p", "/renderer/puppeteer-config.json",
            "-i", str(source_path), "-o", str(svg_path),
            "-b", "transparent", "--quiet",
        )
        svg_path.write_text(canonicalize_svg(svg_path.read_text(encoding="utf-8")), encoding="utf-8")
        parts.append(f"![Mermaid diagram]({svg_path.name})\n")
        offset = match.end()
    parts.append(markdown[offset:])
    return "".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--stylesheet", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--inventory-sha256", required=True)
    parser.add_argument("--offline", action="store_true", required=True)
    parser.add_argument("--canonicalize-mermaid", action="store_true", required=True)
    parser.add_argument("--canonicalize-pdf", action="store_true", required=True)
    args = parser.parse_args()

    release_sha = os.environ.get("RELEASE_SHA", "")
    if not re.fullmatch(r"[0-9a-f]{40}", release_sha):
        raise SystemExit("RELEASE_SHA must be 40 lowercase hexadecimal characters")
    expected_inventory = Path("/renderer/inventory.sha256").read_text(encoding="ascii").strip()
    if not re.fullmatch(r"[0-9a-f]{64}", args.inventory_sha256) or args.inventory_sha256 != expected_inventory:
        raise SystemExit("renderer inventory hash mismatch")

    source = Path(args.source).resolve()
    documents = sorted((source / "docs" / "report").glob("*.md"))
    if not documents or any(path.is_symlink() for path in documents):
        raise SystemExit("report Markdown allowlist is empty or contains a symlink")
    metadata = Path(args.metadata).read_text(encoding="utf-8")
    if metadata.count("RELEASE_SHA") != 1:
        raise SystemExit("metadata must contain one RELEASE_SHA placeholder")

    with fixed_workdir() as temporary:
        work = Path(temporary)
        combined = f"Release SHA: `{release_sha}`\n\n" + "\n\n".join(
            path.read_text(encoding="utf-8") for path in documents
        )
        markdown_path = work / "report.md"
        markdown_path.write_text(render_mermaid(combined, work), encoding="utf-8")
        metadata_path = work / "metadata.yaml"
        metadata_path.write_text(metadata.replace("RELEASE_SHA", release_sha), encoding="utf-8")
        html_path = work / "report.html"
        raw_pdf = work / "raw.pdf"
        rewritten_pdf = work / "rewritten.pdf"

        run(
            "pandoc", str(markdown_path), "--from=gfm", "--to=html5", "--standalone",
            "--metadata-file", str(metadata_path), "--css", args.stylesheet,
            "--embed-resources", "--output", str(html_path),
        )
        identifier = hashlib.sha256((release_sha + markdown_path.read_text(encoding="utf-8")).encode()).digest()
        HTML(filename=html_path).write_pdf(
            raw_pdf,
            pdf_identifier=identifier,
            full_fonts=True,
            hinting=False,
            optimize_images=False,
        )

        reader = PdfReader(raw_pdf)
        writer = PdfWriter()
        writer.clone_document_from_reader(reader)
        writer.metadata = None
        for page in writer.pages:
            annotations = page.get("/Annots", [])
            retained = ArrayObject()
            for reference in annotations:
                annotation = reference.get_object()
                action = annotation.get("/A")
                if action and action.get("/URI"):
                    continue
                retained.append(reference)
            if retained:
                page[NameObject("/Annots")] = retained
            elif "/Annots" in page:
                del page["/Annots"]
        with rewritten_pdf.open("wb") as stream:
            writer.write(stream)
        run(
            "qpdf", "--static-id", "--object-streams=generate",
            "--stream-data=compress", str(rewritten_pdf), args.output,
        )


if __name__ == "__main__":
    main()
