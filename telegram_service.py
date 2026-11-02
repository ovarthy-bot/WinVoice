# telegram_service.py
#
# Arka planda sürekli çalışan Telegram uzun-yoklama (long polling) servisi.
# `TelegramPollThread`, dashboard_ui.py'deki diğer QThread'lerle (ör.
# WeatherFetchThread, eski TelegramInboxThread) AYNI deseni izler: run()
# içinde try/except, sonuçlar pyqtSignal ile bildirilir.
#
# NOT — mevcut "📥 Telegram Notlarını İşle" butonunun (telegram_inbox.py)
# kullandığı AYNI `telegram_last_update_id` offset'ini paylaşır: Telegram'ın
# getUpdates offset mekanizması sunucu tarafında TEK bir sayaçtır (bota özel,
# çağırana özel değil) — iki ayrı sayaç tutmak aynı mesajın iki ayrı sisteme
# (eski .md notu + yeni sınıflandırılmış not) düşmesine ya da mesajların
# atlanmasına yol açardı. Bu servis sürekli çalıştığı için pratikte eski
# butona artık "yeni mesaj yok" düşer — bu beklenen ve zararsızdır, buton
# yine de çalışır durumda kalır.

from PyQt5.QtCore import QThread, pyqtSignal

import note_database
import note_manager
import telegram_notify
import telegram_settings

POLL_TIMEOUT_SECONDS = 25
NOT_CONFIGURED_RETRY_SECONDS = 30
ERROR_RETRY_SECONDS = 10


class TelegramPollThread(QThread):
    messageProcessed = pyqtSignal()
    pollError = pyqtSignal(str)

    def __init__(self, get_llm_func, parent=None):
        super().__init__(parent)
        # Model Dashboard > Ayarlar'da değişebildiği için (bkz. main.py
        # set_active_llm_model) `llm` nesnesini sabit almak yerine, her
        # mesajda GÜNCEL modeli almak için bir fonksiyon referansı tutulur.
        self._get_llm = get_llm_func
        self._running = True

    def run(self):
        note_database.init_db()
        while self._running:
            if not telegram_settings.is_telegram_configured():
                self._sleep(NOT_CONFIGURED_RETRY_SECONDS)
                continue
            try:
                self._poll_once()
            except telegram_notify.TelegramError as e:
                print(f"⚠️ Telegram uzun-yoklama hatası: {e}")
                self.pollError.emit(str(e))
                self._sleep(ERROR_RETRY_SECONDS)
            except Exception as e:
                print(f"⚠️ Telegram servisinde beklenmeyen hata: {e}")
                self.pollError.emit(str(e))
                self._sleep(ERROR_RETRY_SECONDS)

    def _poll_once(self):
        token = telegram_settings.get_telegram_bot_token()
        expected_chat_id = str(telegram_settings.get_telegram_chat_id())
        last_update_id = telegram_settings.get_telegram_last_update_id()
        offset = (last_update_id + 1) if last_update_id is not None else None

        updates = telegram_notify.get_updates(token, offset=offset, poll_timeout=POLL_TIMEOUT_SECONDS)
        if not updates:
            return

        highest_update_id = last_update_id
        for update in updates:
            update_id = update.get("update_id")
            if update_id is not None:
                highest_update_id = update_id if highest_update_id is None else max(highest_update_id, update_id)

            message = update.get("message") or {}
            chat_id = str(message.get("chat", {}).get("id", ""))
            text = message.get("text")

            # Yalnızca ayarlı chat_id'den gelen YAZILI mesajlar işlenir (bkz.
            # telegram_inbox.py'deki aynı güvenlik kuralı).
            if chat_id != expected_chat_id or not text:
                continue

            # ÖNCE ham mesajı kaydet (kaybolmama güvencesi), SONRA sınıflandır.
            msg_id = note_database.insert_telegram_message(
                chat_id, text,
                telegram_update_id=update_id,
                telegram_message_id=message.get("message_id"),
            )
            try:
                note_manager.process_telegram_message(self._get_llm(), chat_id, text, msg_id)
            except Exception as e:
                note_database.mark_message_status(msg_id, "error")
                print(f"⚠️ Not işlenemedi (mesaj yine de kayıtlı, id={msg_id}): {e}")
            self.messageProcessed.emit()

        if highest_update_id is not None:
            telegram_settings.set_telegram_last_update_id(highest_update_id)

    def _sleep(self, seconds):
        for _ in range(seconds * 10):
            if not self._running:
                return
            self.msleep(100)

    def stop(self):
        self._running = False
        self.wait()
