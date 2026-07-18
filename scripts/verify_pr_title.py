from __future__ import annotations

import argparse
import re
import sys
import unicodedata

TITLE_RE = re.compile(
    r"^(?P<type>docs|feat|fix|security|test|chore)"
    r"\((?P<scope>[a-z][a-z0-9-]*)\): (?P<body>.+)$"
)
HANGUL_RE = re.compile(r"[가-힣]+")
VERSION_RE = re.compile(r"(?:[0-9]+(?:\.[0-9]+)*|v[0-9]+(?:\.[0-9]+){1,3})")
ASCII_TOKEN_ALLOWLIST = frozenset(
    {
        "Django",
        "PostgreSQL",
        "Redis",
        "Stitch",
        "UI",
        "API",
        "CI",
        "RC",
        "SHA",
        "WebSocket",
        "Playwright",
        "axe",
        "WCAG",
        "ProductImage",
        "ProductConversation",
        "Trade",
        "Review",
        "Notification",
    }
)

PLANNED_TITLES = (
    "chore(governance): 확장 재합의 실행 계약과 검증 도구 고정",
    "feat(ui): 로컬 Stitch 디자인 시스템 기반 구축",
    "feat(catalog): 다중 이미지와 상품 분류 지역 권위 구축",
    "security(accounts): 회원 탈퇴 폐기 기반을 비활성 상태로 준비",
    "feat(demo): 로컬 데모 상품과 자동 초기화 구축",
    "feat(chat): 기존 메시지 경로에 상품 대화 연결",
    "feat(trade): 예약 취소 완료 거래 권위 구현",
    "feat(transfer): 모의 잔액 원장과 이체 권위 구현",
    "feat(catalog): 관심과 재계산 가능한 상품 지표 구현",
    "feat(chat): 관계 제한 온라인 상태와 폐기 연동 구현",
    "feat(notification): 중복 없는 알림과 자동 만료 구현",
    "feat(management): 범위 제한 관리 권위와 작업대 구현",
    "feat(review): 신고 기반 불변 후기와 가역 비노출 구현",
    "security(accounts): 모든 권위 확인 뒤 회원 탈퇴 활성화",
    "feat(search): 카테고리 지역과 거래 상태 검색 통합",
    "feat(ui): 전체 Stitch 여정의 공통 상태와 탐색 수렴",
    "test(release): 확장 릴리스 종합 검증과 복구 절차 고정",
    "docs(release): 최종 한국어 보고서와 추적표 정합화",
)


def validate_title(title: str) -> tuple[str, ...]:
    errors: list[str] = []
    if title != unicodedata.normalize("NFC", title):
        errors.append("title must already be NFC")

    match = TITLE_RE.fullmatch(title)
    if match is None:
        errors.append("title must match <type>(<scope>): <body>")
        return tuple(errors)

    body = match.group("body")
    if body != body.strip(" "):
        errors.append("body must not have leading or trailing U+0020")
    if "  " in body:
        errors.append("body must not contain consecutive U+0020")

    tokens = body.split(" ")
    has_hangul = False
    for token in tokens:
        if HANGUL_RE.fullmatch(token):
            has_hangul = True
        elif VERSION_RE.fullmatch(token) or token in ASCII_TOKEN_ALLOWLIST:
            continue
        else:
            errors.append(f"body token is not allowed: {token!r}")
    if not has_hangul:
        errors.append("body must contain at least one Hangul token")
    return tuple(errors)


def validate_pr(title: str, subject: str, commit_count: int) -> tuple[str, ...]:
    errors = list(validate_title(title))
    if subject != title:
        errors.append("branch HEAD subject must equal PR title")
    if commit_count != 1:
        errors.append("PR branch must contain exactly one commit")
    return tuple(errors)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 6R PR title governance check")
    parser.add_argument("--title", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--commit-count", required=True, type=int)
    args = parser.parse_args(argv)

    errors = validate_pr(args.title, args.subject, args.commit_count)
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print("PASS: title, subject, and single-commit contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
