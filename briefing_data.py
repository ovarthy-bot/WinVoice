# briefing_data.py
#
# Günlük Brifing'in ham veri kaynaklarını (saatlik hava durumu, yüzde değişimli
# piyasa ve 3 eksenli kişisel haber akışı) çeken saf Python fonksiyonları.
# PyQt bağımlılığı YOKTUR — hem dashboard_ui.py'deki QThread sınıfları hem de
# arayüzsüz telegram_briefing.py aynı kodu çağırabilir.

import concurrent.futures
import email.utils
import hashlib
import html
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import note_database
import persona_settings

# Çatalca / İstanbul koordinatları
LATITUDE = 41.1431
LONGITUDE = 28.4606

ISTANBUL_TZ = timezone(timedelta(hours=3))

# Kişisel ilgi alanlarına göre kürate edilmiş ücretsiz RSS kaynakları
FEED_SOURCES = [
    # Havacılık (küresel + Türkiye sivil havacılık / teknik)
    {"name": "AeroTime", "category": "HAVACILIK", "kind": "rss2", "url": "https://www.aerotime.aero/feed", "limit": 8},
    {"name": "HavaSosyalMedya", "category": "HAVACILIK", "kind": "rss2", "url": "https://www.havasosyalmedya.com/feed/", "limit": 6},
    {"name": "AirlineHaber", "category": "HAVACILIK", "kind": "rss2", "url": "https://www.airlinehaber.com/feed/", "limit": 6},
    # Yapay Zekâ & Yazılım
    {"name": "TechCrunchAI", "category": "YAPAY ZEKA VE YAZILIM", "kind": "rss2", "url": "https://techcrunch.com/category/artificial-intelligence/feed/", "limit": 6},
    {"name": "GitHubBlog", "category": "YAPAY ZEKA VE YAZILIM", "kind": "rss2", "url": "https://github.blog/feed/", "limit": 5},
    {"name": "HackerNews", "category": "YAPAY ZEKA VE YAZILIM", "kind": "rss2", "url": "https://hnrss.org/frontpage?points=150", "limit": 6},
    # Türkiye & Dünya Gündemi
    {"name": "NTVGundem", "category": "TÜRKİYE", "kind": "atom", "url": "https://www.ntv.com.tr/gundem.rss", "limit": 8},
    {"name": "NTVDunya", "category": "DÜNYA", "kind": "atom", "url": "https://www.ntv.com.tr/dunya.rss", "limit": 6},
    {"name": "BBCTurkce", "category": "DÜNYA", "kind": "rss2", "url": "https://feeds.bbci.co.uk/turkce/rss.xml", "limit": 6},
]

TCMB_RATES_URL = "https://www.tcmb.gov.tr/kurlar/today.xml"
USDTRY_YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/TRY=X"
BIST100_URL = "https://query1.finance.yahoo.com/v8/finance/chart/XU100.IS"
GOLD_FUTURES_URL = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F"
BTC_PRICE_URL = (
    "https://api.coingecko.com/api/v3/simple/price"
    "?ids=bitcoin&vs_currencies=try,usd&include_24hr_change=true"
)
GRAMS_PER_OUNCE = 31.1034768

NEWS_SUMMARY_MAX_LEN = 190

CLICKBAIT_PATTERNS = [
    "son dakika", "açıklandı", "sorgulama", "canlı sonuç", "canlı sonuçlar",
    "çekiliş sonuçları", "kazandıran numaralar", "sorgula", "belli oldu",
    "şok karar", "bakın kim", "inanılmaz", "görenler şaşırdı",
]

