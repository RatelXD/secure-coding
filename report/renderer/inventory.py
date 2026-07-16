#!/opt/renderer-venv/bin/python3
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess

from fontTools.ttLib import TTCollection


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(records: list[dict[str, str]]) -> str:
    payload = json.dumps(
        records, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def tree_inventory(root: Path) -> dict[str, object]:
    records: list[dict[str, str]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            records.append({"path": relative, "symlink": os.readlink(path)})
        elif path.is_file():
            records.append({"path": relative, "sha256": sha256(path)})
    return {"files": len(records), "sha256": canonical_hash(records)}


def python_distributions() -> dict[str, object]:
    result: dict[str, object] = {}
    for distribution in sorted(
        importlib.metadata.distributions(),
        key=lambda item: (item.metadata["Name"].lower(), item.version),
    ):
        records: list[dict[str, str]] = []
        for entry in sorted(distribution.files or [], key=str):
            path = Path(distribution.locate_file(entry))
            if path.is_file():
                records.append({"path": str(entry), "sha256": sha256(path)})
        name = distribution.metadata["Name"].lower().replace("_", "-")
        result[name] = {
            "version": distribution.version,
            "files": len(records),
            "tree_sha256": canonical_hash(records),
        }
    return result


def font_inventory(paths: list[Path]) -> dict[str, object]:
    result: dict[str, object] = {}
    found_families: set[str] = set()
    for path in paths:
        collection = TTCollection(path)
        families = sorted(
            {
                record.toUnicode()
                for font in collection.fonts
                for record in font["name"].names
                if record.nameID == 1 and record.toUnicode().endswith(" CJK KR")
            }
        )
        revisions = sorted({f"{font['head'].fontRevision:.3f}" for font in collection.fonts})
        found_families.update(families)
        result[str(path)] = {
            "families": families,
            "revisions": revisions,
            "sha256": sha256(path),
        }

    required = {"Noto Sans CJK KR", "Noto Sans Mono CJK KR"}
    if not required.issubset(found_families):
        raise SystemExit("both required Noto CJK KR font families must be present")
    relevant_revisions = {
        revision
        for item in result.values()
        for revision in item["revisions"]
    }
    if relevant_revisions != {"2.004"}:
        raise SystemExit(f"Noto Sans CJK revision mismatch: {sorted(relevant_revisions)}")
    return result


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
            if "NotoSansCJK" in line
        },
        key=str,
    )
    if not font_paths:
        raise SystemExit("Noto Sans CJK fonts are absent")

    inventory = {
        "schema": 2,
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
            for name in (
                "pandoc",
                "mmdc",
                "chromium-browser",
                "qpdf",
                "pdfinfo",
                "pdffonts",
                "pdftotext",
            )
        },
        "python_distributions": python_distributions(),
        "mermaid_package_tree": tree_inventory(Path("/opt/mermaid/node_modules")),
        "fonts": font_inventory(font_paths),
        "locks": {
            path: sha256(Path(path))
            for path in (
                "/tmp/renderer-requirements.txt",
                "/opt/mermaid/package-lock.json",
            )
        },
        "renderer": {
            name: sha256(Path("/renderer") / name)
            for name in (
                "render.py",
                "pdf_inspect.py",
                "inventory.py",
                "puppeteer-config.json",
            )
        },
    }
    payload = (
        json.dumps(inventory, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode()
    digest = hashlib.sha256(payload).hexdigest()

    if args.write:
        Path(args.write[0]).write_bytes(payload)
        Path(args.write[1]).write_text(digest + "\n", encoding="ascii")
    else:
        os.write(1, payload)
        print(digest, file=os.sys.stderr)


if __name__ == "__main__":
    main()