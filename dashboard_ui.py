import io
import os
import subprocess
import threading
import time
from datetime import datetime

import win32api
import win32con
import win32gui
import win32process
from PIL import Image, ImageFilter

from PyQt5.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QFrame, QSizePolicy,
    QApplication, QStackedWidget, QScrollArea, QRadioButton, QButtonGroup, QSlider,
    QGraphicsDropShadowEffect, QPlainTextEdit, QLineEdit, QDialog, QFormLayout,
    QMessageBox, QComboBox
)
from PyQt5.QtCore import Qt, QTimer, QThread, QObject, pyqtSignal, QRectF, QSize
from PyQt5.QtGui import QPainter, QPen, QColor, QPixmap, QIcon

from chat_ui import ChatPage
from worker_threads import (
    speak_text, speak_text_interruptible, list_turkish_voices, get_selected_voice_id,
    set_selected_voice_id, get_setting, set_setting,
)
from persona_settings import (
    get_espri_pct, set_espri_pct, get_arkadaslik_pct, set_arkadaslik_pct,
)
from llm_settings import AVAILABLE_LLM_MODELS, get_llm_model
import briefing_data
import briefing_text as briefing_text_module
import tr_dates
import telegram_settings
import note_database
import vault_cache
import cloud_sync
import cloud_sync_service

# "Müzik Çal" hızlı işlem butonuyla açılan varsayılan müzik çalar
ORCHARD_EXE_PATH = r"C:\Users\Onur\Documents\GitHub\orchard\build\dev\orchard.exe"

# Pencerenin arkasında bulanıklaştırılıp koyulaştırılarak gösterilen oda fotoğrafı
BACKGROUND_PHOTO_PATH = r"C:\Users\Onur\Documents\GitHub\orchard\Sıcak Japandi Salon Tasarımı.png"

# Marka vurgu rengi: amber/altın (sıcak, "akıllı ev" temalı arayüze uygun)
ACCENT = "#F59E0B"
ACCENT_STRONG = "#D97706"
ACCENT_SOFT = "#FDE68A"

# Konum/WMO hava durumu kodları ve Türkçe tarih biçimleme artık
# briefing_data.py / tr_dates.py'de (dashboard'suz telegram_briefing.py
# tarafından da kullanılabilsin diye).
WEATHER_CODES = briefing_data.WEATHER_CODES
TR_MONTHS = tr_dates.TR_MONTHS
TR_DAYS = tr_dates.TR_DAYS
format_tr_date = tr_dates.format_tr_date
format_tr_date_short = tr_dates.format_tr_date_short


# "Akıllı Ev Kontrolleri" kartındaki görsel yer tutucu cihazlar. Hiçbiri
# gerçek bir cihaza bağlı değil — yalnızca açık/kapalı durumu yerel olarak
# (settings.json) hatırlanır. İleride gerçek bir akıllı ev entegrasyonu
# eklenirse bu liste ve _on_smart_home_toggled() güncellenebilir.
SMART_HOME_DEVICES = [
    {"id": "mutfak_isik", "icon": "💡", "title": "Mutfak", "subtitle": "Durum / Dimmer"},
    {"id": "salon_isik", "icon": "🛋️", "title": "Salon", "subtitle": "Salon / Dimmer"},
    {"id": "termostat", "icon": "🌡️", "title": "Termostat", "subtitle": "18°C · Otomatik"},
    {"id": "guvenlik_kilit", "icon": "🔒", "title": "Güvenlik", "subtitle": "Akıllı Kilit"},
]


def _load_blurred_background(path, target_size):
    """Arka plan fotoğrafını hedef boyuta 'cover' modunda kırpıp
    bulanıklaştırır ve koyulaştırır (üzerindeki yarı saydam kartların
    okunaklı kalması için), sonra QPixmap'e çevirir. Fotoğraf yoksa None
    döner — pencere bu durumda düz koyu renge geri düşer."""
    if not path or not os.path.exists(path):
        print(f"⚠️ Arka plan fotoğrafı bulunamadı: {path}")
        return None
    try:
        target_w, target_h = max(1, int(target_size[0])), max(1, int(target_size[1]))
        img = Image.open(path).convert("RGB")
        src_w, src_h = img.size
        scale = max(target_w / src_w, target_h / src_h)
        new_w, new_h = max(1, round(src_w * scale)), max(1, round(src_h * scale))
        img = img.resize((new_w, new_h), Image.LANCZOS)
        left = (new_w - target_w) // 2
        top = (new_h - target_h) // 2
        img = img.crop((left, top, left + target_w, top + target_h))
        img = img.filter(ImageFilter.GaussianBlur(radius=24))
        dark_overlay = Image.new("RGB", img.size, (10, 7, 4))
        img = Image.blend(img, dark_overlay, alpha=0.7)

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        pixmap = QPixmap()
        pixmap.loadFromData(buffer.getvalue())
        return pixmap
    except Exception as e:
        print(f"⚠️ Arka plan fotoğrafı hazırlanamadı: {e}")
        return None


# Günlük Brifing'in ham veri kaynakları (hava/haber/piyasa) artık
# briefing_data.py'de — fetch mantığı dashboard'suz telegram_briefing.py ile
# de paylaşılsın diye (bkz. WeatherFetchThread/NewsFetchThread/FinanceFetchThread).

# --------------------------------------------------------------------------- #
# Yardımcı widget'lar
# --------------------------------------------------------------------------- #

class IconBadge(QLabel):
    """Renkli, yuvarlak köşeli küçük ikon rozeti (başlıkların yanındaki simgeler)."""

    def __init__(self, glyph, bg_color="#78350F", fg_color=ACCENT_SOFT, size=40,
                 font_size=18, radius=None, parent=None):
        super().__init__(glyph, parent)
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignCenter)
        r = radius if radius is not None else size // 2
        self.setStyleSheet(f"""
            background-color: {bg_color};
            color: {fg_color};
            border-radius: {r}px;
            font-size: {font_size}px;
        """)


def _to_qcolor(color):
    """color bir (r, g, b, a) demeti veya '#RRGGBB' gibi bir QColor dizgisi
    olabilir. QColor'ın Python kurucusu CSS 'rgba(...)' söz dizimini kabul
    ETMEZ (yalnızca Qt stylesheet'leri eder) — bu yüzden saydam/tonlu rozet
    renkleri için demet kullanılması gerekir."""
    if isinstance(color, (tuple, list)):
        return QColor(*color)
    return QColor(color)


def render_icon_pixmap(glyph, bg_color="#2A2420", fg_color=ACCENT, size=28, font_size=14):
    """IconBadge ile aynı görünümü (renkli, yuvarlak rozet) bir QPixmap olarak
    çizer — QPushButton.setIcon() ile hızlı işlem butonlarının solunda sabit
    bir marka/ikon rozeti göstermek için kullanılır."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(_to_qcolor(bg_color))
    painter.drawEllipse(0, 0, size, size)
    painter.setPen(_to_qcolor(fg_color))
    font = painter.font()
    font.setPointSize(font_size)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, glyph)
    painter.end()
    return pixmap


class Divider(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(1)
        self.setStyleSheet("background-color: rgba(255, 255, 255, 25);")


class LogRelay(QObject):
    """main.py, baslat.bat'ın açtığı konsol penceresi yerine print() çıktılarını
    bir sahte stdout'ta (bkz. main.py._StdoutRelay) toplar; bu sınıf o çıktıyı
    GUI iş parçacığına güvenli şekilde taşır. emit_line() herhangi bir iş
    parçacığından (ör. HotwordListener) çağrılabilir — Qt, verici ile alıcı
    farklı iş parçacığında olduğunda sinyali otomatik olarak kuyruğa alıp ana
    iş parçacığındaki slot'a (DailyDashboardWindow.append_log_line) teslim eder."""
    line_received = pyqtSignal(str)

    def emit_line(self, text):
        self.line_received.emit(text)


class AIOrbWidget(QWidget):
    """Günlük Brifing kartının üstünde dönen, çok katmanlı amber halka
    grafiği — WinVoice'un görsel "yapay zeka çekirdeği" kimliği. Brifing
    durumuna göre (yükleniyor/hazır/hata) ortasındaki durum metni
    set_status_text() ile güncellenir."""

    def __init__(self, size=170, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._angle = 0.0
        self._status_text = "Sistem Aktif"
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(30)

    def set_status_text(self, text):
        self._status_text = text
        self.update()

    def _tick(self):
        self._angle = (self._angle + 0.9) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        base_radius = min(self.width(), self.height()) / 2 - 6

        rings = [
            (base_radius, 60, 9, 1.0),
            (base_radius * 0.76, 110, 5, -1.6),
            (base_radius * 0.54, 180, 3, 2.2),
        ]
        for radius, alpha, width, speed in rings:
            pen = QPen(QColor(245, 158, 11, alpha))
            pen.setWidth(width)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            rect = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)
            painter.drawArc(rect, int(self._angle * speed * 16), int(250 * 16))

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(245, 158, 11, 50))
        inner_r = base_radius * 0.3
        painter.drawEllipse(QRectF(cx - inner_r, cy - inner_r, inner_r * 2, inner_r * 2))

        font = painter.font()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#FDE68A"))
        painter.drawText(QRectF(cx - base_radius, cy - 12, base_radius * 2, 18),
                          Qt.AlignCenter, "WinVoice AI Core")

        font.setBold(False)
        font.setPointSize(8)
        painter.setFont(font)
        painter.setPen(QColor("#FCD34D"))
        painter.drawText(QRectF(cx - base_radius, cy + 6, base_radius * 2, 18),
                          Qt.AlignCenter, self._status_text)


class ToggleSwitch(QPushButton):
    """Akıllı Ev Kontrolleri kartındaki aç/kapat anahtarı (kayan topuzlu,
    checkable QPushButton). Hiçbir gerçek cihazı kontrol etmez — görsel
    bir yer tutucudur; durumu yalnızca settings.json'a kaydedilir."""

    def __init__(self, checked=False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(44, 24)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("QPushButton { border: none; background: transparent; }")
        self.toggled.connect(lambda _checked: self.update())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(ACCENT) if self.isChecked() else QColor("#374151"))
        painter.drawRoundedRect(self.rect(), 12, 12)

        knob_d = 18
        knob_x = self.width() - knob_d - 3 if self.isChecked() else 3
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(knob_x, 3, knob_d, knob_d)


# --------------------------------------------------------------------------- #
# Hava durumu verisi (yerel, API anahtarı gerekmeyen Open-Meteo servisi)
# --------------------------------------------------------------------------- #

class WeatherFetchThread(QThread):
    weatherReady = pyqtSignal(dict)
    weatherError = pyqtSignal(str)

    def run(self):
        try:
            self.weatherReady.emit(briefing_data.fetch_weather())
        except Exception as e:
            self.weatherError.emit(str(e))


