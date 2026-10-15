"""Telegram message builders. Each returns the message text, or None when there is nothing to say."""
from analysis import adjusted_cost, meets_arrival_window


def _pair(outbound, ret):
    return f"{outbound}→{ret[5:]}"


def _truncate(text, limit=120):
    return text if len(text) <= limit else text[:limit - 3] + "..."


def failure_summary(started_at, results):
    """results: (outbound, return, ok, attempts) per pair."""
    failed = [(o, r, attempts) for o, r, ok, attempts in results if not ok]
    if not failed:
        return None
    lines = [f"Run {started_at[11:16]} — {len(results) - len(failed)}/{len(results)} OK."]
    for outbound, ret, attempts in failed:
        # A pair can fail after its last fetch succeeded, when storing the rows raised.
        error = attempts[-1]["error"] or "fetched but not stored"
        lines.append(f"{_pair(outbound, ret)} failed after {len(attempts)} attempts ({_truncate(error)})")
    return "\n".join(lines)


def _sgd(amount):
    return f"SGD {amount:,.0f}"


def _describe(row, cost, notes):
    return ", ".join([f"{_sgd(cost)} (quoted {_sgd(row['total_price_sgd'])})",
                      " ".join(filter(None, [row["airline"], row["flight_numbers"]])),
                      f"{row['depart_time'][11:16]}→{row['arrive_time'][11:16]} {row['arrival_airport']}",
                      *notes])


def deal_alert(conn, run_id, cfg):
    """New all-time low per date pair, or a first crossing below cfg.DEAL_THRESHOLD_SGD."""
    best = {}  # (outbound, return, run_id) -> (adjusted cost, notes, row), qualifying itineraries only
    for row in conn.execute("SELECT * FROM itineraries WHERE run_id <= ?", (run_id,)):
        if not meets_arrival_window(row, cfg):
            continue
        cost, notes = adjusted_cost(row, cfg)
        key = (row["outbound_date"], row["return_date"], row["run_id"])
        if key not in best or cost < best[key][0]:
            best[key] = (cost, notes, row)

    threshold = cfg.DEAL_THRESHOLD_SGD
    lines = []
    for (outbound, ret, rid), (cost, notes, row) in sorted(best.items()):
        if rid != run_id:
            continue
        earlier = [best[k][0] for k in sorted(best) if k[:2] == (outbound, ret) and k[2] < run_id]
        prev_low = min(earlier, default=None)
        new_low = prev_low is not None and cost < prev_low
        crossed = threshold is not None and cost < threshold and not (earlier and earlier[-1] < threshold)
        if not (new_low or crossed):
            continue
        parts = [f"{_pair(outbound, ret)}: {_describe(row, cost, notes)}",
                 f"previous low {_sgd(prev_low)}" if prev_low is not None else "no previous low"]
        if crossed:
            parts.append(f"below {_sgd(threshold)} threshold")
        lines.append(", ".join(parts))
    return "\n".join(["Flight deal", *lines]) if lines else None


def run_summary(conn, run_id, cfg, top=3):
    """Digest of one run: status, its cheapest qualifying options per pair, and each pair's all-time low."""
    run = conn.execute("SELECT started_at, pairs_ok, pairs_failed FROM runs WHERE id = ?", (run_id,)).fetchone()
    lines = [f"Run {run_id}, {run['started_at'][:16].replace('T', ' ')}: "
             f"{run['pairs_ok']}/{run['pairs_ok'] + run['pairs_failed']} pairs OK"]
    latest, all_time = {}, {}  # (outbound, return) -> qualifying (cost, notes, row); all_time keeps the min
    for row in conn.execute("SELECT * FROM itineraries WHERE run_id <= ? ORDER BY id", (run_id,)):
        if not meets_arrival_window(row, cfg):
            continue
        cost, notes = adjusted_cost(row, cfg)
        key = (row["outbound_date"], row["return_date"])
        if row["run_id"] == run_id:
            latest.setdefault(key, []).append((cost, notes, row))
        if key not in all_time or cost < all_time[key][0]:
            all_time[key] = (cost, notes, row)
    for key in sorted(latest):
        options = sorted(latest[key], key=lambda option: option[0])
        lines.append(f"\n{_pair(*key)} (via {options[0][2]['source']}):")
        lines += [f"{i}. {_describe(row, cost, notes)}" for i, (cost, notes, row) in enumerate(options[:top], 1)]
        lines.append(f"All-time low: {_sgd(all_time[key][0])} (run {all_time[key][2]['run_id']})")
    if not latest:
        lines.append("No flight in this run meets the arrival window.")
    return "\n".join(lines)
