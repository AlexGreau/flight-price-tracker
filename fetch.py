"""Source adapters (SerpApi primary, fast-flights fallback) and the retry/fallback loop.

Run: python fetch.py                 -> live query (1 SerpApi credit), saves fixture
     python fetch.py <fixture.json>  -> parse a saved response, no API call
"""
import dataclasses
import json
import logging
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv
from fast_flights import FlightQuery, Passengers, create_query, get_flights

import config
import validate

log = logging.getLogger(__name__)

SERPAPI_URL = "https://serpapi.com/search"


def fetch_serpapi(watch, outbound_date, return_date, api_key):
    """One round-trip search. Returns raw SerpApi JSON (outbound options only)."""
    params = {
        "engine": "google_flights",
        "type": 1,
        "departure_id": watch["origin"],
        "arrival_id": ",".join(watch["destinations"]),
        "outbound_date": outbound_date,
        "return_date": return_date,
        "adults": watch["adults"],
        "currency": watch["currency"],
        "stops": 1 if watch["nonstop"] else 0,
        "hl": "en",
        "gl": "sg",
        "api_key": api_key,
    }
    r = requests.get(SERPAPI_URL, params=params, timeout=60)
    data = r.json()
    # Don't use raise_for_status: its message includes the URL, which contains the api_key.
    if r.status_code != 200 or "error" in data:
        raise RuntimeError(f"SerpApi {r.status_code}: {data.get('error')}")
    return data


def parse_serpapi(data):
    """Flatten best_flights + other_flights into itinerary dicts (outbound leg only)."""
    itineraries = []
    for item in data.get("best_flights", []) + data.get("other_flights", []):
        legs = item["flights"]
        itineraries.append({
            "source": "serpapi",
            "airline": legs[0]["airline"],
            "flight_numbers": ",".join(leg["flight_number"] for leg in legs),
            "arrival_airport": legs[-1]["arrival_airport"]["id"],
            "depart_time": legs[0]["departure_airport"]["time"],
            "arrive_time": legs[-1]["arrival_airport"]["time"],
            "total_price_sgd": item.get("price"),
            "raw_json": json.dumps(item),
        })
    return itineraries


def serpapi_source(watch, outbound_date, return_date, api_key):
    data = fetch_serpapi(watch, outbound_date, return_date, api_key)
    return parse_serpapi(data), data["search_parameters"]["currency"]


def _format_datetime(point):
    year, month, day = point["date"]
    hour, minute = point["time"]
    return f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}"


def parse_fast_flights(flights):
    """Normalize fast-flights results (dataclasses.asdict form) into itinerary dicts (outbound leg only)."""
    return [{
        "source": "fast_flights",
        "airline": f["airlines"][0],
        "flight_numbers": None,
        "arrival_airport": f["flights"][-1]["to_airport"]["code"],
        "depart_time": _format_datetime(f["flights"][0]["departure"]),
        "arrive_time": _format_datetime(f["flights"][-1]["arrival"]),
        "total_price_sgd": f["price"],
        "raw_json": json.dumps(f),
    } for f in flights]


def fast_flights_source(watch, outbound_date, return_date, api_key):
    # One query per airport: "HND,NRT" in one query raises IndexError in fast-flights 3.1.0.
    flights = []
    for airport in watch["destinations"]:
        q = create_query(
            flights=[FlightQuery(date=outbound_date, from_airport=watch["origin"], to_airport=airport),
                     FlightQuery(date=return_date, from_airport=airport, to_airport=watch["origin"])],
            trip="round-trip", passengers=Passengers(adults=watch["adults"]), currency=watch["currency"],
            max_stops=0 if watch["nonstop"] else None, language="en-US",
        )
        flights += [dataclasses.asdict(f) for f in get_flights(q)]
    # The library returns no currency, so the requested one is all we can report.
    return parse_fast_flights(flights), watch["currency"]


# (name, fetch function, delays before each retry); tried in order until one validates.
SOURCES = [
    ("serpapi", serpapi_source, config.RETRY_DELAYS_SEC),
    ("fast_flights", fast_flights_source, []),
]


def fetch_pair(watch, outbound_date, return_date, api_key, sleep=time.sleep):
    """Try every source with retries. Returns (itineraries or None, attempt dicts); never raises."""
    attempts = []
    for source, fetch_source, delays in SOURCES:
        for attempt, delay in enumerate([0, *delays], start=1):
            if attempt > 1:
                sleep(delay * random.uniform(0.8, 1.2))
            try:
                itineraries, currency = fetch_source(watch, outbound_date, return_date, api_key)
                kept, error = validate.validate(itineraries, currency, watch["currency"])
                outcome = "invalid" if error else "ok"
            except Exception as e:
                outcome, error = "error", repr(e)
                if api_key:
                    # requests exceptions embed the full URL, which carries the key.
                    error = error.replace(api_key, "***")
            attempts.append({"ts": datetime.now(config.SGT).isoformat(timespec="seconds"),
                             "source": source, "attempt": attempt, "outcome": outcome, "error": error})
            if outcome == "ok":
                return kept, attempts
            log.warning("%s -> %s %s attempt %d %s: %s", outbound_date, return_date, source, attempt,
                        outcome, error)
    return None, attempts


if __name__ == "__main__":
    outbound, ret = "2027-01-22", "2027-01-30"
    if len(sys.argv) > 1:
        data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    else:
        load_dotenv()
        watch = {"origin": "SIN", "destinations": ["HND", "NRT"], "adults": 4,
                 "nonstop": True, "currency": "SGD"}
        data = fetch_serpapi(watch, outbound, ret, os.environ["SERPAPI_KEY"])
        fixture = Path("tests/fixtures") / f"serpapi_{outbound}_{ret}.json"
        fixture.parent.mkdir(parents=True, exist_ok=True)
        fixture.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"Saved {fixture}")

    print(f"Currency: {data.get('search_parameters', {}).get('currency')}")
    for it in parse_serpapi(data):
        print(f"{it['total_price_sgd']:>8}  {it['airline']:<25} {it['flight_numbers']:<12} "
              f"{it['depart_time']} -> {it['arrive_time']} {it['arrival_airport']}")
