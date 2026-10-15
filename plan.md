# Flight Price Tracker — SIN → Tokyo, Jan 2027

Context file for AI coding assistants. Read this fully before writing code.

## Goal

Track round-trip fares Singapore → Tokyo twice a day for ~3 weeks, so we can:
1. Pick the best return date (2 candidates)
2. Decide Haneda (HND) vs Narita (NRT) on **true** cost
3. Learn what a "good" price is and get alerted when one appears
4. Produce a shareable report for friends at the end

Non-goals: "best day of the week to book" (sample too small, effect ~1%), award/miles seats, booking automation, a web UI.

## Trip constraints (hard)

- Origin: SIN. Destination: Tokyo — HND or NRT
- **Direct (nonstop) flights only**
- **4 adults**, economy, **1 checked bag each**
- Lodging is fixed Jan 22 → Jan 30 2027. Candidate dates:
  - Outbound: `2027-01-22` only (no Jan 21 overnight flights)
  - Return: `2027-01-30`, or `2027-01-31` (morning departure, requires 1 extra lodging night)
- → 2 date pairs per run
- **Outbound must land in Tokyo on Jan 22, no later than 19:00 Tokyo time** (before dinner).

## Stack

- Python 3.11+, runs on a Raspberry Pi (always on), scheduled via cron
- Storage: **SQLite** (single file, owned locally). No Google Sheets during collection.
- Data source: **SerpApi Google Flights** (primary), **fast-flights** (fallback)
- Alerts: Telegram Bot API `sendMessage` via plain HTTP (`requests`) — do NOT pull in python-telegram-bot or the existing bot's router; this is a standalone project that only reuses the bot token
- Config/secrets: `.env` + `python-dotenv`
- No LLM calls anywhere — data is already structured
- Timezone for all timestamps: `Asia/Singapore`

## Project structure

```
flight_tracker/
├── CLAUDE.md
├── config.py          # Loads .env, holds constants (dates, thresholds, penalties)
├── fetch.py           # Source adapters (serpapi, fast_flights) + retry/fallback logic
├── validate.py        # Sanity checks that turn silent failures into failures
├── db.py              # SQLite schema + insert/query helpers
├── notify.py          # Telegram sendMessage wrapper
├── run.py             # Entry point for cron: one full snapshot run
├── heartbeat.py       # Entry point for cron: alert if no success in 24h
├── export.py          # Dump tables to CSV for the final report
├── .env / .env.example
├── requirements.txt
└── logs/              # Rotating text logs (gitignored)
```

Rules: snake_case for all files/folders; single-responsibility modules; no god files.

## Environment variables

```
SERPAPI_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
DB_PATH=flights.db
```

## Config constants (config.py)

```python
OUTBOUND_DATES = ["2027-01-22"]
RETURN_DATES   = ["2027-01-30", "2027-01-31"]
ADULTS = 4
CURRENCY = "SGD"
DESTINATIONS = ["HND", "NRT"]          # see "Airport query" below

REQUIRED_ARRIVAL_DATE = "2027-01-22"   # outbound arrival date, Tokyo local
ARRIVAL_EARLIEST_LOCAL = None          # optional, e.g. "07:00"; None = no minimum
ARRIVAL_LATEST_LOCAL = "19:00"         # outbound arrival cutoff, Asia/Tokyo

NARITA_PENALTY_SGD = 200               # total for group: transfer cost + time
EXTRA_NIGHT_COST_SGD = None            # TODO: fill in — applies to return on Jan 31
LCC_BAG_FEE_PER_PAX_SGD = {}           # e.g. {"Scoot": <fee>} if prices exclude bags
DEAL_THRESHOLD_SGD = None              # set after ~1 week of data

PRICE_SANITY_MIN_SGD = 1000            # total for 4 pax, round trip
PRICE_SANITY_MAX_SGD = 10000

RETRY_DELAYS_SEC = [30, 120, 300]      # 3 retries after first attempt, + jitter
```

## Data source details

