#!/usr/bin/env python3
"""Verify G1 provenance and the user-approved documented self-review gate.

The JSON receipt deliberately excludes credentials and the source PDF's local path.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

TEMPLATE_REPOSITORY = "ChosunUniv2026Capstone/Backend"
TEMPLATE_COMMIT = "e1e524bcff217999044ca6db3da65eedf990e5e5"
TEMPLATE_BLOB = "8e4fed1229b1a12d7090c23222230917db738e18"
TEMPLATE_PATH = ".github/pull_request_template.md"
DEFAULT_REQUIRED_CHECKS = ("governance",)
TEMPLATE_SECTIONS = (
    "## Why",
    "## What changed",
    "## Docs consulted",
    "## Docs updated",
    "## Tests / validation",
    "## Migration / rollback",
    "## Screenshots (UI only)",
    "## Open questions / follow-ups",
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decode_github_base64(content: str) -> bytes:
    compact = "".join(content.split())
    return base64.b64decode(compact, validate=True)


def http_bytes(url: str, *, accept: str | None = None) -> bytes:
    headers = {"User-Agent": "secure-coding-g1-verifier/1"}
    if accept:
        headers["Accept"] = accept
    with urlopen(Request(url, headers=headers), timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status} for {url}")
        return response.read()


def http_json(url: str) -> Any:
    return json.loads(http_bytes(url, accept="application/vnd.github+json"))


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, capture_output=True, text=True)


def check_template() -> dict[str, Any]:
    encoded_path = quote(TEMPLATE_PATH, safe="/")
    contents_url = (
        f"https://api.github.com/repos/{TEMPLATE_REPOSITORY}/contents/"
        f"{encoded_path}?ref={TEMPLATE_COMMIT}"
    )
    raw_url = (
        f"https://raw.githubusercontent.com/{TEMPLATE_REPOSITORY}/"
        f"{TEMPLATE_COMMIT}/{TEMPLATE_PATH}"
    )
    blob_url = (
        f"https://api.github.com/repos/{TEMPLATE_REPOSITORY}/git/blobs/{TEMPLATE_BLOB}"
    )
    tree_url = (
        f"https://api.github.com/repos/{TEMPLATE_REPOSITORY}/git/trees/"
        f"{TEMPLATE_COMMIT}?recursive=1"
    )

    contents = http_json(contents_url)
    blob = http_json(blob_url)
    raw = http_bytes(raw_url)
    if contents.get("encoding") != "base64" or blob.get("encoding") != "base64":
        raise ValueError("GitHub content encoding is not base64")
    content_bytes = decode_github_base64(contents["content"])
    blob_bytes = decode_github_base64(blob["content"])
    tree = http_json(tree_url).get("tree", [])
    tree_entry = next((item for item in tree if item.get("path") == TEMPLATE_PATH), None)
    hashes = {
        "commit_file": sha256(content_bytes),
        "raw": sha256(raw),
        "api_blob_decoded": sha256(blob_bytes),
    }
    lengths = {
        "commit_file": len(content_bytes),
        "raw": len(raw),
        "api_blob_decoded": len(blob_bytes),
    }
    text = raw.decode("utf-8")
    return {
        "passed": (
            len(set(hashes.values())) == 1
            and len(set(lengths.values())) == 1
            and contents.get("sha") == TEMPLATE_BLOB
            and blob.get("sha") == TEMPLATE_BLOB
            and tree_entry is not None
            and tree_entry.get("sha") == TEMPLATE_BLOB
            and all(section in text for section in TEMPLATE_SECTIONS)
        ),
        "commit": TEMPLATE_COMMIT,
        "blob": TEMPLATE_BLOB,
        "encoding": {"contents": contents.get("encoding"), "blob": blob.get("encoding")},
        "hashes": hashes,
        "lengths": lengths,
        "tree_blob": tree_entry.get("sha") if tree_entry else None,
        "required_sections": {section: section in text for section in TEMPLATE_SECTIONS},
    }


def check_pdf(source_pdf: Path) -> dict[str, Any]:
    data = source_pdf.read_bytes()
    info = run(["pdfinfo", os.fspath(source_pdf)])
    page25 = run(["pdftotext", "-f", "25", "-l", "25", "-layout", os.fspath(source_pdf), "-"])
    page35 = run(["pdftotext", "-f", "35", "-l", "35", "-layout", os.fspath(source_pdf), "-"])
    page25_anchors = (
        "사람들이 플랫폼에 가입할 수 있어야 함",
        "상품들을 올리고 볼 수 있어야 함",
        "플랫폼 사용자들끼리 소통이 가능해야함",
        "악성 유저나 상품을 차단 해야 함",
    )
    page35_anchors = (
        "24page",
        "유저들 간의 송금이 가능해야함",
        "상품의 검색할 수 있어야 함",
        "관리자가 플랫폼의 모든 요소를 관리할 수 있어야 함",
    )
    pages_line = next((line for line in info.stdout.splitlines() if line.startswith("Pages:")), "")
    return {
        "passed": (
            info.returncode == 0
            and page25.returncode == 0
            and page35.returncode == 0
            and pages_line.split(":", 1)[-1].strip() == "36"
            and all(anchor in page25.stdout for anchor in page25_anchors)
            and all(anchor in page35.stdout for anchor in page35_anchors)
        ),
        "source_id": "SRC-PDF-001",
        "basename": source_pdf.name,
        "byte_size": len(data),
        "sha256": sha256(data),
        "page_count": pages_line.split(":", 1)[-1].strip() or None,
        "physical_page_25_anchors": {anchor: anchor in page25.stdout for anchor in page25_anchors},
        "physical_page_35_anchors": {anchor: anchor in page35.stdout for anchor in page35_anchors},
        "tools": {"pdfinfo_exit": info.returncode, "pdftotext_exit": [page25.returncode, page35.returncode]},
    }


def gh_json(arguments: list[str]) -> tuple[Any | None, str | None]:
    result = run(["gh", *arguments])
    if result.returncode != 0:
        return None, result.stderr.strip() or result.stdout.strip()
    return json.loads(result.stdout), None


def check_github(
    repository: str,
    *,
    pull_request: int | None,
    expected_required_checks: tuple[str, ...],
) -> dict[str, Any]:
    repo, repo_error = gh_json([
        "repo", "view", repository, "--json",
        "nameWithOwner,isPrivate,defaultBranchRef,viewerPermission,mergeCommitAllowed,"
        "rebaseMergeAllowed,squashMergeAllowed,deleteBranchOnMerge,url",
    ])
    collaborators, collaborators_error = gh_json([
        "api", f"repos/{repository}/collaborators?affiliation=direct&per_page=100",
    ])
    protection, protection_error = gh_json(["api", f"repos/{repository}/branches/main/protection"])
    pages, pages_error = gh_json(["api", f"repos/{repository}/pages"])
    environment, environment_error = gh_json(["api", f"repos/{repository}/environments/release"])
    actions, actions_error = gh_json(["api", f"repos/{repository}/actions/permissions"])
    actor, actor_error = gh_json(["api", "user"])
    pr: Any | None = None
    pr_error: str | None = "pull request number is required"
    comments: Any | None = None
    comments_error: str | None = "pull request number is required"
    if pull_request is not None:
        pr, pr_error = gh_json([
            "pr", "view", str(pull_request), "--repo", repository, "--json",
            "number,state,baseRefName,headRefOid,author,reviewDecision,reviews,"
            "reviewRequests,statusCheckRollup,url",
        ])
        comments, comments_error = gh_json([
            "api", f"repos/{repository}/issues/{pull_request}/comments?per_page=100",
        ])

    actor_login = (actor or {}).get("login")
    collaborator_logins = [item.get("login") for item in collaborators or []]
    rules = (environment or {}).get("protection_rules", [])
    reviewer_rules = [rule for rule in rules if rule.get("type") == "required_reviewers"]
    reviewers = [
        reviewer.get("reviewer", {}).get("login")
        for rule in reviewer_rules
        for reviewer in rule.get("reviewers", [])
    ]
    independent_reviewer_available = bool(actor_login) and any(
        login != actor_login for login in collaborator_logins
    )
    environment_self_review_allowed = (
        bool(actor_login)
        and bool(reviewer_rules)
        and actor_login in reviewers
        and all(rule.get("prevent_self_review") is False for rule in reviewer_rules)
        and (environment or {}).get("can_admins_bypass") is False
    )
    pull_request_reviews = (protection or {}).get("required_pull_request_reviews") or {}
    status_checks = (protection or {}).get("required_status_checks") or {}
    branch_rules_complete = (
        not pull_request_reviews
        and (protection or {}).get("enforce_admins", {}).get("enabled") is True
        and (protection or {}).get("required_linear_history", {}).get("enabled") is True
        and (protection or {}).get("allow_force_pushes", {}).get("enabled") is False
        and (protection or {}).get("allow_deletions", {}).get("enabled") is False
    )
    configured_checks = status_checks.get("checks") or []
    configured_contexts = {
        item.get("context") if isinstance(item, dict) else item
        for item in configured_checks
    }
    configured_contexts.discard(None)
    expected_contexts = set(expected_required_checks)
    exact_required_checks = (
        status_checks.get("strict") is True
        and bool(expected_contexts)
        and configured_contexts == expected_contexts
    )

    head_sha = (pr or {}).get("headRefOid")
    self_review_marker = f"G1-SELF-REVIEW: APPROVED head={head_sha}"
    self_review_comments = [
        comment for comment in comments or []
        if comment.get("user", {}).get("login") == actor_login
        and self_review_marker in comment.get("body", "")
    ]
    documented_self_review = (
        bool(pr)
        and pr.get("state") == "OPEN"
        and pr.get("baseRefName") == "main"
        and bool(head_sha)
        and bool(self_review_comments)
    )
    pr_check_runs = {
        item.get("name"): item.get("conclusion")
        for item in (pr or {}).get("statusCheckRollup", [])
        if item.get("__typename", "CheckRun") == "CheckRun"
    }
    pr_required_checks_passed = (
        bool(expected_contexts)
        and all(pr_check_runs.get(context) == "SUCCESS" for context in expected_contexts)
    )

    checks = {
        "public": bool(repo) and repo.get("isPrivate") is False,
        "admin_write": bool(repo) and repo.get("viewerPermission") == "ADMIN",
        "default_main": bool(repo) and repo.get("defaultBranchRef", {}).get("name") == "main",
        "squash_only": bool(repo) and repo.get("squashMergeAllowed") is True
        and repo.get("mergeCommitAllowed") is False and repo.get("rebaseMergeAllowed") is False,
        "branch_protected": protection is not None,
        "branch_rules_complete": branch_rules_complete,
        "required_status_checks_exact": exact_required_checks,
        "documented_self_review": documented_self_review,
        "pr_required_checks_passed": pr_required_checks_passed,
        "pages_public_workflow_https": bool(pages) and pages.get("public") is True
        and pages.get("build_type") == "workflow" and pages.get("https_enforced") is True,
        "release_environment_self_review_allowed": environment_self_review_allowed,
        "actions_enabled": bool(actions) and actions.get("enabled") is True,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "review_mode": "documented-self-review",
        "authenticated_actor": actor_login,
        "collaborators": collaborator_logins,
        "independent_reviewer_available": independent_reviewer_available,
        "release_reviewers": reviewers,
        "release_can_admins_bypass": (environment or {}).get("can_admins_bypass"),
        "required_status_checks": {
            "expected": sorted(expected_contexts),
            "configured": sorted(configured_contexts),
            "strict": status_checks.get("strict"),
        },
        "pull_request": {
            "number": (pr or {}).get("number"),
            "url": (pr or {}).get("url"),
            "head_sha": head_sha,
            "review_decision": (pr or {}).get("reviewDecision"),
            "self_review_marker": self_review_marker,
            "self_review_comment_ids": sorted(
                comment.get("id") for comment in self_review_comments if comment.get("id") is not None
            ),
            "check_runs": pr_check_runs,
        },
        "errors": {
            key: value for key, value in {
                "repository": repo_error,
                "actor": actor_error,
                "collaborators": collaborators_error,
                "branch_protection": protection_error,
                "pages": pages_error,
                "release_environment": environment_error,
                "actions": actions_error,
                "pull_request": pr_error,
                "pull_request_comments": comments_error,
            }.items() if value
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-pdf", required=True, type=Path)
    parser.add_argument("--repository", default="RatelXD/secure-coding")
    parser.add_argument("--pull-request", type=int)
    parser.add_argument(
        "--required-check",
        action="append",
        dest="required_checks",
        help="Exact required Actions check context; repeat for multiple contexts",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    receipt: dict[str, Any] = {"schema_version": 1}
    try:
        receipt["pdf_provenance"] = check_pdf(args.source_pdf)
        receipt["template_provenance"] = check_template()
        receipt["github_governance"] = check_github(
            args.repository,
            pull_request=args.pull_request,
            expected_required_checks=tuple(args.required_checks or DEFAULT_REQUIRED_CHECKS),
        )
    except Exception as error:  # fail closed with a serializable receipt
        receipt["verification_error"] = f"{type(error).__name__}: {error}"
    components = [value.get("passed", False) for value in receipt.values() if isinstance(value, dict)]
    receipt["gate"] = "PASS" if len(components) == 3 and all(components) else "BLOCK"
    rendered = json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 0 if receipt["gate"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
