#!/opt/renderer-venv/bin/python3
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def command(*args: str) -> str:
    result = subprocess.run(args, check=True, capture_output=True, text=True)
    return (result.stdout or result.stderr).strip()


def executable(name: str) -> dict[str, str]:
    path = Path(command("/usr/bin/which", name)).resolve()
    return {"path": str(path), "sha256": sha256(path)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", nargs=2, metavar=("JSON", "SHA256"))
    args = parser.parse_args()

    font_paths = sorted(
        {
            Path(line.split(":", 1)[0]).resolve()
            for line in command("fc-list").splitlines()
            if "NotoSansCJK" in line or "NotoSansMonoCJK" in line
        },
        key=str,
    )
    if not font_paths:
        raise SystemExit("Noto CJK fonts are absent")

    inventory = {
        "schema": 1,
        "platform": "linux/amd64",
        "versions": {
            "pandoc": command("pandoc", "--version").splitlines()[0],
            "weasyprint": command("/opt/renderer-venv/bin/weasyprint", "--version"),
            "mermaid-cli": command("mmdc", "--version"),
            "chromium": command("chromium-browser", "--version"),
            "qpdf": command("qpdf", "--version").splitlines()[0],
            "poppler": command("pdfinfo", "-v").splitlines()[0],
        },
        "executables": {
            name: executable(name)
            for name in ("pandoc", "mmdc", "chromium-browser", "qpdf", "pdfinfo", "pdffonts", "pdftotext")
        },
        "python": {
            name: importlib.metadata.version(name)
            for name in ("weasyprint", "pypdf")
        },
        "fonts": {str(path): sha256(path) for path in font_paths},
        "locks": {
            path: sha256(Path(path))
            for path in ("/tmp/renderer-requirements.txt", "/opt/mermaid/package-lock.json")
        },
        "renderer": {
            name: sha256(Path("/renderer") / name)
            for name in ("render.py", "pdf_inspect.py", "inventory.py", "puppeteer-config.json")
        },
    }
    payload = (json.dumps(inventory, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    digest = hashlib.sha256(payload).hexdigest()

    if args.write:
        Path(args.write[0]).write_bytes(payload)
        Path(args.write[1]).write_text(digest + "\n", encoding="ascii")
    else:
        os.write(1, payload)
        print(digest, file=os.sys.stderr)


if __name__ == "__main__":
    main()
