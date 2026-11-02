# personal_context.py
#
# Doğum günü, randevu ve ödeme hatırlatmalarını hem HAKKIMDA kasasındaki
# yapılandırılmış tablodan (REMINDERS_VAULT_PATH — vault_cache.py üzerinden)
# hem de yerel SQLite veritabanındaki (notes.db — note_database.py üzerinden)
# randevu/hatırlatma kayıtlarından birleşik ve tekilleştirilmiş olarak hesaplar.
# Kasadaki başka hiçbir not (ör. Şifrelerim.md) burada hiç taranmaz.
#
# Tarih/sayı hesaplaması tamamen burada, Python'da yapılır; gemma3:4b'ye asla
# "bugünün tarihi X, buna göre kaç gün kaldı hesapla" gibi bir iş bırakılmaz
# (main.py/dashboard_ui.py'deki hava & piyasa brifinginde de aynı prensip
# uygulanıyor: küçük yerel model sayı/tarih işlemlerinde güvenilmiyor).

import calendar
import re
from datetime import date, timedelta

import note_database
import vault_cache
from vault_knowledge import _ELAPSED_DAYS_KEYWORDS, _meaningful_terms, _stem, tr_lower

# vault_cache.get_note_by_path'e geçirilen anahtar; migrate_hakkimda_to_cloud.py'nin
# bu notu D1'e taşırken kullandığı AYNI göreli yol (forward-slash, HAKKIMDA'ya
# göre) — bkz. o script ve cloudflare-worker/src/briefing.js'teki aynı sabit.
REMINDERS_VAULT_PATH = "50_Rutinler/Doğum Günleri ve Randevular.md"

TR_AYLAR = [
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
]

_ROW_RE = re.compile(r"^\|(.+)\|\s*$")
_DATE_FULL_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$")
_DATE_ISO_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
_DATE_ANNUAL_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})$")
_DAY_ONLY_RE = re.compile(r"^(\d{1,2})$")

_CALENDAR_KEYWORDS = [
    "takvim", "doğum günü", "doğum gününü", "doğum günleri",
    "randevu", "randevum", "randevularım",
    "ödeme tarihi", "son ödeme", "kredi kartı", "fatura",
    # "öde" kökü ödeme/ödemem/ödeyecek/ödenecek gibi tüm çekimleri alt
    # string olarak yakalar (bkz. "unutma" için aşağıdaki not).
    "öde", "taksit", "aidat",
    # "hatırla" kökü hatırlatma/hatırlatıcı/hatırlatır mısın/hatırlamam
    # gereken gibi tüm çekimleri alt string olarak yakalar (ör. "Pazartesi
    # hatırlamam gereken bir şey var mı?").
    "hatırla",
    # Doğal, dolaylı ifadeler ("bu ay unutmamam gereken bir şey var mı?"
    # gibi) — "unutma" kökü unutmamam/unutmayacağım/unutmuşum gibi tüm
    # çekimleri alt string olarak yakalar.
    "unutma", "bu ay", "gelecek ay", "önümüzdeki ay", "bu hafta", "aklımda olması",
]

# Haftanın günü adıyla sorulan sorguları ("Pazartesi hatırlatmam var mı?")
# somut bir tarihe çevirmek için (bkz. _resolve_mentioned_date). date.weekday()
# ile aynı sırada: Pazartesi=0 ... Pazar=6.
_WEEKDAY_NAME_TO_INDEX = {
    "pazartesi": 0, "salı": 1, "çarşamba": 2, "perşembe": 3,
    "cuma": 4, "cumartesi": 5, "pazar": 6,
}

_EXPLICIT_DATE_IN_TEXT_RE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")

# Alt string çakışmasına karşı (ör. "cumartesi" içinde "cuma", "pazartesi"
# içinde "pazar" geçiyor) her gün adı \b kelime sınırlarıyla eşleştirilir;
# aksi halde "cumartesi hatırlatıcım var mı?" yanlışlıkla Cuma'ya eşleşirdi.
_WEEKDAY_NAME_RE = {
    isim: re.compile(r"\b" + isim + r"\b")
    for isim in _WEEKDAY_NAME_TO_INDEX
}

