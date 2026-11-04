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
# HAKKIMDA kasası <-> D1 vault_notes çift yönlü senkronunun cursor'ı (bkz.
# vault_sync_bidi.py) — en son görülen vault_notes.updated_at /
# vault_notes_deleted.deleted_at değeri. Mesaj/not cursor'larından farklı
# olarak id değil zaman damgası, çünkü vault_notes'ta autoincrement id yok.
CLOUD_SYNC_LAST_VAULT_SYNC_AT_KEY = "cloud_sync_last_vault_sync_at"

# Günlük brifingin "Önemli Etkinlikler" bölümü (bkz. events_data.py) için
# dış API anahtarları ve öncelik eşiği. Aynı anahtarlar buluta
# `wrangler secret put TMDB_API_KEY` / `FOOTBALL_API_KEY` ile ayrıca
# eklenir (bkz. cloudflare-worker/README.md) — iki taraf birbirinden
# bağımsız ayarlanır.
TMDB_API_KEY_KEY = "tmdb_api_key"
FOOTBALL_API_KEY_KEY = "football_api_key"
BRIEFING_EVENTS_MIN_PRIORITY_KEY = "briefing_events_min_priority"


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


def get_tmdb_api_key():
    return get_setting(TMDB_API_KEY_KEY, "")


def set_tmdb_api_key(key):
    set_setting(TMDB_API_KEY_KEY, key.strip())


def get_football_api_key():
    return get_setting(FOOTBALL_API_KEY_KEY, "")


def set_football_api_key(key):
    set_setting(FOOTBALL_API_KEY_KEY, key.strip())


def get_briefing_events_min_priority():
    return get_setting(BRIEFING_EVENTS_MIN_PRIORITY_KEY, "high")


def set_briefing_events_min_priority(level):
    level = level.strip().lower()
    if level not in ("high", "medium"):
        raise ValueError("min_priority sadece 'high' veya 'medium' olabilir")
    set_setting(BRIEFING_EVENTS_MIN_PRIORITY_KEY, level)


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


def get_cloud_sync_last_vault_sync_at():
    return get_setting(CLOUD_SYNC_LAST_VAULT_SYNC_AT_KEY, "1970-01-01T00:00:00.000Z")


def set_cloud_sync_last_vault_sync_at(timestamp):
    set_setting(CLOUD_SYNC_LAST_VAULT_SYNC_AT_KEY, timestamp)
