import unittest

from validate import validate


def itinerary(price, airline="ANA", depart_time="2027-01-22 06:35"):
    return {"source": "serpapi", "airline": airline, "flight_numbers": "NH 802", "arrival_airport": "NRT",
            "depart_time": depart_time, "arrive_time": "2027-01-22 14:30", "total_price_sgd": price,
            "raw_json": "{}"}


class ValidateTest(unittest.TestCase):
    def test_drops_bad_items_and_keeps_the_rest(self):
        good = [itinerary(3732), itinerary(1000), itinerary(10000)]
        bad = [itinerary(933), itinerary(None), itinerary(10001), itinerary(3732, airline=""),
               itinerary(3732, depart_time=None)]
        with self.assertLogs("validate", "WARNING") as logs:
            kept, problem = validate(bad[:2] + good + bad[2:], "SGD", "SGD")
        self.assertEqual(kept, good)
        self.assertIsNone(problem)
        self.assertEqual(len(logs.output), 5)
        self.assertIn("price=933", logs.output[0])

    def test_wrong_currency_is_a_problem(self):
        kept, problem = validate([itinerary(3732)], "USD", "SGD")
        self.assertEqual(problem, "currency USD, expected SGD")

    def test_everything_dropped_is_a_problem(self):
        with self.assertLogs("validate", "WARNING"):
            kept, problem = validate([itinerary(933), itinerary(None)], "SGD", "SGD")
        self.assertEqual((kept, problem), ([], "no valid itineraries (2 dropped)"))


if __name__ == "__main__":
    unittest.main()
