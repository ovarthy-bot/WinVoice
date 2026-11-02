# telegram_settings.py
#
# Günlük brifingin Telegram'a gönderilmesi için gereken bot token / chat_id
# bilgilerini settings.json üzerinden okur/yazar (bkz. tts_engine.py'deki
# get_setting/set_setting — proje genelinde tek bir ayar dosyası kullanılır).

from tts_engine import get_setting, set_setting

TELEGRAM_BOT_TOKEN_KEY = "telegram_bot_token"
TELEGRAM_CHAT_ID_KEY = "telegram_chat_id"
# HAKKIMDA Gelen Kutusu'na not olarak kaydedilmiş en son Telegram güncellemesinin
# update_id'si (bkz. telegram_inbox.py) — aynı mesajın tekrar tekrar not
# olarak eklenmesini önlemek için saklanır.
TELEGRAM_LAST_UPDATE_ID_KEY = "telegram_last_update_id"

# Bulut tarafı (Cloudflare Worker) ayarları — bkz. cloudflare-worker/README.md
# ve cloud_sync.py. PC açıldığında buluttaki yeni not/mesajları çekmek için.
CLOUD_WORKER_URL_KEY = "cloud_worker_url"
CLOUD_SYNC_SECRET_KEY = "cloud_sync_secret"
CLOUD_SYNC_LAST_MESSAGE_ID_KEY = "cloud_sync_last_message_id"
CLOUD_SYNC_LAST_NOTE_ID_KEY = "cloud_sync_last_note_id"


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


def get_telegram_last_update_id():
    return get_setting(TELEGRAM_LAST_UPDATE_ID_KEY, None)


def set_telegram_last_update_id(update_id):
    set_setting(TELEGRAM_LAST_UPDATE_ID_KEY, update_id)


def get_cloud_worker_url():
    return get_setting(CLOUD_WORKER_URL_KEY, "")


def set_cloud_worker_url(url):
    set_setting(CLOUD_WORKER_URL_KEY, url.strip().rstrip("/"))


def get_cloud_sync_secret():
    return get_setting(CLOUD_SYNC_SECRET_KEY, "")


def set_cloud_sync_secret(secret):
    set_setting(CLOUD_SYNC_SECRET_KEY, secret.strip())


def is_cloud_sync_configured():
    return bool(get_cloud_worker_url()) and bool(get_cloud_sync_secret())


def get_cloud_sync_last_message_id():
    return get_setting(CLOUD_SYNC_LAST_MESSAGE_ID_KEY, 0)


def set_cloud_sync_last_message_id(message_id):
    set_setting(CLOUD_SYNC_LAST_MESSAGE_ID_KEY, message_id)


def get_cloud_sync_last_note_id():
    return get_setting(CLOUD_SYNC_LAST_NOTE_ID_KEY, 0)


def set_cloud_sync_last_note_id(note_id):
    set_setting(CLOUD_SYNC_LAST_NOTE_ID_KEY, note_id)
