# notification_service.py
#
# Not Yönetimi modülünün Telegram'a giden TÜM bildirim metinlerinin tek
# merkezi. telegram_notify.send_message üzerine ince bir sarmalayıcıdır;
# böylece "kullanıcıya nasıl haber veriyoruz" tek bir yerde değişir (ör.
# ileride TTS eklenecekse tek değişiklik noktası burası olur — bu modülün
# kapsamında TTS YOK, yalnızca Telegram).

import telegram_notify
import telegram_settings

CATEGORY_LABELS = {
    "appointment": "Randevu",
    "shopping": "Alışveriş",
    "reminder": "Hatırlatma",
    "general": "Genel Not",
}


def _send(chat_id, text):
    token = telegram_settings.get_telegram_bot_token()
    if not token or not chat_id:
        print("⚠️ Telegram bildirimi gönderilemedi: bot token veya chat_id eksik.")
        return
    try:
        telegram_notify.send_message(token, chat_id, text)
    except telegram_notify.TelegramError as e:
        # Bildirim gönderilemese bile çağıran taraf (note_manager) notu zaten
        # veritabanına kaydetmiş olur — bildirim hatası veri kaybına yol açmaz.
        print(f"⚠️ Telegram bildirimi gönderilemedi: {e}")


def notify_note_saved(chat_id, note):
    label = CATEGORY_LABELS.get(note["category"], "Not")
    review_hint = " (kategoriyi kontrol et — düşük/orta güven)" if note.get("needs_review") else ""
    _send(chat_id, f"✅ {label} eklendi: {note['title']}{review_hint}")


def ask_clarifying_question(chat_id, question_text):
    _send(chat_id, f"❓ {question_text}")


def send_answer(chat_id, answer_text):
    _send(chat_id, f"💬 {answer_text}")


def notify_reminder_due(chat_id, note):
    _send(chat_id, f"⏰ Hatırlatma: {note['title']}" + (f"\n{note['description']}" if note.get("description") else ""))
