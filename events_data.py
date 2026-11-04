# events_data.py
#
# Günlük Brifing'in "Önemli Etkinlikler" bölümü için ham veri kaynaklarını
# çeken saf Python fonksiyonları — briefing_data.py ile aynı prensip (PyQt
# bağımsız, urllib.request — repo'da requests paketi yok, mevcut HTTP
# deseniyle tutarlı kalınır). Amaç: internetten otomatik çekilen etkinlikleri
# (film, maç, fuar, fırlatma, indirim günü, astronomi) ÖNCELİK PUANIYLA
# etiketleyip SADECE eşiği geçenleri brifinge taşımak — kullanıcıyı önemsiz
# bilgiyle bombardıman etmemek için (bkz. telegram_settings.
# get_briefing_events_min_priority). Her kaynak kendi try/except'i içinde
# çalışır (fetch_finance() deseniyle aynı, bkz. briefing_data.py:198-238) —
# biri başarısız olursa diğerleri ve brifingin geri kalanı etkilenmez.
#
# Skorlama tamamen DETERMİNİSTİK (LLM'e hiç gitmez) — hava/piyasa/kişisel
# hatırlatma paragraflarının LLM'den önce koda yazılmasıyla aynı mantık
# (bkz. briefing_text.py build_weather_finance_paragraph).
#
# Bu dosyanın JS portu: cloudflare-worker/src/events.js — aynı kaynak
# URL'leri, aynı öncelik kuralları, aynı astronomik formül, iki tarafın
# brifingi (yerel sesli + bulut/Telegram metin) tutarlı kalsın diye.

import json
import math
import re
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta

TMDB_DISCOVER_URL = "https://api.themoviedb.org/3/discover/movie"
FOOTBALL_API_BASE = "https://v3.football.api-sports.io"
SPACE_LAUNCHES_URL = "https://ll.thespacedevs.com/2.2.0/launch/upcoming/?limit=20"
TUYAP_FAIR_URL = "https://tuyap.com.tr/fuarlar/uluslararasi-istanbul-kitap-fuari"

# API-Football takım ID'leri — Süper Lig "büyük 4" (derbi/Avrupa kupası
# tespiti için) ve Şampiyonlar Ligi'nde oynayan kürate edilmiş güçlü yabancı
# kulüpler (sadece bunların grup aşaması maçları da Medium önemli sayılır;
# aksi halde her ŞL maçını çekmek gürültü olurdu).
TURKISH_BIG_TEAMS = {
    611: "Galatasaray",
    610: "Fenerbahçe",
    549: "Beşiktaş",
    607: "Trabzonspor",
}
STRONG_FOREIGN_TEAMS = {
    541: "Real Madrid",
    529: "Barcelona",
    157: "Bayern Münih",
    50: "Manchester City",
    40: "Liverpool",
    85: "Paris Saint-Germain",
    496: "Juventus",
    505: "Inter",
    33: "Manchester United",
    49: "Chelsea",
    42: "Arsenal",
    165: "Borussia Dortmund",
    489: "AC Milan",
}
# API-Football lig ID'leri: 203 Süper Lig, 2 Şampiyonlar Ligi, 3 Avrupa Ligi,
# 848 Konferans Ligi.
EUROPEAN_CUP_LEAGUE_IDS = {2, 3, 848}

# Her yıl aynı takvim günü ± 1 gün tekrar eden meteor yağmurları (ay, gün).
METEOR_SHOWERS = [
    ("Quadrantids", 1, 4),
    ("Lyrids", 4, 22),
    ("Eta Aquariids", 5, 6),
    ("Perseids", 8, 12),
    ("Orionids", 10, 21),
    ("Leonids", 11, 17),
    ("Geminids", 12, 14),
]

# NASA'nın yıllarca önce yayınladığı tutulma tarihleri — statik tablo, canlı
# bir API yok (bkz. plan). Zamanı gelince (ör. her yıl başı) genişletilmeli.
KNOWN_ECLIPSES = [
    ("2026-02-17", "Güneş tutulması (halkasal)"),
    ("2026-08-12", "Güneş tutulması (tam)"),
    ("2026-03-03", "Ay tutulması (tam)"),
    ("2026-08-28", "Ay tutulması (parçalı)"),
    ("2027-02-06", "Güneş tutulması (halkasal)"),
    ("2027-08-02", "Güneş tutulması (tam)"),
]


