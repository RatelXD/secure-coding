from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from apps.chat.policies import ChatPolicyError, canonical_payload_sha256, normalize_chat_text, require_uuid4
from apps.moderation.policies import (
    ACTION_DURATION,
    ModerationPolicyError,
    ReportContext,
    TargetType,
    action_expiry,
    is_reporter_eligible,
    qualifies_for_action,
    validate_report_context,
)


class ChatPolicyTests(unittest.TestCase):
    def test_utf8_and_control_boundaries(self) -> None:
        self.assertEqual(len(normalize_chat_text("a" * 2_000).encode("utf-8")), 2_000)
        with self.assertRaises(ChatPolicyError):
            normalize_chat_text("a" * 2_001)
        for rejected in ("", "  ", "hello\x00", "hello\t", "hello\tworld", "hello\rworld"):
            with self.subTest(rejected=repr(rejected)), self.assertRaises(ChatPolicyError):
                normalize_chat_text(rejected)
        self.assertEqual(normalize_chat_text("hello\nworld"), "hello\nworld")

    def test_uuid4_and_replay_payload_identity(self) -> None:
        value = uuid4()
        self.assertIs(require_uuid4(value), value)
        with self.assertRaises(ChatPolicyError):
            require_uuid4(UUID("00000000-0000-1000-8000-000000000000"))
        digest = canonical_payload_sha256(room_id=1, sender_id=2, body=" hello ")
        self.assertEqual(digest, canonical_payload_sha256(room_id=1, sender_id=2, body="hello"))
        self.assertNotEqual(digest, canonical_payload_sha256(room_id=2, sender_id=2, body="hello"))


class ModerationPolicyTests(unittest.TestCase):
    def test_target_context_matrix(self) -> None:
        validate_report_context(target_type=TargetType.PRODUCT, context=ReportContext.PRODUCT)
        validate_report_context(target_type=TargetType.USER, context=ReportContext.PROFILE)
        with self.assertRaises(ModerationPolicyError):
            validate_report_context(target_type=TargetType.PRODUCT, context=ReportContext.GLOBAL_CHAT)
        with self.assertRaises(ModerationPolicyError):
            validate_report_context(target_type=TargetType.USER, context=ReportContext.PRODUCT)

    def test_independent_report_thresholds(self) -> None:
        product_reports = {ReportContext.PRODUCT: {1, 2, 3, 4}}
        self.assertFalse(qualifies_for_action(target_type=TargetType.PRODUCT, independent_reporters_by_context=product_reports))
        product_reports[ReportContext.PRODUCT].add(5)
        self.assertTrue(qualifies_for_action(target_type=TargetType.PRODUCT, independent_reporters_by_context=product_reports))

        user_reports = {ReportContext.PROFILE: {1, 2, 3, 4}}
        self.assertFalse(qualifies_for_action(target_type=TargetType.USER, independent_reporters_by_context=user_reports))
        user_reports[ReportContext.DIRECT_CHAT] = {5}
        self.assertTrue(qualifies_for_action(target_type=TargetType.USER, independent_reporters_by_context=user_reports))
        with self.assertRaises(ModerationPolicyError):
            qualifies_for_action(
                target_type=TargetType.USER,
                independent_reporters_by_context={
                    ReportContext.PROFILE: {1},
                    ReportContext.DIRECT_CHAT: {1},
                },
            )

    def test_reporter_age_and_action_boundaries(self) -> None:
        now = datetime(2026, 7, 16, tzinfo=timezone.utc)
        self.assertFalse(
            is_reporter_eligible(
                joined_at=now - timedelta(days=7) + timedelta(microseconds=1),
                is_active=True,
                database_now=now,
            )
        )
        self.assertTrue(
            is_reporter_eligible(
                joined_at=now - timedelta(days=7),
                is_active=True,
                database_now=now,
            )
        )
        self.assertFalse(
            is_reporter_eligible(
                joined_at=now - timedelta(days=8),
                is_active=False,
                database_now=now,
            )
        )
        self.assertEqual(action_expiry(database_now=now), now + ACTION_DURATION)


if __name__ == "__main__":
    unittest.main()
