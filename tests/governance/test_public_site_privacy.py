from __future__ import annotations

import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_public_site.py"
SPEC = importlib.util.spec_from_file_location("check_public_site", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
find_private_material = MODULE.find_private_material


class PublicSitePrivacyTests(unittest.TestCase):
    def write(self, root: Path, relative: str, content: bytes) -> None:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def test_vendor_css_cookie_selector_is_not_a_credential(self) -> None:
        with TemporaryDirectory() as temporary:
            site = Path(temporary)
            self.write(
                site,
                "css/fontawesome.min.css",
                b".fa-cookie:before{content:'\\f563'}.authorization:after{display:none}",
            )

            self.assertEqual([], find_private_material(site))

    def test_actual_authorization_and_cookie_values_are_rejected(self) -> None:
        samples = {
            "authorization": b"Authorization" + b": Bearer " + (b"a" * 32),
            "cookie": b"Cookie" + b": sessionid=" + (b"b" * 32),
        }
        for name, content in samples.items():
            with self.subTest(name=name), TemporaryDirectory() as temporary:
                site = Path(temporary)
                self.write(site, "index.html", content)

                findings = find_private_material(site)
                self.assertEqual(1, len(findings))
                self.assertIn(f"{name} credential", findings[0])


    def test_highlighted_html_and_search_json_credentials_are_rejected(self) -> None:
        samples = {
            "index.html": (
                b"<span>Authorization</span><span>:</span><span>Bearer</span>"
                + b"<span>"
                + (b"a" * 32)
                + b"</span>"
            ),
            "search/search_index.json": (
                b'{"text":"<span>Cookie</span><span>:</span>'
                + b'<span>sessionid=</span><span>'
                + (b"b" * 32)
                + b'</span>"}'
            ),
        }
        for relative, content in samples.items():
            with self.subTest(relative=relative), TemporaryDirectory() as temporary:
                site = Path(temporary)
                self.write(site, relative, content)

                self.assertTrue(find_private_material(site))


    def test_private_markers_are_rejected(self) -> None:
        samples = {
            "home": b"/home/student/private/report.pdf",
            "ngrok": b"https://temporary-123.ngrok-free.app",
            "environment": b"LMS_" + b"PASSWORD=",
        }
        for name, content in samples.items():
            with self.subTest(name=name), TemporaryDirectory() as temporary:
                site = Path(temporary)
                self.write(site, "index.html", content)

                self.assertTrue(find_private_material(site))

    def test_private_paths_and_symbolic_links_are_rejected(self) -> None:
        with TemporaryDirectory() as temporary:
            site = Path(temporary)
            self.write(site, "private-submission/report.html", b"private")
            (site / "outside.txt").write_text("outside", encoding="utf-8")
            (site / "linked.txt").symlink_to(site / "outside.txt")

            findings = find_private_material(site)
            self.assertIn("private path: private-submission/report.html", findings)
            self.assertIn("symbolic link: linked.txt", findings)

    def test_missing_site_root_fails_closed(self) -> None:
        with TemporaryDirectory() as temporary:
            missing = Path(temporary) / "missing"

            self.assertEqual(
                [f"site root is not a directory: {missing}"],
                find_private_material(missing),
            )


if __name__ == "__main__":
    unittest.main()