def _today(today=None):
    return today or date.today()


def _http_get_json(url, headers=None):
    # thespacedevs.com gibi bazı servisler User-Agent'sız istekleri (urllib'in
    # varsayılan "Python-urllib/3.x" imzasını) 403 ile reddediyor.
    merged_headers = {"User-Agent": "Mozilla/5.0"}
    merged_headers.update(headers or {})
    req = urllib.request.Request(url, headers=merged_headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_get_text(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.read().decode("utf-8", errors="replace")


# --------------------------------------------------------------------------- #
# Bilim kurgu filmleri (TMDb)
# --------------------------------------------------------------------------- #

def fetch_scifi_movies(api_key, today=None, within_days=60):
    if not api_key:
        return []
    bugun = _today(today)
    bitis = bugun + timedelta(days=within_days)
    url = (
        f"{TMDB_DISCOVER_URL}?api_key={api_key}&with_genres=878"
        f"&sort_by=popularity.desc&primary_release_date.gte={bugun.isoformat()}"
        f"&primary_release_date.lte={bitis.isoformat()}&language=tr-TR"
    )
    try:
        data = _http_get_json(url)
    except Exception:
        return []

    events = []
    for movie in data.get("results", []):
        release = movie.get("release_date")
        popularity = movie.get("popularity") or 0
        title = movie.get("title")
        if not release or not title:
            continue
        if popularity >= 40:
            priority = "high"
        elif popularity >= 15:
            priority = "medium"
        else:
            continue
        events.append({"title": f"\"{title}\" filmi vizyona giriyor", "date": release, "priority": priority})
    return events


# --------------------------------------------------------------------------- #
# Futbol (derbi / Türk takımı Avrupa kupası / güçlü yabancı takım ŞL)
# --------------------------------------------------------------------------- #

def _football_headers(api_key):
    return {"x-apisports-key": api_key}


def fetch_football_events(api_key, today=None, within_days=14):
    if not api_key:
        return []
    bugun = _today(today)
    bitis = bugun + timedelta(days=within_days)
    events = []

    for team_id, team_name in TURKISH_BIG_TEAMS.items():
        fixtures = _fetch_team_fixtures(api_key, team_id, bugun, bitis)
        for fx in fixtures:
            home_id = fx["teams"]["home"]["id"]
            away_id = fx["teams"]["away"]["id"]
            home_name = fx["teams"]["home"]["name"]
            away_name = fx["teams"]["away"]["name"]
            match_date = fx["fixture"]["date"][:10]
            league_id = fx["league"]["id"]

            is_derby = home_id in TURKISH_BIG_TEAMS and away_id in TURKISH_BIG_TEAMS
            is_euro_cup = league_id in EUROPEAN_CUP_LEAGUE_IDS
            if is_derby:
                title = f"{home_name} - {away_name} derbisi"
                events.append({"title": title, "date": match_date, "priority": "high"})
            elif is_euro_cup:
                title = f"{team_name}, {fx['league']['name']}'de {away_name if home_id == team_id else home_name} ile oynuyor"
                events.append({"title": title, "date": match_date, "priority": "high"})

    for team_id, team_name in STRONG_FOREIGN_TEAMS.items():
        fixtures = _fetch_team_fixtures(api_key, team_id, bugun, bitis)
        for fx in fixtures:
            if fx["league"]["id"] != 2:  # sadece Şampiyonlar Ligi
                continue
            opponent = fx["teams"]["away"]["name"] if fx["teams"]["home"]["id"] == team_id else fx["teams"]["home"]["name"]
            match_date = fx["fixture"]["date"][:10]
            events.append({
                "title": f"{team_name}, Şampiyonlar Ligi'nde {opponent} ile oynuyor",
                "date": match_date,
                "priority": "medium",
            })

    # Aynı maç hem derbi hem de iki büyük takımın fikstür taramasında ayrı
    # ayrı görünebilir — başlık+tarih ikilisine göre tekilleştir.
    seen = set()
    unique = []
    for e in events:
        key = (e["title"], e["date"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(e)
    return unique


def _fetch_team_fixtures(api_key, team_id, start, end):
    url = f"{FOOTBALL_API_BASE}/fixtures?team={team_id}&from={start.isoformat()}&to={end.isoformat()}"
    try:
        data = _http_get_json(url, headers=_football_headers(api_key))
        return data.get("response", [])
    except Exception:
        return []


# --------------------------------------------------------------------------- #
# SpaceX / NASA fırlatmaları — rutin Falcon 9/Starlink fırlatmaları
# bilerek elenir, aksi halde günlük gürültü olur.
# --------------------------------------------------------------------------- #

_NOTABLE_LAUNCH_KEYWORDS = ["starship", "artemis", "crew-", "crew dragon"]


def fetch_space_launches(today=None, within_days=14):
    bugun = _today(today)
    bitis = bugun + timedelta(days=within_days)
    try:
        data = _http_get_json(SPACE_LAUNCHES_URL)
    except Exception:
        return []

    events = []
    for launch in data.get("results", []):
        name = (launch.get("name") or "").strip()
        net = launch.get("net")
        if not name or not net:
            continue
        try:
            launch_date = datetime.fromisoformat(net.replace("Z", "+00:00")).date()
        except ValueError:
            continue
        if not (bugun <= launch_date <= bitis):
            continue
        if not any(kw in name.lower() for kw in _NOTABLE_LAUNCH_KEYWORDS):
            continue
        events.append({"title": f"{name} fırlatması", "date": launch_date.isoformat(), "priority": "medium"})
    return events


# --------------------------------------------------------------------------- #
# Tüyap İstanbul Kitap Fuarı — resmi API yok, sayfadaki "TAKVİME EKLE"
# bloğundaki makine-okunur tarih (statik HTML, JS-render değil) çekilir.
# --------------------------------------------------------------------------- #

_TUYAP_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2}) \d{2}:\d{2}:\d{2}")


def fetch_tuyap_fair(today=None, within_days=60):
    bugun = _today(today)
    try:
        html = _http_get_text(TUYAP_FAIR_URL)
    except Exception:
        return []

    match = _TUYAP_DATE_RE.search(html)
    if not match:
        return []
    try:
        start_date = datetime.strptime(match.group(1), "%Y-%m-%d").date()
    except ValueError:
        return []
    if not (bugun <= start_date <= bugun + timedelta(days=within_days)):
        return []
    return [{"title": "İstanbul Kitap Fuarı (Tüyap) başlıyor", "date": start_date.isoformat(), "priority": "high"}]


# --------------------------------------------------------------------------- #
# Black Friday / Siber Pazartesi / Kara Cuma — tarih KURALIYLA hesaplanır,
# scraping'den daha güvenilir ve hep otomatik (bakım gerektirmez).
# --------------------------------------------------------------------------- #

def compute_flash_sale_dates(today=None):
    bugun = _today(today)
    year = bugun.year
    events = []
    for y in (year, year + 1):
        black_friday = _nth_weekday_of_november(y, weekday=3, n=4) + timedelta(days=1)  # 4. Perşembe + 1 gün
        cyber_monday = black_friday + timedelta(days=3)
        events.append({"title": "Black Friday / Kara Cuma indirimleri", "date": black_friday.isoformat(), "priority": "high"})
        events.append({"title": "Siber Pazartesi (Cyber Monday) indirimleri", "date": cyber_monday.isoformat(), "priority": "high"})
    return events


def _nth_weekday_of_november(year, weekday, n):
    """weekday: Pazartesi=0 ... Pazar=6. Kasım ayının n'inci `weekday` günü."""
    d = date(year, 11, 1)
    count = 0
    while True:
        if d.weekday() == weekday:
            count += 1
            if count == n:
                return d
        d += timedelta(days=1)


# --------------------------------------------------------------------------- #
# Meteor yağmurları — sabit yıllık takvim.
# --------------------------------------------------------------------------- #

def compute_meteor_showers(today=None):
    bugun = _today(today)
    events = []
    for name, month, day in METEOR_SHOWERS:
        for y in (bugun.year, bugun.year + 1):
            try:
                peak = date(y, month, day)
            except ValueError:
                continue
            events.append({"title": f"{name} meteor yağmuru zirvesi", "date": peak.isoformat(), "priority": "medium"})
    return events


# --------------------------------------------------------------------------- #
# Ay/Güneş tutulması (statik NASA tablosu) + süper ay (astronomik hesap).
# --------------------------------------------------------------------------- #

def compute_astro_events(today=None):
    events = list(KNOWN_ECLIPSES)
    events = [{"title": desc, "date": d, "priority": "high"} for d, desc in events]
    events.extend(_compute_supermoons(today))
    return events


def _julian_day(dt):
    # Meeus düşük-hassasiyet Julian gün formülü (UTC gece yarısı referanslı).
    y, m = dt.year, dt.month
    d = dt.day + (dt.hour + dt.minute / 60.0) / 24.0
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    return int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + d + b - 1524.5


def _moon_phase_and_distance(dt):
    """Jean Meeus'un düşük-hassasiyet ay formülleri — dolunay evresi (0..1,
    0.5=dolunay) ve Dünya-Ay mesafesini (km) döner. Tam ephemeris hassasiyeti
    gerekmiyor, sadece "dolunay mı ve perigeeye yakın mı" (süper ay) sorusunu
    cevaplamaya yetecek kabalıkta."""
    jd = _julian_day(dt)
    days_since_new = jd - 2451550.1  # 2000-01-06 dolunay referansı
    new_moons = days_since_new / 29.530588853
    phase = new_moons - math.floor(new_moons)  # 0=yeni ay, 0.5=dolunay

    # Ay'ın yörünge anomalisine bağlı kaba mesafe tahmini (ortalama 385000 km,
    # dışmerkezlikten ötürü ±21000 km salınım) — süper ay tespiti için yeterli.
    anomaly_days = jd - 2451534.7  # bir perigee referans tarihi
    anomaly_cycles = anomaly_days / 27.554550
    anomaly_phase = (anomaly_cycles - math.floor(anomaly_cycles)) * 2 * math.pi
    distance_km = 385000 - 21000 * math.cos(anomaly_phase)
    return phase, distance_km


def _compute_supermoons(today=None, within_days=60):
    bugun = _today(today)
    events = []
    for offset in range(within_days):
        day = bugun + timedelta(days=offset)
        phase, distance_km = _moon_phase_and_distance(datetime(day.year, day.month, day.day, 12))
        is_full_moon = abs(phase - 0.5) < (1 / 29.530588853)  # o gün dolunaya denk geliyor
        is_super = distance_km < 361000  # NASA'nın yaygın süper ay eşiği
        if is_full_moon and is_super:
            events.append({"title": "Süper ay (dolunay, Dünya'ya en yakın konumunda)", "date": day.isoformat(), "priority": "medium"})
    return events


# --------------------------------------------------------------------------- #
# Toplayıcı
# --------------------------------------------------------------------------- #

def get_prioritized_events(min_priority="high", within_days=14, today=None, tmdb_api_key=None, football_api_key=None):
    """Tüm kaynakları toplar, `within_days` penceresine ve `min_priority`
    eşiğine göre filtreler, tarihe göre sıralı döner. Her kaynak kendi
    try/except'i içinde çalıştığı için bir kaynağın hatası diğerlerini ya da
    bu fonksiyonun kendisini asla düşürmez."""
    bugun = _today(today)
    bitis = bugun + timedelta(days=within_days)

    all_events = []
    for fetcher, args in (
        (fetch_scifi_movies, (tmdb_api_key, bugun, within_days)),
        (fetch_football_events, (football_api_key, bugun, within_days)),
        (fetch_space_launches, (bugun, within_days)),
        (fetch_tuyap_fair, (bugun, within_days)),
        (compute_flash_sale_dates, (bugun,)),
        (compute_meteor_showers, (bugun,)),
        (compute_astro_events, (bugun,)),
    ):
        try:
            all_events.extend(fetcher(*args))
        except Exception:
            continue

    priority_rank = {"high": 2, "medium": 1, "low": 0}
    min_rank = priority_rank.get(min_priority, 2)

    filtered = []
    for e in all_events:
        try:
            event_date = datetime.strptime(e["date"], "%Y-%m-%d").date()
        except (ValueError, KeyError):
            continue
        if not (bugun <= event_date <= bitis):
            continue
        if priority_rank.get(e.get("priority"), 0) < min_rank:
            continue
        filtered.append({**e, "_date": event_date})

    filtered.sort(key=lambda e: e["_date"])
    for e in filtered:
        del e["_date"]
    return filtered
