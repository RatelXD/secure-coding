from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

POLICY_IDS = {
    "이체-범위-01",
    "이체-계정-01",
    "이체-금액-01",
    "이체-대상-01",
    "이체-잔액-01",
    "이체-원자성-01",
    "이체-멱등-01",
    "이체-동시성-01",
    "이체-보정-01",
    "이체-대사-01",
    "검색-공개-01",
    "검색-입력-01",
    "검색-필터-01",
    "검색-정렬-01",
    "검색-페이지-01",
    "관리-최소권한-01",
    "관리-범위-01",
    "관리-재인증-01",
    "관리-가역성-01",
    "관리-감사-01",
    "관리-중복-01",
}

EXPECTED_TEST_POLICIES = {
    "C2-TRF-SEED-001": {"이체-범위-01"},
    "C2-TRF-CLOSE-001": {"이체-계정-01"},
    "C2-TRF-UNIT-001": {"이체-금액-01", "이체-잔액-01"},
    "C2-TRF-AUTH-001": {"이체-대상-01"},
    "C2-TRF-IDEM-001": {"이체-멱등-01"},
    "C2-TRF-CONC-001": {"이체-동시성-01"},
    "C2-TRF-FAULT-001": {"이체-원자성-01", "이체-동시성-01"},
    "C2-TRF-LEDGER-001": {"이체-원자성-01", "이체-보정-01", "이체-대사-01"},
    "C2-SRCH-VIS-001": {"검색-공개-01"},
    "C2-SRCH-INPUT-001": {"검색-입력-01"},
    "C2-SRCH-FILTER-001": {"검색-필터-01"},
    "C2-SRCH-ORDER-001": {"검색-정렬-01"},
    "C2-SRCH-PAGE-001": {"검색-페이지-01"},
    "C2-SRCH-RESOURCE-001": {"검색-입력-01", "검색-페이지-01"},
    "C2-ADM-DENY-001": {"관리-최소권한-01"},
    "C2-ADM-REQ-001": {"관리-재인증-01"},
    "C2-ADM-MATRIX-001": {"관리-최소권한-01"},
    "C2-ADM-GRANT-001": {"관리-범위-01", "관리-재인증-01"},
    "C2-ADM-PRIV-001": {"관리-범위-01"},
    "C2-ADM-AUDIT-001": {"관리-감사-01"},
    "C2-ADM-AUDIT-FAIL-001": {"관리-감사-01"},
    "C2-ADM-APPLY-RACE-001": {"관리-가역성-01", "관리-중복-01"},
    "C2-ADM-EXPIRY-001": {"관리-가역성-01", "관리-중복-01"},
    "C2-ADM-RELEASE-RACE-001": {"관리-가역성-01", "관리-중복-01"},
}