# Sorguda "Emin Akbulut", "Tüyap", "Laptop", "Şampuanlık" gibi ÖZEL bir konu
# adı geçip geçmediğini ayırt etmek için genel takvim/zaman/soru kelimelerinin
# kök kümesi. Bunun dışında kalan anlamlı terimler özel konu kabul edilir.
_CALENDAR_GENERIC_WORDS = {
    "takvim", "takvimim", "takvimimde", "hatırla", "hatırlat", "hatırlatma",
    "hatırlatıcı", "hatırlatmalar", "hatırlatmalarım", "hatırlamam",
    "unutma", "unutmamam", "aklımda", "olması", "gereken", "gerek",
    "doğum", "gün", "günü", "günleri", "randevu", "randevum", "randevular",
    "randevularım", "ödeme", "ödemeler", "ödemelerim", "öde", "son", "tarih",
    "tarihi", "kredi", "kart", "kartı", "fatura", "faturalar", "taksit",
    "taksitler", "taksitlerim", "aidat", "yaklaşan", "yakın", "gelecek",
    "önümüzdeki", "hafta", "ay", "yıl", "sene", "günlerde", "dönemde",
    "kayıt", "kayıtlı", "liste", "listem", "listemde", "bekleyen", "aktif",
    "yapılacak", "yapılacaklar", "tamamlanmamış", "iş", "işler", "işlerim",
    "şey", "şeyler", "kaldı", "zaman", "zamandı",
    *(tr_lower(m) for m in TR_AYLAR),
    *_WEEKDAY_NAME_TO_INDEX.keys(),
}
_CALENDAR_GENERIC_STEMS = {_stem(w) for w in _CALENDAR_GENERIC_WORDS} | _CALENDAR_GENERIC_WORDS


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


def _load_vault_entries():
    note = vault_cache.get_note_by_path(REMINDERS_VAULT_PATH)
    if not note:
        return []
    text = note["content"]

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
            "tekrar": tr_lower(tekrar),
            "not": not_,
        })
    return entries


def _db_note_to_calendar_entry(n):
    """notes.db'deki tarihli bir appointment veya reminder satırını
    personal_context tablosuyla aynı sözlük yapısına çevirir. Tarihi olmayan
    ('yok' / None) serbest hatırlatmalar burada None döner; onlar RAG ve
    yapılacaklar listesi (db_query_resolver) katmanında yanıtlanır."""
    cat = n.get("category")
    title = (n.get("title") or "").strip()
    desc = (n.get("description") or "").strip()

    if cat == "appointment":
        tarih_raw = (n.get("appt_date") or "").strip()
        if not tarih_raw or tr_lower(tarih_raw) == "yok":
            return None
        title_low = tr_lower(title)
        if title_low.endswith(" randevusu"):
            kim = title[: -len(" randevusu")].strip()
        elif title_low.endswith(" randevu"):
            kim = title[: -len(" randevu")].strip()
        else:
            kim = title or (n.get("related_person") or "").strip() or "Randevu"

        not_parts = []
        if n.get("appt_time"):
            not_parts.append(f"Saat: {n['appt_time']}")
        if n.get("location"):
            not_parts.append(f"Konum: {n['location']}")
        if desc and tr_lower(desc) != tr_lower(title):
            not_parts.append(desc)

        return {
            "tur": "Randevu",
            "kim": kim,
            "tarih_raw": tarih_raw,
            "tekrar": "",
            "not": ", ".join(not_parts),
        }

    if cat == "reminder":
        tarih_raw = (n.get("remind_at") or "").strip()
        if not tarih_raw or tr_lower(tarih_raw) == "yok":
            return None
        tekrar = tr_lower(n.get("repeat_frequency") or "").strip()
        if tekrar == "yok":
            tekrar = ""

        title_low = tr_lower(title)
        desc_low = tr_lower(desc)
        if title_low.endswith(" doğum günü"):
            tur = "Doğum günü"
            kim = title[: -len(" doğum günü")].strip()
        elif "doğum günü" in title_low:
            tur = "Doğum günü"
            kim = title
        elif title_low.endswith(" ödeme hatırlatması"):
            tur = "Ödeme"
            kim = title[: -len(" ödeme hatırlatması")].strip()
        elif any(k in title_low or k in desc_low for k in ("ödeme", "fatura", "kredi", "taksit", "aidat")):
            tur = "Ödeme"
            kim = title
        else:
            tur = "Hatırlatma"
            kim = title

        return {
            "tur": tur,
            "kim": kim or "Hatırlatma",
            "tarih_raw": tarih_raw,
            "tekrar": tekrar,
            "not": desc,
        }

    return None


