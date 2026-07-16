from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).parents[2]
RENDER_SCRIPT = ROOT / "scripts" / "render-report.sh"
TOOLCHAIN_LOCK = ROOT / "docs" / "report" / "toolchain.lock.md"
IMAGE_PATTERN = re.compile(
    r"^[a-z0-9./_-]+@sha256:[0-9a-f]{64}$"
)


class RendererContractTests(unittest.TestCase):
    def test_renderer_pin_is_immutable_or_gate_is_explicitly_blocked(self) -> None:
        lock = TOOLCHAIN_LOCK.read_text(encoding="utf-8")
        blocked = bool(re.search(r"\*\*Gate status:\*\*\s*BLOCK", lock))
        match = re.search(
            r"^- Renderer OCI image \(linux/amd64\): "
            r"`([a-z0-9./_-]+@sha256:[0-9a-f]{64})`$",
            lock,
            re.MULTILINE,
        )

        if blocked:
            self.assertIsNone(match, "blocked gate must not publish an active renderer pin")
        else:
            self.assertIsNotNone(match, "renderer OCI image is not recorded")
            assert match is not None
            self.assertRegex(match.group(1), IMAGE_PATTERN)
            self.assertIn("--platform linux/amd64", RENDER_SCRIPT.read_text(encoding="utf-8"))

    def test_inventory_contract_is_complete_or_gate_stays_blocked(self) -> None:
        lock = TOOLCHAIN_LOCK.read_text(encoding="utf-8")
        required_components = (
            "Pandoc",
            "WeasyPrint",
            "Mermaid CLI",
            "Noto Sans CJK KR",
            "Noto Sans Mono CJK KR",
            "qpdf",
            "Poppler",
        )
        inventory_match = re.search(
            r"^- Renderer inventory SHA-256: `([0-9a-f]{64})`$",
            lock,
            re.MULTILINE,
        )
        blocked = bool(re.search(r"\*\*Gate status:\*\*\s*BLOCK", lock))

        for component in required_components:
            with self.subTest(component=component):
                self.assertIn(component.casefold(), lock.casefold())

        if blocked:
            self.assertIsNone(
                inventory_match,
                "blocked gate must not publish an unmeasured inventory hash",
            )
        else:
            self.assertIsNotNone(inventory_match, "renderer inventory hash is absent")
            self.assertRegex(
                lock,
                r"(?i)inventory hash covers[^.\n]*every required version"
                r"[^.\n]*executable/package/font byte hash",
            )

    def test_renderer_is_offline_and_has_no_kroki_fallback(self) -> None:
        script = RENDER_SCRIPT.read_text(encoding="utf-8")
        lock = TOOLCHAIN_LOCK.read_text(encoding="utf-8")

        self.assertIn("--pull=never", script)
        self.assertIn("--network none", script)
        self.assertIn("--read-only", script)
        self.assertIn("--cap-drop ALL", script)
        self.assertIn("/renderer/inspect", script)
        self.assertNotRegex(script.lower(), r"https?://|\bcurl\b|\bwget\b")
        self.assertNotIn("kroki_url", script.lower())
        self.assertRegex(lock.lower(), r"mermaid[^\n]*local")
        self.assertNotRegex(lock.lower(), r"kroki[^\n]*(fallback|enabled)")

    def test_tracked_public_files_exclude_private_artifacts_and_absolute_paths(self) -> None:
        tracked_result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
        tracked = [
            ROOT / item.decode("utf-8")
            for item in tracked_result.stdout.split(b"\0")
            if item
        ]
        forbidden_path_parts = (".evidence-private", "private-submission")
        private_home = (Path.home().as_posix().rstrip("/") + "/").encode("utf-8")

        for path in tracked:
            relative = path.relative_to(ROOT).as_posix()
            with self.subTest(path=relative):
                self.assertFalse(
                    any(part in relative for part in forbidden_path_parts),
                    f"private artifact is tracked: {relative}",
                )
                if path.is_file():
                    self.assertNotIn(
                        private_home,
                        path.read_bytes(),
                        f"absolute private path in tracked file: {relative}",
                    )

    def test_repeat_render_orchestration_is_byte_stable_and_offline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            checkout = Path(temporary_directory) / "checkout"
            shutil.copytree(
                ROOT,
                checkout,
                ignore=shutil.ignore_patterns(".git", ".gjc", "dist", "__pycache__"),
            )
            (checkout / ".gitignore").write_text("dist/\n", encoding="utf-8")
            fixture_lock = checkout / "docs" / "report" / "toolchain.lock.md"
            fixture_lock_text = fixture_lock.read_text(encoding="utf-8")
            if not re.search(
                r"^- Renderer OCI image \(linux/amd64\): "
                r"`[^`]+@sha256:[0-9a-f]{64}`$",
                fixture_lock_text,
                re.MULTILINE,
            ):
                fixture_lock.write_text(
                    fixture_lock_text
                    + "\n- Renderer OCI image (linux/amd64): "
                    + "`example.invalid/report-renderer@sha256:"
                    + ("0" * 64)
                    + "`\n",
                    encoding="utf-8",
                )
            if not re.search(
                r"^- Renderer inventory SHA-256: `[0-9a-f]{64}`$",
                fixture_lock.read_text(encoding="utf-8"),
                re.MULTILINE,
            ):
                fixture_lock.write_text(
                    fixture_lock.read_text(encoding="utf-8")
                    + "- Renderer inventory SHA-256: `"
                    + ("1" * 64)
                    + "`\n",
                    encoding="utf-8",
                )
            fixture_metadata = checkout / "report" / "metadata.yaml"
            fixture_metadata_text = fixture_metadata.read_text(encoding="utf-8")
            fixture_metadata_text = re.sub(
                r"^date:.*$", "date: 1970-01-01", fixture_metadata_text, flags=re.MULTILINE
            )
            if not re.search(r"^release-sha:", fixture_metadata_text, re.MULTILINE):
                fixture_metadata_text += "release-sha: RELEASE_SHA\n"
            fixture_metadata.write_text(fixture_metadata_text, encoding="utf-8")
            fake_bin = checkout / "fake-bin"
            fake_bin.mkdir()
            docker_log = Path(temporary_directory) / "docker.log"
            self._write_executable(
                fake_bin / "docker",
                """\
                #!/usr/bin/env python3
                import os
                from pathlib import Path
                import sys

                arguments = sys.argv[1:]
                image = (
                    "example.invalid/report-renderer@sha256:" + ("0" * 64)
                )
                Path(os.environ["DOCKER_LOG"]).open("a", encoding="utf-8").write(
                    " ".join(arguments) + "\\n"
                )
                if arguments[:2] == ["image", "inspect"]:
                    if "--format" in arguments:
                        print(image)
                    raise SystemExit(0)
                if arguments[:2] != ["run", "--rm"] or "--network" not in arguments:
                    raise SystemExit("unexpected docker invocation")
                network_index = arguments.index("--network")
                if arguments[network_index + 1] != "none":
                    raise SystemExit("renderer network must be disabled")
                if "/renderer/render" in arguments:
                    output_mount = next(
                        arguments[index + 1]
                        for index, argument in enumerate(arguments)
                        if argument == "-v"
                        and arguments[index + 1].endswith(":/out/report.pdf:rw")
                    )
                    Path(output_mount.removesuffix(":/out/report.pdf:rw")).write_bytes(
                        b"%PDF-1.4\\n% deterministic fixture\\n"
                    )
                """,
            )
            subprocess.run(["git", "init", "-q"], cwd=checkout, check=True)
            subprocess.run(
                ["git", "config", "user.email", "renderer-test@example.invalid"],
                cwd=checkout,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Renderer Test"],
                cwd=checkout,
                check=True,
            )
            subprocess.run(["git", "add", "."], cwd=checkout, check=True)
            subprocess.run(
                ["git", "commit", "-qm", "renderer fixture"], cwd=checkout, check=True
            )
            release_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=checkout,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            subprocess.run(
                ["git", "tag", "v0.0.0-rc.1"], cwd=checkout, check=True
            )
            environment = os.environ.copy()
            environment.update(
                {
                    "PATH": f"{fake_bin}:{environment['PATH']}",
                    "DOCKER_LOG": str(docker_log),
                }
            )

            outputs: list[bytes] = []
            for _ in range(2):
                completed = subprocess.run(
                    [
                        "bash",
                        "scripts/render-report.sh",
                        "--release-sha",
                        release_sha,
                        "--output",
                        "dist/secure-coding-report-generic.pdf",
                    ],
                    cwd=checkout,
                    env=environment,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(
                    0,
                    completed.returncode,
                    f"render failed:\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
                )
                self.assertRegex(completed.stdout, r"[0-9a-f]{64}")
                outputs.append(
                    (checkout / "dist" / "secure-coding-report-generic.pdf").read_bytes()
                )

            self.assertEqual(outputs[0], outputs[1])
            invocations = docker_log.read_text(encoding="utf-8").splitlines()
            self.assertEqual(8, len(invocations))
            run_invocations = [line for line in invocations if line.startswith("run --rm")]
            self.assertEqual(4, len(run_invocations))
            self.assertTrue(all("--pull=never" in line for line in run_invocations))
            self.assertTrue(all("--network none" in line for line in run_invocations))

    @staticmethod
    def _write_executable(path: Path, content: str) -> None:
        path.write_text(textwrap.dedent(content), encoding="utf-8")
        path.chmod(0o755)


if __name__ == "__main__":
    unittest.main()
