import unittest
from datetime import datetime, timedelta, timezone

import db
import heartbeat

NOW = datetime(2026, 10, 15, 21, 30, tzinfo=timezone(timedelta(hours=8)))


class StaleMessageTest(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        self.addCleanup(self.conn.close)

    def add_run(self, started_at, pairs_ok):
        run_id = db.start_run(self.conn, "tokyo-jan-2027", started_at)
        db.finish_run(self.conn, run_id, started_at, pairs_ok, 2 - pairs_ok)

    def test_empty_db_is_stale(self):
        self.assertEqual(heartbeat.stale_message(self.conn, NOW),
                         "No successful flight run in the last 24h. Last success: never.")

    def test_only_old_success_and_recent_failure_is_stale(self):
        self.add_run("2026-10-14T20:07:00+08:00", 2)
        self.add_run("2026-10-15T08:07:00+08:00", 0)
        self.assertEqual(heartbeat.stale_message(self.conn, NOW),
                         "No successful flight run in the last 24h. Last success: 2026-10-14T20:07:00+08:00.")

    def test_recent_success_is_fine(self):
        self.add_run("2026-10-14T21:30:00+08:00", 1)
        self.assertIsNone(heartbeat.stale_message(self.conn, NOW))


if __name__ == "__main__":
    unittest.main()