# 3 eksenli puanlama için kişisel ilgi anahtar kelimeleri
_AVIATION_HIGH_KEYWORDS = (
    "airbus", "boeing", "easa", "shgm", "faa", "thy", "türk hava yolları",
    "turkish airlines", "turkish technic", "iga", "istanbul havalimanı",
    "mro", "kabin", "cabin", "maintenance", "bakım", "airworthiness",
    "a320", "a321", "a330", "a350", "b737", "b777", "b787", "777", "330",
    "escape slide", "emergency", "avionics", "hangar", "filo", "uçak",
)
_AI_DEV_HIGH_KEYWORDS = (
    "ai", "artificial intelligence", "yapay zeka", "llm", "agent", "agents",
    "claude", "anthropic", "openai", "gpt", "gemini", "ollama", "local model",
    "open source", "github", "copilot", "flutter", "dart", "python", "windows",
    "sqlite", "cloudflare", "reasoning", "coding", "developer",
)
_GENERAL_IMPORTANCE_KEYWORDS = (
    "safety", "directive", "recall", "release", "launched", "announces",
    "merkez bankası", "faiz", "enflasyon", "istanbul", "çatalca", "deprem",
    "savunma", "teknofest", "uzay", "anlaşma", "yönetmelik",
)
_NEWS_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "into", "over", "after",
    "new", "how", "why", "bir", "ile", "için", "olan", "göre", "daha", "yeni",
    "olarak", "sonra", "kadar", "üzerine", "ilgili",
}

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


def _http_get(url, timeout=8):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def _http_get_json(url, timeout=8):
    return json.loads(_http_get(url, timeout=timeout).decode("utf-8"))


# --------------------------------------------------------------------------- #
# Hava Durumu (Güncel + 7 Günlük + Saatlik Sabah/Öğle/Akşam/Gece Dilimleri)
# --------------------------------------------------------------------------- #

def fetch_weather():
    """Open-Meteo'dan güncel hava durumu, 7 günlük tahmin ve ilk 32 saatin
    saatlik verisini (hissedilen sıcaklık, yağış olasılığı, rüzgar hamlesi) çeker."""
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={LATITUDE}&longitude={LONGITUDE}"
        "&current=temperature_2m,apparent_temperature,relative_humidity_2m,surface_pressure,wind_speed_10m,weather_code"
        "&hourly=temperature_2m,apparent_temperature,precipitation_probability,wind_gusts_10m,weather_code"
        "&daily=weather_code,temperature_2m_max,temperature_2m_min"
        "&timezone=Europe%2FIstanbul&forecast_days=7"
    )
    data = _http_get_json(url, timeout=10)
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

    hourly_raw = data.get("hourly") or {}
    h_times = hourly_raw.get("time") or []
    hourly_points = []
    for i in range(min(32, len(h_times))):
        hourly_points.append({
            "time": h_times[i],
            "hour_index": i,
            "temp": (hourly_raw.get("temperature_2m") or [None])[i],
            "apparent": (hourly_raw.get("apparent_temperature") or [None])[i],
            "precip_prob": (hourly_raw.get("precipitation_probability") or [0])[i] or 0,
            "wind_gust": (hourly_raw.get("wind_gusts_10m") or [0])[i] or 0,
            "code": (hourly_raw.get("weather_code") or [0])[i] or 0,
        })

    return {"current": current, "days": days, "hourly": hourly_points}


def extract_weather_for_briefing(weather_result):
    """fetch_weather() çıktısını briefing_text.py'nin beklediği sözlüğe çevirir."""
    if not weather_result:
        return {}
    current = weather_result.get("current") or {}
    days = weather_result.get("days") or []
    today_forecast = days[0] if days else {}
    code = current.get("weather_code")
    desc, _emoji = WEATHER_CODES.get(code, ("Bilinmiyor", "🌡️"))
    return {
        "sicaklik_c": current.get("temperature_2m"),
        "hissedilen_c": current.get("apparent_temperature"),
        "aciklama": desc,
        "nem_yuzde": current.get("relative_humidity_2m"),
        "ruzgar_kmh": current.get("wind_speed_10m"),
        "bugun_max_c": today_forecast.get("tmax"),
        "bugun_min_c": today_forecast.get("tmin"),
        "hourly": weather_result.get("hourly") or [],
    }


# --------------------------------------------------------------------------- #
# 3 Eksenli Kişisel Haber Seçimi, Tekilleştirme ve seen_news Hafızası
# --------------------------------------------------------------------------- #

