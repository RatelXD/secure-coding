from __future__ import annotations

import json
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
RENDER_DOCKERFILE = ROOT / "report" / "renderer" / "Dockerfile"
RENDER_INVENTORY = ROOT / "report" / "renderer" / "inventory.py"
RENDER_REQUIREMENTS = ROOT / "report" / "renderer" / "requirements.txt"
RENDER_NPM_LOCK = ROOT / "report" / "renderer" / "npm" / "package-lock.json"
RENDER_WORKFLOW = ROOT / ".github" / "workflows" / "report-renderer-image.yml"


class RendererContractTests(unittest.TestCase):
    def test_toolchain_status_is_optional_and_non_gating(self) -> None:
        lock = TOOLCHAIN_LOCK.read_text(encoding="utf-8")

        self.assertRegex(lock, r"\*\*Status:\*\*\s*OPTIONAL / NON-GATING")
        self.assertIn(
            "Generated PDF output, renderer publication, OCI attestations, "
            "and renderer receipts are not G1 or G8a requirements",
            lock,
        )
        self.assertIn(
            "PDF generation, image publication, repository digests, "
            "inventory receipts, and repeat renders are not required for G1 or G8a",
            lock,
        )
        self.assertNotRegex(lock, r"\*\*Gate status:\*\*\s*BLOCK")

    def test_optional_inventory_contract_remains_documented(self) -> None:
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

        for component in required_components:
            with self.subTest(component=component):
                self.assertIn(component.casefold(), lock.casefold())

        self.assertIn("## Optional published-image format", lock)
        self.assertIn("No image publication is required or currently configured.", lock)

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

    def test_renderer_mounts_only_a_tracked_report_allowlist(self) -> None:
        script = RENDER_SCRIPT.read_text(encoding="utf-8")

        self.assertNotIn('$PWD:/work', script)
        self.assertIn('$stage:/work:ro', script)
        self.assertIn('path.parent == Path("docs/report")', script)
        self.assertIn(
            'name in ("report/metadata.yaml", "report/pdf.css")',
            script,
        )
        self.assertIn('".gjc/_session-"', script)
        self.assertIn('"/.gjc/_session-"', script)
        for private_name in (".git", ".gjc/state", ".evidence-private", "private-submission"):
            with self.subTest(private_name=private_name):
                self.assertNotRegex(
                    script,
                    rf'-v\s+"?[^"\n]*{re.escape(private_name)}[^"\n]*:/work',
                )

    def test_output_bind_source_is_precreated(self) -> None:
        script = RENDER_SCRIPT.read_text(encoding="utf-8")
        before_first_run = script.split("docker run", 1)[0]

        self.assertRegex(
            before_first_run,
            r'(?:touch|install\s+-m\s+\d+|:\s*>)\s+"?\$tmp_output"?',
        )
        self.assertRegex(before_first_run, r'chmod\s+0600\s+"\$tmp_output"')

    def test_optional_build_uses_pinned_integrity_inputs(self) -> None:
        dockerfile = RENDER_DOCKERFILE.read_text(encoding="utf-8")
        requirements = RENDER_REQUIREMENTS.read_text(encoding="utf-8")
        npm_lock = json.loads(RENDER_NPM_LOCK.read_text(encoding="utf-8"))

        self.assertRegex(
            dockerfile.splitlines()[0],
            r"^FROM [^@\s]+@sha256:[0-9a-f]{64}$",
        )
        self.assertIn("npm ci", dockerfile)
        self.assertIn("QPDF_SHA256=", dockerfile)
        self.assertIn("--require-hashes", dockerfile)
        self.assertTrue(
            all(
                "--hash=sha256:" in line
                for line in requirements.splitlines()
                if line.strip() and not line.lstrip().startswith(("#", "--hash"))
            )
        )
        self.assertTrue(
            all(
                "integrity" in package
                for package in npm_lock.get("packages", {}).values()
                if package.get("resolved")
            )
        )

    def test_optional_inventory_records_complete_local_provenance(self) -> None:
        inventory = RENDER_INVENTORY.read_text(encoding="utf-8")

        for marker in (
            "importlib.metadata.distributions",
            "mermaid_package_tree",
            "fontRevision",
            '"Noto Sans CJK KR", "Noto Sans Mono CJK KR"',
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, inventory)

    def test_optional_image_has_no_repository_publication_workflow(self) -> None:
        lock = TOOLCHAIN_LOCK.read_text(encoding="utf-8")

        self.assertFalse(RENDER_WORKFLOW.exists())
        self.assertIn("No repository workflow publishes this optional utility", lock)
        self.assertIn("no package permission or attestation is required", lock)

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
