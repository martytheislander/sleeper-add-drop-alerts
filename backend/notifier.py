from __future__ import annotations

import requests


class ConsoleNotifier:
    def send(self, body: str) -> None:
        print(f"[ALERT] {body}")


class TwilioNotifier:
    def __init__(self, sid: str, token: str, from_number: str, to_number: str):
        self.sid, self.token, self.from_number, self.to_number = sid, token, from_number, to_number

    def send(self, body: str) -> None:
        r = requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{self.sid}/Messages.json",
            auth=(self.sid, self.token),
            data={"From": self.from_number, "To": self.to_number, "Body": body},
            timeout=20,
        )
        r.raise_for_status()


def build_notifier(cfg, dry_run: bool = False):
    if dry_run or not (cfg.twilio_sid and cfg.twilio_token and cfg.twilio_from and cfg.sms_to):
        return ConsoleNotifier()
    return TwilioNotifier(cfg.twilio_sid, cfg.twilio_token, cfg.twilio_from, cfg.sms_to)
