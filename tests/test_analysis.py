import types
import unittest

import analysis

CFG = dict(
    REQUIRED_ARRIVAL_DATE="2027-01-22", ARRIVAL_EARLIEST_LOCAL=None, ARRIVAL_LATEST_LOCAL="19:00",
    RED_EYE_DEPART_BEFORE_LOCAL="05:00", RED_EYE_PENALTY_SGD=300, NARITA_PENALTY_SGD=200,
    EXTRA_NIGHT_COST_SGD=None, EXTRA_NIGHT_RETURN_DATE="2027-01-31", LCC_BAG_FEE_PER_PAX_SGD={}, ADULTS=4,
)


def cfg(**overrides):
    return types.SimpleNamespace(**{**CFG, **overrides})


def itinerary(**overrides):
    return {"outbound_date": "2027-01-22", "return_date": "2027-01-30", "airline": "ANA",
            "flight_numbers": "NH 802", "arrival_airport": "NRT", "depart_time": "2027-01-22 06:35",
            "arrive_time": "2027-01-22 14:30", "total_price_sgd": 3732, "bags_included": None, **overrides}


class AdjustedCostTest(unittest.TestCase):
    def test_nh802_narita_only(self):
        self.assertEqual(analysis.adjusted_cost(itinerary(), cfg()), (3932, ["NRT +200"]))

    def test_zg54_red_eye_and_narita(self):
        zg54 = itinerary(airline="ZIPAIR Tokyo", flight_numbers="ZG 54", depart_time="2027-01-22 00:40",
                         arrive_time="2027-01-22 08:25", total_price_sgd=2856)
        self.assertEqual(analysis.adjusted_cost(zg54, cfg()), (3356, ["red-eye", "NRT +200"]))

    def test_jan31_without_extra_night_cost_is_labelled(self):
        self.assertEqual(analysis.adjusted_cost(itinerary(return_date="2027-01-31"), cfg()),
                         (3932, ["NRT +200", "extra night not included"]))

    def test_jan31_with_extra_night_cost_adds_it(self):
        self.assertEqual(analysis.adjusted_cost(itinerary(return_date="2027-01-31"), cfg(EXTRA_NIGHT_COST_SGD=150)),
                         (4082, ["NRT +200", "extra night +150"]))

    def test_lcc_bag_fee_for_four_adults(self):
        scoot = itinerary(airline="Scoot", flight_numbers="TR 804", arrival_airport="HND",
                          depart_time="2027-01-22 17:35", total_price_sgd=2788)
        c = cfg(LCC_BAG_FEE_PER_PAX_SGD={"Scoot": 50})
        self.assertEqual(analysis.adjusted_cost(scoot, c), (2988, ["bags +200"]))
        self.assertEqual(analysis.adjusted_cost({**scoot, "bags_included": 1}, c), (2788, []))


class ArrivalWindowTest(unittest.TestCase):
    def test_window(self):
        hnd = itinerary(arrival_airport="HND")
        self.assertEqual(
            [analysis.meets_arrival_window({**hnd, "arrive_time": t}, cfg())
             for t in ["2027-01-22 18:25", "2027-01-22 19:00", "2027-01-22 21:40", "2027-01-23 01:00", None]],
            [True, True, False, False, False],
        )

    def test_earliest_bound(self):
        early = itinerary(arrive_time="2027-01-22 06:55")
        self.assertEqual([analysis.meets_arrival_window(early, cfg(ARRIVAL_EARLIEST_LOCAL=t)) for t in ["07:00", "06:00"]],
                         [False, True])

    def test_red_eye(self):
        self.assertEqual([analysis.is_red_eye(itinerary(depart_time=t), cfg())
                          for t in ["2027-01-22 04:59", "2027-01-22 05:00"]], [True, False])


if __name__ == "__main__":
    unittest.main()
