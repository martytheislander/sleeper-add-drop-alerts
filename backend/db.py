from __future__ import annotations

import os
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    ts           INTEGER NOT NULL,   -- unix seconds of the poll
    kind         TEXT NOT NULL,      -- 'add' | 'drop'
    window_hours INTEGER NOT NULL,
    player_id    TEXT NOT NULL,
    cnt          INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snap ON snapshots(kind, window_hours, ts);
CREATE TABLE IF NOT EXISTS alerts (
    player_id  TEXT NOT NULL,
    kind       TEXT NOT NULL,
    alerted_at INTEGER NOT NULL,
    cnt        INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alerts ON alerts(player_id, kind, alerted_at);
"""


def connect(path: str) -> sqlite3.Connection:
    if path != ":memory:":
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


def save_snapshot(conn, ts: int, kind: str, hours: int, counts: dict[str, int]) -> None:
    conn.executemany(
        "INSERT INTO snapshots VALUES (?,?,?,?,?)",
        [(ts, kind, hours, pid, c) for pid, c in counts.items()],
    )
    conn.commit()


def previous_snapshot(conn, kind: str, hours: int, before_ts: int) -> dict[str, int] | None:
    """The most recent saved snapshot strictly before before_ts, or None on first run."""
    row = conn.execute(
        "SELECT MAX(ts) FROM snapshots WHERE kind=? AND window_hours=? AND ts<?",
        (kind, hours, before_ts),
    ).fetchone()
    if not row or row[0] is None:
        return None
    rows = conn.execute(
        "SELECT player_id, cnt FROM snapshots WHERE kind=? AND window_hours=? AND ts=?",
        (kind, hours, row[0]),
    ).fetchall()
    return {pid: c for pid, c in rows}


def last_alert(conn, player_id: str, kind: str):
    return conn.execute(
        "SELECT alerted_at, cnt FROM alerts WHERE player_id=? AND kind=? "
        "ORDER BY alerted_at DESC LIMIT 1",
        (player_id, kind),
    ).fetchone()


def record_alert(conn, player_id: str, kind: str, ts: int, cnt: int) -> None:
    conn.execute("INSERT INTO alerts VALUES (?,?,?,?)", (player_id, kind, ts, cnt))
    conn.commit()


def prune(conn, older_than_ts: int) -> None:
    conn.execute("DELETE FROM snapshots WHERE ts<?", (older_than_ts,))
    conn.commit()
