#!/usr/bin/env python3
"""Validate the Phase 6R Stitch control and remote-asset mapping contract."""

from __future__ import annotations

import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from typing import Any


CONTROL_TAGS = frozenset({"a", "button", "form", "input", "select", "textarea"})
REMOTE_URL = re.compile(r"https?://")
SHA256 = re.compile(r"[0-9a-f]{64}")
FORBIDDEN_MARKERS = ("TBD", "TODO")


class SourceInventory(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.control_tags: dict[str, int] = {}
        self.non_semantic_interactions = 0
        self.icons: set[str] = set()
        self._material_symbol_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag in CONTROL_TAGS:
            self.control_tags[tag] = self.control_tags.get(tag, 0) + 1
        classes = set((attributes.get("class") or "").split())
        if "cursor-pointer" in classes and tag not in CONTROL_TAGS:
            self.non_semantic_interactions += 1
        if tag == "span" and "material-symbols-outlined" in classes:
            self._material_symbol_depth += 1

    def handle_data(self, data: str) -> None:
        if self._material_symbol_depth and data.strip():
            self.icons.add(data.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag == "span" and self._material_symbol_depth:
            self._material_symbol_depth -= 1


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("manifest root must be an object")
    return value


def _validate_contract(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    screens = manifest.get("screens", [])
    if len(screens) != 7:
        errors.append(f"expected seven screens, got {len(screens)}")

    ids: set[str] = set()
    sources: set[str] = set()
    control_total = 0
    remote_total = 0
    for screen in screens:
        screen_id = screen.get("id", "<missing-id>")
        if screen_id in ids:
            errors.append(f"duplicate screen id: {screen_id}")
        ids.add(screen_id)
        source = screen.get("source", "")
        if source in sources:
            errors.append(f"duplicate source: {source}")
        sources.add(source)
        if not SHA256.fullmatch(screen.get("source_sha256", "")):
            errors.append(f"{screen_id}: invalid source SHA-256")
        icons = screen.get("icons", [])
        if icons != sorted(set(icons)):
            errors.append(f"{screen_id}: icons must be sorted and unique")

        tag_count = sum(screen.get("control_tags", {}).values())
        mapped_count = sum(row.get("count", 0) for row in screen.get("control_map", []))
        declared_count = screen.get("control_count")
        if tag_count != declared_count:
            errors.append(f"{screen_id}: tag count {tag_count} != {declared_count}")
        if mapped_count != declared_count:
            errors.append(f"{screen_id}: mapped count {mapped_count} != {declared_count}")
        interaction_rows = screen.get("non_semantic_interactions", [])
        mapped_non_semantic = sum(row.get("count", 0) for row in interaction_rows)
        declared_non_semantic = screen.get("non_semantic_interaction_count")
        if mapped_non_semantic != declared_non_semantic:
            errors.append(
                f"{screen_id}: non-semantic mapped count {mapped_non_semantic} "
                f"!= {declared_non_semantic}"
            )
        if screen.get("interaction_count") != declared_count + (declared_non_semantic or 0):
            errors.append(f"{screen_id}: interaction count is not semantic plus non-semantic")
        for row in interaction_rows:
            required = {"group", "count", "resolution", "targets", "semantic_control",
                        "keyboard_semantic_conversion"}
            missing = sorted(required - row.keys())
            if missing or row.get("count", 0) < 1 or not row.get("targets"):
                errors.append(f"{screen_id}: incomplete non-semantic row {row!r}")
                continue
            resolution = row["resolution"]
            control = row["semantic_control"]
            conversion = row["keyboard_semantic_conversion"]
            if resolution == "django-route" and (control != "a" or conversion != "replace-with-link"):
                errors.append(f"{screen_id}: route interaction lacks link conversion {row!r}")
            elif resolution == "local-control" and (
                control not in {"button", "label+input"} or
                conversion not in {"replace-with-button", "native-file-input"}
            ):
                errors.append(f"{screen_id}: local interaction lacks keyboard conversion {row!r}")
            elif resolution == "remove" and (control != "remove" or conversion != "remove"):
                errors.append(f"{screen_id}: removed interaction has invalid conversion {row!r}")
            elif resolution not in {"django-route", "local-control", "remove"}:
                errors.append(f"{screen_id}: invalid non-semantic resolution {row!r}")
        for row in screen.get("control_map", []):
            if row.get("count", 0) < 1 or not row.get("resolution") or not row.get("targets"):
                errors.append(f"{screen_id}: incomplete control row {row!r}")
            if any(REMOTE_URL.search(str(target)) for target in row.get("targets", [])):
                errors.append(f"{screen_id}: remote control target {row!r}")
        asset_count = sum(screen.get("remote_assets", {}).values())
        declared_remote = screen.get("remote_occurrences")
        if asset_count != declared_remote:
            errors.append(f"{screen_id}: remote asset count {asset_count} != {declared_remote}")
        control_total += declared_count or 0
        remote_total += declared_remote or 0

    for row in manifest.get("replacement_requirements", []):
        required = {"kind", "remote", "resolution", "target", "usage", "license", "checksum"}
        missing = sorted(required - row.keys())
        if missing:
            errors.append(f"replacement {row.get('kind', '<missing>')}: missing {missing}")
        if REMOTE_URL.search(str(row.get("target", ""))):
            errors.append(f"replacement {row.get('kind')}: remote target")

    summary = manifest.get("summary", {})
    expected_summary = {
        "source_files": len(screens),
        "controls": control_total,
        "interactions": sum(screen.get("interaction_count", 0) for screen in screens),
        "remote_occurrences": remote_total,
        "unresolved_rows": 0,
        "runtime_remote_urls": 0,
    }
    for key, expected in expected_summary.items():
        if summary.get(key) != expected:
            errors.append(f"summary {key}: {summary.get(key)!r} != {expected!r}")

    serialized = json.dumps(manifest, ensure_ascii=False)
    for marker in FORBIDDEN_MARKERS:
        if marker in serialized:
            errors.append(f"forbidden unresolved marker: {marker}")
    return errors


def _validate_sources(manifest: dict[str, Any], source_root: Path) -> list[str]:
    errors: list[str] = []
    for screen in manifest["screens"]:
        source_path = source_root / screen["source"]
        if not source_path.is_file():
            errors.append(f"{screen['id']}: missing source {source_path}")
            continue
        raw = source_path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != screen["source_sha256"]:
            errors.append(f"{screen['id']}: source SHA-256 changed: {digest}")
        text = raw.decode("utf-8")
        inventory = SourceInventory()
        inventory.feed(text)
        if inventory.control_tags != screen["control_tags"]:
            errors.append(
                f"{screen['id']}: controls changed: {inventory.control_tags!r} "
                f"!= {screen['control_tags']!r}"
            )
        if inventory.non_semantic_interactions != screen["non_semantic_interaction_count"]:
            errors.append(
                f"{screen['id']}: non-semantic interactions changed: "
                f"{inventory.non_semantic_interactions} "
                f"!= {screen['non_semantic_interaction_count']}"
            )
        if inventory.icons != set(screen["icons"]):
            errors.append(
                f"{screen['id']}: live icons changed: {sorted(inventory.icons)!r} "
                f"!= {screen['icons']!r}"
            )
        remote_count = len(REMOTE_URL.findall(text))
        if remote_count != screen["remote_occurrences"]:
            errors.append(
                f"{screen['id']}: remote occurrence count changed: "
                f"{remote_count} != {screen['remote_occurrences']}"
            )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("docs/report/stitch-ui-manifest.json"),
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        help="Optional stitch_ directory containing _1/code.html through _7/code.html.",
    )
    args = parser.parse_args()

    manifest = _load(args.manifest)
    errors = _validate_contract(manifest)
    if args.source_root is not None:
        errors.extend(_validate_sources(manifest, args.source_root))
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    mode = "contract+sources" if args.source_root is not None else "contract"
    print(
        "PASS: G6R-1 Stitch manifest "
        f"({mode}, {manifest['summary']['source_files']} sources, "
        f"{manifest['summary']['controls']} controls, "
        f"{manifest['summary']['interactions']} interactions, "
        f"{manifest['summary']['remote_occurrences']} remote occurrences, "
        "0 unresolved, 0 runtime remote URLs)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
