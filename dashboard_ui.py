import html
import io
import json
import os
import re
import subprocess
import threading
import time
from datetime import datetime
import urllib.request
import xml.etree.ElementTree as ET

import win32api
import win32con
import win32gui
import win32process
from PIL import Image, ImageFilter

from PyQt5.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QFrame, QSizePolicy,
    QApplication, QStackedWidget, QScrollArea, QRadioButton, QButtonGroup, QSlider
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QRectF
from PyQt5.QtGui import QPainter, QPen, QColor, QPixmap

from chat_ui import ChatPage
from worker_threads import (
    speak_text, speak_text_interruptible, list_turkish_voices, get_selected_voice_id,
    set_selected_voice_id, get_setting, set_setting,
)
from tr_numbers import currency_to_words, percent_to_words, plain_number_to_words
from personal_context import build_reminder_block
from persona_settings import (
    get_espri_pct, set_espri_pct, get_arkadaslik_pct, set_arkadaslik_pct,
)

# "Müzik Çal" hızlı işlem butonuyla açılan varsayılan müzik çalar
ORCHARD_EXE_PATH = r"C:\Users\Onur\Documents\GitHub\orchard\build\dev\orchard.exe"

# Pencerenin arkasında bulanıklaştırılıp koyulaştırılarak gösterilen oda fotoğrafı
BACKGROUND_PHOTO_PATH = r"C:\Users\Onur\Documents\GitHub\orchard\Sıcak Japandi Salon Tasarımı.png"

# Marka vurgu rengi: amber/altın (sıcak, "akıllı ev" temalı arayüze uygun)
ACCENT = "#F59E0B"
ACCENT_STRONG = "#D97706"
ACCENT_SOFT = "#FDE68A"

# Çatalca / İstanbul koordinatları
LATITUDE = 41.1431
LONGITUDE = 28.4606

TR_MONTHS = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
             "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
TR_DAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]

# WMO hava durumu kodları -> (açıklama, emoji)
WEATHER_CODES = {
    0: ("Açık", "☀️"),
    1: ("Az bulutlu", "🌤️"),
    2: ("Parçalı Bulutlu", "⛅"),
    3: ("Kapalı", "☁️"),
    45: ("Sisli", "🌫️"),
    48: ("Kırağı sisi", "🌫️"),
    51: ("Hafif çisenti", "🌦️"),
    53: ("Çisenti", "🌦️"),
    55: ("Yoğun çisenti", "🌦️"),
    61: ("Hafif Yağmur", "🌧️"),
    63: ("Yağmur", "🌧️"),
    65: ("Şiddetli yağmur", "🌧️"),
    71: ("Hafif kar", "🌨️"),
    73: ("Kar", "🌨️"),
    75: ("Yoğun kar", "🌨️"),
    80: ("Sağanak", "🌦️"),
    81: ("Kuvvetli sağanak", "🌧️"),
    82: ("Şiddetli sağanak", "⛈️"),
    95: ("Gök gürültülü fırtına", "⛈️"),
    96: ("Dolu ile fırtına", "⛈️"),
    99: ("Şiddetli dolu fırtınası", "⛈️"),
}


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


def format_tr_date(dt: datetime) -> str:
    return f"{dt.day} {TR_MONTHS[dt.month - 1]} {dt.year} {TR_DAYS[dt.weekday()]}"


def format_tr_date_short(dt: datetime) -> str:
    return f"{dt.day} {TR_MONTHS[dt.month - 1]}"


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


# --------------------------------------------------------------------------- #
# Günlük Brifing: ham veri kaynakları (hepsi ücretsiz, API anahtarı gerekmez)
# --------------------------------------------------------------------------- #

NEWS_AI_RSS_URL = "https://techcrunch.com/category/artificial-intelligence/feed/"
NEWS_TURKEY_RSS_URL = "https://www.ntv.com.tr/gundem.rss"
NEWS_WORLD_RSS_URL = "https://www.ntv.com.tr/dunya.rss"

TCMB_RATES_URL = "https://www.tcmb.gov.tr/kurlar/today.xml"
BIST100_URL = "https://query1.finance.yahoo.com/v8/finance/chart/XU100.IS"
GOLD_FUTURES_URL = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F"
BTC_PRICE_URL = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=try,usd"
GRAMS_PER_OUNCE = 31.1034768

