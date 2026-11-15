# sleeper-add-drop-alerts
Polls sleepers read-only API for player add/drop trends (NFL Fantasy)

Texts you when a player's adds or drops **across all of Sleeper** surge.

## How it works
Each poll makes 4 calls (add/drop x 1h/24h windows):
1. Short window (default 1h) = what's happening *now*.
2. Long window (default 24h) = baseline. The player's usual hourly rate is
   `(24h count - 1h count) / 23`.
3. Alert when `count_1h >= MIN_COUNT` **and** `count_1h >= MIN_RATIO x max(usual rate, 1)`.
4. Same player is muted for `COOLDOWN_MINUTES`, unless their count has grown to
   `ESCALATION_FACTOR` x the last alert's count (so a snowballing add trend re-pings you).

Because the baseline comes from the API itself, it works from the first poll. Every poll is also
saved to SQLite (kept 7 days), and each alert includes the change since the previous poll.

Example text:
`Sleeper ADD surge: Jaylen Warren (RB/PIT) added 142x in 1h (usually ~9/hr, 15.8x), +37 since last check`

## Setup
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt pytest
cp .env.example .env
python -m sleeper_trending --top              # see current movers + ratios; use this to tune thresholds
python -m sleeper_trending --once --dry-run   # one poll, alerts print to console
python -m sleeper_trending                    # poll forever (every 30 sec by default)
pytest
```
Add Twilio creds to `.env` to get real texts; with them blank, alerts print to the console.
Edit `POLL_SECONDS` and the alert thresholds in `.env` to tune polling and notifications.

## Tuning
- Raise `MIN_COUNT` if you get noise from low-volume players; the right level changes a lot between
  the offseason and a Tuesday night in-season. `--top` shows what's normal right now.
- The API's window is in whole hours, so 1h is the shortest "now" window. For faster signals, lower
  `POLL_SECONDS`; the "+N since last check" in each alert shows momentum between polls. Lengthen
  `COOLDOWN_MINUTES` for fewer texts.
- `ALERT_KINDS=add` for adds only.

## Notes
- Sleeper's API is free for **non-commercial** use and asks for attribution if you publicly display
  trending data. The default configuration makes 4 trending calls per poll (2 kinds x 2 windows),
  or about 8 calls/minute at a 30-second poll interval. The player catalog is cached for up to a day.
- A player absent from the 24h top-N list is treated as having a baseline of 0 (brand new). Raise
  `TRENDING_LIMIT` if you see false positives from mid-tier players.
- Waiver runs and injury news cause sudden add/drop waves; that's the signal working as intended.
