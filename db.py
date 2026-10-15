import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY,
  watch_id TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  pairs_ok INTEGER DEFAULT 0,
  pairs_failed INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS itineraries (
  id INTEGER PRIMARY KEY,
  run_id INTEGER NOT NULL REFERENCES runs(id),
  fetched_at TEXT NOT NULL,
  days_to_departure INTEGER NOT NULL,
  outbound_date TEXT NOT NULL,
  return_date TEXT NOT NULL,
  source TEXT NOT NULL,
  airline TEXT NOT NULL,
  flight_numbers TEXT,
  arrival_airport TEXT NOT NULL,
  depart_time TEXT,
  arrive_time TEXT,
  total_price_sgd REAL NOT NULL,
  bags_included INTEGER,
  raw_json TEXT
);

CREATE TABLE IF NOT EXISTS fetch_log (
  id INTEGER PRIMARY KEY,
  run_id INTEGER REFERENCES runs(id),
  ts TEXT NOT NULL,
  outbound_date TEXT NOT NULL,
  return_date TEXT NOT NULL,
  source TEXT NOT NULL,
  attempt INTEGER NOT NULL,
  outcome TEXT NOT NULL,
  error TEXT
);
"""


def connect(path):
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


def start_run(conn, watch_id, started_at):
    cur = conn.execute("INSERT INTO runs (watch_id, started_at) VALUES (?, ?)", (watch_id, started_at))
    conn.commit()
    return cur.lastrowid


def insert_itineraries(conn, run_id, rows):
    conn.executemany(
        """INSERT INTO itineraries (run_id, fetched_at, days_to_departure, outbound_date, return_date,
             source, airline, flight_numbers, arrival_airport, depart_time, arrive_time,
             total_price_sgd, raw_json)
           VALUES (:run_id, :fetched_at, :days_to_departure, :outbound_date, :return_date,
             :source, :airline, :flight_numbers, :arrival_airport, :depart_time, :arrive_time,
             :total_price_sgd, :raw_json)""",
        [{**row, "run_id": run_id} for row in rows],
    )


def finish_run(conn, run_id, finished_at, pairs_ok, pairs_failed):
    conn.execute(
        "UPDATE runs SET finished_at = ?, pairs_ok = ?, pairs_failed = ? WHERE id = ?",
        (finished_at, pairs_ok, pairs_failed, run_id),
    )
    conn.commit()


def insert_fetch_log(conn, run_id, outbound_date, return_date, attempts):
    conn.executemany(
        """INSERT INTO fetch_log (run_id, ts, outbound_date, return_date, source, attempt, outcome, error)
           VALUES (:run_id, :ts, :outbound_date, :return_date, :source, :attempt, :outcome, :error)""",
        [{**a, "run_id": run_id, "outbound_date": outbound_date, "return_date": return_date} for a in attempts],
    )
