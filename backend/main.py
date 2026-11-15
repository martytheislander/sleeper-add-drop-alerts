import argparse
import time

from . import db as database
from .config import Config
from .detector import find_surges, metrics
from .notifier import build_notifier
from .sleeper import SleeperClient

MAX_DELTA_AGE_MIN = 60  # don't show "since last check" if the last check was longer ago than this


def fetch(cfg: Config, client: SleeperClient, kind: str):
    short = client.trending(cfg.sport, kind, cfg.short_hours, cfg.limit)
    long = client.trending(cfg.sport, kind, cfg.long_hours, cfg.limit)
    return short, long


def position_of(cfg: Config, client: SleeperClient, player_id: str):
    return (client.players(cfg.sport).get(player_id) or {}).get("position")


def line(cfg: Config, client: SleeperClient, r) -> str:
    label = client.player_label(r.player_id, cfg.sport)
    bound = ">=" if r.baseline_is_bound else ""
    msg = f"{r.kind.upper()} {label}: {r.count} in {cfg.short_hours}h, {bound}{r.ratio:.1f}x normal"
    if r.delta is not None and r.delta_minutes is not None:
        msg += f", {r.delta:+d} vs {r.delta_minutes}m ago"
    return msg


def collect(cfg: Config, client: SleeperClient, conn, now: int):
    surges = []
    exclude = set(cfg.exclude_positions)
    for kind in cfg.kinds:
        try:
            short, long = fetch(cfg, client, kind)
        except Exception as e:  # one failed call shouldn't kill the loop
            print(f"{kind}: fetch failed: {e}")
            continue
        prev, age = None, None
        snap = database.previous_snapshot(conn, kind, cfg.short_hours, now)
        if snap:
            age = (now - snap[0]) / 60.0
            if age <= MAX_DELTA_AGE_MIN:
                prev = snap[1]
            else:
                age = None
        database.save_snapshot(conn, now, kind, cfg.short_hours, short)
        database.save_snapshot(conn, now, kind, cfg.long_hours, long)
        rows = metrics(kind, short, long, cfg.short_hours, cfg.long_hours, prev, age)
        if exclude:
            rows = [r for r in rows if position_of(cfg, client, r.player_id) not in exclude]
        surges.extend(find_surges(conn, rows, min_count=cfg.min_count, min_ratio=cfg.min_ratio,
                                  cooldown_minutes=cfg.cooldown_minutes,
                                  escalation=cfg.escalation, now=now))
    return surges


def run_cycle(cfg: Config, client: SleeperClient, conn, notifier, now=None) -> int:
    now = now or int(time.time())
    surges = collect(cfg, client, conn, now)
    surges.sort(key=lambda r: r.ratio, reverse=True)
    if surges:
        top = surges[:cfg.max_alerts]
        lines = [line(cfg, client, r) for r in top]
        extra = len(surges) - len(top)
        if extra:
            lines.append(f"(+{extra} more)")
        notifier.send("Sleeper trends:\n" + "\n".join(lines))  # one text per poll, not one per player
        for r in surges[len(top):]:
            print("  (not texted) " + line(cfg, client, r))
        for r in surges:
            database.record_alert(conn, r.player_id, r.kind, now, r.count)
    database.prune(conn, now - 7 * 86400)
    return len(surges)


def show_top(cfg: Config, client: SleeperClient, n: int = 15) -> None:
    """Print current top movers; 'adj' is the market-adjusted ratio the alert rule uses."""
    for kind in cfg.kinds:
        short, long = fetch(cfg, client, kind)
        rows = metrics(kind, short, long, cfg.short_hours, cfg.long_hours)
        market = rows[0].market_factor if rows else 1.0
        print(f"\nTop {kind}s, last {cfg.short_hours}h (market-wide factor {market:.2f}x)")
        print(f"{'player':38}{'count':>7}{'usual/hr':>10}{'raw':>7}{'adj':>7}")
        for r in rows[:n]:
            print(f"{client.player_label(r.player_id, cfg.sport):38}{r.count:>7}"
                  f"{r.baseline_per_hr:>10.1f}{r.raw_ratio:>7.1f}{r.ratio:>7.1f}")


def cli() -> None:
    ap = argparse.ArgumentParser(description="Sleeper-wide add/drop surge alerts")
    ap.add_argument("--once", action="store_true", help="poll once and exit (for cron)")
    ap.add_argument("--dry-run", action="store_true", help="print alerts instead of texting")
    ap.add_argument("--top", action="store_true", help="show current top movers and exit")
    args = ap.parse_args()

    cfg = Config.from_env()
    client = SleeperClient(cfg.players_cache)
    if args.top:
        return show_top(cfg, client)

    conn = database.connect(cfg.db_path)
    notifier = build_notifier(cfg, args.dry_run)
    while True:
        try:
            n = run_cycle(cfg, client, conn, notifier)
            print(f"{time.strftime('%H:%M:%S')} poll complete, {n} alert(s)")
        except Exception as e:
            print(f"poll failed: {e}")
        if args.once:
            break
        time.sleep(cfg.poll_seconds)
