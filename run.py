"""Cron entry point: one snapshot run over every date pair of the watch."""
import itertools
import logging
from datetime import date, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

import config
import db
from fetch import fetch_pair

LOG_DIR = Path(__file__).resolve().parent / "logs"

log = logging.getLogger(__name__)


def build_watch():
    return {
        "id": config.WATCH_ID,
        "origin": config.ORIGIN, "destinations": config.DESTINATIONS,
        "outbound_dates": config.OUTBOUND_DATES,
        "return_dates": config.RETURN_DATES,
        "adults": config.ADULTS, "nonstop": config.NONSTOP, "currency": config.CURRENCY,
        "ends_at": config.ENDS_AT,
    }


def now_sgt():
    return datetime.now(config.SGT).isoformat(timespec="seconds")


def setup_logging():
    LOG_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[RotatingFileHandler(LOG_DIR / "run.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"),
                  logging.StreamHandler()],
    )


def main():
    setup_logging()
    watch = build_watch()
    conn = db.connect(config.DB_PATH)
    try:
        run_id = db.start_run(conn, watch["id"], now_sgt())
        pairs_ok = pairs_failed = 0
        for outbound, ret in itertools.product(watch["outbound_dates"], watch["return_dates"]):
            rows, attempts = fetch_pair(watch, outbound, ret, config.SERPAPI_KEY)
            try:
                db.insert_fetch_log(conn, run_id, outbound, ret, attempts)
                conn.commit()
                if rows is None:
                    raise RuntimeError(f"all {len(attempts)} attempts failed")
                fetched_at = now_sgt()
                days = (date.fromisoformat(outbound) - datetime.now(config.SGT).date()).days
                for row in rows:
                    row.update(fetched_at=fetched_at, days_to_departure=days,
                               outbound_date=outbound, return_date=ret)
                db.insert_itineraries(conn, run_id, rows)
                conn.commit()
                pairs_ok += 1
            except Exception as e:
                conn.rollback()
                pairs_failed += 1
                log.error("%s -> %s failed: %r", outbound, ret, e)
        db.finish_run(conn, run_id, now_sgt(), pairs_ok, pairs_failed)
        log.info("Run %d: %d ok, %d failed", run_id, pairs_ok, pairs_failed)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
