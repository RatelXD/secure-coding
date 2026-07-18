#!/usr/bin/env python3
"""Verify the committed CI/browser toolchain contract without network access."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def require_equal(actual: object, expected: object, label: str) -> None:
    if actual != expected:
        raise SystemExit(f"{label}: expected {expected!r}, got {actual!r}")


def require_workflow_pin(workflow: str, name: str, expected: str) -> None:
    match = re.search(rf"^\s*{re.escape(name)}:\s*['\"]?([^'\"\s]+)", workflow, re.MULTILINE)
    if match is None:
        raise SystemExit(f"CI workflow is missing {name}")
    require_equal(match.group(1), expected, f"CI {name} pin")


def main(static: bool) -> None:
    pins = load(".github/toolchain.json")
    package = load("package.json")
    lock = load("package-lock.json")
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    playwright_config = (ROOT / "playwright.config.js").read_text(encoding="utf-8")
    if "push:" in workflow:
        raise SystemExit("required CI must be pull_request-only")
    if not re.search(r"^\s*pull_request:\s*$", workflow, re.MULTILINE):
        raise SystemExit("required CI must declare a pull_request trigger")
    for name, pin in (
        ("PYTHON_VERSION", pins["python"]),
        ("NODE_VERSION", pins["node"]),
        ("UV_VERSION", pins["uv"]),
    ):
        require_workflow_pin(workflow, name, pin)
    if '"uv==${UV_VERSION}"' not in workflow:
        raise SystemExit("CI must install uv using the canonical UV_VERSION pin")
    if not re.search(r"^\s*retries:\s*0,\s*$", playwright_config, re.MULTILINE):
        raise SystemExit("required browser checks must not retry")
    if any(path in workflow for path in ("path: test-results/", "path: playwright-report/")):
        raise SystemExit("required CI must not upload raw Playwright artifacts")

    require_equal(
        (ROOT / ".python-version").read_text(encoding="utf-8").strip(),
        pins["python"],
        "local Python pin",
    )
    require_equal(
        (ROOT / ".node-version").read_text(encoding="utf-8").strip(),
        pins["node"],
        "local Node pin",
    )
    if "pull_request_target" in workflow:
        raise SystemExit("fork-unsafe pull_request_target trigger is forbidden")
    if "secrets." in workflow:
        raise SystemExit("required CI must not consume repository secrets")
    for required_name in (
        "governance-title",
        "unit",
        "integration-postgres-redis",
        "security",
        "migration",
        "browser-a11y",
    ):
        if f"name: {required_name}" not in workflow:
            raise SystemExit(f"missing required CI check: {required_name}")
    image = pins["browserOciImage"]
    pinned_image = (
        f"mcr.microsoft.com/playwright:{image['version']}@{image['digest']}"
    )
    if pinned_image not in workflow:
        raise SystemExit("required browser OCI version+digest is not used by CI")

    require_equal(package["engines"]["node"], pins["node"], "Node pin")
    require_equal(
        package["devDependencies"]["@playwright/test"],
        pins["playwright"],
        "Playwright pin",
    )
    require_equal(
        package["devDependencies"]["@axe-core/playwright"],
        pins["axeCorePlaywright"],
        "axe pin",
    )
    require_equal(lock["lockfileVersion"], 3, "npm lockfile version")
    require_equal(
        lock["packages"]["node_modules/@playwright/test"]["version"],
        pins["playwright"],
        "locked Playwright version",
    )
    require_equal(
        lock["packages"]["node_modules/@axe-core/playwright"]["version"],
        pins["axeCorePlaywright"],
        "locked axe version",
    )

    if static:
        print("static toolchain contract verified")
        return

    browser_file = ROOT / "node_modules/playwright-core/browsers.json"
    if not browser_file.is_file():
        raise SystemExit("installed Playwright Chromium metadata is required")
    browsers = json.loads(browser_file.read_text(encoding="utf-8"))["browsers"]
    try:
        chromium = next(item for item in browsers if item["name"] == "chromium")
    except StopIteration as error:
        raise SystemExit("installed Playwright Chromium metadata is missing chromium") from error
    require_equal(chromium["revision"], pins["chromium"]["revision"], "Chromium revision")
    require_equal(
        chromium["browserVersion"],
        pins["chromium"]["version"],
        "Chromium version",
    )

    print("toolchain contract verified")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--static",
        action="store_true",
        help="verify committed pins without requiring installed browser metadata",
    )
    main(parser.parse_args().static)
