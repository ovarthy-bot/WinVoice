# personal_context.py
#
# HAKKIMDA Obsidian kasasındaki TEK bir dosyayı (aşağıdaki REMINDERS_FILE)
# okuyup doğum günü/randevu/ödeme hatırlatmalarını hesaplar. Kasadaki başka
# hiçbir dosya (ör. Şifrelerim.md) taranmaz — dizin genel taraması YAPILMAZ,
# sadece bu sabit dosya yolu açılır.
#
# Tarih/sayı hesaplaması tamamen burada, Python'da yapılır; gemma3:4b'ye asla
# "bugünün tarihi X, buna göre kaç gün kaldı hesapla" gibi bir iş bırakılmaz
# (main.py/dashboard_ui.py'deki hava & piyasa brifinginde de aynı prensip
# uygulanıyor: küçük yerel model sayı/tarih işlemlerinde güvenilmiyor).

import calendar
import os
import re
from datetime import date

REMINDERS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "HAKKIMDA", "50_Rutinler", "Doğum Günleri ve Randevular.md",
)

TR_AYLAR = [
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
]

_ROW_RE = re.compile(r"^\|(.+)\|\s*$")
_DATE_FULL_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$")
_DATE_ANNUAL_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})$")
_DAY_ONLY_RE = re.compile(r"^(\d{1,2})$")

_CALENDAR_KEYWORDS = [
    "takvim", "doğum günü", "doğum gününü", "doğum günleri",
    "randevu", "randevum", "randevularım",
    "ödeme tarihi", "son ödeme", "kredi kartı", "fatura",
    # "öde" kökü ödeme/ödemem/ödeyecek/ödenecek gibi tüm çekimleri alt
    # string olarak yakalar (bkz. "unutma" için aşağıdaki not).
    "öde", "taksit", "aidat",
    "hatırlatma", "hatırlatıcı",
    # Doğal, dolaylı ifadeler ("bu ay unutmamam gereken bir şey var mı?"
    # gibi) — "unutma" kökü unutmamam/unutmayacağım/unutmuşum gibi tüm
    # çekimleri alt string olarak yakalar.
    "unutma", "bu ay", "gelecek ay", "önümüzdeki ay", "bu hafta", "aklımda olması",
]


def _parse_table_rows(markdown_text):
    """Markdown tablo satırlarını ('| a | b | c |') hücre listelerine çevirir.
    Başlık ve ayraç ('---') satırlarıyla örnek satırlar atlanır."""
    rows = []
    for line in markdown_text.splitlines():
        line = line.strip()
        match = _ROW_RE.match(line)
        if not match:
            continue
        cells = [c.strip() for c in match.group(1).split("|")]
        if len(cells) < 3:
            continue
        first = cells[0]
        if first in ("Tür", "") or set(first) <= {"-", ":"}:
            continue
        if len(cells) > 1 and "Örnek" in cells[1]:
            continue
        rows.append(cells)
    return rows