def _parse_pub_datetime(raw_date):
    if not raw_date:
        return None
    text = raw_date.strip()
    try:
        dt = email.utils.parsedate_to_datetime(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        pass
    try:
        iso = text.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _title_tokens(title):
    cleaned = re.sub(r"[^\w\sçğıöşüÇĞİÖŞÜ]", " ", (title or "").lower())
    return {
        tok for tok in cleaned.split()
        if len(tok) >= 3 and tok not in _NEWS_STOPWORDS and not tok.isdigit()
    }


def _news_fingerprint(title):
    tokens = sorted(_title_tokens(title))
    basis = " ".join(tokens[:8]) if tokens else (title or "").lower().strip()
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:20]


def _jaccard_similarity(tokens_a, tokens_b):
    if not tokens_a or not tokens_b:
        return 0.0
    inter = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)
    return inter / union if union else 0.0


def _fetch_single_feed(source):
    url = source["url"]
    limit = source["limit"]
    kind = source["kind"]
    category = source["category"]
    try:
        root = ET.fromstring(_http_get(url, timeout=6))
        results = []
        if kind == "atom":
            ns = {"a": "http://www.w3.org/2005/Atom"}
            for entry in root.findall("a:entry", ns):
                title = _strip_html(entry.findtext("a:title", namespaces=ns) or "")
                if not title or _is_clickbait(title):
                    continue
                summary = _truncate(_strip_html(entry.findtext("a:summary", namespaces=ns) or ""))
                pub = (
                    entry.findtext("a:published", namespaces=ns)
                    or entry.findtext("a:updated", namespaces=ns)
                    or ""
                )
                results.append({
                    "title": title,
                    "summary": summary,
                    "category": category,
                    "source": source["name"],
                    "pub_dt": _parse_pub_datetime(pub),
                })
                if len(results) >= limit:
                    break
        else:
            for item in root.findall("./channel/item"):
                title = _strip_html(item.findtext("title") or "")
                if not title or _is_clickbait(title):
                    continue
                summary = _truncate(_strip_html(item.findtext("description") or ""))
                pub = item.findtext("pubDate") or ""
                results.append({
                    "title": title,
                    "summary": summary,
                    "category": category,
                    "source": source["name"],
                    "pub_dt": _parse_pub_datetime(pub),
                })
                if len(results) >= limit:
                    break
        return results
    except Exception as e:
        print(f"⚠️ RSS alınamadı ({source['name']}): {e}")
        return []


def _score_news_item(item, now_utc, duplicate_count=1):
    """Haber maddesini Kişisel İlgi (0-50) + Önem (0-30) + Güncellik (0-20)
    olmak üzere deterministik olarak 0-100 arasında puanlar."""
    haystack = f"{item['title']} {item.get('summary', '')}".lower()
    cat = item["category"]

    # 1) Kişisel İlgi (0-50)
    avi_hits = sum(1 for kw in _AVIATION_HIGH_KEYWORDS if kw in haystack)
    ai_hits = sum(1 for kw in _AI_DEV_HIGH_KEYWORDS if kw in haystack)
    if cat == "HAVACILIK" or avi_hits >= 1:
        interest = min(50, 34 + avi_hits * 6)
    elif cat == "YAPAY ZEKA VE YAZILIM" or ai_hits >= 1:
        interest = min(48, 30 + ai_hits * 5)
    elif cat == "TÜRKİYE":
        interest = 24
    else:
        interest = 20

    # 2) Önem (0-30)
    imp_hits = sum(1 for kw in _GENERAL_IMPORTANCE_KEYWORDS if kw in haystack)
    multi_source_boost = min(14, (duplicate_count - 1) * 8)
    summary_quality = 4 if len(item.get("summary") or "") >= 50 else 0
    importance = min(30, 8 + imp_hits * 5 + multi_source_boost + summary_quality)

    # 3) Güncellik (0-20)
    pub_dt = item.get("pub_dt")
    if pub_dt is not None:
        age_hours = max(0.0, (now_utc - pub_dt).total_seconds() / 3600.0)
        if age_hours > 36:
            return -1  # 36 saatten eski haberleri ele
        if age_hours <= 6:
            recency = 20
        elif age_hours <= 14:
            recency = 15
        elif age_hours <= 24:
            recency = 10
        else:
            recency = 5
    else:
        recency = 10

    return interest + importance + recency