### SerpApi (primary)
- `engine=google_flights`, `type=1` (round trip), `departure_id=SIN`, `adults=4`, `currency=SGD`, nonstop only
- **Verify parameter names against current SerpApi docs before coding** — especially the nonstop filter (`stops`), checked-bag handling (`bags`), and whether `arrival_id` accepts `"HND,NRT"` in one query.
- Round-trip responses list **outbound** options; the shown price is the cheapest round-trip total for that outbound. Return-leg details need a second call with `departure_token`. **MVP: do NOT make the second call** — store outbound details + total price only. Record this as a known limitation.
- **Verified in Phase 1 (2026-10-15):** `arrival_id="HND,NRT"` works in one query; `stops=1` = nonstop; `price` is the round-trip total for all passengers (matched the browser: NH 802, SGD 3,732). `bags` is **carry-on only** — there is no checked-bag filter, so checked-bag cost is handled via `LCC_BAG_FEE_PER_PAX_SGD` at analysis time
- Budget: ~100 queries over the whole project (free tier = 250/month). Never loop queries in tests against the live API — cache a sample response to `tests/fixtures/` and develop against it.

### fast-flights (fallback)
- Unofficial Google Flights scraper; used only when SerpApi fails after retries
- Normalize its output into the same itinerary dict shape as SerpApi

### Airport query
- If `arrival_id` accepts both airports, use one query per date pair and read the airport from each result
- Otherwise query HND and NRT separately (4 queries/run, ~200 total) — check quota math still fits

## Retry, validation, logging

Per query (one date pair):
1. Try SerpApi. On exception **or validation failure**, retry per `RETRY_DELAYS_SEC` with random jitter (±20%)
2. After all SerpApi attempts fail, try fast-flights once
3. If everything fails, mark the date pair failed for this run and move on — never crash the whole run

Validation (`validate.py`) treats these as failures:
- Zero direct itineraries returned
- Any total price outside the sanity range
- Missing airline, airport code, or departure time
- Response currency not SGD

Logging:
- Every attempt → row in `fetch_log`
- Rotating text log in `logs/` (Python `logging`, `RotatingFileHandler`)
- After a run: send a Telegram message **only if** something failed, e.g. `Run 08:07 — 1/2 OK. 2027-01-22→01-31 failed after 4 attempts (no results)`
- `heartbeat.py` (separate cron, daily): alert if no successful run in the last 24h

## SQLite schema

```sql
CREATE TABLE runs (
  id INTEGER PRIMARY KEY,
  watch_id TEXT NOT NULL,            -- 'tokyo-jan-2027' in v1
  started_at TEXT NOT NULL,          -- ISO, Asia/Singapore
  finished_at TEXT,
  pairs_ok INTEGER DEFAULT 0,
  pairs_failed INTEGER DEFAULT 0
);

CREATE TABLE itineraries (
  id INTEGER PRIMARY KEY,
  run_id INTEGER NOT NULL REFERENCES runs(id),
  fetched_at TEXT NOT NULL,          -- ISO, Asia/Singapore
  days_to_departure INTEGER NOT NULL,
  outbound_date TEXT NOT NULL,
  return_date TEXT NOT NULL,
  source TEXT NOT NULL,              -- 'serpapi' | 'fast_flights'
  airline TEXT NOT NULL,
  flight_numbers TEXT,
  arrival_airport TEXT NOT NULL,     -- HND | NRT
  depart_time TEXT,                  -- outbound local departure
  arrive_time TEXT,                  -- outbound local arrival
  total_price_sgd REAL NOT NULL,     -- for all 4 pax, as quoted
  bags_included INTEGER,             -- 1/0/NULL if unknown
  raw_json TEXT                      -- original item, for re-parsing later
);

CREATE TABLE fetch_log (
  id INTEGER PRIMARY KEY,
  run_id INTEGER REFERENCES runs(id),
  ts TEXT NOT NULL,
  outbound_date TEXT NOT NULL,
  return_date TEXT NOT NULL,
  source TEXT NOT NULL,
  attempt INTEGER NOT NULL,
  outcome TEXT NOT NULL,             -- 'ok' | 'error' | 'invalid'
  error TEXT
);
```

Store raw quoted prices only. Adjustments (Narita penalty, extra night, LCC bag fees) are applied at analysis/export time, never written into stored prices.