def _load_entries(include_db=True, today=None):
    """Hem HAKKIMDA tablosundaki hem de notes.db'deki tarihli randevu ve
    hatırlatmaları yükler. import_hakkimda_notes.py daha önce tablo satırlarını
    notes.db'ye aktardığı için (kim, çözümlenen_tarih) anahtarıyla tekilleştirme
    yapılır; ayrıca notes.db'de tamamlandı (completed=1) işaretlenmiş kayıtlar
    elenir."""
    vault_entries = _load_vault_entries()
    if not include_db:
        return vault_entries

    bugun = today or date.today()
    try:
        db_rows = note_database.get_notes(category="all", include_completed=True)
    except Exception:
        db_rows = []

    completed_keys = set()
    active_db_entries = []
    for row in db_rows:
        entry = _db_note_to_calendar_entry(row)
        if entry is None:
            continue
        hedef = _resolve_date(entry, bugun)
        key = (tr_lower(entry["kim"]).strip(), hedef)
        if row.get("completed"):
            if hedef is not None:
                completed_keys.add(key)
        else:
            active_db_entries.append((entry, key))

    merged = []
    seen_keys = set()
    for entry in vault_entries:
        hedef = _resolve_date(entry, bugun)
        key = (tr_lower(entry["kim"]).strip(), hedef)
        if hedef is not None:
            if key in completed_keys or key in seen_keys:
                continue
            seen_keys.add(key)
        merged.append(entry)

    for entry, key in active_db_entries:
        if key[1] is not None:
            if key in completed_keys or key in seen_keys:
                continue
            seen_keys.add(key)
        merged.append(entry)

    return merged


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


def _extract_ymd(tarih_raw):
    m = _DATE_ISO_RE.match(tarih_raw)
    if m:
        return int(m.group(3)), int(m.group(2)), int(m.group(1))
    m = _DATE_FULL_RE.match(tarih_raw)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    return None


def _resolve_date(entry, bugun):
    """Bir kaydın 'Tarih'/'Tekrar' hücrelerinden bir sonraki gerçekleşme
    tarihini hesaplar. Biçim tanınmazsa None döner (kayıt sessizce atlanır)."""
    tarih_raw = (entry.get("tarih_raw") or "").strip()
    tekrar = tr_lower(entry.get("tekrar") or "").strip()

    if tekrar in ("aylık", "aylik"):
        m = _DAY_ONLY_RE.match(tarih_raw)
        if m:
            return _next_monthly(int(m.group(1)), bugun)
        ymd = _extract_ymd(tarih_raw)
        if ymd:
            gun, ay, yil = ymd
            try:
                aday = date(yil, ay, gun)
            except ValueError:
                return None
            return aday if aday >= bugun else _next_monthly(gun, bugun)
        return None

    if tekrar in ("yıllık", "yillik"):
        m = _DATE_ANNUAL_RE.match(tarih_raw)
        if m:
            return _next_annual(int(m.group(1)), int(m.group(2)), bugun)
        ymd = _extract_ymd(tarih_raw)
        if ymd:
            return _next_annual(ymd[0], ymd[1], bugun)
        return None

    if tekrar in ("haftalık", "haftalik"):
        ymd = _extract_ymd(tarih_raw)
        if not ymd:
            return None
        try:
            aday = date(ymd[2], ymd[1], ymd[0])
        except ValueError:
            return None
        while aday < bugun:
            aday += timedelta(days=7)
        return aday

    if tekrar in ("günlük", "gunluk"):
        ymd = _extract_ymd(tarih_raw)
        if not ymd:
            return None
        try:
            aday = date(ymd[2], ymd[1], ymd[0])
        except ValueError:
            return None
        return aday if aday >= bugun else bugun

    # Tekrar belirtilmemiş / tek seferlik: GG.AA -> yıllık gibi davran,
    # GG.AA.YYYY veya YYYY-MM-DD -> tek seferlik
    ymd = _extract_ymd(tarih_raw)
    if ymd:
        gun, ay, yil = ymd
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
    for entry in _load_entries(today=bugun):
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
    for entry in _load_entries(today=bugun):
        hedef = _resolve_date(entry, bugun)
        if hedef is None or hedef < bugun or hedef > ay_bitis:
            continue
        if hedef < ay_baslangic:
            continue
        sonuc.append({**entry, "tarih": hedef, "kalan_gun": (hedef - bugun).days})
    sonuc.sort(key=lambda e: e["tarih"])
    return sonuc


