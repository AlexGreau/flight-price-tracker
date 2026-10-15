#!/usr/bin/env bash
# Health check for the tracker. Read-only and quota-free by default.
#   ./check.sh          system, config, unit tests, cron, recent runs
#   ./check.sh --live   also does one real run (2 SerpApi queries, may send Telegram alerts)
set -u
cd "$(dirname "$0")"
PY=.venv/bin/python
[ -x "$PY" ] || PY=.venv/Scripts/python.exe  # Windows dev machine
failed=0
ok()   { echo "ok    $1"; }
fail() { echo "FAIL  $1"; failed=1; }

echo "== System"
echo "      arch: $(uname -m)"
if [ -x "$PY" ] && "$PY" -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
  ok "python $("$PY" -c 'import platform; print(platform.python_version())') in .venv"
else
  fail "venv python 3.11+ missing (python3 -m venv .venv && .venv/bin/pip install -r requirements.txt)"
fi
# Cron reads schedule times in local time, so the machine must be on Singapore time.
[ "$(date +%z)" = "+0800" ] && ok "timezone UTC+8" || fail "timezone is $(date +%z), expected +0800 (sudo timedatectl set-timezone Asia/Singapore)"

echo "== Config"
for var in SERPAPI_KEY TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID; do
  grep -qE "^$var=.+" .env 2>/dev/null && ok "$var set" || fail "$var missing in .env"
done

echo "== Unit tests"
if out=$("$PY" -m unittest discover -s tests 2>&1); then
  ok "$(echo "$out" | grep -E '^Ran ')"
else
  echo "$out" | tail -20; fail "unit tests"
fi

echo "== Cron"
if command -v crontab >/dev/null; then
  for job in run.py heartbeat.py; do
    crontab -l 2>/dev/null | grep -v '^#' | grep -q "$job" && ok "$job scheduled" || fail "$job not in crontab"
  done
else
  echo "      skipped (no crontab on this machine)"
fi

if [ "${1:-}" = "--live" ]; then
  echo "== Live run (2 SerpApi queries)"
  "$PY" run.py 2>&1 | grep -E 'WARNING|ERROR|Run [0-9]+' || true
fi

echo "== Recent data"
"$PY" - <<'EOF' || failed=1
import os, sqlite3, sys
from datetime import datetime, timedelta
import config, heartbeat

if not os.path.exists(config.DB_PATH):
    print(f"FAIL  {config.DB_PATH} does not exist yet (no run so far): ./check.sh --live"); sys.exit(1)
try:
    conn = sqlite3.connect(f"file:{config.DB_PATH}?mode=ro", uri=True)
    runs = conn.execute("SELECT id, started_at, pairs_ok, pairs_failed FROM runs ORDER BY id DESC LIMIT 4").fetchall()
except sqlite3.Error as e:
    print(f"FAIL  cannot read {config.DB_PATH}: {e}"); sys.exit(1)
for r in runs:
    print("      run %d  %s  ok=%d failed=%d" % r)
since = (datetime.now(config.SGT) - timedelta(hours=48)).isoformat(timespec="seconds")
clean = conn.execute("SELECT COUNT(*) FROM runs WHERE started_at >= ? AND pairs_failed = 0 AND pairs_ok > 0", (since,)).fetchone()[0]
total = conn.execute("SELECT COUNT(*) FROM runs WHERE started_at >= ?", (since,)).fetchone()[0]
print(f"      last 48h: {clean}/{total} clean runs (cron target: 4)")
for source, n in conn.execute(
        "SELECT source, COUNT(DISTINCT run_id || return_date) FROM itineraries "
        "WHERE fetched_at >= ? GROUP BY source", (since,)):
    print(f"      last 48h: {n} pair(s) served by {source}")
# Same check the daily heartbeat runs, without sending anything.
stale = heartbeat.stale_message(conn, datetime.now(config.SGT))
print(f"FAIL  {stale}" if stale else "ok    a run succeeded in the last 24h")
sys.exit(1 if stale else 0)
EOF

echo
[ $failed = 0 ] && echo "ALL OK" || { echo "SOME CHECKS FAILED"; exit 1; }
