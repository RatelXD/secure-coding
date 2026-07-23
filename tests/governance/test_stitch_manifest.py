from __future__ import annotations

import hashlib
import json
import copy
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ET


MANIFEST = Path("docs/report/stitch-ui-manifest.json")
SPEC = importlib.util.spec_from_file_location(
    "verify_stitch_manifest", Path("scripts/verify_stitch_manifest.py")
)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class StitchManifestGovernanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_manifest_validator_reports_closed_g6r_1_contract(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/verify_stitch_manifest.py"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("7 sources", result.stdout)
        expected_controls = sum(
            screen["control_count"] for screen in self.manifest["screens"]
        )
        expected_interactions = sum(
            screen["interaction_count"] for screen in self.manifest["screens"]
        )
        self.assertIn(f"{expected_controls} controls", result.stdout)
        self.assertIn(f"{expected_interactions} interactions", result.stdout)
        self.assertIn("0 unresolved, 0 runtime remote URLs", result.stdout)

    def test_all_seven_sources_have_exact_checksums_and_complete_control_maps(self) -> None:
        screens = self.manifest["screens"]
        self.assertEqual(
            [f"_{number}/code.html" for number in range(1, 8)],
            [screen["source"] for screen in screens],
        )
        for screen in screens:
            with self.subTest(screen=screen["id"]):
                self.assertRegex(screen["source_sha256"], r"\A[0-9a-f]{64}\Z")
                self.assertEqual(
                    screen["control_count"],
                    sum(screen["control_tags"].values()),
                )
                self.assertEqual(
                    screen["control_count"],
                    sum(row["count"] for row in screen["control_map"]),
                )
                self.assertEqual(
                    screen["remote_occurrences"],
                    sum(screen["remote_assets"].values()),
                )
                self.assertEqual(
                    screen["interaction_count"],
                    screen["control_count"] + screen["non_semantic_interaction_count"],
                )

    def test_remote_dependencies_have_local_replacement_or_removal_contracts(self) -> None:
        requirements = {
            requirement["kind"]: requirement
            for requirement in self.manifest["replacement_requirements"]
        }
        self.assertEqual(
            {"font", "icon", "toolchain", "logo", "hero", "product", "avatar"},
            requirements.keys(),
        )
        self.assertIn("Korean", requirements["font"]["usage"])
        self.assertRegex(requirements["font"]["checksum"], r"\A[0-9a-f]{64}\Z")
        self.assertEqual("remove", requirements["avatar"]["resolution"])
        for requirement in requirements.values():
            with self.subTest(kind=requirement["kind"]):
                self.assertNotIn("http://", requirement["target"])
                self.assertNotIn("https://", requirement["target"])
                self.assertTrue(requirement["license"])
                self.assertTrue(requirement["checksum"])

    def test_phase_gated_controls_name_authority_instead_of_dead_links(self) -> None:
        rows = [
            row
            for screen in self.manifest["screens"]
            for row in screen["control_map"]
        ]
        self.assertFalse(any("#" in target for row in rows for target in row["targets"]))
        gated = [row for row in rows if row["resolution"].startswith("phase-gated")]
        self.assertTrue(gated)
        for row in gated:
            with self.subTest(group=row["group"]):
                self.assertTrue(
                    all(target.startswith("G7") for target in row["targets"]),
                    row,
                )
        removed = [row for row in rows if row["resolution"] == "remove"]
        self.assertEqual(
            {
                "room menu",
                "attachment action",
                "condition select",
                "public-profile direct chat",
            },
            {row["group"] for row in removed},
        )

    def test_public_profile_excludes_direct_chat_and_retains_user_report(self) -> None:
        public_profile = next(
            screen
            for screen in self.manifest["screens"]
            if screen["id"] == "STITCH-07-PUBLIC-PROFILE"
        )
        public_profile_groups = {
            row["group"] for row in public_profile["control_map"]
        }

        self.assertNotIn("direct chat", public_profile_groups)
        self.assertFalse(
            any(
                "DIRECT Room" in target
                for row in public_profile["control_map"]
                for target in row["targets"]
            )
        )
        self.assertIn("user report", public_profile_groups)

    def test_non_semantic_affordances_are_completely_mapped_with_keyboard_semantics(self) -> None:
        expected_counts = {
            "STITCH-01-HOME": 0,
            "STITCH-02-PRODUCT-LIST": 5,
            "STITCH-03-PRODUCT-DETAIL": 2,
            "STITCH-04-CHAT": 1,
            "STITCH-05-PRODUCT-CREATE": 1,
            "STITCH-06-OWN-PROFILE": 0,
            "STITCH-07-PUBLIC-PROFILE": 5,
        }
        for screen in self.manifest["screens"]:
            with self.subTest(screen=screen["id"]):
                rows = screen.get("non_semantic_interactions", [])
                self.assertEqual(expected_counts[screen["id"]], sum(row["count"] for row in rows))
                for row in rows:
                    self.assertIn(row["resolution"], {"django-route", "local-control", "remove"})
                    self.assertTrue(row["targets"])
                    self.assertTrue(row["semantic_control"])
                    self.assertTrue(row["keyboard_semantic_conversion"])

    def test_validator_rejects_omitted_interactions_and_duplicate_icons(self) -> None:
        omitted = copy.deepcopy(self.manifest)
        omitted["screens"][1]["non_semantic_interactions"] = []
        self.assertTrue(
            any("non-semantic mapped count" in error for error in VALIDATOR._validate_contract(omitted))
        )

        duplicate_icon = copy.deepcopy(self.manifest)
        duplicate_icon["screens"][1]["icons"].append("add_circle")
        self.assertTrue(
            any(
                "icons must be sorted and unique" in error
                for error in VALIDATOR._validate_contract(duplicate_icon)
            )
        )

    def test_validator_rejects_a_stale_summary_after_control_removal(self) -> None:
        stale_summary = copy.deepcopy(self.manifest)
        stale_summary["summary"]["controls"] += 1
        stale_summary["summary"]["interactions"] += 1

        errors = VALIDATOR._validate_contract(stale_summary)

        self.assertTrue(any("summary controls" in error for error in errors))
        self.assertTrue(any("summary interactions" in error for error in errors))

    def test_validator_rejects_a_remote_control_target(self) -> None:
        remote_control = copy.deepcopy(self.manifest)
        remote_control["screens"][0]["control_map"][0]["targets"].append(
            "https://stitch.example.invalid/route"
        )

        errors = VALIDATOR._validate_contract(remote_control)

        self.assertTrue(any("remote control target" in error for error in errors))

    def test_g6r_2_assets_match_checksums_provenance_and_icon_allowlist(self) -> None:
        assets = {
            asset["kind"]: asset
            for asset in self.manifest["installed_assets"]
        }
        self.assertEqual(
            {"font", "license", "icon", "logo", "hero", "product-default"},
            assets.keys(),
        )

        for asset in assets.values():
            with self.subTest(asset=asset["kind"]):
                path = Path(asset["path"])
                self.assertFalse(path.is_absolute())
                self.assertTrue(path.is_file(), path)
                self.assertEqual(
                    asset["sha256"],
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                )
                self.assertTrue(asset["usage_conditions"])
                self.assertTrue(asset["license"])
                self.assertNotIn("://", asset["path"])

        self.assertEqual(b"wOF2", Path(assets["font"]["path"]).read_bytes()[:4])
        self.assertEqual(assets["license"]["path"], assets["font"]["license_path"])
        self.assertEqual(
            assets["license"]["sha256"],
            hashlib.sha256(Path(assets["font"]["license_path"]).read_bytes()).hexdigest(),
        )

        allowed_icons = sorted(
            {icon for screen in self.manifest["screens"] for icon in screen["icons"]}
        )
        self.assertEqual(allowed_icons, assets["icon"]["symbols"])
        sprite = ET.parse(assets["icon"]["path"]).getroot()
        installed_icons = sorted(
            element.attrib["id"]
            for element in sprite.iter()
            if element.tag.rsplit("}", 1)[-1] == "symbol"
        )
        self.assertEqual(allowed_icons, installed_icons)

        for asset in assets.values():
            if Path(asset["path"]).suffix != ".svg":
                continue
            root = ET.parse(asset["path"]).getroot()
            for element in root.iter():
                for attribute in ("href", "src"):
                    value = element.attrib.get(attribute, "")
                    self.assertFalse(value.startswith(("http://", "https://")), value)


if __name__ == "__main__":
    unittest.main()