def get_on_date(target_date, today=None):
    """get_upcoming'in "bugünden itibaren N gün" aralığından farklı olarak,
    tek bir güne (target_date) denk gelen kayıtları döner. Haftanın günü
    adıyla ('Pazartesi hatırlatmam var mı?') ya da açık bir tarihle
    ('02.11.2026 tarihinde ne var?') sorulan sorgular için kullanılır
    (bkz. _resolve_mentioned_date / answer_calendar_query)."""
    bugun = today or date.today()
    sonuc = []
    for entry in _load_entries(today=bugun):
        hedef = _resolve_date(entry, bugun)
        if hedef == target_date:
            sonuc.append({**entry, "tarih": hedef, "kalan_gun": (hedef - bugun).days})
    return sonuc


def _resolve_mentioned_date(user_text_lower, today=None):
    """Sorgu metninde açık bir tarih (GG.AA.YYYY) ya da haftanın günü adı
    (ör. 'pazartesi') geçiyorsa, buna karşılık gelen somut tarihi döner;
    geçmiyorsa None. Haftanın günü adı için: bugün zaten o günse bugünü,
    değilse bir sonraki geldiği tarihi hesaplar (asla geçmişe gitmez) —
    tıpkı _next_annual/_next_monthly'nin "bir sonraki gerçekleşme"
    mantığıyla tutarlı."""
    bugun = today or date.today()

    m = _EXPLICIT_DATE_IN_TEXT_RE.search(user_text_lower)
    if m:
        gun, ay, yil = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return date(yil, ay, gun)
        except ValueError:
            pass

    for isim, hedef_indeks in _WEEKDAY_NAME_TO_INDEX.items():
        if _WEEKDAY_NAME_RE[isim].search(user_text_lower):
            gun_farki = (hedef_indeks - bugun.weekday()) % 7
            return bugun + timedelta(days=gun_farki)

    return None


def resolve_date_hint(user_text_lower, today=None):
    """main.py'nin HAKKIMDA kasasındaki serbest metin notlarını ararken
    (bkz. vault_knowledge.answer_from_vault'un extra_search_terms'ü)
    kullanması için: sorguda geçen tarih/haftanın günü ipucunu çözüp, o
    tarihin notlarda muhtemelen yazılmış olabileceği birkaç biçimini
    (GG.AA.YYYY ve 'G Ay YYYY') döner."""
    hedef = _resolve_mentioned_date(tr_lower(user_text_lower), today=today)
    if not hedef:
        return None
    return [
        f"{hedef.day:02d}.{hedef.month:02d}.{hedef.year}",
        f"{hedef.day} {TR_AYLAR[hedef.month - 1]} {hedef.year}",
    ]


def _tarih_ifadesi(kalan_gun, tarih, bugun=None):
    if kalan_gun == 0:
        return "bugün"
    if kalan_gun == 1:
        return "yarın"
    ref_year = bugun.year if bugun else date.today().year
    if tarih.year != ref_year or kalan_gun > 180:
        return f"{kalan_gun} gün sonra ({tarih.day} {TR_AYLAR[tarih.month - 1]} {tarih.year})"
    return f"{kalan_gun} gün sonra ({tarih.day} {TR_AYLAR[tarih.month - 1]})"


def _cumle(entry, bugun=None):
    ifade = _tarih_ifadesi(entry["kalan_gun"], entry["tarih"], bugun=bugun)
    tur = tr_lower(entry["tur"])
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
    bugun = today or date.today()
    olaylar = get_upcoming(within_days=within_days, today=bugun)
    if not olaylar:
        return ""
    return " ".join(_cumle(e, bugun=bugun) for e in olaylar)


