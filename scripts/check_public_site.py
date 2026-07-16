#!/usr/bin/env python3
"""Reject private material from generated public-site output."""

from __future__ import annotations

import argparse
from collections.abc import Iterator
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from typing import Any

_FORBIDDEN_PATH_PARTS = frozenset({".evidence-private", "private-submission"})
_FORBIDDEN_CONTENT = (
    (
        "local home path",
        re.compile(r"/(?:home|Users)/[A-Za-z0-9._-]+/", re.IGNORECASE),
    ),
    (
        "temporary ngrok hostname",
        re.compile(r"https://[a-z0-9-]+\.ngrok-free\.app", re.IGNORECASE),
    ),
    (
        "private environment assignment",
        re.compile(
            r"(?:LMS_(?:ID|PASSWORD)|SESSION_KEY)\s*=",
            re.IGNORECASE,
        ),
    ),
    (
        "authorization credential",
        re.compile(
            r"\bauthorization\s*:\s*(?:(?:bearer|basic|token)\s+)?"
            r"[A-Za-z0-9._~+/=-]{16,}",
            re.IGNORECASE,
        ),
    ),
    (
        "cookie credential",
        re.compile(
            r"\bcookie\s*:\s*[A-Za-z0-9_.-]{1,128}\s*=\s*"
            r"[^\s<>\"']{8,}",
            re.IGNORECASE,
        ),
    ),
)


class _VisibleTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        return " ".join(self.parts)


def _iter_json_strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _iter_json_strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_json_strings(item)


def _visible_html(text: str) -> str:
    parser = _VisibleTextExtractor()
    parser.feed(text)
    parser.close()
    return parser.text()


def _searchable_text(path: Path) -> tuple[str, ...]:
    raw = path.read_bytes().decode("utf-8", errors="ignore")
    normalized: list[str] = []

    if path.suffix.casefold() in {".html", ".htm"}:
        normalized.append(_visible_html(raw))
    elif path.suffix.casefold() == ".json":
        try:
            strings = tuple(_iter_json_strings(json.loads(raw)))
        except json.JSONDecodeError:
            strings = ()
        normalized.extend(strings)
        normalized.extend(_visible_html(value) for value in strings if "<" in value)

    return (raw, *normalized)


def find_private_material(root: Path) -> list[str]:
    """Return stable descriptions of private material under ``root``."""
    if not root.is_dir():
        return [f"site root is not a directory: {root}"]

    findings: list[str] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if _FORBIDDEN_PATH_PARTS.intersection(relative.parts):
            findings.append(f"private path: {relative.as_posix()}")
            continue
        if path.is_symlink():
            findings.append(f"symbolic link: {relative.as_posix()}")
            continue
        if not path.is_file():
            continue

        searchable = _searchable_text(path)
        for label, pattern in _FORBIDDEN_CONTENT:
            if any(pattern.search(text) for text in searchable):
                findings.append(f"{label}: {relative.as_posix()}")

    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path, nargs="?", default=Path("site"))
    args = parser.parse_args()

    findings = find_private_material(args.root)
    if findings:
        for finding in findings:
            print(f"private material: {finding}")
        return 1

    print(f"public-site privacy scan passed: {args.root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
