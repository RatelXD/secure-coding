#!/usr/bin/env python3
"""Verify public G1 supply provenance and documented self-review governance."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
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
DEFAULT_REQUIRED_CHECKS = (
    "governance-title",
    "unit",
    "integration-postgres-redis",
    "security",
    "migration",
    "browser-a11y",
)
GITHUB_ACTIONS_APP_ID = 15368
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

RELEASE_STATES = (
    "PR7_MERGED_CANDIDATE",
    "RC_ALLOCATED",
    "RC_QUALIFYING",
    "ATTESTED",
    "FORMAL_PROMOTED",
    "PUBLIC_VERIFIED",
)
TERMINAL_FAILURE_STATE = "RC_FAILED_IMMUTABLE"


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


def check_release_state(receipt: dict[str, Any]) -> dict[str, Any]:
    """Validate the same-SHA monotonic release state machine without mutating it."""
    release_sha = receipt.get("release_sha")
    events = receipt.get("events")
    valid_sha = (
        isinstance(release_sha, str)
        and len(release_sha) == 40
        and all(character in "0123456789abcdef" for character in release_sha)
    )
    errors: list[str] = []
    if not isinstance(events, list) or not events:
        errors.append("events must be a non-empty list")
        events = []
    states: list[str] = []
    terminal_seen = False
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            errors.append(f"event {index} is not an object")
            continue
        state = event.get("state")
        states.append(state)
        if event.get("release_sha") != release_sha:
            errors.append(f"event {index} SHA mismatch")
        if terminal_seen:
            errors.append("events exist after terminal failure")
        if state == TERMINAL_FAILURE_STATE:
            terminal_seen = True
        elif state not in RELEASE_STATES:
            errors.append(f"event {index} has unknown state")
    if states:
        if states[0] != RELEASE_STATES[0]:
            errors.append("state machine must begin at PR7_MERGED_CANDIDATE")
        non_failure = [state for state in states if state != TERMINAL_FAILURE_STATE]
        expected = list(RELEASE_STATES[: len(non_failure)])
        if non_failure != expected:
            errors.append("release states are not monotonic")
    return {
        "passed": valid_sha and not errors,
        "release_sha": release_sha,
        "states": states,
        "terminal_failure": terminal_seen,
        "errors": errors,
    }


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
    actions, actions_error = gh_json(["api", f"repos/{repository}/actions/permissions"])
    actor, actor_error = gh_json(["api", "user"])
    pr: Any | None = None
    pr_error: str | None = "pull request number is required"
    comments: Any | None = None
    comments_error: str | None = "pull request number is required"
    check_runs_payload: Any | None = None
    check_runs_error: str | None = "pull request number is required"
    if pull_request is not None:
        pr, pr_error = gh_json([
            "pr", "view", str(pull_request), "--repo", repository, "--json",
            "number,state,baseRefName,headRefOid,author,reviewDecision,reviews,"
            "reviewRequests,statusCheckRollup,url",
        ])
        comments, comments_error = gh_json([
            "api", f"repos/{repository}/issues/{pull_request}/comments?per_page=100",
        ])
        head_ref_oid = (pr or {}).get("headRefOid")
        if head_ref_oid:
            check_runs_payload, check_runs_error = gh_json([
                "api", f"repos/{repository}/commits/{head_ref_oid}/check-runs?per_page=100",
            ])
    repository_name = (repo or {}).get("nameWithOwner", "")
    repository_owner = repository_name.split("/", 1)[0] if "/" in repository_name else None
    actor_login = (actor or {}).get("login")
    actor_is_owner = (
        bool(repository_owner)
        and bool(actor_login)
        and actor_login.casefold() == repository_owner.casefold()
    )
    collaborator_logins = [item.get("login") for item in collaborators or []]
    independent_reviewer_available = bool(actor_login) and any(
        login.casefold() != actor_login.casefold()
        for login in collaborator_logins
        if login
    )
    pull_request_reviews = (protection or {}).get("required_pull_request_reviews") or {}
    status_checks = (protection or {}).get("required_status_checks") or {}
    branch_rules_complete = (
        not pull_request_reviews
        and (protection or {}).get("enforce_admins", {}).get("enabled") is True
        and (protection or {}).get("required_conversation_resolution", {}).get("enabled") is True
        and (protection or {}).get("required_linear_history", {}).get("enabled") is True
        and (protection or {}).get("allow_force_pushes", {}).get("enabled") is False
        and (protection or {}).get("allow_deletions", {}).get("enabled") is False
    )
    configured_checks = status_checks.get("checks") or []
    configured_check_pairs = {
        (item.get("context"), item.get("app_id"))
        for item in configured_checks
        if isinstance(item, dict) and item.get("context")
    }
    expected_contexts = set(expected_required_checks)
    expected_check_pairs = {
        (context, GITHUB_ACTIONS_APP_ID) for context in expected_contexts
    }
    exact_required_checks = (
        status_checks.get("strict") is True
        and bool(expected_contexts)
        and configured_check_pairs == expected_check_pairs
    )

    head_sha = (pr or {}).get("headRefOid")
    self_review_marker = f"G1-GOVERNANCE-SELF-REVIEW: APPROVED head={head_sha}"
    self_review_comments = [
        comment for comment in comments or []
        if actor_is_owner
        and comment.get("user", {}).get("login", "").casefold()
        == repository_owner.casefold()
        and comment.get("body") == self_review_marker
        and bool(comment.get("created_at"))
        and comment.get("updated_at") == comment.get("created_at")
    ]
    documented_self_review = (
        actor_is_owner
        and bool(pr)
        and pr.get("state") == "OPEN"
        and pr.get("baseRefName") == "main"
        and bool(head_sha)
        and bool(self_review_comments)
    )
    check_runs = (check_runs_payload or {}).get("check_runs", [])
    check_runs_by_context = {
        context: [run for run in check_runs if run.get("name") == context]
        for context in expected_contexts
    }
    pr_required_checks_passed = (
        bool(expected_contexts)
        and all(
            len(check_runs_by_context[context]) == 1
            and check_runs_by_context[context][0].get("head_sha") == head_sha
            and check_runs_by_context[context][0].get("status") == "completed"
            and check_runs_by_context[context][0].get("conclusion") == "success"
            and check_runs_by_context[context][0].get("app", {}).get("id")
            == GITHUB_ACTIONS_APP_ID
            for context in expected_contexts
        )
    )
    check_run_evidence = {
        context: [
            {
                "id": run.get("id"),
                "name": run.get("name"),
                "head_sha": run.get("head_sha"),
                "status": run.get("status"),
                "conclusion": run.get("conclusion"),
                "app_id": run.get("app", {}).get("id"),
                "details_url": run.get("details_url"),
            }
            for run in runs
        ]
        for context, runs in check_runs_by_context.items()
    }

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
        "actions_enabled": bool(actions) and actions.get("enabled") is True,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "review_mode": "documented-self-review",
        "authenticated_actor": actor_login,
        "repository_owner": repository_owner,
        "authenticated_actor_is_owner": actor_is_owner,
        "collaborators": collaborator_logins,
        "independent_reviewer_available": independent_reviewer_available,
        "required_status_check_app_id": GITHUB_ACTIONS_APP_ID,
        "required_status_checks": {
            "expected": [
                {"context": context, "app_id": GITHUB_ACTIONS_APP_ID}
                for context in sorted(expected_contexts)
            ],
            "configured": [
                {"context": context, "app_id": app_id}
                for context, app_id in sorted(
                    configured_check_pairs,
                    key=lambda pair: (pair[0], str(pair[1])),
                )
            ],
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
            "check_runs": check_run_evidence,
        },
        "errors": {
            key: value for key, value in {
                "repository": repo_error,
                "actor": actor_error,
                "collaborators": collaborators_error,
                "branch_protection": protection_error,
                "pages": pages_error,
                "actions": actions_error,
                "pull_request": pr_error,
                "pull_request_comments": comments_error,
                "commit_check_runs": check_runs_error,
            }.items() if value
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", default="RatelXD/secure-coding")
    parser.add_argument("--pull-request", type=int)
    parser.add_argument(
        "--required-check",
        action="append",
        dest="required_checks",
        help="Exact required Actions check context; repeat for multiple contexts",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--release-state", type=Path)
    args = parser.parse_args()

    receipt: dict[str, Any] = {
        "schema_version": 2,
        "scope": "public-governance",
        "local_assignment_context": "required but intentionally untracked",
    }
    try:
        receipt["template_provenance"] = check_template()
        receipt["github_governance"] = check_github(
            args.repository,
            pull_request=args.pull_request,
            expected_required_checks=tuple(args.required_checks or DEFAULT_REQUIRED_CHECKS),
        )
        if args.release_state:
            receipt["release_state"] = check_release_state(
                json.loads(args.release_state.read_text(encoding="utf-8"))
            )
    except Exception as error:  # fail closed with a serializable receipt
        receipt["verification_error"] = f"{type(error).__name__}: {error}"
    components = [value.get("passed", False) for value in receipt.values() if isinstance(value, dict)]
    expected_components = 3 if args.release_state else 2
    receipt["gate"] = (
        "PASS" if len(components) == expected_components and all(components) else "BLOCK"
    )
    rendered = json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 0 if receipt["gate"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
