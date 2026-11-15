from sleeper_trending import db
from sleeper_trending.detector import find_surges, metrics

NOW = 1_700_000_000
KW = dict(min_count=50, min_ratio=3.0, cooldown_minutes=180, escalation=2.0, now=NOW)


def rows(short, long, prev=None):
    return metrics("add", short, long, 1, 24, prev)


def test_surge_vs_baseline():
    conn = db.connect(":memory:")
    short = {"p1": 60, "p2": 10, "p3": 80}
    long = {"p1": 60 + 23 * 5, "p2": 10 + 23 * 10, "p3": 80 + 23 * 40}
    # p1: 60 vs ~5/hr (12x) -> surge; p2: below min_count; p3: 80 vs 40/hr (2x) -> not a surge
    assert [r.player_id for r in find_surges(conn, rows(short, long), **KW)] == ["p1"]


def test_new_player_not_in_long_list_counts_as_surge():
    conn = db.connect(":memory:")
    s = find_surges(conn, rows({"rookie": 90}, {}), **KW)
    assert s and s[0].baseline_per_hr == 0


def test_cooldown_and_escalation():
    conn = db.connect(":memory:")
    db.record_alert(conn, "p1", "add", NOW, 60)
    long = {"p1": 60}
    later = dict(KW, now=NOW + 600)
    assert find_surges(conn, rows({"p1": 60}, long), **later) == []        # still cooling down
    assert find_surges(conn, rows({"p1": 130}, {"p1": 130}), **later)      # >= 2x last alert
    after = dict(KW, now=NOW + 181 * 60)
    assert find_surges(conn, rows({"p1": 60}, long), **after)              # cooldown over


def test_delta_and_snapshots():
    conn = db.connect(":memory:")
    db.save_snapshot(conn, NOW - 300, "add", 1, {"p1": 40})
    prev = db.previous_snapshot(conn, "add", 1, NOW)
    assert prev == {"p1": 40}
    assert rows({"p1": 60}, {"p1": 60}, prev)[0].delta == 20
    assert db.previous_snapshot(conn, "add", 1, NOW - 600) is None
