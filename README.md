# sleeper-add-drop-alerts
Polls sleepers read-only API for player add/drop trends (NFL Fantasy)

Texts you when a player's adds or drops **across all of Sleeper** surge.

## How it works
Each poll makes 4 calls (add/drop x 1h/24h windows):
1. Short window (default 1h) = what's happening *now*.
2. Long window (default 24h) estimates the player's usual hourly rate:
  `(24h count - 1h count) / 23`.
3. If a player is missing from the long-window top 100, its lowest count is used as an upper-bound
  estimate instead of assuming the player's usual rate is zero.
4. With at least 10 usable baselines, ratios are normalized against the median player ratio to
  account for market-wide activity spikes.
5. Alert when the short-window count meets `MIN_COUNT` and the market-adjusted ratio meets
  `MIN_RATIO`. `EXCLUDE_POSITIONS` filters positions before alerting.
6. A player is muted for `COOLDOWN_MINUTES`, unless its count reaches `ESCALATION_FACTOR` times
  the last alerted count. At most `MAX_ALERTS_PER_POLL` players are included in one notification.

The baseline is available on the first poll. Snapshots are saved to SQLite for seven days. When a
previous poll is less than an hour old, alerts include the count change and age of that snapshot.

Example text:
`Sleeper trends:\nADD Jaylen Warren (RB/PIT): 142 in 1h, 3.2x normal, +37 vs 5m ago`

## Setup
Run these commands from the repository root so the database and player cache stay under `data/`.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt pytest
cp .env.example .env
python -m backend --top             # see current movers + ratios; tune thresholds
python -m backend --once --dry-run  # one poll, alerts print to console
python -m backend                   # poll forever (every 5 min by default)
pytest backend/tests
```
Add Twilio creds to `.env` to get real texts; with them blank, alerts print to the console.
Edit `POLL_SECONDS` and the alert thresholds in `.env` to tune polling and notifications.

## Tuning
- Raise `MIN_COUNT` or `MIN_RATIO` to reduce alerts; `--top` shows raw and market-adjusted ratios.
- Set `EXCLUDE_POSITIONS` to omit positions (defaults to kickers and defenses), and lower
  `MAX_ALERTS_PER_POLL` to send fewer player entries per notification.
- The API's window is in whole hours, so 1h is the shortest "now" window. Lower `POLL_SECONDS` for
  more frequent checks. Alert deltas are shown only when the previous snapshot is less than an hour
  old. Lengthen `COOLDOWN_MINUTES` for fewer repeat alerts.
- `ALERT_KINDS=add` for adds only.

## Notes
- Sleeper's API is free for **non-commercial** use and asks for attribution if you publicly display
  trending data. The default configuration makes 4 trending calls per poll (2 kinds x 2 windows),
  or about 0.8 calls/minute at a 5-minute poll interval. The player catalog is cached for up to a day.
- The long-window API is top-N limited. Increase `TRENDING_LIMIT` if its cutoff is too high to give
  useful baseline estimates for players near the bottom of the short-window list.
- Waiver runs and injury news cause sudden add/drop waves; that's the signal working as intended.
