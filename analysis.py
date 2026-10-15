"""Pure itinerary analysis: arrival window, red-eye, adjusted cost. Times are "YYYY-MM-DD HH:MM" local."""


def meets_arrival_window(it, cfg):
    arrive = it["arrive_time"] or ""
    date, time = arrive[:10], arrive[11:16]
    return (date == cfg.REQUIRED_ARRIVAL_DATE and time <= cfg.ARRIVAL_LATEST_LOCAL
            and (cfg.ARRIVAL_EARLIEST_LOCAL is None or time >= cfg.ARRIVAL_EARLIEST_LOCAL))


def is_red_eye(it, cfg):
    return it["depart_time"][11:16] < cfg.RED_EYE_DEPART_BEFORE_LOCAL


def adjusted_cost(it, cfg):
    """Quoted group price plus the penalties in plan.md. Returns (cost, notes)."""
    cost, notes = it["total_price_sgd"], []
    if is_red_eye(it, cfg):
        cost += cfg.RED_EYE_PENALTY_SGD
        notes.append("red-eye")
    if it["arrival_airport"] == "NRT":
        cost += cfg.NARITA_PENALTY_SGD
        notes.append(f"NRT +{cfg.NARITA_PENALTY_SGD}")
    if it["return_date"] == cfg.EXTRA_NIGHT_RETURN_DATE:
        if cfg.EXTRA_NIGHT_COST_SGD is None:
            notes.append("extra night not included")
        else:
            cost += cfg.EXTRA_NIGHT_COST_SGD
            notes.append(f"extra night +{cfg.EXTRA_NIGHT_COST_SGD}")
    fee = cfg.LCC_BAG_FEE_PER_PAX_SGD.get(it["airline"])
    if fee is not None and it["bags_included"] != 1:
        cost += fee * cfg.ADULTS
        notes.append(f"bags +{fee * cfg.ADULTS}")
    return cost, notes