# --------------------------------------------------------------------------- #
# Ham haber akışı (yerel, API anahtarı gerekmeyen ücretsiz RSS kaynakları).
# Bu başlıklar doğrudan kullanıcıya gösterilmez/okunmaz; brifing metnini
# üretmesi için LLM'e ham girdi olarak verilir (bkz. BriefingGenerationThread).
# --------------------------------------------------------------------------- #

class NewsFetchThread(QThread):
    newsReady = pyqtSignal(str)

    def run(self):
        self.newsReady.emit(briefing_data.fetch_news_items_text())


# --------------------------------------------------------------------------- #
# Piyasa verisi (yerel, API anahtarı gerekmeyen ücretsiz kaynaklar: TCMB,
# Yahoo Finance uç noktaları, CoinGecko).
# --------------------------------------------------------------------------- #

class FinanceFetchThread(QThread):
    financeReady = pyqtSignal(dict)

    def run(self):
        self.financeReady.emit(briefing_data.fetch_finance())


# --------------------------------------------------------------------------- #
# Günlük sesli brifing: toplanan hava/piyasa/haber verilerini LLM'e
# gönderip tek, akıcı, TTS'e uygun bir brifing metni üretir.
# --------------------------------------------------------------------------- #

class BriefingGenerationThread(QThread):
    briefingReady = pyqtSignal(str)
    briefingError = pyqtSignal(str)

    def __init__(self, generate_briefing_func, location, time_str, news_items_text, parent=None):
        super().__init__(parent)
        self._generate_briefing_func = generate_briefing_func
        self._location = location
        self._time_str = time_str
        self._news_items_text = news_items_text

    def run(self):
        try:
            text = self._generate_briefing_func(self._location, self._time_str, self._news_items_text)
            self.briefingReady.emit((text or "").strip())
        except Exception as e:
            self.briefingError.emit(str(e))


class BriefingReaderThread(QThread):
    """Brifing metni üretildikten hemen sonra, TTS ile sırayla (paragraf
    paragraf, doğal duraklamalarla) okur. Dashboard'daki Duraklat/Devam Et
    ve Durdur düğmeleri request_pause()/request_resume()/request_stop() ile
    bu iş parçacığına sinyal gönderir.

    pyttsx3'te gerçek bir pause() API'si olmadığından (bkz.
    speak_text_interruptible), "duraklatma" o anki paragrafın okunmasını
    hemen keser; "devam et" ise kesilen paragrafı BAŞTAN tekrar okur
    (tüm brifingi yeniden başlatmaz, sadece o anki paragrafı tekrarlar)."""
    finishedSpeaking = pyqtSignal()

    def __init__(self, briefing_text, pause_hotword_func=None, resume_hotword_func=None, parent=None):
        super().__init__(parent)
        self._briefing_text = briefing_text
        self._pause_hotword_func = pause_hotword_func
        self._resume_hotword_func = resume_hotword_func
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._resume_event = threading.Event()
        self._resume_event.set()

    def request_pause(self):
        self._pause_event.set()
        self._resume_event.clear()

    def request_resume(self):
        self._pause_event.clear()
        self._resume_event.set()

    def request_stop(self):
        self._stop_event.set()
        self._resume_event.set()  # duraklatılmışken durdurulursa beklemede kalmasın

    def _should_abort_word(self):
        return self._stop_event.is_set() or self._pause_event.is_set()

    def run(self):
        import pythoncom
        pythoncom.CoInitialize()
        try:
            if self._pause_hotword_func:
                try:
                    self._pause_hotword_func()
                except Exception:
                    pass

            paragraphs = [p.strip() for p in self._briefing_text.split("\n\n") if p.strip()]
            i = 0
            while i < len(paragraphs):
                if self._stop_event.is_set():
                    break
                self._resume_event.wait()  # duraklatılmışsa burada bekler
                if self._stop_event.is_set():
                    break
                speak_text_interruptible(paragraphs[i], self._should_abort_word)
                if self._stop_event.is_set():
                    break
                if self._pause_event.is_set():
                    # Bu paragraf duraklatma yüzünden kesildi; devam edilince
                    # aynı paragraf baştan tekrar okunur.
                    continue
                i += 1
        finally:
            pythoncom.CoUninitialize()
            if self._resume_hotword_func:
                try:
                    self._resume_hotword_func()
                except Exception:
                    pass
            self.finishedSpeaking.emit()


class VoiceTestThread(QThread):
    """Ayarlar sayfasında bir ses seçildiğinde/kullanıcı "Tekrar Dinle"ye
    bastığında, kısa bir örnek cümleyi o ses ile okur."""
    finishedSpeaking = pyqtSignal()

    def __init__(self, text, pause_hotword_func=None, resume_hotword_func=None, parent=None):
        super().__init__(parent)
        self._text = text
        self._pause_hotword_func = pause_hotword_func
        self._resume_hotword_func = resume_hotword_func

    def run(self):
        import pythoncom
        pythoncom.CoInitialize()
        try:
            if self._pause_hotword_func:
                try:
                    self._pause_hotword_func()
                except Exception:
                    pass
            speak_text(self._text)
        finally:
            pythoncom.CoUninitialize()
            if self._resume_hotword_func:
                try:
                    self._resume_hotword_func()
                except Exception:
                    pass
            self.finishedSpeaking.emit()


# --------------------------------------------------------------------------- #
# Hızlı işlemler: "Müzik Çal" butonu
# --------------------------------------------------------------------------- #

class MusicLaunchThread(QThread):
    """Varsayılan müzik çalarını arka planda başlatır: penceresi açılana
    kadar bekler, çalmayı tetiklemek için (yalnızca bir anlığına) öne
    getirip 'Space' tuşunu simüle eder, sonra hemen simge durumuna
    küçültüp odağı Dashboard'a geri verir. 'Space' sentetik bir tuş
    olduğundan (keybd_event) hedef pencereye ulaşması için o anda gerçekten
    odakta olması gerekiyor — bu yüzden kısa bir an için öne gelmesi
    kaçınılmaz, ama pencere arka plana (simge durumuna) alındıktan sonra
    müzik çalmaya devam eder (Windows'ta ses, pencere görünürlüğünden
    bağımsızdır)."""

    def __init__(self, exe_path, return_focus_hwnd=None, parent=None):
        super().__init__(parent)
        self._exe_path = exe_path
        self._return_focus_hwnd = return_focus_hwnd

    def _find_window_for_pid(self, pid, timeout=5.0):
        deadline = time.time() + timeout
        found = []

        def enum_handler(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd) or not win32gui.GetWindowText(hwnd):
                return
            _, window_pid = win32process.GetWindowThreadProcessId(hwnd)
            if window_pid == pid:
                found.append(hwnd)

        while time.time() < deadline and not found:
            win32gui.EnumWindows(enum_handler, None)
            if not found:
                time.sleep(0.2)
        return found[0] if found else None

    def run(self):
        if not os.path.exists(self._exe_path):
            print(f"⚠️ Müzik çalar bulunamadı: {self._exe_path}")
            return
        try:
            process = subprocess.Popen([self._exe_path])
        except Exception as e:
            print(f"⚠️ Müzik çalar başlatılamadı: {e}")
            return

        hwnd = self._find_window_for_pid(process.pid)
        if hwnd:
            try:
                win32gui.SetForegroundWindow(hwnd)
            except Exception as e:
                print(f"⚠️ Müzik çalar penceresi öne getirilemedi: {e}")
            time.sleep(0.3)
        else:
            time.sleep(0.5)

        win32api.keybd_event(win32con.VK_SPACE, 0, 0, 0)
        time.sleep(0.05)
        win32api.keybd_event(win32con.VK_SPACE, 0, win32con.KEYEVENTF_KEYUP, 0)

        if hwnd:
            # Çalma tetiklendi; pencereyi arka plana (simge durumuna) al.
            # Ses, pencere görünürlüğünden bağımsız çalışır — minimize
            # etmek çalmayı durdurmaz.
            time.sleep(0.2)
            try:
                win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
            except Exception as e:
                print(f"⚠️ Müzik çalar simge durumuna küçültülemedi: {e}")

        if self._return_focus_hwnd:
            try:
                win32gui.SetForegroundWindow(self._return_focus_hwnd)
            except Exception as e:
                print(f"⚠️ Dashboard'a odak geri verilemedi: {e}")


# --------------------------------------------------------------------------- #
# Ana pencere
# --------------------------------------------------------------------------- #

