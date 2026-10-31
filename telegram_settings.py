# telegram_settings.py
#
# Günlük brifingin Telegram'a gönderilmesi için gereken bot token / chat_id
# bilgilerini settings.json üzerinden okur/yazar (bkz. tts_engine.py'deki
# get_setting/set_setting — proje genelinde tek bir ayar dosyası kullanılır).

from tts_engine import get_setting, set_setting

TELEGRAM_BOT_TOKEN_KEY = "telegram_bot_token"
TELEGRAM_CHAT_ID_KEY = "telegram_chat_id"


def get_telegram_bot_token():
    return get_setting(TELEGRAM_BOT_TOKEN_KEY, "")


def set_telegram_bot_token(token):
    set_setting(TELEGRAM_BOT_TOKEN_KEY, token.strip())


def get_telegram_chat_id():
    return get_setting(TELEGRAM_CHAT_ID_KEY, "")


def set_telegram_chat_id(chat_id):
    set_setting(TELEGRAM_CHAT_ID_KEY, str(chat_id).strip())


def is_telegram_configured():
    return bool(get_telegram_bot_token()) and bool(get_telegram_chat_id())
