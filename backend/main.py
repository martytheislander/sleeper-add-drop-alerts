from __future__ import annotations

import argparse
import time

from . import db as database
from .config import Config
from .detector import find_surges, metrics
from .notifier import build_notifier
from .sleeper import SleeperClient


def fetch(cfg: Config, client: SleeperClient, kind: str):
    short = client.trending(cfg.sport, kind, cfg.short_hours, cfg.limit)
    long = client.trending(cfg.sport, kind, cfg.long_hours, cfg.limit)
    return short, long


def format_alert(cfg: Config, client: SleeperClient, r) -> str:
    verb = "added" if r.kind == "add" else "dropped"
    label = client.player_label(r.player_id, cfg.sport)
    msg = (f"Sleeper {r.kind.upper()} surge: {label} {verb} {r.count}x in {cfg.short_hours}h "
           f"(usually ~{r.baseline_per_hr:.0f}/hr, {r.ratio:.1f}x)")
    if r.delta is not None:
        msg += f", {r.delta:+d} since last check"
    return msg


def run_cycle(cfg: Config, client: SleeperClient, conn, notifier, now: int | None = None) -> int:
    now = now or int(time.time())
    sent = 0
    for kind in cfg.kinds:
        try:
            short, long = fetch(cfg, client, kind)
        except Exception as e:  # one failed call shouldn't kill the loop
            print(f"{kind}: fetch failed: {e}")
            continue
        prev = database.previous_snapshot(conn, kind, cfg.short_hours, now)
        database.save_snapshot(conn, now, kind, cfg.short_hours, short)
        database.save_snapshot(conn, now, kind, cfg.long_hours, long)
        rows = metrics(kind, short, long, cfg.short_hours, cfg.long_hours, prev)
        for r in find_surges(conn, rows, min_count=cfg.min_count, min_ratio=cfg.min_ratio,
                             cooldown_minutes=cfg.cooldown_minutes,
                             escalation=cfg.escalation, now=now):
            notifier.send(format_alert(cfg, client, r))
            database.record_alert(conn, r.player_id, r.kind, now, r.count)
            sent += 1
    database.prune(conn, now - 7 * 86400)
    return sent


def show_top(cfg: Config, client: SleeperClient, n: int = 15) -> None:
    """Print current top movers with their ratios, to help you tune MIN_COUNT / MIN_RATIO."""
    for kind in cfg.kinds:
        short, long = fetch(cfg, client, kind)
        print(f"\nTop {kind}s, last {cfg.short_hours}h (vs. prior {cfg.long_hours - cfg.short_hours}h avg)")
        print(f"{'player':38}{'count':>7}{'usual/hr':>10}{'ratio':>8}")
        for r in metrics(kind, short, long, cfg.short_hours, cfg.long_hours)[:n]:
            print(f"{client.player_label(r.player_id, cfg.sport):38}{r.count:>7}"
                  f"{r.baseline_per_hr:>10.1f}{r.ratio:>8.1f}")


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
