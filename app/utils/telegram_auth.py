import hashlib
import hmac
import json
from urllib.parse import unquote, parse_qsl
from app.config import settings


def validate_telegram_init_data(init_data: str) -> dict:
    """
    Telegram WebApp initData ni HMAC-SHA256 bilan tekshiradi.
    To'g'ri bo'lsa, parsed user dict qaytaradi. Xato bo'lsa ValueError.
    
    Docs: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    hash_value = parsed.pop("hash", None)

    if not hash_value:
        raise ValueError("No hash in initData")

    # Ma'lumotlarni alifbo tartibida saralab, "key=value\n" formatda birlashtirish
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(parsed.items())
    )

    # HMAC-SHA256 kalitni hisoblash
    secret_key = hmac.new(
        b"WebAppData",
        settings.BOT_TOKEN.encode(),
        hashlib.sha256,
    ).digest()

    computed_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(computed_hash, hash_value):
        raise ValueError("Invalid Telegram initData hash")

    # User ma'lumotlarini parse qilish
    user_data = parsed.get("user")
    if not user_data:
        raise ValueError("No user data in initData")

    return json.loads(unquote(user_data))


def hmac_new(key: bytes, msg: bytes, digestmod) -> hmac.HMAC:
    """Python 3.11+ da hmac.new deprecated, shu wrapper ishlatiladi."""
    return hmac.HMAC(key, msg, digestmod)