def _load_entries():
    if not os.path.exists(REMINDERS_FILE):
        return []
    try:
        with open(REMINDERS_FILE, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return []

    entries = []
    for cells in _parse_table_rows(text):
        cells = cells + [""] * (5 - len(cells))
        tur, kim, tarih, tekrar, not_ = (c.strip() for c in cells[:5])
        if not tarih:
            continue
        entries.append({
            "tur": tur,
            "kim": kim,
            "tarih_raw": tarih,
            "tekrar": tekrar.lower(),
            "not": not_,
        })
    return entries


def _next_annual(gun, ay, bugun):
    try:
        aday = date(bugun.year, ay, gun)
    except ValueError:
        return None
    if aday < bugun:
        try:
            aday = date(bugun.year + 1, ay, gun)
        except ValueError:
            return None
    return aday


def _next_monthly(gun, bugun):
    yil, ay = bugun.year, bugun.month
    son_gun = calendar.monthrange(yil, ay)[1]
    aday = date(yil, ay, min(gun, son_gun))
    if aday < bugun:
        ay += 1
        if ay > 12:
            ay, yil = 1, yil + 1
        son_gun = calendar.monthrange(yil, ay)[1]
        aday = date(yil, ay, min(gun, son_gun))
    return aday


def _resolve_date(entry, bugun):
    """Bir kaydın 'Tarih'/'Tekrar' hücrelerinden bir sonraki gerçekleşme
    tarihini hesaplar. Biçim tanınmazsa None döner (kayıt sessizce atlanır)."""
    tarih_raw, tekrar = entry["tarih_raw"], entry["tekrar"]

    if tekrar == "aylık":
        m = _DAY_ONLY_RE.match(tarih_raw)
        return _next_monthly(int(m.group(1)), bugun) if m else None

    if tekrar == "yıllık":
        m = _DATE_ANNUAL_RE.match(tarih_raw) or _DATE_FULL_RE.match(tarih_raw)
        return _next_annual(int(m.group(1)), int(m.group(2)), bugun) if m else None

    # Tekrar belirtilmemiş: GG.AA -> yıllık gibi davran, GG.AA.YYYY -> tek seferlik
    m = _DATE_FULL_RE.match(tarih_raw)
    if m:
        gun, ay, yil = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            aday = date(yil, ay, gun)
        except ValueError:
            return None
        return aday if aday >= bugun else None

    m = _DATE_ANNUAL_RE.match(tarih_raw)
    if m:
        return _next_annual(int(m.group(1)), int(m.group(2)), bugun)

    return None


def get_upcoming(within_days=30, today=None):
    """Bugünden itibaren `within_days` gün içindeki kayıtları, en yakından
    en uzağa sıralı döner. Her kayıda hesaplanan 'tarih' (date) ve
    'kalan_gun' (int) eklenir."""
    bugun = today or date.today()
    sonuc = []
    for entry in _load_entries():
        hedef = _resolve_date(entry, bugun)
        if hedef is None:
            continue
        kalan_gun = (hedef - bugun).days
        if 0 <= kalan_gun <= within_days:
            sonuc.append({**entry, "tarih": hedef, "kalan_gun": kalan_gun})
    sonuc.sort(key=lambda e: e["kalan_gun"])
    return sonuc


def get_in_month(month_offset=0, today=None):
    """month_offset=0 -> bu ay, 1 -> gelecek ay. Belirtilen takvim ayının
    (bugünden ay sonuna kadarki kısmının) içine düşen kayıtları, tarihe göre
    sıralı döner. get_upcoming'in "bugünden itibaren kaç gün" mantığından
    farklı olarak burada "hangi takvim ayı" sorusu doğrudan cevaplanır —
    ayın son günlerinde sorulduğunda "bu ay" sahte biçimde boş çıkmaz."""
    bugun = today or date.today()
    yil, ay = bugun.year, bugun.month
    ay += month_offset
    while ay > 12:
        ay -= 12
        yil += 1
    ay_baslangic = date(yil, ay, 1)
    ay_bitis = date(yil, ay, calendar.monthrange(yil, ay)[1])
    if ay_bitis < bugun:
        return []

    sonuc = []
    for entry in _load_entries():
        hedef = _resolve_date(entry, bugun)
        if hedef is None or hedef < bugun or hedef > ay_bitis:
            continue
        if hedef < ay_baslangic:
            continue
        sonuc.append({**entry, "tarih": hedef, "kalan_gun": (hedef - bugun).days})
    sonuc.sort(key=lambda e: e["tarih"])
    return sonuc


def _tarih_ifadesi(kalan_gun, tarih):
    if kalan_gun == 0:
        return "bugün"
    if kalan_gun == 1:
        return "yarın"
    return f"{kalan_gun} gün sonra ({tarih.day} {TR_AYLAR[tarih.month - 1]})"


def _cumle(entry):
    ifade = _tarih_ifadesi(entry["kalan_gun"], entry["tarih"])
    tur = entry["tur"].lower()
    kim = entry["kim"] or "Bir kayıt"
    not_ = entry["not"]

    if "doğum" in tur:
        return f"{kim}'in doğum günü {ifade}."
    if "ödeme" in tur or "fatura" in tur or "kredi" in tur:
        ek = f" ({not_})" if not_ else ""
        return f"{kim} son ödeme tarihi {ifade}{ek}."
    if "randevu" in tur:
        ek = f" ({not_})" if not_ else ""
        return f"{kim} randevunuz {ifade}{ek}."
    ek = f" — {not_}" if not_ else ""
    return f"{kim}: {ifade}{ek}."


def build_reminder_block(within_days=14, today=None):
    """Günlük brifing gibi deterministik metin akışlarına eklenecek, hazır
    Türkçe cümlelerden oluşan tek bir blok döner. Kayıt yoksa boş string."""
    olaylar = get_upcoming(within_days=within_days, today=today)
    if not olaylar:
        return ""
    return " ".join(_cumle(e) for e in olaylar)


def answer_calendar_query(user_text_lower):
    """Kullanıcının yazılı/sesli girdisinde takvim/hatırlatma anahtar
    kelimesi varsa deterministik, hazır bir Türkçe cevap döner (LLM'e hiç
    gidilmez). Eşleşme yoksa None döner — çağıran taraf normal LLM akışına
    (SOHBET/KOMUT) devam etmeli."""
    if not any(kw in user_text_lower for kw in _CALENDAR_KEYWORDS):
        return None

    if "gelecek ay" in user_text_lower or "önümüzdeki ay" in user_text_lower:
        olaylar = get_in_month(month_offset=1)
        if not olaylar:
            return "Gelecek ay takviminizde kayıtlı bir hatırlatma görünmüyor."
        return "Gelecek ay takviminizde şunlar var: " + " ".join(_cumle(e) for e in olaylar)

    if "bu ay" in user_text_lower:
        olaylar = get_in_month(month_offset=0)
        if not olaylar:
            return "Bu ay takviminizde kayıtlı bir hatırlatma görünmüyor."
        return "Bu ay takviminizde şunlar var: " + " ".join(_cumle(e) for e in olaylar)

    within_days = 7 if "bu hafta" in user_text_lower else 30
    olaylar = get_upcoming(within_days=within_days)
    if not olaylar:
        return "Yaklaşan günlerde takviminizde kayıtlı bir hatırlatma görünmüyor."
    return "Takviminizde şunlar var: " + " ".join(_cumle(e) for e in olaylar)