## Adjusted cost (analysis time)

```
adjusted = total_price_sgd
         + (NARITA_PENALTY_SGD if arrival_airport == "NRT")
         + (EXTRA_NIGHT_COST_SGD if return_date == "2027-01-31")
         + (LCC_BAG_FEE_PER_PAX_SGD[airline] * 4 if bags not included)
```

Arrival constraint: compute `meets_arrival = arrival date == REQUIRED_ARRIVAL_DATE and arrival time <= ARRIVAL_LATEST_LOCAL and (ARRIVAL_EARLIEST_LOCAL is None or arrival time >= ARRIVAL_EARLIEST_LOCAL)` (Tokyo local). Implement as one helper, `meets_arrival_window(itinerary, cfg)`, so the window is a config change only — no code edits when the earliest hour gets set later. In the v2 watch dict these become `arrival_earliest` / `arrival_latest`. **Store all itineraries regardless** (so the cutoff can be revisited), but exclude `meets_arrival = False` from deal alerts and from the "best option" in reports. Store `arrive_time` as a full local datetime, not just a time, so the date check works.

## Cron

```
7 8,20 * * *   cd ~/flight_tracker && .venv/bin/python run.py
30 21 * * *    cd ~/flight_tracker && .venv/bin/python heartbeat.py
```

Run at odd minutes, not on the hour.

## Phases

Work one phase at a time. Don't start the next until "done when" passes.

1. **Spike** — `fetch.py` (SerpApi only), print results for one date pair.
   *Done when:* output for 2027-01-22 → 2027-01-30 matches Google Flights in a browser (4 adults, nonstop). Save the raw response as a test fixture.
2. **Storage** — `db.py`, `config.py`, `run.py` looping the 2 pairs and writing rows.
   *Done when:* one manual run writes rows for both pairs; re-running creates a new `run_id`, no duplicates within a run.
3. **Resilience** — retries, `validate.py`, fast-flights fallback, `fetch_log`, rotating log.
   *Done when:* forcing a bad API key produces retries, fallback attempts, `fetch_log` rows, and no crash.
4. **Alerts** — `notify.py`, failure summary, `heartbeat.py`, deal alert when adjusted cost < `DEAL_THRESHOLD_SGD` or a new all-time low per pair.
   *Done when:* a simulated failure and a simulated low price each send exactly one Telegram message.
5. **Deploy** — venv on the Pi, cron entries, `.env` filled.
   *Done when:* 2 consecutive days of scheduled runs with clean data.
6. **Export** — `export.py` writes `itineraries.csv` and `fetch_log.csv` with adjusted cost columns.
   *Done when:* CSV opens cleanly and has one row per itinerary per run. (Report itself is built separately from the CSV.)

## Design for a future v2 (do not build v2 now)

A later version may let the user create "watches" via Telegram (multiple routes/dates, stored in a DB). To keep that a refactor rather than a rewrite:

- Core functions take a `watch` dict as an argument; they never read route/date/pax constants from `config.py` directly:
  ```python
  watch = {
      "id": "tokyo-jan-2027",
      "origin": "SIN", "destinations": ["HND", "NRT"],
      "outbound_dates": ["2027-01-22"],
      "return_dates": ["2027-01-30", "2027-01-31"],
      "adults": 4, "nonstop": True, "currency": "SGD",
      "ends_at": "2026-11-08",
  }
  fetch_watch(watch)  # not fetch()
  ```
- `run.py` is the only place that builds the watch (from `config.py` in v1)
- Add a `watch_id TEXT` column to `runs` now (always `"tokyo-jan-2027"` in v1)
- Do NOT build: watch CRUD, NL parsing, scheduling changes, multi-watch loops

## Guidance for the AI assistant

- Default to the minimal version; flag anything that looks like scope creep
- Don't add dependencies beyond: `requests`, `python-dotenv`, `fast-flights` (+ stdlib `sqlite3`, `logging`)
- Never hard-code secrets; never commit `.env` or `flights.db`
- When unsure about an external API parameter, say so and point to the doc to check — don't guess