class DailyDashboardWindow(QWidget):
    def __init__(self, process_input_func=None, execute_powershell_func=None,
                 pause_hotword_func=None, resume_hotword_func=None,
                 generate_briefing_func=None, set_listening_muted_func=None,
                 set_llm_model_func=None, get_llm_func=None):
        super().__init__()
        self._process_input_func = process_input_func
        self._execute_powershell_func = execute_powershell_func
        self._pause_hotword_func = pause_hotword_func
        self._resume_hotword_func = resume_hotword_func
        self._generate_briefing_func = generate_briefing_func
        self._set_listening_muted_func = set_listening_muted_func
        self._set_llm_model_func = set_llm_model_func
        # Not Yönetimi modülü (bkz. telegram_service.TelegramPollThread) için:
        # main.py'deki `llm` global'i Ayarlar'dan model değiştirilince yeniden
        # atanıyor, bu yüzden nesnenin kendisi değil GÜNCEL değeri döndüren
        # bir fonksiyon referansı tutulur.
        self._get_llm_func = get_llm_func or (lambda: None)
        self._listening_muted = False

        self.setWindowTitle("WinVoice - Günlük Dashboard")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setMinimumSize(1100, 650)
        self._drag_pos = None

        # QWidget'a background-color VERMİYORUZ: pencere arkası fotoğrafla
        # (bulanık+koyu) paintEvent() içinde elle çiziliyor; buradaki renk
        # yalnızca metin/font için.
        self.setStyleSheet("""
            QWidget { color: #E5E7EB; font-family: 'Segoe UI'; }
        """)

        bg_target_geo = QApplication.primaryScreen().availableGeometry() if QApplication.primaryScreen() else None
        bg_size = (bg_target_geo.width(), bg_target_geo.height()) if bg_target_geo else (1280, 800)
        self._background_pixmap = _load_blurred_background(BACKGROUND_PHOTO_PATH, bg_size)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_title_bar())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_sidebar())

        self._voice_test_thread = None
        self._music_launch_thread = None

        self.content_stack = QStackedWidget()
        self.content_stack.addWidget(self._build_dashboard_page())  # index 0
        self.content_stack.addWidget(ChatPage(
            process_input_func=self._process_input_func,
            execute_powershell_func=self._execute_powershell_func,
            pause_hotword_func=self._pause_hotword_func,
            resume_hotword_func=self._resume_hotword_func,
        ))  # index 1
        self.content_stack.addWidget(self._build_settings_page())  # index 2
        self.content_stack.addWidget(self._build_notes_page())  # index 3
        body.addWidget(self.content_stack, stretch=1)

        root_layout.addLayout(body, stretch=1)

        self._start_note_management_services()

        # Not: Qt.FramelessWindowHint ile birlikte showMaximized() Windows'ta
        # pencereyi ekranın biraz dışına taşırıyor (bilinen bir Qt/Windows
        # kısıtı). Bunun yerine ekranın kullanılabilir alanına elle
        # geometri veriyoruz; "simge durumuna küçült/büyüt" butonları da
        # bu özel durumu kendileri yönetiyor.
        self._is_custom_maximized = True
        self._apply_maximized_geometry()

        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)
        self._update_clock()

        # Günlük sesli brifing: hava, piyasa ve haber verisi birbirinden
        # bağımsız iş parçacıklarında toplanır; üçü de elimize geçince
        # (biri başarısız olsa bile en azından boş veriyle "geldi" sayılır)
        # LLM ile tek bir brifing metni üretilir (_maybe_generate_briefing).
        self._weather_data_for_briefing = None
        self._finance_data = None
        self._news_items_text = None
        self._briefing_thread = None
        self._briefing_reader_thread = None

        self._weather_thread = WeatherFetchThread()
        self._weather_thread.weatherReady.connect(self._on_weather_ready)
        self._weather_thread.weatherError.connect(self._on_weather_error)
        self._weather_thread.start()

        self._finance_thread = FinanceFetchThread()
        self._finance_thread.financeReady.connect(self._on_finance_ready)
        self._finance_thread.start()

        self._news_thread = NewsFetchThread()
        self._news_thread.newsReady.connect(self._on_news_raw_ready)
        self._news_thread.start()

    # ------------------------------------------------------------------- #
    # Üst başlık çubuğu (özel - pencere çerçevesi olmadığı için elle çizildi)
    # ------------------------------------------------------------------- #
    def _build_title_bar(self):
        bar = QFrame()
        bar.setFixedHeight(48)
        bar.setStyleSheet("background-color: rgba(10, 8, 6, 160); border-bottom: 1px solid rgba(255,255,255,20);")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 10, 0)
        layout.setSpacing(10)

        layout.addWidget(IconBadge("🎤", bg_color=ACCENT, fg_color="#FFFFFF", size=30, font_size=15, radius=9))

        brand_label = QLabel("WinVoice")
        brand_label.setStyleSheet("font-size: 15px; font-weight: 600; color: #F1F5F9;")
        layout.addWidget(brand_label)

        layout.addStretch()

        btn_style = """
            QPushButton { background-color: transparent; color: #CBD5E1; border: none;
                          font-size: 14px; border-radius: 6px; }
            QPushButton:hover { background-color: rgba(255,255,255,20); }
        """
        close_style = """
            QPushButton { background-color: transparent; color: #CBD5E1; border: none;
                          font-size: 14px; border-radius: 6px; }
            QPushButton:hover { background-color: #E81123; color: white; }
        """

        min_btn = QPushButton("—")
        min_btn.setFixedSize(40, 32)
        min_btn.setStyleSheet(btn_style)
        min_btn.clicked.connect(self.showMinimized)
        layout.addWidget(min_btn)

        self._maximize_btn = QPushButton("☐")
        self._maximize_btn.setFixedSize(40, 32)
        self._maximize_btn.setStyleSheet(btn_style)
        self._maximize_btn.clicked.connect(self._toggle_maximize_restore)
        layout.addWidget(self._maximize_btn)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(40, 32)
        close_btn.setStyleSheet(close_style)
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

        self._title_bar = bar
        return bar

    def _apply_maximized_geometry(self):
        screen = QApplication.primaryScreen()
        geo = screen.availableGeometry() if screen else None
        if geo:
            self.setGeometry(geo)
        else:
            self.resize(1280, 800)
        self.show()
        self._is_custom_maximized = True
        self._maximize_btn.setText("❐")

    def _apply_normal_geometry(self):
        screen = QApplication.primaryScreen()
        geo = screen.availableGeometry() if screen else None
        w, h = 1200, 760
        if geo:
            x = geo.x() + (geo.width() - w) // 2
            y = geo.y() + (geo.height() - h) // 2
            self.setGeometry(x, y, w, h)
        else:
            self.resize(w, h)
        self.show()
        self._is_custom_maximized = False
        self._maximize_btn.setText("☐")

    def _toggle_maximize_restore(self):
        if self._is_custom_maximized:
            self._apply_normal_geometry()
        else:
            self._apply_maximized_geometry()

    # Başlık çubuğundan pencereyi sürükleyebilme (sadece tam ekran değilken)
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._title_bar.geometry().contains(event.pos()):
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() == Qt.LeftButton and not self._is_custom_maximized:
            self.move(event.globalPos() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        if self._background_pixmap and not self._background_pixmap.isNull():
            pm = self._background_pixmap
            if pm.size() != self.size():
                pm = pm.scaled(self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            x = (self.width() - pm.width()) // 2
            y = (self.height() - pm.height()) // 2
            painter.drawPixmap(x, y, pm)
        else:
            # Fotoğraf bulunamazsa düz koyu renge geri düş.
            painter.fillRect(self.rect(), QColor("#0B0F19"))
        # Qt aynı widget üzerinde aynı anda iki QPainter'a izin vermez;
        # painter burada açıkça end() edilmezse (Python onu fonksiyon
        # dönene kadar canlı tutar), super().paintEvent(event)'in kendi
        # QPainter'ı açması bazı durumlarda sessizce başarısız olup alt
        # widget'ların (ör. dinamik olarak eklenen kart satırları) ilk
        # boyama turunu atlamasına yol açabiliyordu.
        painter.end()
        super().paintEvent(event)

    # ------------------------------------------------------------------- #
    # Sol kenar menü
    # ------------------------------------------------------------------- #
    def _build_sidebar(self):
        sidebar = QFrame()
        sidebar.setFixedWidth(320)
        sidebar.setStyleSheet("background-color: rgba(10, 8, 6, 160); border-right: 1px solid rgba(255,255,255,20);")
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(14, 20, 14, 20)
        layout.setSpacing(6)

        self.nav_buttons = {}
        nav_items = [
            ("🏠", "Günlük Dashboard", "dashboard"),
            ("🎙️", "Sesli Asistan", "chat"),
            ("🗒️", "Not Yönetimi", "notes"),
            ("⚙️", "Ayarlar", "settings"),
            ("ℹ️", "Hakkında", "about"),
        ]
        for icon, text, key in nav_items:
            btn = self._build_nav_button(icon, text, key)
            self.nav_buttons[key] = btn
            layout.addWidget(btn)

        self._active_nav_key = "dashboard"
        self._refresh_nav_styles()

        layout.addSpacing(14)
        layout.addWidget(self._build_clock_card(), stretch=1)
        return sidebar

    def _build_nav_button(self, icon, text, key):
        btn = QPushButton(f"  {icon}   {text}")
        btn.setFixedHeight(42)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(lambda checked=False, k=key: self._on_nav_clicked(k))
        return btn

    def _on_nav_clicked(self, key):
        # "Hakkında" için henüz bir sayfa yok; şimdilik etkisiz.
        if key == "dashboard":
            self.content_stack.setCurrentIndex(0)
            self._active_nav_key = "dashboard"
        elif key == "chat":
            self.content_stack.setCurrentIndex(1)
            self._active_nav_key = "chat"
        elif key == "notes":
            self.content_stack.setCurrentIndex(3)
            self._active_nav_key = "notes"
            self._refresh_notes_list()
        elif key == "settings":
            self.content_stack.setCurrentIndex(2)
            self._active_nav_key = "settings"
        self._refresh_nav_styles()

    def _refresh_nav_styles(self):
        active_style = f"""
            QPushButton {{ text-align: left; background-color: {ACCENT_STRONG}; color: white;
                          border-radius: 10px; font-size: 14px; font-weight: 600; padding-left: 4px; }}
        """
        inactive_style = """
            QPushButton { text-align: left; background-color: transparent; color: #94A3B8;
                          border-radius: 10px; font-size: 14px; padding-left: 4px; }
            QPushButton:hover { background-color: rgba(255,255,255,15); color: #E5E7EB; }
        """
        for key, btn in self.nav_buttons.items():
            btn.setStyleSheet(active_style if key == self._active_nav_key else inactive_style)

    # ------------------------------------------------------------------- #
    # Not Yönetimi sayfası (Telegram Akıllı Not Yönetimi modülü)
    # ------------------------------------------------------------------- #
    _NOTES_CATEGORY_META = {
        "all": ("Tümü", "🗂️"),
        "appointment": ("Randevular", "📅"),
        "shopping": ("Alışveriş", "🛒"),
        "reminder": ("Hatırlatmalar", "⏰"),
        "general": ("Genel", "📝"),
    }

    def _build_notes_page(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        header = QHBoxLayout()
        badge = IconBadge("🗒️", bg_color=ACCENT_STRONG, fg_color="white", size=46, font_size=20, radius=12)
        header.addWidget(badge)
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("Not Yönetimi")
        title.setStyleSheet("font-size: 26px; font-weight: 700; color: #F8FAFC;")
        subtitle = QLabel("Telegram'a yazdığın notlar otomatik sınıflandırılıp burada listelenir.")
        subtitle.setStyleSheet("font-size: 13px; color: #8592A6;")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addSpacing(12)
        header.addLayout(title_box)
        header.addStretch()
        layout.addLayout(header)

        # Kategori filtre çipleri
        self._notes_active_category = "all"
        self._notes_filter_buttons = {}
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)
        for key, (label, icon) in self._NOTES_CATEGORY_META.items():
            btn = QPushButton(f"{icon}  {label}")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(34)
            btn.clicked.connect(lambda checked=False, k=key: self._on_notes_filter_clicked(k))
            filter_row.addWidget(btn)
            self._notes_filter_buttons[key] = btn
        filter_row.addStretch()
        layout.addLayout(filter_row)

        # Arama + sıralama
        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        self._notes_search_box = QLineEdit()
        self._notes_search_box.setPlaceholderText("Notlarda ara...")
        self._notes_search_box.setStyleSheet("""
            QLineEdit { background-color: rgba(255,255,255,12); color: #E8EAED;
                        border: 1px solid rgba(255,255,255,20); border-radius: 10px;
                        padding: 6px 12px; font-size: 13px; }
            QLineEdit:focus { border: 1px solid %s; }
        """ % ACCENT)
        self._notes_search_box.textChanged.connect(lambda _text: self._refresh_notes_list())
        search_row.addWidget(self._notes_search_box, stretch=1)

        self._notes_sort_combo = QComboBox()
        self._notes_sort_combo.addItem("Yeni → Eski", "date_desc")
        self._notes_sort_combo.addItem("Eski → Yeni", "date_asc")
        self._notes_sort_combo.setFixedWidth(140)
        self._notes_sort_combo.setStyleSheet("""
            QComboBox { background-color: rgba(255,255,255,12); color: #E8EAED;
                        border: 1px solid rgba(255,255,255,20); border-radius: 10px;
                        padding: 6px 10px; font-size: 13px; }
        """)
        self._notes_sort_combo.currentIndexChanged.connect(lambda _i: self._refresh_notes_list())
        search_row.addWidget(self._notes_sort_combo)
        layout.addLayout(search_row)

        # Not listesi
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")
        scroll.viewport().setStyleSheet("background: transparent;")

        list_container = QWidget()
        list_container.setStyleSheet("background: transparent;")
        self.notes_list_layout = QVBoxLayout(list_container)
        self.notes_list_layout.setSpacing(10)
        self.notes_list_layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(list_container)
        layout.addWidget(scroll, stretch=1)

        self._refresh_notes_filter_styles()
        return container

    def _refresh_notes_filter_styles(self):
        active_style = f"""
            QPushButton {{ background-color: {ACCENT_STRONG}; color: white; border: none;
                          border-radius: 10px; font-size: 12px; font-weight: 600; padding: 0 12px; }}
        """
        inactive_style = """
            QPushButton { background-color: rgba(255,255,255,12); color: #94A3B8;
                          border: 1px solid rgba(255,255,255,18); border-radius: 10px;
                          font-size: 12px; padding: 0 12px; }
            QPushButton:hover { background-color: rgba(255,255,255,22); color: #E5E7EB; }
        """
        for key, btn in self._notes_filter_buttons.items():
            btn.setStyleSheet(active_style if key == self._notes_active_category else inactive_style)

    def _on_notes_filter_clicked(self, category):
        self._notes_active_category = category
        self._refresh_notes_filter_styles()
        self._refresh_notes_list()

    def _refresh_notes_list(self):
        """Veritabanını (bkz. note_database.get_notes) mevcut filtre/arama/
        sıralama seçimlerine göre sorgulayıp listeyi yeniden çizer. Hem nav
        tıklamasında hem de arka planda yeni bir not kaydedildiğinde (bkz.
        _start_note_management_services) çağrılır."""
        if not hasattr(self, "notes_list_layout"):
            return
        while self.notes_list_layout.count():
            item = self.notes_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        category = getattr(self, "_notes_active_category", "all")
        search = self._notes_search_box.text().strip() if hasattr(self, "_notes_search_box") else ""
        sort = self._notes_sort_combo.currentData() if hasattr(self, "_notes_sort_combo") else "date_desc"

        try:
            notes = note_database.get_notes(category=category, search=search or None, sort=sort)
        except Exception as e:
            print(f"⚠️ Notlar yüklenemedi: {e}")
            notes = []

        if not notes:
            empty_label = QLabel("Henüz not yok. Telegram'a bir mesaj yazarak başlayabilirsin.")
            empty_label.setStyleSheet("color: #8592A6; font-size: 13px;")
            empty_label.setAlignment(Qt.AlignCenter)
            self.notes_list_layout.addWidget(empty_label)
            return

        for note in notes:
            self.notes_list_layout.addWidget(self._build_note_row(note))

    def _build_note_row(self, note):
        label, icon = self._NOTES_CATEGORY_META.get(note["category"], ("Not", "📝"))
        row = self._card_frame()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(14, 10, 14, 10)
        row_layout.setSpacing(10)

        row_layout.addWidget(IconBadge(icon, bg_color="rgba(245, 158, 11, 35)",
                                        fg_color=ACCENT, size=36, font_size=15, radius=10))

        text_box = QVBoxLayout()
        text_box.setSpacing(2)
        title_text = note["title"]
        if note.get("needs_review"):
            title_text += "  ·  kontrol et"
        title_lbl = QLabel(title_text)
        title_lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #F1F5F9;")
        if note.get("completed"):
            title_lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #64748B; text-decoration: line-through;")
        desc = (note.get("description") or "").strip()
        meta_bits = [label]
        for key in ("appt_date", "remind_at", "product_name"):
            if note.get(key):
                meta_bits.append(str(note[key]))
        subtitle_lbl = QLabel(" · ".join(meta_bits) + (f"\n{desc}" if desc else ""))
        subtitle_lbl.setStyleSheet("font-size: 11px; color: #8592A6;")
        subtitle_lbl.setWordWrap(True)
        text_box.addWidget(title_lbl)
        text_box.addWidget(subtitle_lbl)
        row_layout.addLayout(text_box, stretch=1)

        toggle = ToggleSwitch(checked=bool(note.get("completed")))
        toggle.toggled.connect(lambda checked, nid=note["id"]: self._on_note_completed_toggled(nid, checked))
        row_layout.addWidget(toggle)

        edit_btn = QPushButton("✏️")
        edit_btn.setCursor(Qt.PointingHandCursor)
        edit_btn.setFixedSize(30, 30)
        edit_btn.setStyleSheet("QPushButton { background: transparent; border: none; font-size: 14px; } "
                                "QPushButton:hover { background: rgba(255,255,255,20); border-radius: 6px; }")
        edit_btn.clicked.connect(lambda checked=False, nid=note["id"]: self._on_note_edit_clicked(nid))
        row_layout.addWidget(edit_btn)

        delete_btn = QPushButton("🗑️")
        delete_btn.setCursor(Qt.PointingHandCursor)
        delete_btn.setFixedSize(30, 30)
        delete_btn.setStyleSheet("QPushButton { background: transparent; border: none; font-size: 14px; } "
                                  "QPushButton:hover { background: rgba(239,68,68,40); border-radius: 6px; }")
        delete_btn.clicked.connect(lambda checked=False, nid=note["id"]: self._on_note_delete_clicked(nid))
        row_layout.addWidget(delete_btn)

        return row

    def _on_note_completed_toggled(self, note_id, checked):
        note_database.set_completed(note_id, checked)
        self._refresh_notes_list()

    def _on_note_delete_clicked(self, note_id):
        reply = QMessageBox.question(
            self, "Notu sil", "Bu notu silmek istediğine emin misin?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            note_database.delete_note(note_id)
            self._refresh_notes_list()

    def _on_note_edit_clicked(self, note_id):
        note = note_database.get_note(note_id)
        if not note:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Notu Düzenle")
        dialog.setStyleSheet("QDialog { background-color: #15110C; } QLabel { color: #E5E7EB; }")
        form = QFormLayout(dialog)

        title_edit = QLineEdit(note["title"])
        desc_edit = QLineEdit(note.get("description") or "")
        category_combo = QComboBox()
        for key in ("appointment", "shopping", "reminder", "general"):
            category_combo.addItem(self._NOTES_CATEGORY_META[key][0], key)
        current_index = category_combo.findData(note["category"])
        if current_index >= 0:
            category_combo.setCurrentIndex(current_index)

        form.addRow("Başlık", title_edit)
        form.addRow("Açıklama", desc_edit)
        form.addRow("Kategori", category_combo)

        buttons_row = QHBoxLayout()
        save_btn = QPushButton("Kaydet")
        cancel_btn = QPushButton("Vazgeç")
        buttons_row.addWidget(save_btn)
        buttons_row.addWidget(cancel_btn)
        form.addRow(buttons_row)

        def on_save():
            note_database.update_note(note_id, fields={
                "title": title_edit.text().strip() or note["title"],
                "description": desc_edit.text().strip(),
                "category": category_combo.currentData(),
            })
            dialog.accept()
            self._refresh_notes_list()

        save_btn.clicked.connect(on_save)
        cancel_btn.clicked.connect(dialog.reject)
        dialog.exec_()

    def _start_note_management_services(self):
        """Not yönetimi artık bulutta (Cloudflare Worker + Groq, bkz.
        cloudflare-worker/README.md) çalışır: Telegram mesajları webhook ile
        doğrudan oraya gider ve hatırlatmalar bir cron tetikleyiciyle oradan
        gönderilir — PC açık/kapalı fark etmez. Burada SADECE PC açıkken
        buluttaki yeni not/mesajları yerel notes.db'ye çeken senkronizasyon
        başlatılır (bkz. cloud_sync.py). Eski yerel long-polling
        (telegram_service.TelegramPollThread) ve hatırlatma döngüsü
        (reminder_scheduler.ReminderSchedulerThread) kasıtlı olarak
        BAŞLATILMIYOR — aynı bot için Telegram webhook ile long-polling
        birlikte çalışamaz ve hatırlatmalar artık buluttan gönderiliyor,
        ikisi birden çalışsa aynı not/hatırlatma iki kez işlenir."""
        note_database.init_db()
        vault_cache.init_db()

        try:
            cloud_sync.push_config()
        except Exception as e:
            print(f"⚠️ Bulut ayarları gönderilemedi: {e}")

        # HAKKIMDA artık SADECE Cloudflare D1'de yönetildiği için (bkz.
        # vault_knowledge.py / personal_context.py modül yorumları), sesli
        # asistanın kullandığı yerel önbellek her açılışta D1 ile güncellenir.
        try:
            synced = cloud_sync.sync_vault_from_cloud()
            if synced:
                print(f"📚 Kasa önbelleği güncellendi: {synced} not.")
        except Exception as e:
            print(f"⚠️ Kasa önbelleği güncellenemedi: {e}")

        self._cloud_sync_thread = cloud_sync_service.CloudSyncThread()
        self._cloud_sync_thread.messageSynced.connect(self._refresh_notes_list)
        self._cloud_sync_thread.start()

    # ------------------------------------------------------------------- #
    # Ayarlar sayfası (ör. TTS ses modeli seçimi)
    # ------------------------------------------------------------------- #
    def _build_settings_page(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(20)

        header = QHBoxLayout()
        badge = IconBadge("⚙️", bg_color=ACCENT_STRONG, fg_color="white", size=46, font_size=20, radius=12)
        header.addWidget(badge)
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("Ayarlar")
        title.setStyleSheet("font-size: 26px; font-weight: 700; color: #F8FAFC;")
        subtitle = QLabel("WinVoice'un davranışını özelleştirin.")
        subtitle.setStyleSheet("font-size: 13px; color: #8592A6;")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addSpacing(12)
        header.addLayout(title_box)
        header.addStretch()
        layout.addLayout(header)

        layout.addWidget(self._build_persona_settings_card())
        layout.addWidget(self._build_llm_settings_card())
        layout.addWidget(self._build_voice_settings_card())
        layout.addStretch()

        return container

    def _build_persona_slider_row(self, icon, title_text, desc_text, initial_pct, on_change):
        row = QVBoxLayout()
        row.setSpacing(6)

        header = QHBoxLayout()
        header.addWidget(IconBadge(icon, bg_color="transparent", fg_color=ACCENT, size=24, font_size=15))
        header_text = QVBoxLayout()
        header_text.setSpacing(0)
        t1 = QLabel(title_text)
        t1.setStyleSheet("font-size: 14px; font-weight: 600; color: #F1F5F9;")
        t2 = QLabel(desc_text)
        t2.setStyleSheet("font-size: 11px; color: #8592A6;")
        header_text.addWidget(t1)
        header_text.addWidget(t2)
        header.addSpacing(6)
        header.addLayout(header_text)
        header.addStretch()

        value_label = QLabel(f"%{initial_pct}")
        value_label.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {ACCENT};")
        header.addWidget(value_label)
        row.addLayout(header)

        slider = QSlider(Qt.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(initial_pct)
        slider.setCursor(Qt.PointingHandCursor)
        slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{ height: 6px; background: #1E293B; border-radius: 3px; }}
            QSlider::handle:horizontal {{ background: {ACCENT}; width: 16px; height: 16px;
                                           margin: -5px 0; border-radius: 8px; }}
            QSlider::sub-page:horizontal {{ background: {ACCENT_STRONG}; border-radius: 3px; }}
        """)

        def _on_value_changed(value):
            value_label.setText(f"%{value}")
            on_change(value)

        slider.valueChanged.connect(_on_value_changed)
        row.addWidget(slider)

        return row

    def _build_persona_settings_card(self):
        card = self._card_frame()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 20, 22, 20)
        card_layout.setSpacing(16)

        header = QHBoxLayout()
        header.addWidget(IconBadge("🎭", bg_color="transparent", fg_color=ACCENT, size=28, font_size=18))
        header_text = QVBoxLayout()
        header_text.setSpacing(0)
        t1 = QLabel("Kişilik")
        t1.setStyleSheet("font-size: 15px; font-weight: 600; color: #F1F5F9;")
        t2 = QLabel("Asistanın sohbet ve brifing sırasındaki üslubunu ayarlayın")
        t2.setStyleSheet("font-size: 11px; color: #8592A6;")
        header_text.addWidget(t1)
        header_text.addWidget(t2)
        header.addSpacing(6)
        header.addLayout(header_text)
        header.addStretch()
        card_layout.addLayout(header)
        card_layout.addWidget(Divider())

        card_layout.addLayout(self._build_persona_slider_row(
            "😄", "Espri", "Mizahın sıklığı ve yoğunluğu.",
            get_espri_pct(), set_espri_pct,
        ))
        card_layout.addLayout(self._build_persona_slider_row(
            "🤝", "Arkadaş canlısı yaklaşım", "İletişimin sıcaklığı.",
            get_arkadaslik_pct(), set_arkadaslik_pct,
        ))

        return card

    def _build_llm_settings_card(self):
        card = self._card_frame()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 20, 22, 20)
        card_layout.setSpacing(14)

        header = QHBoxLayout()
        header.addWidget(IconBadge("🧠", bg_color="transparent", fg_color=ACCENT, size=28, font_size=18))
        header_text = QVBoxLayout()
        header_text.setSpacing(0)
        t1 = QLabel("Yapay Zeka Modeli")
        t1.setStyleSheet("font-size: 15px; font-weight: 600; color: #F1F5F9;")
        t2 = QLabel("Asistanın komutları yorumlarken kullanacağı yerel model")
        t2.setStyleSheet("font-size: 11px; color: #8592A6;")
        header_text.addWidget(t1)
        header_text.addWidget(t2)
        header.addSpacing(6)
        header.addLayout(header_text)
        header.addStretch()
        card_layout.addLayout(header)
        card_layout.addWidget(Divider())

        selected_id = get_llm_model()
        self._llm_radio_group = QButtonGroup(card)

        for model in AVAILABLE_LLM_MODELS:
            row_widget = QWidget()
            row = QVBoxLayout(row_widget)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(2)
            radio = QRadioButton(model["label"])
            radio.setStyleSheet("""
                QRadioButton { font-size: 14px; color: #E5E7EB; padding: 4px 0; spacing: 8px; }
                QRadioButton::indicator { width: 16px; height: 16px; }
            """)
            radio.setFixedHeight(26)
            radio.setChecked(model["id"] == selected_id)
            radio.toggled.connect(
                lambda checked, m=model: self._on_llm_radio_toggled(m) if checked else None
            )
            self._llm_radio_group.addButton(radio)
            desc_label = QLabel(model["desc"])
            desc_label.setStyleSheet("font-size: 11px; color: #8592A6; padding-left: 24px;")
            row.addWidget(radio)
            row.addWidget(desc_label)
            row_widget.setMinimumHeight(46)
            card_layout.addWidget(row_widget)

        card_layout.addWidget(Divider())

        self.llm_settings_status_label = QLabel("")
        self.llm_settings_status_label.setStyleSheet("font-size: 12px; color: #8592A6;")
        card_layout.addWidget(self.llm_settings_status_label)

        return card

    def _on_llm_radio_toggled(self, model):
        if self._set_llm_model_func:
            try:
                self._set_llm_model_func(model["id"])
            except Exception as e:
                self.llm_settings_status_label.setText(f"⚠️ Model değiştirilemedi: {e}")
                return
        self.llm_settings_status_label.setText(f"Kaydedildi: {model['label']}")

    def _build_voice_settings_card(self):
        card = self._card_frame()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 20, 22, 20)
        card_layout.setSpacing(14)

        header = QHBoxLayout()
        header.addWidget(IconBadge("🔊", bg_color="transparent", fg_color=ACCENT, size=28, font_size=18))
        header_text = QVBoxLayout()
        header_text.setSpacing(0)
        t1 = QLabel("Ses Modeli")
        t1.setStyleSheet("font-size: 15px; font-weight: 600; color: #F1F5F9;")
        t2 = QLabel("Asistanın sizi seslendirirken kullanacağı Türkçe ses")
        t2.setStyleSheet("font-size: 11px; color: #8592A6;")
        header_text.addWidget(t1)
        header_text.addWidget(t2)
        header.addSpacing(6)
        header.addLayout(header_text)
        header.addStretch()
        card_layout.addLayout(header)
        card_layout.addWidget(Divider())

        voices = list_turkish_voices()
        selected_id = get_selected_voice_id()
        # Henüz açıkça bir seçim kaydedilmediyse, _set_turkish_voice'un
        # kullanacağı gerçek varsayılanı (Piper varsa o, yoksa Türkçe ses)
        # yansıtacak şekilde listede önceden işaretli göster.
        if not selected_id:
            piper = next((v for v in voices if "piper" in v["description"].lower()), None)
            selected_id = piper["id"] if piper else (voices[0]["id"] if voices else None)

        self._voice_radio_group = QButtonGroup(card)
        self._voice_radio_buttons = {}

        if not voices:
            empty_label = QLabel("Sistemde Türkçe bir ses bulunamadı.")
            empty_label.setStyleSheet("font-size: 13px; color: #94A3B8;")
            card_layout.addWidget(empty_label)
        else:
            for voice in voices:
                radio = QRadioButton(voice["description"])
                radio.setStyleSheet("""
                    QRadioButton { font-size: 14px; color: #E5E7EB; padding: 6px 0; spacing: 8px; }
                    QRadioButton::indicator { width: 16px; height: 16px; }
                """)
                radio.setMinimumHeight(28)
                radio.setChecked(voice["id"] == selected_id)
                radio.toggled.connect(
                    lambda checked, v=voice: self._on_voice_radio_toggled(v) if checked else None
                )
                self._voice_radio_group.addButton(radio)
                self._voice_radio_buttons[voice["id"]] = radio
                card_layout.addWidget(radio)

        card_layout.addWidget(Divider())

        footer_row = QHBoxLayout()
        self.voice_settings_status_label = QLabel("")
        self.voice_settings_status_label.setStyleSheet("font-size: 12px; color: #8592A6;")
        footer_row.addWidget(self.voice_settings_status_label)
        footer_row.addStretch()

        replay_btn = QPushButton("🔁 Tekrar Dinle")
        replay_btn.setCursor(Qt.PointingHandCursor)
        replay_btn.setStyleSheet(f"""
            QPushButton {{ background-color: #1E293B; color: #E5E7EB; border-radius: 8px;
                          padding: 8px 14px; font-size: 13px; }}
            QPushButton:hover {{ background-color: {ACCENT_STRONG}; }}
        """)
        replay_btn.clicked.connect(self._on_replay_voice_clicked)
        footer_row.addWidget(replay_btn)

        card_layout.addLayout(footer_row)

        return card

    def _on_voice_radio_toggled(self, voice):
        set_selected_voice_id(voice["id"])
        self.voice_settings_status_label.setText(f"Kaydedildi: {voice['description']}")
        self._speak_voice_test_sample()

    def _on_replay_voice_clicked(self):
        self._speak_voice_test_sample()

    def _speak_voice_test_sample(self):
        sample_text = "Merhaba Patron, ben WinVoice sesli asistanınızım. Bu, seçtiğiniz sesin bir örneğidir."
        self._voice_test_thread = VoiceTestThread(
            sample_text,
            pause_hotword_func=self._pause_hotword_func,
            resume_hotword_func=self._resume_hotword_func,
        )
        self._voice_test_thread.start()

    # ------------------------------------------------------------------- #
    # Ana içerik
    # ------------------------------------------------------------------- #
    def _build_dashboard_page(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(20)

        layout.addLayout(self._build_header())

        columns = QHBoxLayout()
        columns.setSpacing(18)
        # Sağ sütun (Hava/Akıllı Ev/Hızlı İşlemler/Tahmin) metin kırpılmasın
        # diye kendi içerik genişliğine (bkz. _build_right_column'daki
        # setMinimumWidth) sabitlenir (stretch=0); fazla alan Günlük
        # Brifing kartına (stretch=1) verilir.
        columns.addWidget(self._build_news_card(), stretch=1)
        columns.addWidget(self._build_right_column(), stretch=0)
        layout.addLayout(columns, stretch=1)

        return container

    def _build_right_column(self):
        """Sağ taraf iki alt sütuna ayrılır: solda Hava Durumu + Akıllı Ev
        Kontrolleri, sağda Hızlı İşlemler + 7 Günlük Tahmin. Toplamda dar
        ekranlarda taşabileceği için kaydırılabilir bir alan içine konur."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent; border: none;")
        scroll.viewport().setStyleSheet("background: transparent;")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content_layout = QHBoxLayout(content)
        # Sağda 18px boşluk: QScrollArea'ya stylesheet uygulanınca dikey
        # kaydırma çubuğu (7 Günlük Tahmin uzunsa görünür) viewport'tan yer
        # ayırmak yerine içeriğin üzerine biniyor — bu pay olmadan en
        # sağdaki sıcaklık etiketleri çubuğun altında kalıp görünmez oluyordu.
        content_layout.setContentsMargins(0, 0, 18, 0)
        content_layout.setSpacing(18)

        # Her alt sütun kendi QWidget'ına sarmalanıp bir asgari genişlik
        # veriliyor: aksi halde (yalnızca layout stretch oranlarıyla)
        # pencere daraldığında buton/başlık metinleri kaydırma çubuğu
        # göstermek yerine sessizce kırpılıyordu.
        col_a = QWidget()
        col_a_layout = QVBoxLayout(col_a)
        col_a_layout.setContentsMargins(0, 0, 0, 0)
        col_a_layout.setSpacing(18)
        col_a_layout.addWidget(self._build_weather_card())
        col_a_layout.addWidget(self._build_smart_home_card())
        col_a_layout.addStretch()
        # Hava Durumu kartının gerçek asgari genişliği (başlık + "İstanbul /
        # Çatalca" + ikon/sıcaklık/istatistikler) ~260-270px; 280 güvenli pay
        # bırakıyor ama eski 380'den çok daha dar — dar ekranlarda sağ
        # sütunun ekrandan taşmasına neden oluyordu.
        col_a.setMinimumWidth(280)

        col_b = QWidget()
        col_b_layout = QVBoxLayout(col_b)
        col_b_layout.setContentsMargins(0, 0, 0, 0)
        col_b_layout.setSpacing(18)
        col_b_layout.addWidget(self._build_quick_actions_card())
        col_b_layout.addWidget(self._build_forecast_card())
        col_b_layout.addStretch()
        # 7 Günlük Tahmin satırı (gün adı + ikon/açıklama + maks/min sıcaklık)
        # en dar haliyle ~300px gerektiriyor (bkz. _build_forecast_row); 320
        # güvenli pay bırakıyor ama eski 390'dan belirgin şekilde daha dar.
        col_b.setMinimumWidth(320)

        content_layout.addWidget(col_a, stretch=11)
        content_layout.addWidget(col_b, stretch=9)

        scroll.setWidget(content)
        # +16px: 7 Günlük Tahmin listesi dikey kaydırmaya ihtiyaç duyduğunda
        # QScrollArea viewport'u kendi genişliğinden dikey kaydırma çubuğu
        # kadar dar olur — bu pay eklenmezse en sağdaki sıcaklık etiketleri
        # çubuğun altında kalıp görünmez olur.
        scroll.setMinimumWidth(
            col_a.minimumWidth() + col_b.minimumWidth() + content_layout.spacing() + 16
        )
        return scroll

    def _on_play_music_clicked(self):
        self._music_launch_thread = MusicLaunchThread(
            ORCHARD_EXE_PATH, return_focus_hwnd=int(self.winId())
        )
        self._music_launch_thread.start()

    def _on_toggle_listening_clicked(self):
        """Asistanın her an açık olan hotword mikrofon dinlemesini kalıcı
        olarak duraklatır/başlatır (bkz. HotwordListener.set_muted).
        Kalıcı olması önemli: Brifing okunurken veya Ayarlar'da ses testi
        yapılırken dinleyici geçici olarak pause/resume ediliyor, bu
        otomatik resume() çağrıları kullanıcının burada verdiği kararı
        geçersiz kılmamalı."""
        self._listening_muted = not self._listening_muted
        if self._set_listening_muted_func:
            try:
                self._set_listening_muted_func(self._listening_muted)
            except Exception:
                pass
        if self._listening_muted:
            self._listen_toggle_btn.setText(" Dinlemeyi Başlat")
            self._listen_toggle_btn.setIcon(QIcon(render_icon_pixmap(
                "🔇", bg_color=(248, 113, 113, 110), fg_color="#FEF2F2"
            )))
        else:
            self._listen_toggle_btn.setText(" Dinlemeyi Duraklat")
            self._listen_toggle_btn.setIcon(QIcon(render_icon_pixmap(
                "🎤", bg_color=(52, 211, 153, 110), fg_color="#ECFDF5"
            )))

    def _build_header(self):
        row = QHBoxLayout()

        badge = IconBadge("▦", bg_color=ACCENT_STRONG, fg_color="white", size=46, font_size=20, radius=12)
        row.addWidget(badge)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("Günlük Dashboard")
        title.setStyleSheet("font-size: 26px; font-weight: 700; color: #F8FAFC;")
        subtitle = QLabel("Günün önemli bilgileri, tek bir ekranda.")
        subtitle.setStyleSheet("font-size: 13px; color: #8592A6;")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        row.addSpacing(12)
        row.addLayout(title_box)

        row.addStretch()

        cal_icon = QLabel("📅")
        cal_icon.setStyleSheet("font-size: 15px;")
        row.addWidget(cal_icon)
        self.header_date_label = QLabel()
        self.header_date_label.setStyleSheet("font-size: 14px; color: #CBD5E1;")
        row.addWidget(self.header_date_label)

        return row

    def _card_frame(self):
        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet("""
            QFrame#card { background-color: rgba(18, 16, 14, 165); border-radius: 16px;
                          border: 1px solid rgba(255, 255, 255, 18); }
        """)
        return card

    # --- Kart 1: Yerel Saat ---------------------------------------------------
    def _build_clock_card(self):
        card = self._card_frame()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 0, 0)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.addWidget(IconBadge("🕐", bg_color="transparent", fg_color=ACCENT, size=28, font_size=18))
        header_text = QVBoxLayout()
        header_text.setSpacing(0)
        t1 = QLabel("Yerel Saat")
        t1.setStyleSheet("font-size: 15px; font-weight: 600; color: #F1F5F9;")
        t2 = QLabel("(Türkiye)")
        t2.setStyleSheet("font-size: 11px; color: #8592A6;")
        header_text.addWidget(t1)
        header_text.addWidget(t2)
        header.addSpacing(6)
        header.addLayout(header_text)
        header.addStretch()
        layout.addLayout(header)

        self.clock_time_label = QLabel()
        self.clock_time_label.setStyleSheet("font-size: 32px; font-weight: 700;")
        layout.addWidget(self.clock_time_label)

        self.clock_date_label = QLabel()
        self.clock_date_label.setStyleSheet("font-size: 13px; color: #94A3B8;")
        layout.addWidget(self.clock_date_label)

        layout.addSpacing(4)
        div = Divider()
        layout.addWidget(div)
        layout.addSpacing(4)

        loc_row = QHBoxLayout()
        loc_row.addWidget(IconBadge("📍", bg_color="transparent", fg_color=ACCENT, size=22, font_size=15))
        loc_text = QVBoxLayout()
        loc_text.setSpacing(0)
        l1 = QLabel("İstanbul / Çatalca")
        l1.setStyleSheet("font-size: 14px; font-weight: 600; color: #F1F5F9;")
        l2 = QLabel("(Yerel Saat)")
        l2.setStyleSheet("font-size: 11px; color: #8592A6;")
        loc_text.addWidget(l1)
        loc_text.addWidget(l2)
        loc_row.addSpacing(6)
        loc_row.addLayout(loc_text)
        loc_row.addStretch()
        layout.addLayout(loc_row)

        layout.addSpacing(10)

        # Sistem günlüğü: baslat.bat artık bir komut penceresi açmıyor — bunun
        # yerine main.py'de print() çağrıları sahte bir stdout'ta (_StdoutRelay)
        # toplanıp LogRelay ile buraya (append_log_line) akıtılıyor. Kartın alt
        # kısmını kaplayan bu alan, eskiden konsolda görünen çıktıyı gösterir.
        self.console_log = QPlainTextEdit()
        self.console_log.setReadOnly(True)
        self.console_log.setMaximumBlockCount(400)
        self.console_log.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.console_log.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.console_log.setFrameShape(QFrame.NoFrame)
        self.console_log.setStyleSheet("""
            QPlainTextEdit {
                background-color: rgba(3, 3, 3, 190);
                color: #8B95A1;
                border: 1px solid rgba(255, 255, 255, 14);
                border-radius: 10px;
                padding: 8px 10px;
                font-family: 'Cascadia Mono', 'Consolas', monospace;
                font-size: 10px;
            }
        """)
        layout.addWidget(self.console_log, stretch=1)

        return card

    def append_log_line(self, text):
        """LogRelay.line_received'a bağlanır (bkz. main.py) — her satırı sistem
        günlüğü kutusuna ekler ve görünümü en alta kaydırır."""
        console = getattr(self, "console_log", None)
        if console is None or not text:
            return
        console.appendPlainText(text)
        scrollbar = console.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _add_quick_action_button(self, actions_layout, icon_glyph, text, handler,
                                  icon_bg="#2A2420", icon_fg=ACCENT):
        btn = QPushButton(f" {text}")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedHeight(46)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn.setIcon(QIcon(render_icon_pixmap(icon_glyph, bg_color=icon_bg, fg_color=icon_fg)))
        btn.setIconSize(QSize(28, 28))
        btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 12);
                color: #E8EAED;
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 12px;
                padding: 0 14px;
                font-size: 13px;
                font-weight: 600;
                text-align: left;
            }
            QPushButton:hover {
                background-color: rgba(245, 158, 11, 38);
                border: 1px solid rgba(245, 158, 11, 110);
                color: #FFFFFF;
            }
            QPushButton:pressed {
                background-color: rgba(245, 158, 11, 60);
            }
            QPushButton:disabled {
                background-color: rgba(255, 255, 255, 6);
                border: 1px solid rgba(255, 255, 255, 10);
                color: #64748B;
            }
        """)
        shadow = QGraphicsDropShadowEffect(btn)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(0, 0, 0, 100))
        btn.setGraphicsEffect(shadow)
        btn.clicked.connect(handler)
        actions_layout.addWidget(btn)
        return btn

    # --- Kart: Hızlı İşlemler ----------------------------------------------------
    def _build_quick_actions_card(self):
        card = self._card_frame()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.addWidget(IconBadge("⚡", bg_color="transparent", fg_color=ACCENT, size=22, font_size=15))
        header_label = QLabel("HIZLI İŞLEMLER")
        header_label.setStyleSheet(
            "font-size: 11px; font-weight: 700; color: #7C8696; letter-spacing: 1px;"
        )
        header.addSpacing(6)
        header.addWidget(header_label)
        header.addStretch()
        layout.addLayout(header)
        layout.addSpacing(4)

        actions_layout = QVBoxLayout()
        actions_layout.setSpacing(10)
        actions_layout.setAlignment(Qt.AlignTop)

        self._add_quick_action_button(
            actions_layout, "🎵", "Müzik Çal", self._on_play_music_clicked,
            icon_bg=(167, 139, 250, 110), icon_fg="#EDE9FE",
        )
        self._listen_toggle_btn = self._add_quick_action_button(
            actions_layout, "🎤", "Dinlemeyi Duraklat", self._on_toggle_listening_clicked,
            icon_bg=(52, 211, 153, 110), icon_fg="#ECFDF5",
        )
        layout.addLayout(actions_layout)

        return card

    # --- Kart 2: Günlük Brifing --------------------------------------------------
    def _build_news_card(self):
        card = self._card_frame()
        outer = QVBoxLayout(card)
        outer.setContentsMargins(22, 20, 22, 20)
        outer.setSpacing(12)

        # Başlık ve Duraklat/Durdur butonları artık AYRI satırlarda: aynı
        # satırda sıkıştırılmaları, Günlük Brifing kartının asgari genişliğini
        # gereksiz yere ~180px artırıp dar pencerelerde sağ sütunun (Hızlı
        # İşlemler / 7 Günlük Tahmin) ekrandan taşmasına yol açıyordu.
        header = QHBoxLayout()
        header.addWidget(IconBadge("📰", bg_color="transparent", fg_color=ACCENT, size=28, font_size=18))
        header_label = QLabel("Günlük Brifing")
        header_label.setStyleSheet("font-size: 15px; font-weight: 600; color: #F1F5F9;")
        header.addSpacing(6)
        header.addWidget(header_label)
        header.addStretch()
        outer.addLayout(header)

        briefing_control_btn_style = """
            QPushButton { background-color: #1E293B; color: #E5E7EB; border-radius: 8px;
                          padding: 5px 10px; font-size: 12px; }
            QPushButton:hover { background-color: #334155; }
            QPushButton:disabled { background-color: #161C28; color: #475569; }
        """
        controls_row = QHBoxLayout()
        controls_row.addStretch()
        self.briefing_pause_btn = QPushButton("⏸ Duraklat")
        self.briefing_pause_btn.setCursor(Qt.PointingHandCursor)
        self.briefing_pause_btn.setStyleSheet(briefing_control_btn_style)
        self.briefing_pause_btn.setEnabled(False)
        self.briefing_pause_btn.clicked.connect(self._on_briefing_pause_clicked)
        controls_row.addWidget(self.briefing_pause_btn)

        self.briefing_stop_btn = QPushButton("⏹ Durdur")
        self.briefing_stop_btn.setCursor(Qt.PointingHandCursor)
        self.briefing_stop_btn.setStyleSheet(briefing_control_btn_style)
        self.briefing_stop_btn.setEnabled(False)
        self.briefing_stop_btn.clicked.connect(self._on_briefing_stop_clicked)
        controls_row.addWidget(self.briefing_stop_btn)
        outer.addLayout(controls_row)
        self._briefing_is_paused = False

        # AI çekirdeği grafiği: yükleniyor/hazır/hata durumunu ortasındaki
        # metinle (bkz. AIOrbWidget.set_status_text) yansıtan dekoratif
        # halka. Hem yükleniyor hem de hazır durumunda görünür kalır.
        self.ai_orb = AIOrbWidget(170)
        self.ai_orb.set_status_text("Veriler toplanıyor...")
        orb_row = QHBoxLayout()
        orb_row.addStretch()
        orb_row.addWidget(self.ai_orb)
        orb_row.addStretch()
        outer.addLayout(orb_row)

        # Yükleniyor durumu (brifing üretilince gizlenir)
        self.news_loading_box = QWidget()
        loading_layout = QVBoxLayout(self.news_loading_box)
        loading_layout.setAlignment(Qt.AlignCenter)
        self.news_loading_label = QLabel("Veriler toplanıyor...")
        self.news_loading_label.setAlignment(Qt.AlignCenter)
        self.news_loading_label.setStyleSheet("font-size: 14px; color: #94A3B8;")
        loading_layout.addWidget(self.news_loading_label)
        outer.addWidget(self.news_loading_box, stretch=1)

        # Brifing metni (üretildikten sonra doldurulur), kaydırılabilir
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")
        scroll.viewport().setStyleSheet("background: transparent;")

        content_box = QWidget()
        content_box.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content_box)
        content_layout.setContentsMargins(0, 0, 0, 0)

        self.briefing_text_label = QLabel()
        self.briefing_text_label.setWordWrap(True)
        self.briefing_text_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.briefing_text_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.briefing_text_label.setCursor(Qt.IBeamCursor)
        self.briefing_text_label.setStyleSheet(
            "font-size: 13px; color: #E5E7EB; line-height: 150%;"
        )
        content_layout.addWidget(self.briefing_text_label)
        content_layout.addStretch()

        scroll.setWidget(content_box)
        scroll.hide()
        outer.addWidget(scroll, stretch=1)
        self._news_scroll_area = scroll

        return card

    # --- Kart 3: Hava Durumu ---------------------------------------------------
    def _build_weather_card(self):
        card = self._card_frame()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.addWidget(IconBadge("⛅", bg_color="transparent", fg_color=ACCENT, size=28, font_size=18))
        header_text = QVBoxLayout()
        header_text.setSpacing(0)
        t1 = QLabel("Hava Durumu")
        t1.setStyleSheet("font-size: 15px; font-weight: 600; color: #F1F5F9;")
        t2 = QLabel("İstanbul / Çatalca")
        t2.setStyleSheet("font-size: 11px; color: #8592A6;")
        header_text.addWidget(t1)
        header_text.addWidget(t2)
        header.addSpacing(6)
        header.addLayout(header_text)
        header.addStretch()

        refresh_box = QVBoxLayout()
        refresh_box.setSpacing(0)
        refresh_top = QHBoxLayout()
        refresh_top.addStretch()
        r_icon = QLabel("🔄")
        r_icon.setStyleSheet("font-size: 11px;")
        refresh_top.addWidget(r_icon)
        refresh_box.addLayout(refresh_top)
        self.weather_updated_label = QLabel("Son güncelleme\n--:--")
        self.weather_updated_label.setAlignment(Qt.AlignRight)
        self.weather_updated_label.setStyleSheet("font-size: 10px; color: #8592A6;")
        refresh_box.addWidget(self.weather_updated_label)
        header.addLayout(refresh_box)

        layout.addLayout(header)

        current_row = QHBoxLayout()
        self.current_icon_label = QLabel("…")
        self.current_icon_label.setStyleSheet("font-size: 40px;")
        current_row.addWidget(self.current_icon_label)

        current_text = QVBoxLayout()
        current_text.setSpacing(0)
        self.current_temp_label = QLabel("--°C")
        self.current_temp_label.setStyleSheet("font-size: 30px; font-weight: 700; color: #F8FAFC;")
        self.current_desc_label = QLabel("Yükleniyor...")
        self.current_desc_label.setStyleSheet("font-size: 12px; color: #94A3B8;")
        current_text.addWidget(self.current_temp_label)
        current_text.addWidget(self.current_desc_label)
        current_row.addSpacing(6)
        current_row.addLayout(current_text)
        current_row.addStretch()

        stats_box = QVBoxLayout()
        stats_box.setSpacing(4)
        self.humidity_label = self._stat_row(stats_box, "💧", "Nem", "--%")
        self.wind_label = self._stat_row(stats_box, "💨", "Rüzgar", "-- km/s")
        self.pressure_label = self._stat_row(stats_box, "🧭", "Basınç", "-- hPa")
        current_row.addLayout(stats_box)

        layout.addLayout(current_row)

        self.weather_status_label = QLabel("Hava durumu yükleniyor...")
        self.weather_status_label.setStyleSheet("color: #8592A6; font-size: 12px;")
        layout.addWidget(self.weather_status_label)

        return card

    def _build_forecast_card(self):
        card = self._card_frame()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.addWidget(IconBadge("📅", bg_color="transparent", fg_color=ACCENT, size=28, font_size=16))
        forecast_title = QLabel("7 Günlük Tahmin")
        forecast_title.setStyleSheet("font-size: 15px; font-weight: 600; color: #F1F5F9;")
        header.addSpacing(6)
        header.addWidget(forecast_title)
        header.addStretch()
        layout.addLayout(header)
        layout.addWidget(Divider())

        self.forecast_list_layout = QVBoxLayout()
        self.forecast_list_layout.setSpacing(10)
        layout.addLayout(self.forecast_list_layout)

        return card

    # --- Kart: Akıllı Ev Kontrolleri (görsel yer tutucu) -----------------------
    def _build_smart_home_card(self):
        card = self._card_frame()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        header = QHBoxLayout()
        header.addWidget(IconBadge("🏠", bg_color="transparent", fg_color=ACCENT, size=28, font_size=18))
        header_text = QVBoxLayout()
        header_text.setSpacing(0)
        t1 = QLabel("Akıllı Ev Kontrolleri")
        t1.setStyleSheet("font-size: 15px; font-weight: 600; color: #F1F5F9;")
        t2 = QLabel("Henüz bağlı değil · görsel önizleme")
        t2.setStyleSheet("font-size: 11px; color: #8592A6;")
        header_text.addWidget(t1)
        header_text.addWidget(t2)
        header.addSpacing(6)
        header.addLayout(header_text)
        header.addStretch()
        layout.addLayout(header)
        layout.addWidget(Divider())

        saved_states = get_setting("smart_home_devices", {}) or {}

        # Sağ sütun (hava/akıllı ev/tahmin kartlarının paylaştığı dar alan)
        # bir 2 sütunlu ızgaraya yetecek kadar geniş değil — bu yüzden
        # cihazlar tek sütunda alt alta sıralanıyor (bkz. yorum: 2 sütun
        # denendiğinde ızgaranın minimum genişliği sütunu zorlayıp tüm
        # kartlarda sağdan metin kırpılmasına yol açıyordu).
        devices_box = QVBoxLayout()
        devices_box.setSpacing(12)
        for device in SMART_HOME_DEVICES:
            devices_box.addWidget(
                self._build_smart_home_row(device, saved_states.get(device["id"], False))
            )
        layout.addLayout(devices_box)

        return card

    def _build_smart_home_row(self, device, is_on):
        row_widget = QWidget()
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)

        row.addWidget(IconBadge(device["icon"], bg_color="rgba(245, 158, 11, 35)",
                                 fg_color=ACCENT, size=36, font_size=15, radius=10))

        text_box = QVBoxLayout()
        text_box.setSpacing(0)
        title_lbl = QLabel(device["title"])
        title_lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #F1F5F9;")
        subtitle_lbl = QLabel(device["subtitle"])
        subtitle_lbl.setStyleSheet("font-size: 10px; color: #8592A6;")
        text_box.addWidget(title_lbl)
        text_box.addWidget(subtitle_lbl)
        row.addLayout(text_box)
        row.addStretch()

        toggle = ToggleSwitch(checked=is_on)
        toggle.toggled.connect(lambda checked, device_id=device["id"]: self._on_smart_home_toggled(device_id, checked))
        row.addWidget(toggle)

        return row_widget

    def _on_smart_home_toggled(self, device_id, is_on):
        states = get_setting("smart_home_devices", {}) or {}
        states[device_id] = is_on
        set_setting("smart_home_devices", states)

    def _stat_row(self, parent_layout, icon, label, value_text):
        row = QHBoxLayout()
        row.setSpacing(6)
        icon_label = QLabel(icon)
        icon_label.setStyleSheet("font-size: 13px;")
        row.addWidget(icon_label)
        text_box = QVBoxLayout()
        text_box.setSpacing(0)
        name_label = QLabel(label)
        name_label.setStyleSheet("font-size: 10px; color: #8592A6;")
        value_label = QLabel(value_text)
        value_label.setStyleSheet("font-size: 13px; font-weight: 600; color: #E5E7EB;")
        text_box.addWidget(name_label)
        text_box.addWidget(value_label)
        row.addLayout(text_box)
        parent_layout.addLayout(row)
        return value_label

    def _build_forecast_row(self, day):
        row = QFrame()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)

        date_obj = datetime.strptime(day["date"], "%Y-%m-%d")
        day_box = QVBoxLayout()
        day_box.setSpacing(0)
        name_label = QLabel(TR_DAYS[date_obj.weekday()])
        name_label.setStyleSheet("font-size: 13px; font-weight: 600; color: #F1F5F9;")
        date_label = QLabel(format_tr_date_short(date_obj))
        date_label.setStyleSheet("font-size: 11px; color: #8592A6;")
        day_box.addWidget(name_label)
        day_box.addWidget(date_label)
        day_box_widget = QWidget()
        day_box_widget.setLayout(day_box)
        day_box_widget.setFixedWidth(92)
        row_layout.addWidget(day_box_widget)

        desc, emoji = WEATHER_CODES.get(day["code"], ("Bilinmiyor", "❓"))
        mid_box = QHBoxLayout()
        icon_label = QLabel(emoji)
        icon_label.setStyleSheet("font-size: 18px;")
        mid_box.addWidget(icon_label)
        desc_label = QLabel(desc)
        desc_label.setStyleSheet("font-size: 12px; color: #CBD5E1;")
        # "Gök gürültülü fırtına" gibi uzun açıklamalar, Hızlı İşlemler kartıyla
        # paylaşılan dar sütunda satırı genişletip yatay kaydırma çubuğuna yol
        # açmasın diye sarmalanıyor (sabit genişlikte tutulmuyor).
        desc_label.setWordWrap(True)
        mid_box.addWidget(desc_label)
        mid_box.addStretch()
        row_layout.addLayout(mid_box, stretch=1)

        # Maks/min tek bir QLabel'de (iki ayrı dar widget yerine) zengin
        # metinle gösteriliyor: sağ sütuna bu kart kapandıktan uzun süre
        # sonra (hava durumu API'si tamamlandığında) dinamik olarak eklenen
        # iki ayrı dar/sabit genişlikli kardeş widget, bazı Windows/Qt
        # kurulumlarında geometrisi/visible=True durumu doğru olsa bile
        # ekrana hiç boyanmıyordu; tek widget'a indirmek bunu bypass ediyor.
        temp_label = QLabel(
            f'<span style="color:#FBBF24;">{round(day["tmax"])}°</span> '
            f'<span style="color:#60A5FA;">{round(day["tmin"])}°</span>'
        )
        temp_label.setStyleSheet("font-size: 13px; font-weight: 700;")
        temp_label.setFixedWidth(60)
        temp_label.setAlignment(Qt.AlignRight)
        row_layout.addWidget(temp_label)

        return row

    # ------------------------------------------------------------------- #
    # Güncellemeler
    # ------------------------------------------------------------------- #
    def _update_clock(self):
        now = datetime.now()
        self.clock_time_label.setText(
            f'<span style="color:#F1F5F9;">{now.strftime("%H:%M")}</span>'
            f'<span style="color:{ACCENT};">:{now.strftime("%S")}</span>'
        )
        self.clock_date_label.setText(format_tr_date(now))
        self.header_date_label.setText(format_tr_date(now))

    def _on_weather_ready(self, result):
        self.weather_status_label.hide()

        current = result["current"]
        desc, emoji = WEATHER_CODES.get(current.get("weather_code"), ("Bilinmiyor", "❓"))
        self.current_icon_label.setText(emoji)
        self.current_temp_label.setText(f"{round(current.get('temperature_2m', 0))}°C")
        self.current_desc_label.setText(desc)
        self.humidity_label.setText(f"%{round(current.get('relative_humidity_2m', 0))}")
        self.wind_label.setText(f"{round(current.get('wind_speed_10m', 0))} km/s")
        self.pressure_label.setText(f"{round(current.get('surface_pressure', 0))} hPa")

        try:
            updated_time = datetime.fromisoformat(current["time"])
            self.weather_updated_label.setText(f"Son güncelleme\n{updated_time.strftime('%H:%M')}")
        except Exception:
            pass

        for day in result["days"]:
            row = self._build_forecast_row(day)
            self.forecast_list_layout.addWidget(row)

        # Satırlar, pencere zaten gösterildikten çok sonra (hava durumu API
        # yanıtı gelince) dinamik olarak ekleniyor; yeniden boyama tetikler.
        self.update()

        today_forecast = result["days"][0] if result["days"] else {}
        self._weather_data_for_briefing = {
            "sicaklik_c": current.get("temperature_2m"),
            "aciklama": desc,
            "nem_yuzde": current.get("relative_humidity_2m"),
            "ruzgar_kmh": current.get("wind_speed_10m"),
            "bugun_max_c": today_forecast.get("tmax"),
            "bugun_min_c": today_forecast.get("tmin"),
        }
        self._maybe_generate_briefing()

    def _on_weather_error(self, error_message):
        self.weather_status_label.setText(f"Hava durumu alınamadı: {error_message}")
        self.current_desc_label.setText("Hava durumu alınamadı")
        # Brifing için hava verisi yoksa bile boş sözlükle "geldi" sayıyoruz;
        # tek bir kaynağın başarısız olması tüm brifingi bloke etmemeli.
        self._weather_data_for_briefing = {}
        self._maybe_generate_briefing()

    def _on_finance_ready(self, data):
        self._finance_data = data
        self._maybe_generate_briefing()

    def _on_news_raw_ready(self, news_items_text):
        self._news_items_text = news_items_text
        self._maybe_generate_briefing()

    # ------------------------------------------------------------------- #
    # Günlük sesli brifing (LLM ile üretilir, sonra TTS ile okunur)
    # ------------------------------------------------------------------- #
    def _maybe_generate_briefing(self):
        if (self._weather_data_for_briefing is None
                or self._finance_data is None
                or self._news_items_text is None):
            return
        if not self._generate_briefing_func:
            self.news_loading_label.setText("Brifing oluşturulamadı (üretim fonksiyonu tanımlı değil).")
            return

        now = datetime.now()
        location = "İstanbul / Çatalca"
        time_str = f"{format_tr_date(now)} {now.strftime('%H:%M')}"

        self.news_loading_label.setText("Günlük brifing hazırlanıyor...")
        self.ai_orb.set_status_text("Hazırlanıyor...")

        self._briefing_thread = BriefingGenerationThread(
            self._generate_briefing_func, location, time_str, self._news_items_text,
        )
        self._briefing_thread.briefingReady.connect(self._on_briefing_ready)
        self._briefing_thread.briefingError.connect(self._on_briefing_error)
        self._briefing_thread.start()

    def _on_briefing_ready(self, briefing_text):
        self.news_loading_box.hide()
        self._news_scroll_area.show()

        if not briefing_text:
            self.ai_orb.set_status_text("Hata")
            self.briefing_text_label.setText("Brifing şu anda oluşturulamadı.")
            return

        self.ai_orb.set_status_text("Sistem Aktif")
        # Hava & Piyasa ve Kişisel Hatırlatmalar paragrafları LLM'den gelmiyor
        # (bkz. briefing_text.py); LLM'in ürettiği metne doğru sırada eklenir.
        briefing_text = briefing_text_module.assemble_final_briefing(
            briefing_text, self._weather_data_for_briefing, self._finance_data,
        )

        self.briefing_text_label.setText(briefing_text)

        self._briefing_reader_thread = BriefingReaderThread(
            briefing_text,
            pause_hotword_func=self._pause_hotword_func,
            resume_hotword_func=self._resume_hotword_func,
        )
        self._briefing_reader_thread.finishedSpeaking.connect(self._on_briefing_speaking_finished)
        self._briefing_reader_thread.start()
        self._set_briefing_controls_enabled(True)

    def _on_briefing_error(self, error_message):
        self.news_loading_box.hide()
        self._news_scroll_area.show()
        self.ai_orb.set_status_text("Hata")
        self.briefing_text_label.setText(f"Brifing oluşturulamadı: {error_message}")

    # --- Günlük Brifing Duraklat/Devam Et/Durdur düğmeleri -----------------
    def _set_briefing_controls_enabled(self, enabled):
        self.briefing_pause_btn.setEnabled(enabled)
        self.briefing_stop_btn.setEnabled(enabled)
        if not enabled:
            self._briefing_is_paused = False
            self.briefing_pause_btn.setText("⏸ Duraklat")

    def _on_briefing_pause_clicked(self):
        thread = self._briefing_reader_thread
        if not thread or not thread.isRunning():
            return
        if self._briefing_is_paused:
            thread.request_resume()
            self._briefing_is_paused = False
            self.briefing_pause_btn.setText("⏸ Duraklat")
        else:
            thread.request_pause()
            self._briefing_is_paused = True
            self.briefing_pause_btn.setText("▶ Devam Et")

    def _on_briefing_stop_clicked(self):
        thread = self._briefing_reader_thread
        if thread and thread.isRunning():
            thread.request_stop()
        self._set_briefing_controls_enabled(False)

    def _on_briefing_speaking_finished(self):
        self._set_briefing_controls_enabled(False)

    def closeEvent(self, event):
        # Dashboard kapanınca sesli brifing de durmalı; aksi halde pencere
        # gizlenmiş olsa bile TTS arka planda okumaya devam eder.
        thread = self._briefing_reader_thread
        if thread and thread.isRunning():
            thread.request_stop()
        super().closeEvent(event)
