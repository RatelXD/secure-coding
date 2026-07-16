from __future__ import annotations

import base64
import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).parents[2] / "scripts" / "verify_g1.py"
SPEC = importlib.util.spec_from_file_location("verify_g1", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
verify_g1 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify_g1)


class GitHubBlobDecodingTests(unittest.TestCase):
    def test_decodes_rfc4648_content_after_removing_line_breaks(self) -> None:
        expected = b"commit-pinned template bytes\n"
        encoded = base64.b64encode(expected).decode("ascii")
        wrapped = "\n".join(encoded[index:index + 8] for index in range(0, len(encoded), 8))

        self.assertEqual(verify_g1.decode_github_base64(wrapped), expected)

    def test_rejects_non_base64_content(self) -> None:
        with self.assertRaises(ValueError):
            verify_g1.decode_github_base64("not-base64!")

    def test_sha256_is_byte_exact(self) -> None:
        self.assertNotEqual(verify_g1.sha256(b"line\n"), verify_g1.sha256(b"line\r\n"))


class TemplateContractTests(unittest.TestCase):
    def test_preserves_all_approved_source_sections(self) -> None:
        self.assertEqual(
            verify_g1.TEMPLATE_SECTIONS,
            (
                "## Why",
                "## What changed",
                "## Docs consulted",
                "## Docs updated",
                "## Tests / validation",
                "## Migration / rollback",
                "## Screenshots (UI only)",
                "## Open questions / follow-ups",
            ),
        )

    def test_uses_approved_commit_and_blob(self) -> None:
        self.assertEqual(verify_g1.TEMPLATE_COMMIT, "e1e524bcff217999044ca6db3da65eedf990e5e5")
        self.assertEqual(verify_g1.TEMPLATE_BLOB, "8e4fed1229b1a12d7090c23222230917db738e18")


if __name__ == "__main__":
    unittest.main()
