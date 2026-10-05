"""Telegram WebApp initData verification.

Ported from the reference repo's `verify_telegram_init_data` (saveitkh/BarameyDabber
server.py): HMAC-SHA256 over the sorted `key=value` fields using a secret derived from
the literal key "WebAppData" + bot token, constant-time compare, max-age check.
"""

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl


def verify_telegram_init_data(init_data: str, bot_token: str, max_age: int = 24 * 3600) -> dict | None:
    if not init_data or not bot_token:
        return None
    try:
        fields = dict(parse_qsl(init_data, keep_blank_values=True))
    except ValueError:
        return None
    received = fields.pop("hash", "")
    if not received:
        return None
    check_string = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        return None
    try:
        if time.time() - int(fields.get("auth_date", "0")) > max_age:
            return None
        user = json.loads(fields.get("user") or "{}")
    except (ValueError, TypeError):
        return None
    return user if user.get("id") else None
