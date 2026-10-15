import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import fetch
import run

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


SERPAPI_OK = (fetch.parse_serpapi(load("serpapi_2027-01-22_2027-01-30.json")), "SGD")
FF_OK = (fetch.parse_fast_flights(load("fast_flights_2027-01-22_2027-01-30_NRT.json")
                                  + load("fast_flights_2027-01-22_2027-01-30_HND.json")), "SGD")


class RunTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db_path = os.path.join(tmp.name, "flights.db")
        real_fetch_pair = run.fetch_pair
        for patcher in [
            mock.patch("config.DB_PATH", self.db_path),
            mock.patch("run.setup_logging"),
            mock.patch("run.fetch_pair", lambda *args: real_fetch_pair(*args, sleep=lambda seconds: None)),
        ]:
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_with_sources(self, serpapi, fast_flights, runs=1):
        """Run main() with fake source functions in place of the live ones, keeping retry delays."""
        fakes = {"serpapi": serpapi, "fast_flights": fast_flights}
        sources = [(name, fakes[name], delays) for name, _, delays in fetch.SOURCES]
        with mock.patch("fetch.SOURCES", sources), self.assertLogs(level="INFO") as logs:
            for _ in range(runs):
                run.main()
        return logs.output

    def query(self, sql):
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute(sql).fetchall()
        finally:
            conn.close()

    def test_two_runs_store_both_pairs_without_duplicates(self):
        def serpapi(watch, outbound_date, return_date, api_key):
            return [dict(it) for it in SERPAPI_OK[0]], "SGD"

        self.run_with_sources(serpapi, mock.Mock(side_effect=AssertionError("fallback not expected")), runs=2)

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

        self.assertEqual(
            self.query("SELECT run_id, return_date, source, attempt, outcome, error, ts IS NOT NULL "
                       "FROM fetch_log ORDER BY id"),
            [
                (1, "2027-01-30", "serpapi", 1, "ok", None, 1),
                (1, "2027-01-31", "serpapi", 1, "ok", None, 1),
                (2, "2027-01-30", "serpapi", 1, "ok", None, 1),
                (2, "2027-01-31", "serpapi", 1, "ok", None, 1),
            ],
        )

    def test_bad_api_key_falls_back_then_fails_pair_without_crashing(self):
        def serpapi(watch, outbound_date, return_date, api_key):
            raise RuntimeError("SerpApi 401: Invalid API key.")

        def fast_flights(watch, outbound_date, return_date, api_key):
            if return_date == "2027-01-31":
                raise IndexError("list index out of range")
            return [dict(it) for it in FF_OK[0]], "SGD"

        logs = self.run_with_sources(serpapi, fast_flights)

        self.assertEqual(self.query("SELECT id, pairs_ok, pairs_failed, finished_at IS NOT NULL FROM runs"), [(1, 1, 1, 1)])
        self.assertEqual(
            self.query("SELECT return_date, source, arrival_airport, COUNT(*) FROM itineraries "
                       "GROUP BY return_date, source, arrival_airport ORDER BY arrival_airport"),
            [("2027-01-30", "fast_flights", "HND", 3), ("2027-01-30", "fast_flights", "NRT", 6)],
        )
        serpapi_errors = [("serpapi", n, "error", "RuntimeError('SerpApi 401: Invalid API key.')") for n in range(1, 5)]
        self.assertEqual(
            self.query("SELECT return_date, source, attempt, outcome, error FROM fetch_log ORDER BY id"),
            [("2027-01-30", *row) for row in serpapi_errors]
            + [("2027-01-30", "fast_flights", 1, "ok", None)]
            + [("2027-01-31", *row) for row in serpapi_errors]
            + [("2027-01-31", "fast_flights", 1, "error", "IndexError('list index out of range')")],
        )
        self.assertIn("ERROR:run:2027-01-22 -> 2027-01-31 failed: RuntimeError('all 5 attempts failed')", logs)
        self.assertEqual(logs[-1], "INFO:run:Run 1: 1 ok, 1 failed")


if __name__ == "__main__":
    unittest.main()
