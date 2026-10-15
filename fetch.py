"""Source adapters. Phase 1: SerpApi only.

Run: python fetch.py                 -> live query (1 SerpApi credit), saves fixture
     python fetch.py <fixture.json>  -> parse a saved response, no API call
"""
import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

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