def answer_calendar_query(user_text_lower, today=None):
    """Kullanıcının yazılı/sesli girdisinde takvim/hatırlatma anahtar
    kelimesi varsa deterministik, hazır bir Türkçe cevap döner (LLM'e hiç
    gidilmez). Eşleşme yoksa None döner — çağıran taraf normal RAG / LLM
    akışına devam etmeli."""
    q = tr_lower(user_text_lower)
    if not any(kw in q for kw in _CALENDAR_KEYWORDS):
        return None

    # "... üzerinden kaç gün geçti?" türü geçmişe dönük sorguları takvim
    # listesi yakalamasın; answer_elapsed_days_from_vault yanıtlasın.
    if any(kw in q for kw in _ELAPSED_DAYS_KEYWORDS):
        return None

    bugun = today or date.today()

    if "gelecek ay" in q or "önümüzdeki ay" in q:
        olaylar = get_in_month(month_offset=1, today=bugun)
        if not olaylar:
            return "Gelecek ay takviminizde kayıtlı bir hatırlatma görünmüyor."
        return "Gelecek ay takviminizde şunlar var: " + " ".join(_cumle(e, bugun=bugun) for e in olaylar)

    if "bu ay" in q:
        olaylar = get_in_month(month_offset=0, today=bugun)
        if not olaylar:
            return "Bu ay takviminizde kayıtlı bir hatırlatma görünmüyor."
        return "Bu ay takviminizde şunlar var: " + " ".join(_cumle(e, bugun=bugun) for e in olaylar)

    hedef_tarih = _resolve_mentioned_date(q, today=bugun)
    if hedef_tarih:
        olaylar = get_on_date(hedef_tarih, today=bugun)
        if olaylar:
            gun_ifadesi = f"{hedef_tarih.day} {TR_AYLAR[hedef_tarih.month - 1]} {hedef_tarih.year}"
            return f"{gun_ifadesi} tarihinde takviminizde şunlar var: " + " ".join(_cumle(e, bugun=bugun) for e in olaylar)
        return None

    # Sorguda özel bir kişi/kurum/konu adı geçiyorsa ("Emin Akbulut'un doğum
    # günü ne zaman?", "Tüyap randevum ne zaman?", "Şampuanlık hatırlatmam
    # neydi?" gibi), genel 30 günlük listeyi dökmek yerine tüm gelecek
    # ufukta bu konuyu ara; tarihsiz bir hatırlatmaysa None dön ki RAG bulsun.
    subject_terms = _meaningful_terms(q) - _CALENDAR_GENERIC_STEMS
    if subject_terms:
        tum_olaylar = get_upcoming(within_days=3650, today=bugun)
        eslesenler = [
            e for e in tum_olaylar
            if subject_terms & (_meaningful_terms(e["kim"]) | _meaningful_terms(e["not"]))
        ]
        if eslesenler:
            return " ".join(_cumle(e, bugun=bugun) for e in eslesenler)
        return None

    # Tarihsiz hatırlatma/yapılacak notlarını soran ifadeleri ("hatırlatma
    # notlarım neler?", "bekleyen işlerim/hatırlatmalarım neler?") db_query_resolver
    # katmanına bırak ki tarihsiz görevler (örn. "Şampuanlık askısını sök") de
    # listelensin.
    if "hatırla" in q and any(k in q for k in ("not", "bekleyen", "yapılacak", "listem")):
        return None

    # Kategoriye özel genel liste sorguları ("randevularım neler?", "doğum
    # günleri neler?", "ödemelerim/taksitlerim neler?") — 30 gün sınırına
    # takılmadan ilgili türdeki tüm gelecek kayıtları döndür.
    if "bu hafta" not in q and "takvim" not in q:
        if "randevu" in q and "doğum" not in q:
            randevular = [
                e for e in get_upcoming(within_days=3650, today=bugun)
                if "randevu" in tr_lower(e["tur"])
            ]
            if not randevular:
                return "Kayıtlı yaklaşan bir randevunuz görünmüyor."
            return "Kayıtlı randevularınız şunlar: " + " ".join(_cumle(e, bugun=bugun) for e in randevular)

        if "doğum" in q:
            dogum_gunleri = [
                e for e in get_upcoming(within_days=366, today=bugun)
                if "doğum" in tr_lower(e["tur"])
            ]
            if not dogum_gunleri:
                return "Kayıtlı doğum günü bulunmuyor."
            return "Kayıtlı doğum günleri şunlar: " + " ".join(_cumle(e, bugun=bugun) for e in dogum_gunleri)

        if any(k in q for k in ("öde", "taksit", "aidat", "fatura", "kredi kartı")):
            odemeler = [
                e for e in get_upcoming(within_days=366, today=bugun)
                if any(k in tr_lower(e["tur"]) for k in ("ödeme", "fatura", "kredi"))
            ]
            if not odemeler:
                return "Yaklaşan kayıtlı bir ödemeniz görünmüyor."
            return "Kayıtlı ödemeleriniz şunlar: " + " ".join(_cumle(e, bugun=bugun) for e in odemeler)

    within_days = 7 if "bu hafta" in q else 30
    olaylar = get_upcoming(within_days=within_days, today=bugun)
    if not olaylar:
        return "Yaklaşan günlerde takviminizde kayıtlı bir hatırlatma görünmüyor."
    return "Takviminizde şunlar var: " + " ".join(_cumle(e, bugun=bugun) for e in olaylar)
