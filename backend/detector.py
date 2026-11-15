from __future__ import annotations

from dataclasses import dataclass

from . import db


@dataclass
class Row:
    player_id: str
    kind: str
    count: int            # adds/drops in the short window
    baseline_per_hr: float  # avg hourly rate over the rest of the long window
    ratio: float          # count / max(baseline, 1)
    delta: int | None     # change in short-window count since the previous poll


def metrics(kind, short: dict[str, int], long: dict[str, int], short_hours: int,
            long_hours: int, prev: dict[str, int] | None = None) -> list[Row]:
    """Score every player in the short-window list against their own recent baseline.

    The long window includes the short one, so the 'usual' rate is
    (long - short) / (long_hours - short_hours). A player missing from the long list
    (outside the top N) is treated as brand new, i.e. baseline 0.
    """
    rest_hours = max(long_hours - short_hours, 1)
    rows = []
    for pid, c in short.items():
        rest = max(long.get(pid, c) - c, 0)
        baseline = rest / rest_hours
        ratio = c / max(baseline, 1.0)
        delta = None if prev is None else c - prev.get(pid, 0)
        rows.append(Row(pid, kind, c, baseline, ratio, delta))
    return sorted(rows, key=lambda r: r.count, reverse=True)


def find_surges(conn, rows: list[Row], *, min_count: int, min_ratio: float,
                cooldown_minutes: int, escalation: float, now: int) -> list[Row]:
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
