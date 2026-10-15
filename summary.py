"""Cron/manual entry point: send a Telegram digest of the latest run. Uses no SerpApi quota."""
import config
import db
import run
from alerts import run_summary


def main():
    run.setup_logging()
    conn = db.connect(config.DB_PATH)
    try:
        last = conn.execute("SELECT MAX(id) FROM runs").fetchone()[0]
        text = run_summary(conn, last, config) if last else "No runs yet."
    finally:
        conn.close()
    run.send_alert(text)


if __name__ == "__main__":
    main()
