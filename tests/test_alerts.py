import unittest

import alerts
import db
from test_analysis import cfg

NH802 = {"source": "serpapi", "airline": "ANA", "flight_numbers": "NH 802", "arrival_airport": "NRT",
         "depart_time": "2027-01-22 06:35", "arrive_time": "2027-01-22 14:30", "total_price_sgd": 3732}
NH842 = {**NH802, "flight_numbers": "NH 842", "arrival_airport": "HND",
         "depart_time": "2027-01-22 10:45", "arrive_time": "2027-01-22 18:25"}
SQ634 = {**NH842, "airline": "Singapore Airlines", "flight_numbers": "SQ 634",
         "depart_time": "2027-01-22 14:05", "arrive_time": "2027-01-22 21:40"}


class FailureSummaryTest(unittest.TestCase):
    def test_one_failed_pair(self):
        errors = ["RuntimeError('SerpApi 401: Invalid API key.')"] * 4 + ["IndexError('list index out of range')"]
        results = [
            ("2027-01-22", "2027-01-30", True, [{"error": None}]),
            ("2027-01-22", "2027-01-31", False, [{"error": e} for e in errors]),
        ]
        self.assertEqual(alerts.failure_summary("2026-10-15T08:07:12+08:00", results),
                         "Run 08:07 — 1/2 OK.\n"
                         "2027-01-22→01-31 failed after 5 attempts (IndexError('list index out of range'))")

    def test_long_error_is_truncated(self):
        results = [("2027-01-22", "2027-01-30", False, [{"error": "x" * 200}])]
        self.assertEqual(alerts.failure_summary("2026-10-15T20:07:00+08:00", results),
                         "Run 20:07 — 0/1 OK.\n2027-01-22→01-30 failed after 1 attempts (" + "x" * 117 + "...)")

    def test_all_ok(self):
        results = [("2027-01-22", r, True, [{"error": None}]) for r in ["2027-01-30", "2027-01-31"]]
        self.assertIsNone(alerts.failure_summary("2026-10-15T08:07:12+08:00", results))


class DealAlertTest(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        self.addCleanup(self.conn.close)

    def add_run(self, *itineraries, return_date="2027-01-30"):
        run_id = db.start_run(self.conn, "tokyo-jan-2027", "2026-10-15T08:07:00+08:00")
        db.insert_itineraries(self.conn, run_id, [
            {**it, "fetched_at": "2026-10-15T08:08:00+08:00", "days_to_departure": 99,
             "outbound_date": "2027-01-22", "return_date": return_date, "raw_json": None}
            for it in itineraries])
        return run_id

    def test_first_run_never_alerts_on_new_low(self):
        self.assertIsNone(alerts.deal_alert(self.conn, self.add_run(NH802), cfg(DEAL_THRESHOLD_SGD=None)))

    def test_cheaper_qualifying_itinerary_alerts(self):
        self.add_run(NH802)
        run_id = self.add_run(NH802, {**NH842, "total_price_sgd": 3800})
        self.assertEqual(alerts.deal_alert(self.conn, run_id, cfg(DEAL_THRESHOLD_SGD=None)),
                         "Flight deal\n"
                         "2027-01-22→01-30: SGD 3,800 (quoted SGD 3,800), ANA NH 842, 10:45→18:25 HND, "
                         "previous low SGD 3,932")

    def test_cheaper_late_arrival_does_not_alert(self):
        self.add_run(NH802)
        run_id = self.add_run(NH802, {**SQ634, "total_price_sgd": 3000})
        self.assertIsNone(alerts.deal_alert(self.conn, run_id, cfg(DEAL_THRESHOLD_SGD=None)))

    def test_threshold_crossing_fires_once(self):
        c = cfg(DEAL_THRESHOLD_SGD=4000)
        first = self.add_run(NH802, return_date="2027-01-31")
        second = self.add_run({**NH802, "total_price_sgd": 3750}, return_date="2027-01-31")
        self.assertEqual(alerts.deal_alert(self.conn, first, c),
                         "Flight deal\n"
                         "2027-01-22→01-31: SGD 3,932 (quoted SGD 3,732), ANA NH 802, 06:35→14:30 NRT, NRT +200, "
                         "extra night not included, no previous low, below SGD 4,000 threshold")
        self.assertIsNone(alerts.deal_alert(self.conn, second, c))


if __name__ == "__main__":
    unittest.main()
