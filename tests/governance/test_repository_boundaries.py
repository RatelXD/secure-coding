from __future__ import annotations

import subprocess
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


if __name__ == "__main__":
    unittest.main()
