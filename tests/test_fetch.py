import json
import unittest
from pathlib import Path
from unittest import mock

import fetch

FIXTURES = Path(__file__).parent / "fixtures"
SERPAPI = json.loads((FIXTURES / "serpapi_2027-01-22_2027-01-30.json").read_text(encoding="utf-8"))
FF_NRT = json.loads((FIXTURES / "fast_flights_2027-01-22_2027-01-30_NRT.json").read_text(encoding="utf-8"))
WATCH = {"origin": "SIN", "destinations": ["HND", "NRT"], "adults": 4, "nonstop": True, "currency": "SGD"}
KEY = "secret-key-123"


def patch_sources(**fakes):
    """Swap each source's fetch function, keeping the real names, order and retry delays."""
    return mock.patch("fetch.SOURCES", [(name, fakes[name], delays) for name, _, delays in fetch.SOURCES])


def calls(*results):
    """A fake source that returns or raises each result in turn and records its calls."""
    return mock.Mock(side_effect=list(results))


SERPAPI_OK = (fetch.parse_serpapi(SERPAPI), "SGD")
FF_OK = (fetch.parse_fast_flights(FF_NRT), "SGD")


class ParseFastFlightsTest(unittest.TestCase):
    def test_nrt_fixture(self):
        itineraries = fetch.parse_fast_flights(FF_NRT)
        self.assertEqual(len(itineraries), 6)
        ana_0635 = [it for it in itineraries if it["depart_time"] == "2027-01-22 06:35"]
        self.assertEqual(len(ana_0635), 1)
        self.assertLessEqual({
            "source": "fast_flights", "airline": "ANA", "flight_numbers": None, "arrival_airport": "NRT",
            "depart_time": "2027-01-22 06:35", "arrive_time": "2027-01-22 14:30", "total_price_sgd": 3732,
        }.items(), ana_0635[0].items())


class FetchPairTest(unittest.TestCase):
    def setUp(self):
        self.sleeps = []

    def fetch_pair(self, api_key=KEY):
        with self.assertLogs("fetch", "WARNING") as logs:
            result = fetch.fetch_pair(WATCH, "2027-01-22", "2027-01-30", api_key, sleep=self.sleeps.append)
        self.logs = logs.output
        return result

    def summary(self, attempts):
        return [(a["source"], a["attempt"], a["outcome"]) for a in attempts]

    def test_serpapi_errors_four_times_then_fast_flights_succeeds(self):
        serpapi = calls(*[RuntimeError("SerpApi 500: boom")] * 4)
        ff = calls(FF_OK)
        with patch_sources(serpapi=serpapi, fast_flights=ff):
            itineraries, attempts = self.fetch_pair()

        self.assertEqual(itineraries, FF_OK[0])
        self.assertEqual(self.summary(attempts), [
            ("serpapi", 1, "error"), ("serpapi", 2, "error"), ("serpapi", 3, "error"), ("serpapi", 4, "error"),
            ("fast_flights", 1, "ok"),
        ])
        self.assertEqual(attempts[0]["error"], "RuntimeError('SerpApi 500: boom')")
        self.assertIsNone(attempts[4]["error"])
        self.assertEqual(len(self.sleeps), 3)
        for slept, base in zip(self.sleeps, [30, 120, 300]):
            self.assertTrue(base * 0.8 <= slept <= base * 1.2, (slept, base))
        ff.assert_called_once_with(WATCH, "2027-01-22", "2027-01-30", KEY)
        self.assertEqual(len(self.logs), 4)

    def test_wrong_currency_is_retried_without_fallback(self):
        usd = (fetch.parse_serpapi(SERPAPI), "USD")
        ff = calls()
        with patch_sources(serpapi=calls(usd, SERPAPI_OK), fast_flights=ff):
            itineraries, attempts = self.fetch_pair()

        self.assertEqual(len(itineraries), 15)
        self.assertEqual(self.summary(attempts), [("serpapi", 1, "invalid"), ("serpapi", 2, "ok")])
        self.assertEqual(attempts[0]["error"], "currency USD, expected SGD")
        self.assertEqual(ff.call_count, 0)
        self.assertEqual(len(self.sleeps), 1)

    def test_everything_fails_without_raising(self):
        with patch_sources(serpapi=calls(*[RuntimeError("down")] * 4), fast_flights=calls(IndexError("x"))):
            itineraries, attempts = self.fetch_pair()

        self.assertIsNone(itineraries)
        self.assertEqual([a["outcome"] for a in attempts], ["error"] * 5)
        self.assertEqual(attempts[4]["error"], "IndexError('x')")

    def test_api_key_never_reaches_stored_errors_or_logs(self):
        leak = ConnectionError(f"Max retries exceeded with url: /search?engine=google_flights&api_key={KEY}")
        with patch_sources(serpapi=calls(*[leak] * 4), fast_flights=calls(RuntimeError("down"))):
            _, attempts = self.fetch_pair()

        self.assertEqual(attempts[0]["error"],
                         "ConnectionError('Max retries exceeded with url: /search?engine=google_flights&api_key=***')")
        self.assertFalse(any(KEY in (a["error"] or "") for a in attempts))
        self.assertFalse(any(KEY in line for line in self.logs))


if __name__ == "__main__":
    unittest.main()
