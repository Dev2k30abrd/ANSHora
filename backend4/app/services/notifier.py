"""Deliver monitor alerts: Slack / Teams / generic webhook / email (SMTP) / in-app."""
import logging
import os
import smtplib
from email.message import EmailMessage

import requests

from app.core.netguard import assert_public_url

log = logging.getLogger("anshora.notify")


def deliver(channels: list[str], title: str, body: str, severity: str = "info") -> list[dict]:
    results = []
    for ch in channels or []:
        if ch == "in_app":
            results.append({"channel": ch, "ok": True})
            continue
        try:
            kind, _, target = ch.partition(":")
            if kind in ("slack", "teams", "webhook"):
                assert_public_url(target)
                text = f"*{title}*\n{body}"
                payload = ({"text": text} if kind == "slack" else
                           {"text": f"**{title}**\n\n{body}"} if kind == "teams" else
                           {"title": title, "body": body, "severity": severity})
                r = requests.post(target, json=payload, timeout=10)
                results.append({"channel": ch.split(":")[0], "ok": r.ok, "status": r.status_code})
            elif kind == "email":
                host = os.getenv("SMTP_HOST")
                if not host:
                    results.append({"channel": "email", "ok": False, "error": "SMTP_HOST not configured"})
                    continue
                msg = EmailMessage()
                msg["Subject"], msg["To"] = title, target
                msg["From"] = os.getenv("SMTP_FROM", os.getenv("SMTP_USER", "alerts@anshora.local"))
                msg.set_content(body)
                with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=15) as s:
                    s.starttls()
                    if os.getenv("SMTP_USER"):
                        s.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASS", ""))
                    s.send_message(msg)
                results.append({"channel": "email", "ok": True})
            else:
                results.append({"channel": ch, "ok": False, "error": "unknown channel"})
        except Exception as e:  # noqa: BLE001
            log.warning("notify failed %s: %s", ch, e)
            results.append({"channel": ch.split(":")[0], "ok": False, "error": str(e)[:120]})
    return results
