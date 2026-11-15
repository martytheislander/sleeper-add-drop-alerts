"""Client for Sleeper's free, read-only API. Non-commercial use; stay well under 1000 calls/min."""
from __future__ import annotations

import json
import os
import time

import requests

BASE = "https://api.sleeper.app/v1"


class SleeperClient:
    def __init__(self, players_cache: str = "data/players.json", timeout: int = 20):
        self.session = requests.Session()
        self.timeout = timeout
        self.players_cache = players_cache
        self._players: dict | None = None

    def _get(self, path: str):
        r = self.session.get(f"{BASE}{path}", timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def trending(self, sport: str, kind: str, lookback_hours: int, limit: int) -> dict[str, int]:
        """kind is 'add' or 'drop'. Returns {player_id: count} across all Sleeper users."""
        data = self._get(
            f"/players/{sport}/trending/{kind}?lookback_hours={lookback_hours}&limit={limit}"
        )
        return {str(d["player_id"]): int(d["count"]) for d in data}

    def players(self, sport: str = "nfl", max_age_hours: int = 24) -> dict:
        """~5MB; Sleeper asks for at most one call per day, so it's cached on disk."""
        if self._players is not None:
            return self._players
        fresh = (
            os.path.exists(self.players_cache)
            and time.time() - os.path.getmtime(self.players_cache) < max_age_hours * 3600
        )
        if fresh:
            with open(self.players_cache) as f:
                self._players = json.load(f)
        else:
            self._players = self._get(f"/players/{sport}")
            os.makedirs(os.path.dirname(self.players_cache) or ".", exist_ok=True)
            with open(self.players_cache, "w") as f:
                json.dump(self._players, f)
        return self._players

    def player_label(self, player_id: str, sport: str = "nfl") -> str:
        p = self.players(sport).get(player_id)
        if not p:
            return f"Player {player_id}"
        name = p.get("full_name") or f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
        extras = "/".join(x for x in (p.get("position"), p.get("team")) if x)
        return f"{name} ({extras})" if extras else name
