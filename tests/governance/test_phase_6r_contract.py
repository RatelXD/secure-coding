from __future__ import annotations

import importlib.util
from pathlib import Path
import unicodedata
import unittest

SCRIPT = Path("scripts/verify_pr_title.py")
SPEC = importlib.util.spec_from_file_location("verify_pr_title", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
verify_pr_title = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify_pr_title)


class TitleGovernanceTests(unittest.TestCase):
    def test_exact_eighteen_planned_titles_use_production_parser(self) -> None:
        self.assertEqual(18, len(verify_pr_title.PLANNED_TITLES))
        self.assertEqual(18, len(set(verify_pr_title.PLANNED_TITLES)))
        for title in verify_pr_title.PLANNED_TITLES:
            with self.subTest(title=title):
                self.assertEqual((), verify_pr_title.validate_title(title))

    def test_negative_vectors_are_rejected(self) -> None:
        valid = verify_pr_title.PLANNED_TITLES[0]
        vectors = {
            "old Phase 6R title": "chore(governance): Phase 6R 확장 재합의",
            "mixed 6R token": "chore(governance): 확장 6R단계 재합의",
            "bare 6R token": "chore(governance): 확장 6R 재합의",
            "unregistered ASCII": "chore(governance): 확장 parser 고정",
            "leading space": "chore(governance):  확장 재합의",
            "trailing space": "chore(governance): 확장 재합의 ",
            "double space": "chore(governance): 확장  재합의",
            "NFD": unicodedata.normalize("NFD", valid),
            "punctuation": "chore(governance): 확장 재합의!",
            "no Hangul": "chore(governance): Django PostgreSQL",
            "shell metacharacters": 'chore(governance): 확장"; true; #',
            "output command injection": (
                "chore(governance): 확장\n"
                "GOVERNANCE_TITLE_VALUE\n"
                "title=chore(governance): 확장 재합의"
            ),
        }
        for name, title in vectors.items():
            with self.subTest(name=name, title=title):
                self.assertTrue(verify_pr_title.validate_title(title))

    def test_subject_mismatch_and_commit_count_are_rejected(self) -> None:
        title = verify_pr_title.PLANNED_TITLES[0]
        self.assertIn(
            "branch HEAD subject must equal PR title",
            verify_pr_title.validate_pr(title, f"{title} 변경", 1),
        )
        self.assertIn(
            "PR branch must contain exactly one commit",
            verify_pr_title.validate_pr(title, title, 2),
        )
        self.assertEqual((), verify_pr_title.validate_pr(title, title, 1))


class Phase6RDocumentContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = Path("docs/report/phase-6r-governance.md").read_text(
            encoding="utf-8"
        )

    def test_contract_tables_and_trace_schema_are_present(self) -> None:
        for heading in (
            "단일 권위와 FK 계약",
            "잠금 순서 계약",
            "도메인 사건과 보존 계약",
            "마이그레이션·호환성·되돌리기 계약",
            "Test-ID와 한국어 추적 스키마",
        ):
            with self.subTest(heading=heading):
                self.assertIn(f"## {heading}", self.document)

        for field in (
            "Policy-ID",
            "Design/Threat-ID",
            "Migration-ID",
            "Code owner/path",
            "Test-ID",
            "PR/RC receipt",
        ):
            with self.subTest(field=field):
                self.assertIn(f"`{field}`", self.document)

    def test_contract_has_no_undecided_cells(self) -> None:
        self.assertNotIn("미정", self.document)
        self.assertNotIn("TBD", self.document)
        self.assertNotIn("TODO", self.document)
    def test_cleaner_blocker_contracts_are_explicit(self) -> None:
        for clause in (
            "seller→User(PROTECT, NOT NULL)",
            "`LEGACY_SOLD` COMPLETED일 때만 NULL",
            "CHECK (((kind = 'LEGACY_SOLD' AND status = 'COMPLETED' AND buyer_id IS NULL) OR (kind <> 'LEGACY_SOLD' AND buyer_id IS NOT NULL)) IS TRUE)",
            "기존 Product 수 N을 고정",
            "모든 기존 Product의 category를 결정적으로 `기타`로 설정",
            "`기타`를 가리키는 기존 Product 수 N",
            "mandatory FK 전 rollback은 gate OFF와 nullable application path 복구만 허용",
            "`expires_at = created_at + INTERVAL '90 days'`",
            "fake DB clock migration test",
            "`expires_at < DB now()`",
            "동일 시각 row는 보존",
        ):
            with self.subTest(clause=clause):
                self.assertIn(clause, self.document)



if __name__ == "__main__":
    unittest.main()
