"""Cron entry point: one snapshot run over every date pair of the watch."""
import itertools
import sys
from datetime import date, datetime, timedelta, timezone

import config
import db
from fetch import fetch_serpapi, parse_serpapi

# Singapore has no DST; a fixed offset avoids needing a tz database on Windows.
SGT = timezone(timedelta(hours=8))


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
    return datetime.now(SGT).isoformat(timespec="seconds")


def main():
    watch = build_watch()
    conn = db.connect(config.DB_PATH)
    try:
        run_id = db.start_run(conn, watch["id"], now_sgt())
        pairs_ok = pairs_failed = 0
        for outbound, ret in itertools.product(watch["outbound_dates"], watch["return_dates"]):
            try:
                rows = parse_serpapi(fetch_serpapi(watch, outbound, ret, config.SERPAPI_KEY))
                fetched_at = now_sgt()
                days = (date.fromisoformat(outbound) - datetime.now(SGT).date()).days
                for row in rows:
                    row.update(fetched_at=fetched_at, days_to_departure=days,
                               outbound_date=outbound, return_date=ret)
                db.insert_itineraries(conn, run_id, rows)
                conn.commit()
                pairs_ok += 1
            except Exception as e:
                conn.rollback()
                pairs_failed += 1
                print(f"{outbound} -> {ret} failed: {e!r}", file=sys.stderr)
        db.finish_run(conn, run_id, now_sgt(), pairs_ok, pairs_failed)
        print(f"Run {run_id}: {pairs_ok} ok, {pairs_failed} failed")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
