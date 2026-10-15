import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import run

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "serpapi_2027-01-22_2027-01-30.json").read_text(encoding="utf-8")
)


class RunTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db_path = os.path.join(tmp.name, "flights.db")
        patcher = mock.patch("config.DB_PATH", self.db_path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def query(self, sql):
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute(sql).fetchall()
        finally:
            conn.close()

    def test_two_runs_store_both_pairs_without_duplicates(self):
        with mock.patch("run.fetch_serpapi", return_value=FIXTURE):
            run.main()
            run.main()

        runs = self.query("SELECT id, watch_id, pairs_ok, pairs_failed, finished_at IS NOT NULL FROM runs ORDER BY id")
        self.assertEqual(runs, [(1, "tokyo-jan-2027", 2, 0, 1), (2, "tokyo-jan-2027", 2, 0, 1)])

        counts = self.query(
            "SELECT run_id, outbound_date, return_date, COUNT(*) FROM itineraries "
            "GROUP BY run_id, outbound_date, return_date ORDER BY run_id, return_date"
        )
        self.assertEqual(counts, [
            (1, "2027-01-22", "2027-01-30", 15),
            (1, "2027-01-22", "2027-01-31", 15),
            (2, "2027-01-22", "2027-01-30", 15),
            (2, "2027-01-22", "2027-01-31", 15),
        ])
        self.assertEqual(self.query("SELECT COUNT(*) FROM itineraries"), [(60,)])

        dupes = self.query(
            "SELECT run_id, return_date, flight_numbers FROM itineraries "
            "GROUP BY run_id, return_date, flight_numbers HAVING COUNT(*) > 1"
        )
        self.assertEqual(dupes, [])

        nh802 = self.query(
            "SELECT source, airline, arrival_airport, depart_time, arrive_time, total_price_sgd, bags_included "
            "FROM itineraries WHERE run_id = 1 AND return_date = '2027-01-30' AND flight_numbers = 'NH 802'"
        )
        self.assertEqual(nh802, [("serpapi", "ANA", "NRT", "2027-01-22 06:35", "2027-01-22 14:30", 3732.0, None)])

    def test_failed_pair_is_counted_and_run_continues(self):
        def fake_fetch(watch, outbound_date, return_date, api_key):
            if return_date == "2027-01-31":
                raise RuntimeError("SerpApi 500: boom")
            return FIXTURE

        with mock.patch("run.fetch_serpapi", side_effect=fake_fetch):
            run.main()

        self.assertEqual(self.query("SELECT id, pairs_ok, pairs_failed, finished_at IS NOT NULL FROM runs"), [(1, 1, 1, 1)])
        self.assertEqual(
            self.query("SELECT return_date, COUNT(*) FROM itineraries GROUP BY return_date"),
            [("2027-01-30", 15)],
        )


if __name__ == "__main__":
    unittest.main()
