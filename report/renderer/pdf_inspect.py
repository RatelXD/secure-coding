#!/opt/renderer-venv/bin/python3
import argparse
from pathlib import Path
import re
import subprocess

from pypdf import PdfReader


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--require-font", action="append", default=[])
    parser.add_argument("--reject-metadata")
    parser.add_argument("--reject-uri-scheme")
    args = parser.parse_args()

    pdf_path = Path(args.input)
    reader = PdfReader(pdf_path)
    if not reader.pages:
        raise SystemExit("PDF has no pages")

    forbidden_metadata = re.compile(args.reject_metadata or r"$^")
    for key in (reader.metadata or {}):
        if forbidden_metadata.search(str(key).lstrip("/")):
            raise SystemExit(f"forbidden PDF metadata: {key}")

    forbidden_uri = re.compile(args.reject_uri_scheme or r"$^", re.IGNORECASE)
    for page in reader.pages:
        annotations = page.get("/Annots", [])
        for reference in annotations:
            annotation = reference.get_object()
            action = annotation.get("/A")
            uri = action.get("/URI") if action else None
            if uri and forbidden_uri.match(str(uri)):
                raise SystemExit("external URI is present in PDF")

    fonts = subprocess.run(
        ["pdffonts", str(pdf_path)], check=True, capture_output=True, text=True
    ).stdout
    for required in args.require_font:
        normalized_required = re.sub(r"[^a-z0-9]", "", required.lower())
        normalized_fonts = re.sub(r"[^a-z0-9]", "", fonts.lower())
        if normalized_required not in normalized_fonts:
            raise SystemExit(f"required embedded font is absent: {required}")
    for line in fonts.splitlines()[2:]:
        columns = line.split()
        if len(columns) >= 6 and columns[4:6] != ["yes", "yes"]:
            raise SystemExit(f"font is not embedded and subset: {line}")

    info = subprocess.run(
        ["pdfinfo", str(pdf_path)], check=True, capture_output=True, text=True
    ).stdout
    page_match = re.search(r"^Pages:\s+(\d+)$", info, re.MULTILINE)
    if not page_match or int(page_match.group(1)) < 1:
        raise SystemExit("pdfinfo did not report a positive page count")
    print(f"Pages: {page_match.group(1)}")


if __name__ == "__main__":
    main()
