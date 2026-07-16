from __future__ import annotations

import base64
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


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


class GitHubGovernanceTests(unittest.TestCase):
    @staticmethod
    def response(arguments: list[str]):
        command = " ".join(arguments)
        if command.startswith("repo view"):
            return ({
                "nameWithOwner": "RatelXD/secure-coding",
                "isPrivate": False,
                "viewerPermission": "ADMIN",
                "defaultBranchRef": {"name": "main"},
                "squashMergeAllowed": True,
                "mergeCommitAllowed": False,
                "rebaseMergeAllowed": False,
            }, None)
        if "collaborators?" in command:
            return ([{"login": "RatelXD"}, {"login": "RatelAI"}], None)
        if "branches/main/protection" in command:
            return ({
                "required_status_checks": {
                    "strict": True,
                    "checks": [{"context": "governance", "app_id": 15368}],
                },
                "enforce_admins": {"enabled": True},
                "required_linear_history": {"enabled": True},
                "allow_force_pushes": {"enabled": False},
                "allow_deletions": {"enabled": False},
            }, None)
        if command.endswith("repos/example/repo/pages"):
            return ({"public": True, "build_type": "workflow", "https_enforced": True}, None)
        if "environments/release" in command:
            return ({
                "can_admins_bypass": False,
                "protection_rules": [{
                    "type": "required_reviewers",
                    "prevent_self_review": False,
                    "reviewers": [{"reviewer": {"login": "RatelXD"}}],
                }],
            }, None)
        if "actions/permissions" in command:
            return ({"enabled": True}, None)
        if command == "api user":
            return ({"login": "RatelXD"}, None)
        if command.startswith("pr view"):
            return ({
                "number": 7,
                "state": "OPEN",
                "baseRefName": "main",
                "headRefOid": "abc123",
                "reviewDecision": "REVIEW_REQUIRED",
                "reviews": [],
                "statusCheckRollup": [{
                    "__typename": "CheckRun",
                    "name": "governance",
                    "conclusion": "SUCCESS",
                    "head_sha": "abc123",
                    "status": "completed",
                    "app": {"id": 15368},
                }],
                "url": "https://github.com/example/repo/pull/7",
            }, None)
        if "issues/7/comments?" in command:
            return ([{
                "id": 77,
                "user": {"login": "RatelXD"},
                "body": "G1-GOVERNANCE-BOOTSTRAP-SELF-REVIEW: APPROVED head=abc123",
                "created_at": "2026-07-16T00:00:00Z",
                "updated_at": "2026-07-16T00:00:00Z",
            }], None)
        if "commits/abc123/check-runs?" in command:
            return ({
                "total_count": 1,
                "check_runs": [{
                    "name": "governance",
                    "head_sha": "abc123",
                    "status": "completed",
                    "conclusion": "success",
                    "app": {"id": 15368},
                }],
            }, None)
        raise AssertionError(f"unexpected gh invocation: {arguments}")

    @patch.object(verify_g1, "gh_json", side_effect=response)
    def test_requires_exact_context_and_current_head_self_review(self, _gh_json) -> None:
        receipt = verify_g1.check_github(
            "example/repo",
            pull_request=7,
            expected_required_checks=("governance",),
        )

        self.assertTrue(receipt["passed"])
        self.assertEqual(
            receipt["required_status_checks"]["configured"],
            [{"context": "governance", "app_id": 15368}],
        )
        self.assertEqual(receipt["review_mode"], "documented-self-review")
        self.assertEqual(receipt["pull_request"]["self_review_comment_ids"], [77])

    @patch.object(verify_g1, "gh_json", side_effect=response)
    def test_blocks_when_expected_context_does_not_match(self, _gh_json) -> None:
        receipt = verify_g1.check_github(
            "example/repo",
            pull_request=7,
            expected_required_checks=("governance", "security"),
        )

        self.assertFalse(receipt["passed"])
        self.assertFalse(receipt["checks"]["required_status_checks_exact"])
        self.assertFalse(receipt["checks"]["pr_required_checks_passed"])

    @patch.object(verify_g1, "gh_json")
    def test_blocks_stale_self_review_marker(self, gh_json) -> None:
        def stale_response(arguments: list[str]):
            response = self.response(arguments)
            if "issues/7/comments?" in " ".join(arguments):
                return ([{
                    "id": 78,
                    "user": {"login": "RatelXD"},
                    "body": "G1-GOVERNANCE-BOOTSTRAP-SELF-REVIEW: APPROVED head=old-head",
                }], None)
            return response

        gh_json.side_effect = stale_response
        receipt = verify_g1.check_github(
            "example/repo",
            pull_request=7,
            expected_required_checks=("governance",),
        )

        self.assertFalse(receipt["passed"])
        self.assertFalse(receipt["checks"]["documented_self_review"])

    @patch.object(verify_g1, "gh_json")
    def test_blocks_non_owner_admin(self, gh_json) -> None:
        def non_owner_response(arguments: list[str]):
            if " ".join(arguments) == "api user":
                return ({"login": "OtherAdmin"}, None)
            return self.response(arguments)

        gh_json.side_effect = non_owner_response
        receipt = verify_g1.check_github(
            "example/repo",
            pull_request=7,
            expected_required_checks=("governance",),
        )

        self.assertFalse(receipt["passed"])
        self.assertFalse(receipt["authenticated_actor_is_owner"])
        self.assertFalse(receipt["checks"]["documented_self_review"])

    @patch.object(verify_g1, "gh_json")
    def test_blocks_extra_environment_reviewer(self, gh_json) -> None:
        def extra_reviewer_response(arguments: list[str]):
            response, error = self.response(arguments)
            if "environments/release" in " ".join(arguments):
                response["protection_rules"][0]["reviewers"].append(
                    {"reviewer": {"login": "RatelAI"}}
                )
            return response, error

        gh_json.side_effect = extra_reviewer_response
        receipt = verify_g1.check_github(
            "example/repo",
            pull_request=7,
            expected_required_checks=("governance",),
        )

        self.assertFalse(receipt["passed"])
        self.assertFalse(
            receipt["checks"]["release_environment_owner_review_required"]
        )

    @patch.object(verify_g1, "gh_json")
    def test_blocks_wrong_app_check_run(self, gh_json) -> None:
        def wrong_app_response(arguments: list[str]):
            response, error = self.response(arguments)
            if "commits/abc123/check-runs?" in " ".join(arguments):
                response["check_runs"][0]["app"]["id"] = 999
            return response, error

        gh_json.side_effect = wrong_app_response
        receipt = verify_g1.check_github(
            "example/repo",
            pull_request=7,
            expected_required_checks=("governance",),
        )

        self.assertFalse(receipt["passed"])
        self.assertFalse(receipt["checks"]["pr_required_checks_passed"])

    @patch.object(verify_g1, "gh_json")
    def test_blocks_duplicate_check_run(self, gh_json) -> None:
        def duplicate_response(arguments: list[str]):
            response, error = self.response(arguments)
            if "commits/abc123/check-runs?" in " ".join(arguments):
                response["check_runs"].append(dict(response["check_runs"][0]))
            return response, error

        gh_json.side_effect = duplicate_response
        receipt = verify_g1.check_github(
            "example/repo",
            pull_request=7,
            expected_required_checks=("governance",),
        )

        self.assertFalse(receipt["passed"])
        self.assertFalse(receipt["checks"]["pr_required_checks_passed"])

    @patch.object(verify_g1, "gh_json")
    def test_blocks_embedded_or_edited_marker(self, gh_json) -> None:
        def invalid_marker_response(arguments: list[str]):
            response, error = self.response(arguments)
            if "issues/7/comments?" in " ".join(arguments):
                response[0]["body"] = (
                    "Reviewed\nG1-GOVERNANCE-BOOTSTRAP-SELF-REVIEW: APPROVED head=abc123"
                )
                response[0]["updated_at"] = "2026-07-16T00:01:00Z"
            return response, error

        gh_json.side_effect = invalid_marker_response
        receipt = verify_g1.check_github(
            "example/repo",
            pull_request=7,
            expected_required_checks=("governance",),
        )

        self.assertFalse(receipt["passed"])
        self.assertFalse(receipt["checks"]["documented_self_review"])



if __name__ == "__main__":
    unittest.main()
