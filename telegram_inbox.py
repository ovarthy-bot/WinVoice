# telegram_inbox.py
#
# Telefondan Telegram'a yazılan mesajları HAKKIMDA/00_Gelen_Kutusu'na yeni
# birer not olarak kaydeder — kasadaki mevcut "Hızlı Yakala / Gelen Kutusu"
# akışıyla aynı mantık (bkz. HAKKIMDA/_Sistem/Rehber/Hızlı Ekle Sistemi.md):
# hızlıca yakalanan not buraya düşer, kullanıcı daha sonra Obsidian'daki
# "Gelen Kutusunu İşle" komutuyla ilgili alana taşır.
#
# PyQt bağımlılığı YOKTUR; dashboard_ui.py'deki TelegramInboxThread bu
# modülü bir arka plan iş parçacığından çağırır (bkz. "📥 Telegram
# Notlarını İşle" hızlı işlem butonu).
#
# Güvenlik: SADECE settings.json'da kayıtlı chat_id'den gelen mesajlar işlenir.
# Bot token'ı başka biri ele geçirip bota yazsa bile (chat_id eşleşmediği
# için) kasaya hiçbir şey eklenmez.

import os
import re

import telegram_notify
import telegram_settings

INBOX_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "HAKKIMDA", "00_Gelen_Kutusu",
)

TITLE_MAX_LEN = 60

_INVALID_FS_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WHITESPACE_RE = re.compile(r"\s+")


def _title_from_message(text):
    """Notun başlığını (ve dosya adını) mesajın ilk satırından, en fazla
    TITLE_MAX_LEN karakter olacak şekilde (kelime ortasından kesmeden) çıkarır."""
    first_line = text.strip().splitlines()[0].strip() if text.strip() else ""
    if not first_line:
        return "Telegram Notu"
    if len(first_line) <= TITLE_MAX_LEN:
        return first_line
    truncated = first_line[:TITLE_MAX_LEN].rsplit(" ", 1)[0].strip()
    return truncated or first_line[:TITLE_MAX_LEN]


def _sanitize_filename(name):
    name = _INVALID_FS_CHARS_RE.sub(" ", name)
    name = _WHITESPACE_RE.sub(" ", name).strip().strip(".")
    return name or "Telegram Notu"


def _unique_note_path(title):
    base = _sanitize_filename(title)
    candidate = os.path.join(INBOX_DIR, f"{base}.md")
    counter = 2
    while os.path.exists(candidate):
        candidate = os.path.join(INBOX_DIR, f"{base} ({counter}).md")
        counter += 1
    return candidate


def _note_content(title, message_text):
    # Kasadaki Genel Not Şablonu ile aynı frontmatter alanları (tür/kategori/
    # tags); "telegram" etiketi notun kaynağını işaretler. Dosya oluşturulma
    # zamanı Obsidian tarafından zaten tutulduğundan (bkz. Hızlı Ekle
    # Sistemi.md "Tarih ve saat yaklaşımı") içeriğe ayrıca tarih eklenmez.
    return (
        "---\n"
        "tür: not\n"
        'kategori: ""\n'
        "tags: [telegram]\n"
        "---\n\n"
        f"# {title}\n\n"
        f"{message_text.strip()}\n"
    )


def save_message_as_note(message_text):
    """Mesaj metnini HAKKIMDA/00_Gelen_Kutusu'na yeni bir .md not olarak
    kaydeder. Döner: (title, dosya_yolu)."""
    title = _title_from_message(message_text)
    path = _unique_note_path(title)
    os.makedirs(INBOX_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(_note_content(title, message_text))
    return title, path


def process_new_messages(notify=True):
    """Son kontrolden beri gelen, SADECE ayarlı chat_id'den gönderilmiş
    YAZILI mesajları kasaya yeni not olarak kaydeder (fotoğraf/sesli mesaj/
    sticker gibi metin içermeyenler yok sayılır). Her not için (notify=True
    ise) Telegram'a kısa bir onay gönderilir. Döner: [(title, path), ...]."""
    token = telegram_settings.get_telegram_bot_token()
    expected_chat_id = str(telegram_settings.get_telegram_chat_id())
    if not token or not expected_chat_id:
        raise RuntimeError("Telegram ayarlanmamış (bot_token/chat_id eksik).")

    last_update_id = telegram_settings.get_telegram_last_update_id()
    offset = (last_update_id + 1) if last_update_id is not None else None
    updates = telegram_notify.get_updates(token, offset=offset)

    saved = []
    highest_update_id = last_update_id
    for update in updates:
        update_id = update.get("update_id")
        if update_id is not None:
            highest_update_id = update_id if highest_update_id is None else max(highest_update_id, update_id)

        message = update.get("message") or {}
        chat_id = str(message.get("chat", {}).get("id", ""))
        text = message.get("text")

        if chat_id != expected_chat_id or not text:
            continue

        title, path = save_message_as_note(text)
        saved.append((title, path))
        if notify:
            try:
                telegram_notify.send_message(token, expected_chat_id, f"✅ Not eklendi: {title}")
            except telegram_notify.TelegramError:
                pass  # not zaten kaydedildi; onay gönderilemese de işlem başarısız sayılmaz

    if highest_update_id is not None:
        telegram_settings.set_telegram_last_update_id(highest_update_id)

    return saved
