from __future__ import annotations

import subprocess
from pathlib import Path
import unittest


class RepositoryBoundaryTests(unittest.TestCase):
    def test_only_project_skills_are_tracked_under_gjc(self) -> None:
        result = subprocess.run(
            ["git", "ls-files", "-z", ".gjc"],
            check=True,
            capture_output=True,
        )
        tracked = [
            path.decode("utf-8")
            for path in result.stdout.split(b"\0")
            if path
        ]
        unexpected = [
            path for path in tracked if not path.startswith(".gjc/skills/")
        ]
        self.assertEqual([], unexpected, f"tracked GJC runtime state: {unexpected}")

    def test_runtime_state_paths_are_ignored(self) -> None:
        samples = [
            ".gjc/state/sdk/session.json",
            ".gjc/_session-example/state/team/config.json",
        ]
        for sample in samples:
            with self.subTest(sample=sample):
                result = subprocess.run(
                    ["git", "check-ignore", "--quiet", sample],
                    check=False,
                )
                self.assertEqual(0, result.returncode, f"not ignored: {sample}")

    def test_trusted_workflow_checks_out_pr_bytes_without_executing_them(self) -> None:
        workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

        self.assertIn("\n  pull_request_target:\n", workflow)
        self.assertIn("\n  pull_request:\n", workflow)
        self.assertIn(
            "github.event.pull_request.head.repo.full_name || github.repository",
            workflow,
        )
        self.assertIn(
            "github.event.pull_request.head.sha || github.sha",
            workflow,
        )
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("'governance-trusted' || 'governance'", workflow)
        self.assertNotIn("python3 scripts/", workflow)
        self.assertNotIn("pip install", workflow)
        self.assertLess(
            workflow.index("Reject secret-scanner bypass configuration"),
            workflow.index("ghcr.io/gitleaks/gitleaks@sha256:"),
        )
        self.assertNotIn("gitleaks/gitleaks-action@", workflow)


if __name__ == "__main__":
    unittest.main()