NEWS_SUMMARY_MAX_LEN = 200

# Küçük/yerel LLM'in (gemma3:4b) her zaman güvenilir şekilde filtrelemesini
# beklemek risklidir; bu yüzden en belirgin tık tuzağı (clickbait) kalıpları
# LLM'e hiç gitmeden burada, kod seviyesinde deterministik olarak eleniyor.
CLICKBAIT_PATTERNS = [
    "son dakika", "açıklandı", "sorgulama", "canlı sonuç", "canlı sonuçlar",
    "çekiliş sonuçları", "kazandıran numaralar", "sorgula",
]


def _is_clickbait(title):
    lower = title.lower().strip()
    if lower.endswith("?"):
        return True
    return any(pattern in lower for pattern in CLICKBAIT_PATTERNS)


def _strip_html(text):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _truncate(text, max_len=NEWS_SUMMARY_MAX_LEN):
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip() + "…"


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


class Divider(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(1)
        self.setStyleSheet("background-color: rgba(255, 255, 255, 25);")


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
            url = (
                "https://api.open-meteo.com/v1/forecast"
                f"?latitude={LATITUDE}&longitude={LONGITUDE}"
                "&current=temperature_2m,relative_humidity_2m,surface_pressure,wind_speed_10m,weather_code"
                "&daily=weather_code,temperature_2m_max,temperature_2m_min"
                "&timezone=Europe%2FIstanbul&forecast_days=7"
            )
            with urllib.request.urlopen(url, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))

            current = data["current"]
            daily = data["daily"]
            days = []
            for i in range(len(daily["time"])):
                days.append({
                    "date": daily["time"][i],
                    "code": daily["weather_code"][i],
                    "tmax": daily["temperature_2m_max"][i],
                    "tmin": daily["temperature_2m_min"][i],
                })

            self.weatherReady.emit({"current": current, "days": days})
        except Exception as e:
            self.weatherError.emit(str(e))


# --------------------------------------------------------------------------- #
# Ham haber akışı (yerel, API anahtarı gerekmeyen ücretsiz RSS kaynakları).
# Bu başlıklar doğrudan kullanıcıya gösterilmez/okunmaz; brifing metnini
# üretmesi için LLM'e ham girdi olarak verilir (bkz. BriefingGenerationThread).
# --------------------------------------------------------------------------- #

