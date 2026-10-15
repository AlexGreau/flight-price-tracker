"""Sanity checks that turn silent bad data into failed attempts."""
import logging

import config

log = logging.getLogger(__name__)

REQUIRED_FIELDS = ("airline", "arrival_airport", "depart_time")


def validate(itineraries, currency, expected_currency):
    """Drop bad items; return (kept, problem). problem is None when the response is usable."""
    kept = []
    for it in itineraries:
        price = it["total_price_sgd"]
        in_range = price is not None and config.PRICE_SANITY_MIN_SGD <= price <= config.PRICE_SANITY_MAX_SGD
        if in_range and all(it[field] for field in REQUIRED_FIELDS):
            kept.append(it)
        else:
            log.warning("Dropped %s itinerary: airline=%r airport=%r depart=%r price=%r", it["source"],
                        it["airline"], it["arrival_airport"], it["depart_time"], price)
    if currency != expected_currency:
        return kept, f"currency {currency}, expected {expected_currency}"
    if not kept:
        return kept, f"no valid itineraries ({len(itineraries)} dropped)"
    return kept, None
