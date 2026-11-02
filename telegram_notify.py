# telegram_notify.py
#
# Telegram Bot API'ye düz metin mesaj göndermek için ince bir yardımcı.
# Harici bir kütüphane (ör. python-telegram-bot) gerektirmez — proje
# genelinde zaten kullanılan urllib ile tek bir HTTPS isteği yapılır.

import json
import urllib.request
import urllib.error
import urllib.parse

TELEGRAM_API_BASE = "https://api.telegram.org"

# Telegram sendMessage, mesaj başına en fazla 4096 UTF-16 karakter kabul
# eder; daha uzun brifingler bu sınırın altında birden fazla mesaja bölünüp
# sırayla gönderilir.
TELEGRAM_MAX_MESSAGE_LEN = 4000


class TelegramError(Exception):
    """Telegram API'sine mesaj gönderilemediğinde fırlatılır."""


def _split_text(text, max_len):
    """Metni, mümkünse paragraf sınırlarından bölerek max_len karakterlik
    parçalara ayırır (tek bir kelimeyi ya da cümleyi ortadan kesmemeye çalışır)."""
    if len(text) <= max_len:
        return [text]

    parts = []
    remaining = text
    while len(remaining) > max_len:
        split_at = remaining.rfind("\n\n", 0, max_len)
        if split_at == -1:
            split_at = remaining.rfind(" ", 0, max_len)
        if split_at == -1:
            split_at = max_len
        parts.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        parts.append(remaining)
    return parts


def send_message(bot_token, chat_id, text, timeout=15):
    """Verilen metni (gerekirse birden fazla mesaja bölerek) chat_id'ye
    gönderir. Başarısızlıkta TelegramError fırlatır."""
    if not bot_token or not chat_id:
        raise TelegramError("Telegram bot_token veya chat_id ayarlanmamış.")

    url = f"{TELEGRAM_API_BASE}/bot{bot_token}/sendMessage"

    for chunk in _split_text(text, TELEGRAM_MAX_MESSAGE_LEN):
        payload = json.dumps({"chat_id": chat_id, "text": chunk}).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise TelegramError(f"Telegram API hatası ({e.code}): {body}") from e
        except urllib.error.URLError as e:
            raise TelegramError(f"Telegram'a bağlanılamadı: {e}") from e

        if not result.get("ok"):
            raise TelegramError(f"Telegram API 'ok=false' döndürdü: {result}")


def get_updates(bot_token, offset=None, timeout=15, poll_timeout=None):
    """Bota gönderilmiş güncellemeleri döner. `offset` verilirse, Telegram
    yalnızca o update_id'den itibaren olanları döner VE önceki güncellemeleri
    kendi tarafında 'okundu' işaretler (bkz. telegram_inbox.py — aynı mesajın
    tekrar tekrar işlenmesini önlemek için kullanılır). `offset` verilmezse
    (ör. ilk kurulum/chat_id keşfi) son 24 saatteki tüm güncellemeler döner.

    `poll_timeout` verilirse Telegram'ın KENDİ uzun-yoklama (long polling)
    mekanizması devreye girer: istek, o saniye kadar (en fazla ~50s) yeni bir
    güncelleme gelene dek sunucu tarafında açık tutulur (bkz.
    telegram_service.TelegramPollThread) — her birkaç saniyede bir boş
    sorgu atmak yerine, tek bir bağlantı üzerinden verimli şekilde beklenir.
    Bu durumda HTTP soket zaman aşımı (`timeout`), uzun-yoklama süresinden
    büyük tutulmalı ki sunucu henüz cevap vermeden istemci taraf kesmesin."""
    url = f"{TELEGRAM_API_BASE}/bot{bot_token}/getUpdates"
    params = {}
    if offset is not None:
        params["offset"] = offset
    if poll_timeout is not None:
        params["timeout"] = poll_timeout
        timeout = max(timeout, poll_timeout + 10)
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise TelegramError(f"Telegram API hatası ({e.code}): {body}") from e
    except urllib.error.URLError as e:
        raise TelegramError(f"Telegram'a bağlanılamadı: {e}") from e

    if not result.get("ok"):
        raise TelegramError(f"Telegram API 'ok=false' döndürdü: {result}")
    return result.get("result", [])