class NewsFetchThread(QThread):
    newsReady = pyqtSignal(str)

    def _http_get(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.read()

    def _fetch_rss2_items(self, url, limit):
        try:
            data = self._http_get(url)
            root = ET.fromstring(data)
            results = []
            for item in root.findall("./channel/item"):
                title = _strip_html(item.findtext("title") or "")
                if not title or _is_clickbait(title):
                    continue
                summary = _truncate(_strip_html(item.findtext("description") or ""))
                results.append({"title": title, "summary": summary})
                if len(results) >= limit:
                    break
            return results
        except Exception as e:
            print(f"⚠️ RSS alınamadı ({url}): {e}")
            return []

    def _fetch_atom_items(self, url, limit):
        try:
            data = self._http_get(url)
            root = ET.fromstring(data)
            ns = {"a": "http://www.w3.org/2005/Atom"}
            results = []
            for entry in root.findall("a:entry", ns):
                title = _strip_html(entry.findtext("a:title", namespaces=ns) or "")
                if not title or _is_clickbait(title):
                    continue
                summary = _truncate(_strip_html(entry.findtext("a:summary", namespaces=ns) or ""))
                results.append({"title": title, "summary": summary})
                if len(results) >= limit:
                    break
            return results
        except Exception as e:
            print(f"⚠️ RSS alınamadı ({url}): {e}")
            return []

    @staticmethod
    def _format_block(category_label, items):
        lines = []
        for item in items:
            line = f"[{category_label}] {item['title']}"
            if item.get("summary"):
                line += f" — {item['summary']}"
            lines.append(line)
        return lines

    def run(self):
        turkey_items = self._fetch_atom_items(NEWS_TURKEY_RSS_URL, limit=6)
        world_items = self._fetch_atom_items(NEWS_WORLD_RSS_URL, limit=5)
        ai_items = self._fetch_rss2_items(NEWS_AI_RSS_URL, limit=3)

        # NTV'nin gündem ve dünya akışları aynı haberi (ör. bir piyango
        # haberini) iki kategoride birden yayınlayabiliyor; aynı başlık
        # ikinci kez geçerse ilk gördüğü kategoride tutulur.
        seen_titles = set()
        for items in (turkey_items, world_items, ai_items):
            deduped = []
            for item in items:
                key = item["title"].lower().strip()
                if key in seen_titles:
                    continue
                seen_titles.add(key)
                deduped.append(item)
            items[:] = deduped

        lines = []
        lines += self._format_block("TÜRKİYE", turkey_items)
        lines += self._format_block("DÜNYA", world_items)
        lines += self._format_block("TEKNOLOJİ", ai_items)

        news_items_text = "\n".join(lines) if lines else "(Haber akışı alınamadı.)"
        self.newsReady.emit(news_items_text)


# --------------------------------------------------------------------------- #
# Piyasa verisi (yerel, API anahtarı gerekmeyen ücretsiz kaynaklar: TCMB,
# Yahoo Finance uç noktaları, CoinGecko).
# --------------------------------------------------------------------------- #

class FinanceFetchThread(QThread):
    financeReady = pyqtSignal(dict)

    def _http_get_json(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    def run(self):
        result = {}
        usd_try = None

        try:
            req = urllib.request.Request(TCMB_RATES_URL, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as response:
                root = ET.fromstring(response.read())
            usd_el = root.find("./Currency[@Kod='USD']")
            usd_try = float(usd_el.findtext("ForexSelling"))
            result["usd_try_satis"] = round(usd_try, 4)
        except Exception as e:
            print(f"⚠️ Dolar kuru alınamadı: {e}")

        try:
            data = self._http_get_json(BIST100_URL)
            meta = data["chart"]["result"][0]["meta"]
            result["bist100"] = round(meta["regularMarketPrice"], 2)
            result["bist100_gunluk_yuzde_degisim"] = round(meta.get("regularMarketChangePercent", 0), 2)
        except Exception as e:
            print(f"⚠️ BIST100 verisi alınamadı: {e}")

        try:
            data = self._http_get_json(GOLD_FUTURES_URL)
            meta = data["chart"]["result"][0]["meta"]
            gold_usd_oz = meta["regularMarketPrice"]
            if usd_try:
                result["gram_altin_try"] = round((gold_usd_oz * usd_try) / GRAMS_PER_OUNCE, 2)
        except Exception as e:
            print(f"⚠️ Altın verisi alınamadı: {e}")

        try:
            data = self._http_get_json(BTC_PRICE_URL)
            result["btc_try"] = data["bitcoin"]["try"]
            result["btc_usd"] = data["bitcoin"]["usd"]
        except Exception as e:
            print(f"⚠️ BTC verisi alınamadı: {e}")

        self.financeReady.emit(result)


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
                 generate_briefing_func=None, set_listening_muted_func=None):
        super().__init__()
        self._process_input_func = process_input_func
        self._execute_powershell_func = execute_powershell_func
        self._pause_hotword_func = pause_hotword_func
        self._resume_hotword_func = resume_hotword_func
        self._generate_briefing_func = generate_briefing_func
        self._set_listening_muted_func = set_listening_muted_func
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
        body.addWidget(self.content_stack, stretch=1)

        root_layout.addLayout(body, stretch=1)

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

        mic_label = QLabel("🎤")
        mic_label.setStyleSheet("font-size: 16px;")
        layout.addWidget(mic_label)

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
                    QRadioButton { font-size: 14px; color: #E5E7EB; padding: 6px 0; }
                """)
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
        columns.addWidget(self._build_news_card(), stretch=20)
        columns.addWidget(self._build_right_column(), stretch=12)
        layout.addLayout(columns, stretch=1)

        return container

    def _build_right_column(self):
        """Hava Durumu, Akıllı Ev Kontrolleri ve 7 Günlük Tahmin kartlarını
        dikey olarak sıralar; üçü toplamda dar ekranlarda taşabileceği
        için kaydırılabilir bir alan içine konur."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")
        scroll.viewport().setStyleSheet("background: transparent;")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(18)

        content_layout.addWidget(self._build_weather_card())
        content_layout.addWidget(self._build_smart_home_card())
        content_layout.addWidget(self._build_forecast_card())
        content_layout.addStretch()

        scroll.setWidget(content)
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
            self._listen_toggle_btn.setText("🔇  Dinlemeyi Başlat")
        else:
            self._listen_toggle_btn.setText("🎤  Dinlemeyi Duraklat")

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

        # Hızlı işlem butonları (ör. Müzik Çal) burada çerçevenin sol üst
        # köşesinden başlayarak dikey sırayla listeleniyor. İleride yeni
        # butonlar eklemek için _add_quick_action_button() kullanılabilir.
        quick_actions_container = QWidget()
        self.quick_actions_layout = QVBoxLayout(quick_actions_container)
        self.quick_actions_layout.setContentsMargins(0, 0, 0, 0)
        self.quick_actions_layout.setSpacing(8)
        self.quick_actions_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self._add_quick_action_button("🎵  Müzik Çal", self._on_play_music_clicked)
        self._listen_toggle_btn = self._add_quick_action_button(
            "🎤  Dinlemeyi Duraklat", self._on_toggle_listening_clicked
        )

        layout.addWidget(quick_actions_container, stretch=1)

        return card

    def _add_quick_action_button(self, text, handler):
        btn = QPushButton(text)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedHeight(40)
        btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        btn.setStyleSheet(f"""
            QPushButton {{ background-color: rgba(30, 27, 23, 190); color: #E5E7EB; border-radius: 10px;
                          padding: 0 16px; font-size: 13px; font-weight: 600; }}
            QPushButton:hover {{ background-color: {ACCENT_STRONG}; }}
        """)
        btn.clicked.connect(handler)
        self.quick_actions_layout.addWidget(btn, alignment=Qt.AlignLeft)
        return btn

    # --- Kart 2: Günlük Brifing --------------------------------------------------
    def _build_news_card(self):
        card = self._card_frame()
        outer = QVBoxLayout(card)
        outer.setContentsMargins(22, 20, 22, 20)
        outer.setSpacing(12)

        header = QHBoxLayout()
        header.addWidget(IconBadge("📰", bg_color="transparent", fg_color=ACCENT, size=28, font_size=18))
        header_label = QLabel("Günlük Brifing")
        header_label.setStyleSheet("font-size: 15px; font-weight: 600; color: #F1F5F9;")
        header.addSpacing(6)
        header.addWidget(header_label)
        header.addStretch()

        briefing_control_btn_style = """
            QPushButton { background-color: #1E293B; color: #E5E7EB; border-radius: 8px;
                          padding: 6px 12px; font-size: 13px; }
            QPushButton:hover { background-color: #334155; }
            QPushButton:disabled { background-color: #161C28; color: #475569; }
        """
        self.briefing_pause_btn = QPushButton("⏸ Duraklat")
        self.briefing_pause_btn.setCursor(Qt.PointingHandCursor)
        self.briefing_pause_btn.setStyleSheet(briefing_control_btn_style)
        self.briefing_pause_btn.setEnabled(False)
        self.briefing_pause_btn.clicked.connect(self._on_briefing_pause_clicked)
        header.addWidget(self.briefing_pause_btn)

        self.briefing_stop_btn = QPushButton("⏹ Durdur")
        self.briefing_stop_btn.setCursor(Qt.PointingHandCursor)
        self.briefing_stop_btn.setStyleSheet(briefing_control_btn_style)
        self.briefing_stop_btn.setEnabled(False)
        self.briefing_stop_btn.clicked.connect(self._on_briefing_stop_clicked)
        header.addWidget(self.briefing_stop_btn)

        outer.addLayout(header)
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
        day_box_widget.setFixedWidth(110)
        row_layout.addWidget(day_box_widget)

        desc, emoji = WEATHER_CODES.get(day["code"], ("Bilinmiyor", "❓"))
        mid_box = QHBoxLayout()
        icon_label = QLabel(emoji)
        icon_label.setStyleSheet("font-size: 18px;")
        mid_box.addWidget(icon_label)
        desc_label = QLabel(desc)
        desc_label.setStyleSheet("font-size: 12px; color: #CBD5E1;")
        mid_box.addWidget(desc_label)
        mid_box.addStretch()
        row_layout.addLayout(mid_box, stretch=1)

        tmax_label = QLabel(f"{round(day['tmax'])}°")
        tmax_label.setStyleSheet("font-size: 13px; font-weight: 700; color: #FBBF24;")
        tmax_label.setFixedWidth(34)
        tmax_label.setAlignment(Qt.AlignRight)
        row_layout.addWidget(tmax_label)

        tmin_label = QLabel(f"{round(day['tmin'])}°")
        tmin_label.setStyleSheet("font-size: 13px; font-weight: 700; color: #60A5FA;")
        tmin_label.setFixedWidth(34)
        tmin_label.setAlignment(Qt.AlignRight)
        row_layout.addWidget(tmin_label)

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
            self.forecast_list_layout.addWidget(self._build_forecast_row(day))

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
    def _weather_phrases_for_briefing(self):
        """Hava verisindeki rakamları LLM'e göndermeden önce, burada
        deterministik olarak hazır Türkçe ifadelere çevirir (bkz. tr_numbers.py)."""
        w = self._weather_data_for_briefing or {}
        phrases = {}
        if w.get("sicaklik_c") is not None:
            phrases["sicaklik"] = f"{plain_number_to_words(w['sicaklik_c'])} derece"
        if w.get("aciklama"):
            phrases["hava_durumu_aciklamasi"] = w["aciklama"]
        if w.get("nem_yuzde") is not None:
            phrases["nem_orani"] = percent_to_words(w["nem_yuzde"])
        if w.get("ruzgar_kmh") is not None:
            phrases["ruzgar_hizi"] = f"saatte {plain_number_to_words(w['ruzgar_kmh'])} kilometre"
        if w.get("bugun_max_c") is not None:
            phrases["bugun_en_yuksek_sicaklik"] = f"{plain_number_to_words(w['bugun_max_c'])} derece"
        if w.get("bugun_min_c") is not None:
            phrases["bugun_en_dusuk_sicaklik"] = f"{plain_number_to_words(w['bugun_min_c'])} derece"
        return phrases

    def _finance_phrases_for_briefing(self):
        """Piyasa verisindeki rakamları LLM'e göndermeden önce, burada
        deterministik olarak hazır Türkçe ifadelere çevirir (bkz. tr_numbers.py)."""
        f = self._finance_data or {}
        phrases = {}
        if f.get("usd_try_satis") is not None:
            phrases["dolar_tl_satis_kuru"] = currency_to_words(f["usd_try_satis"])
        if f.get("bist100") is not None:
            phrases["bist100_endeksi"] = f"{plain_number_to_words(f['bist100'])} puan"
        if f.get("bist100_gunluk_yuzde_degisim") is not None:
            phrases["bist100_gunluk_degisim"] = percent_to_words(f["bist100_gunluk_yuzde_degisim"])
        if f.get("gram_altin_try") is not None:
            phrases["gram_altin_fiyati"] = currency_to_words(f["gram_altin_try"])
        if f.get("btc_try") is not None:
            phrases["bitcoin_tl_karsiligi"] = f"{plain_number_to_words(f['btc_try'])} lira"
        if f.get("btc_usd") is not None:
            phrases["bitcoin_dolar_karsiligi"] = f"{plain_number_to_words(f['btc_usd'])} dolar"
        return phrases

    def _build_weather_finance_paragraph(self):
        """Hava & Piyasa paragrafını LLM'e hiç yazdırmadan, tamamen
        deterministik olarak kurar. Testlerde küçük yerel modelin (gemma3:4b)
        hazır Türkçe rakam ifadelerini bile ara sıra yanlış kopyaladığı
        (ör. "yetmiş dokuz" yerine "seksen dokuz" yazması) görüldü; bu
        yüzden rakam içeren tek bölüm LLM'in eline hiç bırakılmıyor."""
        w = self._weather_phrases_for_briefing()
        f = self._finance_phrases_for_briefing()

        sentences = []
        if w.get("hava_durumu_aciklamasi") and w.get("sicaklik"):
            weather_sentence = (
                f"Hava durumuna gelirsek; İstanbul Çatalca'da hava "
                f"{w['hava_durumu_aciklamasi'].lower()}, sıcaklık {w['sicaklik']}"
            )
            if w.get("nem_orani"):
                weather_sentence += f", nem oranı {w['nem_orani']}"
            if w.get("ruzgar_hizi"):
                weather_sentence += f", rüzgar hızı {w['ruzgar_hizi']}"
            sentences.append(weather_sentence + ".")

        finance_bits = []
        if f.get("dolar_tl_satis_kuru"):
            finance_bits.append(f"dolar {f['dolar_tl_satis_kuru']} seviyesinde")
        if f.get("bist100_endeksi"):
            bist_bit = f"BIST 100 endeksi {f['bist100_endeksi']}"
            if f.get("bist100_gunluk_degisim"):
                bist_bit += f" ile günü {f['bist100_gunluk_degisim']} değişimle tamamlıyor"
            finance_bits.append(bist_bit)
        if f.get("gram_altin_fiyati"):
            finance_bits.append(f"gram altın {f['gram_altin_fiyati']}")
        if f.get("bitcoin_tl_karsiligi"):
            btc_bit = f"Bitcoin {f['bitcoin_tl_karsiligi']}"
            if f.get("bitcoin_dolar_karsiligi"):
                btc_bit += f" ({f['bitcoin_dolar_karsiligi']})"
            finance_bits.append(btc_bit)
        if finance_bits:
            sentences.append("Piyasalara bakacak olursak; " + ", ".join(finance_bits) + ".")

        return " ".join(sentences)

    def _build_personal_reminders_paragraph(self):
        """Doğum Günleri ve Randevular.md'deki yaklaşan (14 gün içindeki)
        kayıtları, hava & piyasa paragrafıyla aynı mantıkla (bkz.
        _build_weather_finance_paragraph) tamamen deterministik olarak
        hazırlar; LLM'in eline hiç bırakılmaz."""
        block = build_reminder_block(within_days=14)
        if not block:
            return ""
        return "Kişisel hatırlatmalara gelirsek; " + block

    _KNOWN_SECTION_HEADER_RE = re.compile(
        r"^\s*(giriş|hava\s*&\s*piyasa|hava\s+ve\s+piyasa|türkiye\s+gündemi|"
        r"dünya\s+turu|teknoloji|kapanış)\s*:\s*",
        re.IGNORECASE,
    )

    @classmethod
    def _strip_known_section_headers(cls, text):
        """LLM, talimata uymayıp ara sıra 'Türkiye Gündemi: ...' gibi bölüm
        başlıklarını (tek başına bir satır olarak ya da bir paragrafın başına
        yapıştırarak) çıktıya yazabiliyor; bunlar TTS'te garip durduğu için
        hem tek başına hem de bir paragrafın önüne eklenmiş hallerinde eleniyor."""
        cleaned_lines = []
        for line in text.split("\n"):
            line = cls._KNOWN_SECTION_HEADER_RE.sub("", line, count=1)
            cleaned_lines.append(line)
        return "\n".join(cleaned_lines)

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
        briefing_text = self._strip_known_section_headers(briefing_text)

        # Hava & Piyasa paragrafı LLM'den gelmiyor (bkz. _build_weather_finance_paragraph);
        # LLM'in ürettiği ilk paragrafı (Giriş) hemen ardına ekleniyor.
        paragraphs = [p.strip() for p in briefing_text.split("\n\n") if p.strip()]
        weather_finance_paragraph = self._build_weather_finance_paragraph()
        personal_reminders_paragraph = self._build_personal_reminders_paragraph()
        insert_at = 1
        if paragraphs and weather_finance_paragraph:
            paragraphs.insert(insert_at, weather_finance_paragraph)
            insert_at += 1
        elif weather_finance_paragraph:
            paragraphs.append(weather_finance_paragraph)
        if paragraphs and personal_reminders_paragraph:
            paragraphs.insert(insert_at, personal_reminders_paragraph)
        elif personal_reminders_paragraph:
            paragraphs.append(personal_reminders_paragraph)
        briefing_text = "\n\n".join(paragraphs)

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