class CycleTwoDesignOracleTests(unittest.TestCase):
    def text(self, relative: str) -> str:
        return (ROOT / relative).read_text(encoding="utf-8")

    def policy_ids(self, text: str) -> set[str]:
        return set(re.findall(r"`((?:이체|검색|관리)-[^`]+-\d{2})`", text))
    def table_cells(self, row: str) -> list[str]:
        return [
            cell.replace("\\|", "|").strip()
            for cell in re.split(r"(?<!\\)\|", row.strip("|"))
        ]


    def test_requirements_and_traceability_share_complete_unimplemented_oracle(self) -> None:
        requirements = self.text("docs/report/01-requirements.md")
        traceability = self.text("docs/report/appendix/feature-traceability.md")

        self.assertEqual(self.policy_ids(requirements), POLICY_IDS)
        self.assertEqual(self.policy_ids(traceability), POLICY_IDS)
        self.assertIn(
            "설계 작성 완료이며 제품 코드·마이그레이션·화면·URL·자동 검증은 모두 후속 구현 범위",
            requirements,
        )
        for contract in (
            "`Decimal(12,2)`",
            "`0.01..99,999,999.99`",
            "`SEED_ISSUE`",
            "`100,000.00`",
            "`0.00..1,000,000,000.00`",
            "`SEED_RESERVE`",
            "`40001`",
            "`TransferSafetyState`",
            "`1..500`",
            "`AdminScopeGrant`",
            "`moderation.manage_admin_scope`",
            "300초 이하",
            "10..500",
            "`판매중(AVAILABLE)`, `판매완료(SOLD)`",
            "페이지당 20건",
        ):
            self.assertIn(contract, requirements)

        self.assertIn("## 2차 설계 추적표", traceability)
        self.assertIn("## 추적표 갱신 규칙", traceability)
        cycle_two_trace = traceability.split("## 2차 설계 추적표", maxsplit=1)[1].split(
            "## 추적표 갱신 규칙", maxsplit=1
        )[0]
        trace_ids = re.findall(
            r"^\| `((?:이체|검색|관리)-[^`]+-\d{2})` \|",
            cycle_two_trace,
            flags=re.MULTILINE,
        )
        self.assertEqual(len(trace_ids), len(POLICY_IDS))
        self.assertEqual(set(trace_ids), POLICY_IDS)
        self.assertEqual(cycle_two_trace.count("설계 확정·미구현·미검증"), len(POLICY_IDS))
        self.assertEqual(cycle_two_trace.count("없음(후속 구현)"), len(POLICY_IDS))
        self.assertNotIn("PASS", cycle_two_trace)

        for row in cycle_two_trace.splitlines():
            if not re.match(r"^\| `(?:이체|검색|관리)-", row):
                continue
            cells = [cell.strip() for cell in row.strip("|").split("|")]
            self.assertEqual(cells[3], "없음(후속 구현)", row)
            self.assertEqual(cells[5], "설계 확정·미구현·미검증", row)

        checklist = self.text("docs/report/04-checklist-and-testing.md")
        self.assertIn("## 4.5 2차 개발 검증 계약", checklist)
        self.assertIn("## 4.6 현재 실제 실행 결과", checklist)
        cycle_two_checklist = checklist.split("## 4.5 2차 개발 검증 계약", maxsplit=1)[1].split(
            "## 4.6 현재 실제 실행 결과", maxsplit=1
        )[0]

        actual_test_policies: dict[str, set[str]] = {}
        for row in cycle_two_checklist.splitlines():
            if not row.startswith("| `C2-"):
                continue
            cells = [cell.strip() for cell in row.strip("|").split("|")]
            test_match = re.fullmatch(r"`(C2-[A-Z]+(?:-[A-Z]+)*-\d{3})`", cells[0])
            self.assertIsNotNone(test_match, row)
            test_id = test_match.group(1)
            self.assertNotIn(test_id, actual_test_policies)
            actual_test_policies[test_id] = self.policy_ids(cells[1])
            self.assertTrue(row.endswith("| 구현 예정 |"), row)

        self.assertEqual(actual_test_policies, EXPECTED_TEST_POLICIES)
        self.assertEqual(set().union(*actual_test_policies.values()), POLICY_IDS)

        for requirement_id in ("FR-TRANSFER-01", "FR-SEARCH-01", "FR-ADMIN-01"):
            self.assertRegex(
                requirements,
                rf"(?m)^\| `{requirement_id}` \|.+\| 설계 확정·구현/검증 예정 \|$",
            )

        for shared_contract in (
            "`SEED_RESERVE`",
            "1,000,000,000.00",
            "`40001`",
            "`40P01`",
            "1..500",
            "`AdminScopeGrant`",
            "`moderation.manage_admin_scope`",
            "trigger",
            "safety shared",
            "exclusive",
            "NFC",
            "meta-scope",
            "journal/entry",
            "100,000.00",
            "잔액 0",
            "원장·감사",
            "합계 0",
            "ID 내림차순",
            "`SanctionRelease`",
        ):
            for document in (requirements, traceability, cycle_two_checklist):
                self.assertIn(shared_contract, document)

        system_design = self.text("docs/report/02-system-design.md")
        self.assertIn(
            "2차의 모의 이체·상품 검색·관리자 기능은 이 문서에서 설계만 확정했으며 "
            "제품 코드와 마이그레이션은 아직 구현하지 않았습니다.",
            system_design,
        )

        for transfer_contract in (
            "`POST /transfers/`는 `application/json`만 받고 "
            "`recipient`, `amount`, `idempotency_key` 세 필드만 허용",
            r"`^(0|[1-9][0-9]{0,7})(\.[0-9]{1,2})?$`",
            "`idempotency_key`는 소문자 canonical UUID 문자열",
            '{"transfer_id":"UUID","status":"completed","recipient":"원문",'
            '"amount":"0.00","sender_balance":"0.00"}',
            "신규와 성공 재현 모두 `201`",
            "저장된 업무 거부 재현은 최초 오류 status와 body",
            "OPEN` 검사는 저장 결과가 없는 새 키에만 적용",
            "`TransferSafetyState=BLOCKED` 여부와 무관하게 저장 결과를 그대로 재현",
        ):
            self.assertIn(transfer_contract, system_design)

        transfer_rows: dict[str, list[str]] = {}
        for row in system_design.splitlines():
            if not row.startswith("| ") or "`error_code`" in row:
                continue
            cells = self.table_cells(row)
            if len(cells) == 3 and cells[1] in {"401 / 403", "400", "409", "422", "503"}:
                transfer_rows[cells[0]] = cells[1:]
        self.assertEqual(
            transfer_rows,
            {
                "비인증 / CSRF 실패": ["401 / 403", "`AUTH_REQUIRED` / `CSRF_FAILED`"],
                "형식·범위 오류": ["400", "`INVALID_REQUEST`"],
                "같은 키·다른 payload": ["409", "`IDEMPOTENCY_CONFLICT`"],
                "자기·미존재·비활성·종료·부족·상한": [
                    "422",
                    "`TRANSFER_NOT_ALLOWED`",
                ],
                "새 키의 BLOCKED·재시도 소진": ["503", "`TRANSFER_UNAVAILABLE`"],
            },
        )

        close_contract = next(
            line
            for line in system_design.splitlines()
            if line.startswith("`POST /transfers/account/close/`")
        )
        for exact_close_result in (
            "body와 추가 필드를 허용하지 않습니다",
            "최초·반복 종료는 모두 body 없는 `204`",
            "`401 AUTH_REQUIRED`",
            "`403 CSRF_FAILED`",
            "`400 INVALID_REQUEST`",
            "`409 ACCOUNT_NOT_EMPTY`",
            "`503 TRANSFER_UNAVAILABLE`",
        ):
            self.assertIn(exact_close_result, close_contract)

        http_rows: dict[str, list[str]] = {}
        for row in system_design.splitlines():
            if not row.startswith("| `"):
                continue
            cells = self.table_cells(row)
            if len(cells) == 4 and cells[0].startswith(("`GET /", "`POST /")):
                http_rows[cells[0]] = cells[1:]
        self.assertEqual(
            http_rows,
            {
                "`GET /products/`": [
                    "`q`, `status=available|sold`, `min_price`, `max_price`, "
                    "`sort=newest|price_asc|price_desc`, `page=1..500`; 추가 query 금지",
                    "HTML 200",
                    "입력·추가 필드 400",
                ],
                "`GET /management/reports/`": [
                    "`target_type=user|product`, 양의 10진 `target_id`, "
                    "`page=1..500`; 추가 query 금지",
                    "HTML 200",
                    "비인증 302, 권한 403, 미존재·범위 밖 404, 입력·추가 필드 400",
                ],
                "`GET /management/audit/`": [
                    "reports 필드 + "
                    "`action=apply|release|grant|revoke|deny|conflict`; 추가 query 금지",
                    "HTML 200",
                    "reports와 동일",
                ],
                "`POST /management/sanctions/apply/`": [
                    "`target_type=user|product`, 양의 10진 `target_id`, `reason`, "
                    "`version`, CSRF; 추가 form 필드 금지",
                    "HTML 200",
                    "권한 부족 403, 미존재·범위 밖 404, 입력·재인증·추가 필드 400, "
                    "stale 409, 감사 장애 503",
                ],
                "`POST /management/sanctions/<id>/release/`": [
                    "URL의 양의 10진 sanction `id`, `reason`, `version`, CSRF; "
                    "추가 form 필드 금지",
                    "HTML 200",
                    "apply와 동일; 자연 만료 뒤 요청은 409·충돌 감사 1건·"
                    "`SanctionRelease` 0건",
                ],
                "`POST /management/scopes/grant/`": [
                    "양의 10진 `staff_id`, "
                    "`codename=view_report|apply_sanction|release_sanction|"
                    "view_admin_audit`, `target_type=user|product`, 양의 10진 "
                    "`target_id`, `reason`, `version`(대상 staff `auth_epoch`), "
                    "CSRF; 추가 form 필드 금지",
                    "HTML 200",
                    "meta-scope·자기 변경 403, 입력·재인증·추가 필드 400, "
                    "미존재 404, stale/중복 409, 감사 장애 503",
                ],
                "`POST /management/scopes/<id>/revoke/`": [
                    "URL의 양의 10진 grant `id`, `reason`, grant `version`, CSRF; "
                    "추가 form 필드 금지",
                    "HTML 200",
                    "권한·자기 변경 403, 입력·재인증·추가 필드 400, 미존재 404, "
                    "stale 409, 감사 장애 503",
                ],
            },
        )

        for bootstrap_contract in (
            "`bootstrap_scope_manager --username USERNAME --reason REASON`",
            "전용 bootstrap advisory lock",
            "유효 최고관리자 0명을 다시 확인",
            "permission과 추가 전용 감사 1건을 함께 커밋",
            "감사 실패 시 permission도 롤백",
        ):
            self.assertIn(bootstrap_contract, system_design)

    def test_assignment_report_omits_internal_process_terms(self) -> None:
        report_index = self.text("docs/report/index.md")
        checklist = self.text("docs/report/04-checklist-and-testing.md")
        traceability = self.text("docs/report/appendix/feature-traceability.md")
        for forbidden in (
            "정책 오라클",
            "정식 릴리스 관찰",
            "승인된 경계값",
            "설계 검토는 완료",
        ):
            self.assertNotIn(forbidden, checklist + report_index + traceability)


if __name__ == "__main__":
    unittest.main()
