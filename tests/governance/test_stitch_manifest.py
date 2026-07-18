from __future__ import annotations

import json
import copy
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest


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
        self.assertIn("155 controls", result.stdout)
        self.assertIn("169 interactions", result.stdout)
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
        self.assertIn("SHA-256", requirements["font"]["checksum"])
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
            {"room menu", "attachment action", "condition select"},
            {row["group"] for row in removed},
        )
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


if __name__ == "__main__":
    unittest.main()
