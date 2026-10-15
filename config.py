import os
from datetime import timedelta, timezone

from dotenv import load_dotenv

load_dotenv()

SERPAPI_KEY = os.getenv("SERPAPI_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
DB_PATH = os.getenv("DB_PATH", "flights.db")

# Singapore has no DST; a fixed offset avoids needing a tz database on Windows.
SGT = timezone(timedelta(hours=8))

WATCH_ID = "tokyo-jan-2027"
ORIGIN = "SIN"
NONSTOP = True
ENDS_AT = "2026-11-08"

OUTBOUND_DATES = ["2027-01-22"]
RETURN_DATES   = ["2027-01-30", "2027-01-31"]
ADULTS = 4
CURRENCY = "SGD"
DESTINATIONS = ["HND", "NRT"]

REQUIRED_ARRIVAL_DATE = "2027-01-22"   # outbound arrival date, Tokyo local
ARRIVAL_EARLIEST_LOCAL = None          # optional, e.g. "07:00"; None = no minimum
ARRIVAL_LATEST_LOCAL = "19:00"         # outbound arrival cutoff, Asia/Tokyo

RED_EYE_DEPART_BEFORE_LOCAL = "05:00"  # outbound departs before this (Asia/Singapore) = red-eye
RED_EYE_PENALTY_SGD = 300              # total for group: allowed, but avoided unless clearly cheaper
NARITA_PENALTY_SGD = 200               # total for group: transfer cost + time
EXTRA_NIGHT_COST_SGD = None            # TODO: fill in — applies to return on Jan 31
LCC_BAG_FEE_PER_PAX_SGD = {}           # e.g. {"Scoot": <fee>} if prices exclude bags
DEAL_THRESHOLD_SGD = None              # set after ~1 week of data

PRICE_SANITY_MIN_SGD = 1000            # total for 4 pax, round trip
PRICE_SANITY_MAX_SGD = 10000

RETRY_DELAYS_SEC = [30, 120, 300]      # 3 retries after first attempt, + jitter
