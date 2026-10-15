"""Cron entry point: alert when no run has succeeded in the last 24h."""
import logging
from datetime import datetime, timedelta

import config
import db
import run

log = logging.getLogger(__name__)


def stale_message(conn, now):
    """now: timezone-aware datetime. A run counts as successful when at least one pair succeeded."""
    last = conn.execute("SELECT MAX(started_at) FROM runs WHERE pairs_ok > 0").fetchone()[0]
    if last and datetime.fromisoformat(last) >= now - timedelta(hours=24):
        return None
    return f"No successful flight run in the last 24h. Last success: {last or 'never'}."


def main():
    run.setup_logging()
    conn = db.connect(config.DB_PATH)
    try:
        text = stale_message(conn, datetime.now(config.SGT))
    finally:
        conn.close()
    if text:
        run.send_alert(text)
    else:
        log.info("Heartbeat OK")


if __name__ == "__main__":
    main()