def select_personalized_news(raw_items, seen_fingerprints=None, length_mode="balanced", now_utc=None):
    """Ham RSS listesini tekilleştirir, daha önce okunanları (seen_news) eler,
    3 eksende puanlar ve dengeli çeşitlilikle en yüksek sinyalli başlıkları seçer."""
    now_utc = now_utc or datetime.now(timezone.utc)
    seen_fp = set(seen_fingerprints or ())

    # 1) Çapraz kaynak tekilleştirme (Jaccard >= 0.42 aynı haber sayılır)
    clusters = []
    for item in raw_items:
        tokens = _title_tokens(item["title"])
        fp = _news_fingerprint(item["title"])
        merged = False
        for cl in clusters:
            if cl["fingerprint"] == fp or _jaccard_similarity(tokens, cl["tokens"]) >= 0.42:
                cl["count"] += 1
                if len(item.get("summary") or "") > len(cl["rep"].get("summary") or ""):
                    cl["rep"] = item
                merged = True
                break
        if not merged:
            clusters.append({
                "rep": item,
                "tokens": tokens,
                "fingerprint": fp,
                "count": 1,
            })

    # 2) Daha önce gösterilenleri ve bayat haberleri ele + puanla
    scored = []
    for cl in clusters:
        if cl["fingerprint"] in seen_fp:
            continue
        score = _score_news_item(cl["rep"], now_utc, duplicate_count=cl["count"])
        if score < 0:
            continue
        scored.append({
            **cl["rep"],
            "fingerprint": cl["fingerprint"],
            "score": score,
        })

    scored.sort(key=lambda x: x["score"], reverse=True)

    target_total = 3 if length_mode == "short" else (6 if length_mode == "detailed" else 4)
    selected = []
    used_fps = set()

    # Her ana alandan (Havacılık, YZ/Yazılım, Türkiye/Dünya) en az 1 güçlü haber garanti et
    preferred_buckets = [
        ("HAVACILIK",),
        ("YAPAY ZEKA VE YAZILIM",),
        ("TÜRKİYE", "DÜNYA"),
    ]
    for allowed_cats in preferred_buckets:
        if len(selected) >= target_total:
            break
        for cand in scored:
            if cand["fingerprint"] not in used_fps and cand["category"] in allowed_cats:
                selected.append(cand)
                used_fps.add(cand["fingerprint"])
                break

    # Kalan kontenjanı en yüksek puanlı haberlerle doldur (aynı kategoriden en fazla 2)
    cat_counts = {}
    for s in selected:
        cat_counts[s["category"]] = cat_counts.get(s["category"], 0) + 1

    for cand in scored:
        if len(selected) >= target_total:
            break
        if cand["fingerprint"] in used_fps:
            continue
        cat = cand["category"]
        if cat_counts.get(cat, 0) >= 2 and length_mode != "detailed":
            continue
        selected.append(cand)
        used_fps.add(cand["fingerprint"])
        cat_counts[cat] = cat_counts.get(cat, 0) + 1

    return selected


