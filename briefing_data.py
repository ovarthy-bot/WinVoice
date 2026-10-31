# briefing_data.py
#
# Günlük Brifing'in ham veri kaynaklarını (hava durumu, piyasa, haber) çeken
# saf Python fonksiyonları. PyQt bağımlılığı YOKTUR — bu yüzden hem
# dashboard_ui.py'deki QThread sınıfları (bkz. WeatherFetchThread,
# NewsFetchThread, FinanceFetchThread) hem de arayüzsüz telegram_briefing.py
# aynı kodu çağırabilir. Tüm kaynaklar ücretsiz ve API anahtarı gerektirmez.

import html
import json
import re
import urllib.request
import xml.etree.ElementTree as ET

# Çatalca / İstanbul koordinatları
LATITUDE = 41.1431
LONGITUDE = 28.4606

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


def _http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as response:
        return response.read()


def _http_get_json(url):
    return json.loads(_http_get(url).decode("utf-8"))


def fetch_weather():
    """Open-Meteo'dan güncel hava durumu ve 7 günlük tahmini çeker.
    Dönüş: {"current": {...}, "days": [{"date", "code", "tmax", "tmin"}, ...]}.
    Hata durumunda İstisna fırlatır (çağıran taraf yakalamalı)."""
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={LATITUDE}&longitude={LONGITUDE}"
        "&current=temperature_2m,relative_humidity_2m,surface_pressure,wind_speed_10m,weather_code"
        "&daily=weather_code,temperature_2m_max,temperature_2m_min"
        "&timezone=Europe%2FIstanbul&forecast_days=7"
    )
    data = _http_get_json(url)
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
    return {"current": current, "days": days}


def _fetch_rss2_items(url, limit):
    try:
        root = ET.fromstring(_http_get(url))
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


def _fetch_atom_items(url, limit):
    try:
        root = ET.fromstring(_http_get(url))
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


def _format_news_block(category_label, items):
    lines = []
    for item in items:
        line = f"[{category_label}] {item['title']}"
        if item.get("summary"):
            line += f" — {item['summary']}"
        lines.append(line)
    return lines


def fetch_news_items_text():
    """Türkiye/Dünya/Teknoloji RSS akışlarından ham, LLM'e girdi olacak
    haber metnini üretir. Tek bir haberin iki kategoride (ör. NTV'nin
    gündem+dünya) tekrarlanması durumunda ilk gördüğü kategoride tutulur."""
    turkey_items = _fetch_atom_items(NEWS_TURKEY_RSS_URL, limit=6)
    world_items = _fetch_atom_items(NEWS_WORLD_RSS_URL, limit=5)
    ai_items = _fetch_rss2_items(NEWS_AI_RSS_URL, limit=3)

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
    lines += _format_news_block("TÜRKİYE", turkey_items)
    lines += _format_news_block("DÜNYA", world_items)
    lines += _format_news_block("TEKNOLOJİ", ai_items)

    return "\n".join(lines) if lines else "(Haber akışı alınamadı.)"


def fetch_finance():
    """TCMB (dolar kuru), Yahoo Finance (BIST 100, altın) ve CoinGecko
    (Bitcoin) verilerini çeker. Her kaynak kendi içinde korumalıdır: biri
    başarısız olursa diğerleri yine de sonuca eklenir; hepsi başarısız
    olursa boş sözlük döner."""
    result = {}
    usd_try = None

    try:
        root = ET.fromstring(_http_get(TCMB_RATES_URL))
        usd_el = root.find("./Currency[@Kod='USD']")
        usd_try = float(usd_el.findtext("ForexSelling"))
        result["usd_try_satis"] = round(usd_try, 4)
    except Exception as e:
        print(f"⚠️ Dolar kuru alınamadı: {e}")

    try:
        data = _http_get_json(BIST100_URL)
        meta = data["chart"]["result"][0]["meta"]
        result["bist100"] = round(meta["regularMarketPrice"], 2)
        result["bist100_gunluk_yuzde_degisim"] = round(meta.get("regularMarketChangePercent", 0), 2)
    except Exception as e:
        print(f"⚠️ BIST100 verisi alınamadı: {e}")

    try:
        data = _http_get_json(GOLD_FUTURES_URL)
        meta = data["chart"]["result"][0]["meta"]
        gold_usd_oz = meta["regularMarketPrice"]
        if usd_try:
            result["gram_altin_try"] = round((gold_usd_oz * usd_try) / GRAMS_PER_OUNCE, 2)
    except Exception as e:
        print(f"⚠️ Altın verisi alınamadı: {e}")

    try:
        data = _http_get_json(BTC_PRICE_URL)
        result["btc_try"] = data["bitcoin"]["try"]
        result["btc_usd"] = data["bitcoin"]["usd"]
    except Exception as e:
        print(f"⚠️ BTC verisi alınamadı: {e}")

    return result
