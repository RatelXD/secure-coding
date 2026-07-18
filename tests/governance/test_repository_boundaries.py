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

    def test_pull_request_workflow_is_fork_safe_and_unprivileged(self) -> None:
        workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

        self.assertIn("\n  pull_request:\n", workflow)
        self.assertNotIn("pull_request_target", workflow)
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertNotIn("secrets.", workflow)
        self.assertIn("name: governance-title", workflow)
        for required_check in (
            "name: unit",
            "name: integration-postgres-redis",
            "name: security",
            "name: migration",
            "name: browser-a11y",
        ):
            self.assertIn(required_check, workflow)
        title_step = workflow.split(
            "- name: Resolve and enforce immutable Korean title", 1
        )[1].split("- name: Verify governance and pinned toolchain contracts", 1)[0]
        self.assertNotIn("GITHUB_OUTPUT", title_step)
        self.assertNotIn("steps.title.outputs", title_step)
        self.assertIn("PR_TITLE: ${{ github.event.pull_request.title }}", title_step)
        self.assertIn("validator = runpy.run_path(", title_step)


if __name__ == "__main__":
    unittest.main()
