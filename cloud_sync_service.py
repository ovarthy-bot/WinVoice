# cloud_sync_service.py
#
# cloud_sync.py'nin (PyQt'ten bağımsız) senkronizasyon mantığını periyodik
# olarak arka planda çalıştıran QThread — telegram_service.TelegramPollThread'in
# üstlendiği rolün bulut mimarisindeki karşılığı (bkz. cloudflare-worker/README.md
# "Önemli" notu: artık mesajlar doğrudan Telegram webhook → Worker'a gittiği
# için burada sınıflandırma YAPILMAZ, sadece bulutta zaten sınıflandırılmış
# sonuçlar çekilip yerel notes.db'ye yazılır).

from PyQt5.QtCore import QThread, pyqtSignal

import cloud_sync
import note_database
import telegram_settings

POLL_INTERVAL_SECONDS = 20
NOT_CONFIGURED_RETRY_SECONDS = 30
ERROR_RETRY_SECONDS = 15


class CloudSyncThread(QThread):
    messageSynced = pyqtSignal()
    syncError = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = True

    def run(self):
        note_database.init_db()
        while self._running:
            if not telegram_settings.is_cloud_sync_configured():
                self._sleep(NOT_CONFIGURED_RETRY_SECONDS)
                continue
            try:
                synced_count = cloud_sync.sync_from_cloud()
                if synced_count:
                    self.messageSynced.emit()
            except cloud_sync.CloudSyncError as e:
                print(f"⚠️ Bulut senkronizasyon hatası: {e}")
                self.syncError.emit(str(e))
            except Exception as e:
                print(f"⚠️ Bulut senkronizasyonunda beklenmeyen hata: {e}")
                self.syncError.emit(str(e))
            self._sleep(POLL_INTERVAL_SECONDS)

    def _sleep(self, seconds):
        for _ in range(seconds * 10):
            if not self._running:
                return
            self.msleep(100)

    def stop(self):
        self._running = False
        self.wait()
