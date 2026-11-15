import statistics
from dataclasses import dataclass
from typing import Dict, List, Optional

from . import db

MIN_MARKET_SAMPLE = 10  # players needed before we trust a market-wide activity estimate


@dataclass
class Row:
    player_id: str
    kind: str
    count: int               # adds/drops in the short window
    baseline_per_hr: float   # player's usual hourly rate (an upper bound if baseline_is_bound)
    raw_ratio: float         # count / max(baseline, 1)
    ratio: float = 0.0       # raw_ratio divided by the market-wide factor
    market_factor: float = 1.0
    delta: Optional[int] = None          # change in short-window count since the previous poll
    delta_minutes: Optional[int] = None  # how long ago that previous poll was
    baseline_is_bound: bool = False      # player missing from the long list


def metrics(kind, short: Dict[str, int], long: Dict[str, int], short_hours: int,
            long_hours: int, prev: Optional[Dict[str, int]] = None,
            prev_age_min: Optional[float] = None) -> List[Row]:
    """Score each player in the short-window list.

    Baseline: (long - short) / (long_hours - short_hours) is the player's usual hourly rate.
    Missing from the long top-N: their 24h count is at most the list's smallest entry, so that
    gives an upper bound on their baseline. The ratio is then a conservative lower bound
    instead of the old "baseline = 0" guess, which fired whenever a player merely slid off
    the bottom of the 24h list.

    Market factor: when everyone's count is ~3x their norm (waiver runs, Sunday morning,
    Tuesday-night news cycle), that's platform traffic, not news. We divide every ratio by the
    median ratio so only players moving *more than the market* stand out.
    """
    rest_hours = max(long_hours - short_hours, 1)
    cutoff = min(long.values()) if long else 0
    rows = []
    for pid, c in short.items():
        bound = pid not in long
        long_count = cutoff if bound else long[pid]
        baseline = max(long_count - c, 0) / rest_hours
        raw = c / max(baseline, 1.0)
        delta = delta_min = None
        if prev is not None:
            delta = c - prev.get(pid, 0)
            if prev_age_min is not None:
                delta_min = int(round(prev_age_min))
        rows.append(Row(pid, kind, c, baseline, raw, delta=delta,
                        delta_minutes=delta_min, baseline_is_bound=bound))

    ref = [r.raw_ratio for r in rows if not r.baseline_is_bound]
    market = max(statistics.median(ref), 1.0) if len(ref) >= MIN_MARKET_SAMPLE else 1.0
    for r in rows:
        r.market_factor = market
        r.ratio = r.raw_ratio / market
    return sorted(rows, key=lambda r: r.count, reverse=True)


def find_surges(conn, rows: List[Row], *, min_count: int, min_ratio: float,
                cooldown_minutes: int, escalation: float, now: int) -> List[Row]:
    out = []
    for r in rows:
        if r.count < min_count or r.ratio < min_ratio:
            continue
        last = db.last_alert(conn, r.player_id, r.kind)
        if last:
            alerted_at, last_cnt = last
            in_cooldown = now - alerted_at < cooldown_minutes * 60
            escalated = r.count >= last_cnt * escalation
            if in_cooldown and not escalated:
                continue
        out.append(r)
    return out