def fetch_news_items_text(length_mode=None, record_seen=True):
    """Çoklu RSS kaynaklarını paralel çeker, kişisel puanlama ve tekrar
    engelleme (seen_news) uygulayıp LLM'e yalnız seçilmiş öz haberleri verir."""
    mode = length_mode or persona_settings.get_briefing_length_mode()

    raw_items = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(_fetch_single_feed, src) for src in FEED_SOURCES]
        for fut in concurrent.futures.as_completed(futures):
            try:
                raw_items.extend(fut.result())
            except Exception:
                continue

    try:
        seen_fps = note_database.get_seen_news_fingerprints(days=7)
    except Exception:
        seen_fps = set()

    selected = select_personalized_news(raw_items, seen_fingerprints=seen_fps, length_mode=mode)
    # Tüm haberler daha önce görüldüyse boş kalmamak için seen filtresiz en iyi 3 habere düş
    if not selected and raw_items:
        selected = select_personalized_news(raw_items, seen_fingerprints=set(), length_mode=mode)

    if not selected:
        return "(Haber akışı alınamadı.)"

    if record_seen:
        try:
            note_database.mark_news_seen(selected)
        except Exception as e:
            print(f"⚠️ seen_news güncellenemedi: {e}")

    lines = []
    for item in selected:
        line = f"[{item['category']}] {item['title']}"
        if item.get("summary"):
            line += f" — {item['summary']}"
        lines.append(line)
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Piyasa Verisi + Günlük Yüzde Değişim (Koşullu Piyasa Filtresi için)
# --------------------------------------------------------------------------- #

def _yahoo_price_and_pct(url):
    data = _http_get_json(url, timeout=8)
    meta = data["chart"]["result"][0]["meta"]
    price = meta.get("regularMarketPrice")
    pct = meta.get("regularMarketChangePercent")
    if pct is None:
        prev = meta.get("chartPreviousClose") or meta.get("previousClose")
        if price and prev:
            pct = ((price - prev) / prev) * 100.0
    return price, (round(float(pct), 2) if pct is not None else 0.0)


def fetch_finance():
    """TCMB + Yahoo Finance (Dolar değişim %, BIST 100, Ons Altın) + CoinGecko
    (Bitcoin 24s % değişim) verilerini çeker."""
    result = {}
    usd_try = None
    usd_pct = 0.0

    try:
        root = ET.fromstring(_http_get(TCMB_RATES_URL))
        usd_el = root.find("./Currency[@Kod='USD']")
        usd_try = float(usd_el.findtext("ForexSelling"))
        result["usd_try_satis"] = round(usd_try, 4)
    except Exception as e:
        print(f"⚠️ TCMB dolar kuru alınamadı: {e}")

    try:
        y_usd_price, usd_pct = _yahoo_price_and_pct(USDTRY_YAHOO_URL)
        result["usd_try_gunluk_yuzde_degisim"] = usd_pct
        if usd_try is None and y_usd_price:
            usd_try = float(y_usd_price)
            result["usd_try_satis"] = round(usd_try, 4)
    except Exception as e:
        print(f"⚠️ USD/TRY değişim yüzdesi alınamadı: {e}")

    try:
        bist_price, bist_pct = _yahoo_price_and_pct(BIST100_URL)
        if bist_price is not None:
            result["bist100"] = round(bist_price, 2)
            result["bist100_gunluk_yuzde_degisim"] = bist_pct
    except Exception as e:
        print(f"⚠️ BIST100 verisi alınamadı: {e}")

    try:
        gold_usd_oz, gold_usd_pct = _yahoo_price_and_pct(GOLD_FUTURES_URL)
        if gold_usd_oz and usd_try:
            result["gram_altin_try"] = round((gold_usd_oz * usd_try) / GRAMS_PER_OUNCE, 2)
            result["gram_altin_gunluk_yuzde_degisim"] = round(gold_usd_pct + usd_pct, 2)
    except Exception as e:
        print(f"⚠️ Altın verisi alınamadı: {e}")

    try:
        data = _http_get_json(BTC_PRICE_URL)
        btc = data.get("bitcoin") or {}
        if "try" in btc:
            result["btc_try"] = btc["try"]
        if "usd" in btc:
            result["btc_usd"] = btc["usd"]
        btc_pct = btc.get("try_24h_change")
        if btc_pct is None:
            btc_pct = btc.get("usd_24h_change")
        if btc_pct is not None:
            result["btc_gunluk_yuzde_degisim"] = round(float(btc_pct), 2)
    except Exception as e:
        print(f"⚠️ BTC verisi alınamadı: {e}")

    return result
