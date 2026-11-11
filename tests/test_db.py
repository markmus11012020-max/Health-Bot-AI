"""Database audit/feedback persistence in SQLite."""
from __future__ import annotations

import unittest

from src.core.db import Database


class DatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = Database("sqlite://")
        self.db.init()

    def tearDown(self) -> None:
        self.db.close()

    def test_health(self) -> None:
        self.assertTrue(self.db.health())

    def test_record_and_read_audit(self) -> None:
        event_id = self.db.record_audit(
            request_id="req-1",
            provider="AITunnel",
            model="m",
            success=True,
            latency_ms=42,
            response_chars=10,
            anonymized_input_chars=100,
            pii_counts={"phone": 1},
        )
        self.assertGreater(event_id, 0)
        rows = self.db.get_audit("req-1")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].provider, "AITunnel")
        self.assertIn("phone", rows[0].pii_counts)

    def test_record_feedback_and_stats(self) -> None:
        self.db.record_audit(request_id="req-2")
        self.db.record_feedback(request_id="req-2", rating=5, correct=True, comment="ok")
        stats = self.db.stats()
        self.assertEqual(stats["audit_events"], 1)
        self.assertEqual(stats["feedback"], 1)


if __name__ == "__main__":
    unittest.main()
