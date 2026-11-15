from backend import db
from backend.detector import find_surges, metrics

NOW = 1_700_000_000
KW = dict(min_count=50, min_ratio=3.0, cooldown_minutes=180, escalation=2.0, now=NOW)


def rows(short, long, prev=None, age=None):
    return metrics("add", short, long, 1, 24, prev, age)


def test_surge_vs_baseline():
    conn = db.connect(":memory:")
    short = {"p1": 60, "p2": 10, "p3": 80}
    long = {"p1": 60 + 23 * 5, "p2": 10 + 23 * 10, "p3": 80 + 23 * 40}
    # p1: 60 vs ~5/hr (12x) -> surge; p2: below min_count; p3: 80 vs 40/hr (2x) -> not a surge
    assert [r.player_id for r in find_surges(conn, rows(short, long), **KW)] == ["p1"]


def test_new_player_with_empty_long_list_is_a_surge():
    conn = db.connect(":memory:")
    s = find_surges(conn, rows({"rookie": 90}, {}), **KW)
    assert s and s[0].baseline_per_hr == 0


def test_sliding_off_the_24h_list_is_not_a_surge():
    # 354 adds/hr, not in the 24h top-N whose smallest entry is 5000 -> baseline could be ~200/hr
    conn = db.connect(":memory:")
    long = {"a": 5000, "b": 8000, "c": 9000}
    r = rows({"x": 354}, long)[0]
    assert r.baseline_is_bound and r.ratio < 2
    assert find_surges(conn, [r], **KW) == []


def test_market_wide_waves_are_normalized_away():
    conn = db.connect(":memory:")
    short = {"p%d" % i: 3000 for i in range(12)}
    long = {"p%d" % i: 3000 + 23 * 1000 for i in range(12)}   # everyone at 3x their usual
    short["star"], long["star"] = 12000, 12000 + 23 * 1000    # 12x raw, ~4x vs market
    kw = dict(KW, min_count=1000, min_ratio=2.0)
    assert [r.player_id for r in find_surges(conn, rows(short, long), **kw)] == ["star"]


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
    assert db.previous_snapshot(conn, "add", 1, NOW) == (NOW - 300, {"p1": 40})
    assert db.previous_snapshot(conn, "add", 1, NOW - 600) is None
    r = rows({"p1": 60}, {"p1": 60}, {"p1": 40}, 5.0)[0]
    assert (r.delta, r.delta_minutes) == (20, 5)


def test_twilio_error_is_readable():
    import requests
    from backend.notifier import TwilioNotifier

    class Resp:
        ok = False
        status_code = 400
        text = ""

        def json(self):
            return {"code": 21211, "message": "Invalid 'To' Phone Number"}

    orig = requests.post
    requests.post = lambda *a, **k: Resp()
    try:
        TwilioNotifier("AC1", "t", "+1", "+2").send("hi")
        raise AssertionError("expected RuntimeError")
    except RuntimeError as e:
        assert "21211" in str(e) and "Invalid 'To'" in str(e)
    finally:
        requests.post = orig


def test_ntfy_payload_and_notifier_selection():
    import requests
    from backend.config import Config
    from backend.notifier import ConsoleNotifier, NtfyNotifier, build_notifier

    seen = {}

    class Resp:
        ok = True
        status_code = 200
        text = "{}"

    def fake_post(url, **kw):
        seen["url"] = url
        seen.update(kw)
        return Resp()

    orig = requests.post
    requests.post = fake_post
    try:
        NtfyNotifier("secret-topic", "https://ntfy.example/", "tok").send("body", title="T")
    finally:
        requests.post = orig
    assert seen["url"] == "https://ntfy.example/"
    assert seen["json"]["topic"] == "secret-topic"
    assert seen["json"]["title"] == "T" and seen["json"]["message"] == "body"
    assert seen["headers"]["Authorization"] == "Bearer tok"
    assert isinstance(build_notifier(Config(ntfy_topic="x")), NtfyNotifier)
    assert isinstance(build_notifier(Config()), ConsoleNotifier)
    assert isinstance(build_notifier(Config(ntfy_topic="x"), dry_run=True), ConsoleNotifier)


if __name__ == "__main__":
    for _name, _fn in sorted(globals().items()):
        if _name.startswith("test_") and callable(_fn):
            _fn()
    print("all tests passed")
