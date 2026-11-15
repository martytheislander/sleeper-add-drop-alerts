import os
from dataclasses import dataclass
from typing import Tuple

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def _list(name: str, default: str = "") -> Tuple[str, ...]:
    return tuple(x.strip() for x in os.getenv(name, default).split(",") if x.strip())


@dataclass(frozen=True)
class Config:
    sport: str = "nfl"
    kinds: Tuple[str, ...] = ("add", "drop")
    poll_seconds: int = 300
    short_hours: int = 1
    long_hours: int = 24
    limit: int = 100
    min_count: int = 1000
    min_ratio: float = 2.0
    cooldown_minutes: int = 180
    escalation: float = 2.0
    exclude_positions: Tuple[str, ...] = ("K", "DEF")
    max_alerts: int = 5
    twilio_sid: str = ""
    twilio_token: str = ""
    twilio_from: str = ""
    sms_to: str = ""
    db_path: str = "data/trending.db"
    players_cache: str = "data/players.json"

    @classmethod
    def from_env(cls) -> "Config":
        e = os.getenv
        return cls(
            sport=e("SPORT", "nfl"),
            kinds=_list("ALERT_KINDS", "add,drop"),
            poll_seconds=int(e("POLL_SECONDS", "300")),
            short_hours=int(e("SHORT_HOURS", "1")),
            long_hours=int(e("LONG_HOURS", "24")),
            limit=int(e("TRENDING_LIMIT", "100")),
            min_count=int(e("MIN_COUNT", "1000")),
            min_ratio=float(e("MIN_RATIO", "2.0")),
            cooldown_minutes=int(e("COOLDOWN_MINUTES", "180")),
            escalation=float(e("ESCALATION_FACTOR", "2.0")),
            exclude_positions=_list("EXCLUDE_POSITIONS", "K,DEF"),
            max_alerts=int(e("MAX_ALERTS_PER_POLL", "5")),
            twilio_sid=e("TWILIO_ACCOUNT_SID", ""),
            twilio_token=e("TWILIO_AUTH_TOKEN", ""),
            twilio_from=e("TWILIO_FROM", ""),
            sms_to=e("SMS_TO", ""),
        )
