import requests


class ConsoleNotifier:
    def send(self, body: str, title: str = "") -> None:
        print("[ALERT] " + (title + "\n" if title else "") + body)


class TwilioNotifier:
    def __init__(self, sid: str, token: str, from_number: str, to_number: str):
        self.sid, self.token, self.from_number, self.to_number = sid, token, from_number, to_number

    def send(self, body: str, title: str = "") -> None:
        text = (title + "\n" + body) if title else body
        r = requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{self.sid}/Messages.json",
            auth=(self.sid, self.token),
            data={"From": self.from_number, "To": self.to_number, "Body": text},
            timeout=20,
        )
        if not r.ok:
            try:
                err = r.json()
                detail = "error {}: {}".format(err.get("code"), err.get("message"))
            except ValueError:
                detail = r.text[:200]
            raise RuntimeError("Twilio rejected the text (HTTP {}) - {}".format(r.status_code, detail))


class NtfyNotifier:
    """Push notification via ntfy (https://ntfy.sh or your own server). JSON publish to the
    server root, so titles/messages can contain any characters."""

    def __init__(self, topic: str, server: str = "https://ntfy.sh", token: str = ""):
        self.topic, self.server, self.token = topic, server, token

    def send(self, body: str, title: str = "") -> None:
        payload = {"topic": self.topic, "message": body, "tags": ["chart_with_upwards_trend"]}
        if title:
            payload["title"] = title
        headers = {"Authorization": "Bearer " + self.token} if self.token else {}
        r = requests.post(self.server.rstrip("/") + "/", json=payload, headers=headers, timeout=20)
        if not r.ok:
            raise RuntimeError("ntfy rejected the notification (HTTP {}) - {}".format(
                r.status_code, r.text[:200]))


def build_notifier(cfg, dry_run: bool = False):
    if dry_run:
        return ConsoleNotifier()
    if cfg.ntfy_topic:
        return NtfyNotifier(cfg.ntfy_topic, cfg.ntfy_server, cfg.ntfy_token)
    if cfg.twilio_sid and cfg.twilio_token and cfg.twilio_from and cfg.sms_to:
        return TwilioNotifier(cfg.twilio_sid, cfg.twilio_token, cfg.twilio_from, cfg.sms_to)
    return ConsoleNotifier()
