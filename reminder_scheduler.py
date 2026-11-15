# reminder_scheduler.py
#
# Zamanı gelmiş hatırlatmaları bulup Telegram üzerinden bildiren arka plan
# servisi. HotwordListener'daki (worker_threads.py) sürekli-döngü + stop()
# deseniyle aynı şekilde yazılmıştır.

import time
from datetime import datetime

from PyQt5.QtCore import QThread, pyqtSignal

import note_database
import notification_service
import shift_reminder_utils
import telegram_settings

CHECK_INTERVAL_SECONDS = 60


class ReminderSchedulerThread(QThread):
    reminderNotified = pyqtSignal(int)  # note_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = True

    def run(self):
        note_database.init_db()
        while self._running:
            try:
                self._check_due_reminders()
            except Exception as e:
                print(f"⚠️ Hatırlatma servisi hatası: {e}")
            self._sleep(CHECK_INTERVAL_SECONDS)

    def _check_due_reminders(self):
        chat_id = telegram_settings.get_telegram_chat_id()
        if not chat_id:
            return
        # Uygulama kapalıyken geçen hatırlatmalar da remind_at<=now VE
        # notified_at IS NULL durumunda kalır — ilk kontrolde otomatik
        # yakalanır, ayrı bir "gecikmiş bildirim" mantığı gerekmez.
        due = note_database.get_due_reminders()
        for note in due:
            notification_service.notify_reminder_due(chat_id, note)
            self._advance_or_close(note)
            self.reminderNotified.emit(note["id"])

    def _advance_or_close(self, note):
        """Vardiya bağımlı (bkz. shift_reminder_utils.py) bir hatırlatmayı bir
        sonraki uygun güne taşır; diğer (tek seferlik) hatırlatmaları olduğu
        gibi 'bildirildi' işaretler."""
        repeat = note.get("repeat_frequency")
        if shift_reminder_utils.is_shift_repeat(repeat):
            shift_code = shift_reminder_utils.shift_code_from_repeat(repeat)
            fired_at = datetime.fromisoformat(note["remind_at"])
            time_str = fired_at.strftime("%H:%M")
            next_at = shift_reminder_utils.next_occurrence_iso(shift_code, time_str, fired_at.date())
            if next_at:
                note_database.reschedule_reminder(note["id"], next_at)
                return
            print(f"⚠️ Vardiya hatırlatması için sonraki tarih bulunamadı (not id={note['id']}), tek seferlik kapatılıyor.")
        note_database.mark_reminder_notified(note["id"])

    def _sleep(self, seconds):
        for _ in range(seconds * 10):
            if not self._running:
                return
            self.msleep(100)

    def stop(self):
        self._running = False
        self.wait()
