# briefing_coordinator.py
#
# Akıllı Günlük Brifing'in 2. Katmanı: Deterministik Kişisel Önceliklendirme Motoru.
# - Açık izin listeli (allowlist) HAKKIMDA kasa erişimi (Şifrelerim.md, 10_Kişiler,
#   90_Arşiv gibi özel klasörler kesinlikle okunmaz).
# - R1D Vardiya Motoru (r1d vardiyam.md + 27 günlük tam döngü + manuel ezme).
# - Kişisel Görev / Randevu / Ödeme / Alışveriş Önceliklendiricisi (geciken işler,
#   bugünün en fazla 3 önceliği, 3 gün içindeki kritik işler, tarihsiz görev rotasyonu,
#   alışveriş özeti).
# - Haftalık Aktif Proje Durum Özeti (yalnızca Pazartesi günleri).
#
# Sayı ve tarih ifadeleri masaüstü TTS modunda (for_tts=True) tr_numbers ile
# tamamen yazıya çevrilir; LLM'e asla sayı/tarih hesabı bırakılmaz.

import os
import re
from datetime import date, datetime, timedelta

import note_database
import personal_context
import vault_cache
from tr_numbers import plain_number_to_words
from vault_knowledge import tr_lower

# Kasa gizlilik sınırı: YALNIZCA bu yollardaki notlar brifing motoru tarafından okunabilir.
VAULT_BRIEFING_ALLOWLIST = frozenset({
    "50_Rutinler/Doğum Günleri ve Randevular.md",
    "50_Rutinler/Çatalca İGA Servisi.md",
    "50_Rutinler/Servis Bilgileri.md",
    "50_Rutinler/Ring saatleri.md",
    "30_İş/Eksik Eğitimlerim.md",
    "60_Öğrenme/İngilizce unuttuğum kelimeler.md",
    "60_Öğrenme/Unuttuğum Kavramlar.md",
    "40_Teknoloji/Aktif Projelerim.md",
    "40_Teknoloji/40_Teknoloji.md",
})

_R1D_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "r1d vardiyam.md")
_R1D_ANCHOR_DATE = date(2026, 11, 9)
# r1d vardiyam.md dosyasındaki 162 günün tamamıyla %100 örtüşen 27 günlük R1D döngüsü:
# 5x(15-23) + 2x(Tatil) + 5x(07-15) + 2x(Tatil) + 5x(15-23) + 2x(Tatil) + 6x(07-15) = 27 gün
_R1D_27DAY_CYCLE = (
    ("15-23",) * 5
    + ("tatil",) * 2
    + ("07-15",) * 5
    + ("tatil",) * 2
    + ("15-23",) * 5
    + ("tatil",) * 2
    + ("07-15",) * 6
)

_SHIFT_META = {
    "07-15": {
        "code": "07-15",
        "label": "07-15 Vardiyası",
        "spoken_label": "yedi on beş vardiyası",
        "wake_time": "05:00",
        "leave_time": "05:20",
        "return_time": "16:30",
        "is_workday": True,
    },
    "15-23": {
        "code": "15-23",
        "label": "15-23 Vardiyası",
        "spoken_label": "on beş yirmi üç vardiyası",
        "wake_time": None,
        "leave_time": "13:00",
        "return_time": "00:00",
        "is_workday": True,
    },
    "tatil": {
        "code": "tatil",
        "label": "Tatil",
        "spoken_label": "tatil günü",
        "wake_time": None,
        "leave_time": None,
        "return_time": None,
        "is_workday": False,
    },
}

_r1d_table_cache = None
_DIGIT_TOKEN_RE = re.compile(r"\d+")
_ISO_DATE_PREFIX_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
_TR_DATE_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})")
_ROW_RE = re.compile(r"^\|(.+)\|\s*$")
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")


def get_allowlisted_vault_content(path):
    """Yalnızca izin listesindeki kasa notlarının içeriğini döner; liste dışı
    tüm yollar (ör. Şifrelerim.md, 10_Kişiler, 90_Arşiv) boş döner."""
    normalized = (path or "").replace("\\", "/").strip()
    if normalized not in VAULT_BRIEFING_ALLOWLIST:
        return ""
    note = vault_cache.get_note_by_path(normalized)
    return (note.get("content") or "") if note else ""


def _digits_to_tr_words_in_text(text):
    """Metin içinde kalan ham rakamları (ör. B777, A330, saat ifadeleri) TTS
    için Türkçe okunuşa çevirir."""
    if not text:
        return ""
    out = text.replace("B777", "Boeing yedi yüz yetmiş yedi").replace("A330", "Airbus üç yüz otuz")
    out = re.sub(r"\bTEK\s*\d+\b", "", out)
    out = _DIGIT_TOKEN_RE.sub(lambda m: plain_number_to_words(int(m.group(0))), out)
    return re.sub(r"\s+", " ", out).strip(" —-,")


# --------------------------------------------------------------------------- #
# R1D Vardiya Motoru + İş Günü Hazırlık Asistanı
# --------------------------------------------------------------------------- #

def _normalize_shift_code(raw):
    low = tr_lower(raw or "").strip()
    if "07-15" in low or "07_15" in low or "sabah" in low:
        return "07-15"
    if "15-23" in low or "15_23" in low or "öğle" in low or "oglen" in low or "akşam" in low:
        return "15-23"
    if "tatil" in low or "izin" in low or "off" in low:
        return "tatil"
    return None


def _load_r1d_markdown_schedule():
    global _r1d_table_cache
    if _r1d_table_cache is not None:
        return _r1d_table_cache

    schedule = {}
    if os.path.exists(_R1D_FILE_PATH):
        try:
            with open(_R1D_FILE_PATH, "r", encoding="utf-8") as f:
                lines = [ln.strip() for ln in f if ln.strip()]
            if len(lines) >= 3:
                dates = [c.strip() for c in lines[0].strip("|").split("|")]
                shifts = [c.strip() for c in lines[2].strip("|").split("|")]
                for d_str, s_str in zip(dates, shifts):
                    try:
                        d_obj = datetime.strptime(d_str, "%m/%d/%y").date()
                        code = _normalize_shift_code(s_str)
                        if code:
                            schedule[d_obj] = code
                    except ValueError:
                        continue
        except Exception:
            schedule = {}

    _r1d_table_cache = schedule
    return schedule


def _parse_shift_override(override_str, target_date):
    """override_str: '2026-11-09:07-15' (sadece o gün için) veya doğrudan '07-15'."""
    if not override_str:
        return None
    raw = str(override_str).strip()
    if not raw or raw.lower() in ("auto", "otomatik"):
        return None
    if ":" in raw:
        date_part, code_part = raw.split(":", 1)
        if date_part.strip() == target_date.isoformat():
            return _normalize_shift_code(code_part)
        return None
    return _normalize_shift_code(raw)


def resolve_shift_for_date(target_date=None, override_str=""):
    """Verilen tarih için R1D vardiya bilgisini döner:
    1) Kullanıcı o gün için manuel ezme seçtiyse onu uygular.
    2) r1d vardiyam.md içinde o tarih varsa tablodan okur.
    3) Tablo aralığı dışındaki tarihler için 27 günlük R1D döngüsünü uygular."""
    d = target_date or datetime.now(note_database.ISTANBUL_TZ).date()
    override_code = _parse_shift_override(override_str, d)
    if override_code and override_code in _SHIFT_META:
        return {**_SHIFT_META[override_code], "source": "override", "date": d.isoformat()}

    table = _load_r1d_markdown_schedule()
    if d in table:
        return {**_SHIFT_META[table[d]], "source": "r1d_table", "date": d.isoformat()}

    idx = (d - _R1D_ANCHOR_DATE).days % len(_R1D_27DAY_CYCLE)
    code = _R1D_27DAY_CYCLE[idx]
    return {**_SHIFT_META[code], "source": "r1d_cycle", "date": d.isoformat()}


def _extract_pending_trainings():
    """30_İş/Eksik Eğitimlerim.md içindeki madde işaretli eğitim başlıklarını okur.
    Asla bakım prosedürü türetmez; yalnızca kullanıcının kendi yazdığı satırı alır."""
    content = get_allowlisted_vault_content("30_İş/Eksik Eğitimlerim.md")
    if not content:
        return []
    items = []
    in_section = False
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            in_section = "eksik" in tr_lower(line) or "eğitim" in tr_lower(line)
            continue
        if in_section and line.startswith("- ") and "[[" not in line:
            cleaned = line[2:].strip().replace("**", "")
            if cleaned:
                items.append(cleaned)
    return items


def build_workday_prep_paragraph(today=None, current_hour=7, override_str="", length_mode="balanced", for_tts=True):
    """Vardiya saatine, izin durumuna ve (haftada 2 gün) bekleyen kabin eğitim
    notuna göre iş günü hazırlık paragrafını kurar."""
    today_d = today or datetime.now(note_database.ISTANBUL_TZ).date()
    tomorrow_d = today_d + timedelta(days=1)
    today_shift = resolve_shift_for_date(today_d, override_str)
    tomorrow_shift = resolve_shift_for_date(tomorrow_d, "")

    code = today_shift["code"]
    tmr_code = tomorrow_shift["code"]
    sentences = []

    if for_tts:
        if code == "07-15":
            if current_hour < 8:
                sentences.append(
                    "Vardiya ve iş hazırlığına gelirsek; bugün yedi on beş vardiyasındasın, "
                    "sabah beş yirmide evden çıkıp on altı otuzda eve döneceksin."
                )
            elif current_hour < 16:
                sentences.append(
                    "Bugün yedi on beş vardiyan devam ediyor; eve dönüş saatin on altı otuz."
                )
            else:
                if tmr_code == "07-15":
                    sentences.append(
                        "Bugünkü vardiyanı tamamladın; yarın da yedi on beş vardiyan var, sabah beş yirmide çıkış olacak."
                    )
                elif tmr_code == "15-23":
                    sentences.append("Yarın on beş yirmi üç vardiyasına geçiyorsun, öğlen saat on üçte çıkış var.")
                else:
                    sentences.append("Bugünkü mesainin ardından yarın vardiya tatilin başlıyor.")
        elif code == "15-23":
            if current_hour < 14:
                sentences.append(
                    "Vardiya ve iş hazırlığına gelirsek; bugün on beş yirmi üç vardiyasındasın, "
                    "evden saat on üçte çıkıp gece yarısı eve döneceksin."
                )
            elif current_hour < 22:
                sentences.append("Şu an on beş yirmi üç vardiyasındasın; gece yarısı eve dönüşün var.")
            else:
                if tmr_code == "tatil":
                    sentences.append("Bu gecenin ardından yarın vardiya tatilin başlıyor.")
                elif tmr_code == "15-23":
                    sentences.append("Yarın da on beş yirmi üç vardiyan devam ediyor.")
        else:
            # Tatil günü
            if tmr_code == "07-15":
                sentences.append(
                    "Bugün vardiya tatilindesin; ancak yarın sabah yedi on beş vardiyası başlıyor, "
                    "sabah beşte kalkıp beş yirmide evden çıkacağını şimdiden not et."
                )
            elif tmr_code == "15-23" and current_hour >= 16:
                sentences.append(
                    "Bugün tatil günündesin; yarın on beş yirmi üç vardiyan başlıyor, çıkış saatin on üç."
                )
            else:
                sentences.append("Bugün vardiya tatilindesin, iş temposundan uzak rahat bir gün seni bekliyor.")

        # İş günlerinde haftada yalnızca Salı ve Cuma (sıkmadan) eksik eğitim notunu hatırlat
        if today_shift["is_workday"] and length_mode != "short" and today_d.weekday() in (1, 4):
            trainings = _extract_pending_trainings()
            if trainings:
                pick = trainings[today_d.toordinal() % len(trainings)]
                spoken_pick = _digits_to_tr_words_in_text(pick)
                sentences.append(
                    f"İş notlarından küçük bir hatırlatma olarak, eksik eğitim listende {spoken_pick} kaydı bekliyor."
                )
        return " ".join(sentences)

    # Telegram yazılı biçim
    lines = ["🛫 Vardiya & İş Günü:"]
    if code == "07-15":
        lines.append("• Bugün: 07-15 Vardiyası (05:00 uyanış, 05:20 evden çıkış, 16:30 dönüş)")
    elif code == "15-23":
        lines.append("• Bugün: 15-23 Vardiyası (13:00 evden çıkış, 00:00 eve dönüş)")
    else:
        lines.append("• Bugün: Vardiya Tatili 🏖️")

    if code == "tatil" and tmr_code == "07-15":
        lines.append("• Yarın: 07-15 Vardiyası başlıyor (05:20 çıkış)")
    elif current_hour >= 16:
        lines.append(f"• Yarın: {tomorrow_shift['label']}")

    if today_shift["is_workday"] and length_mode != "short" and today_d.weekday() in (1, 4):
        trainings = _extract_pending_trainings()
        if trainings:
            pick = trainings[today_d.toordinal() % len(trainings)]
            lines.append(f"• Eğitim Hatırlatması: {pick}")

    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Kişisel Görev, Takvim ve Alışveriş Koordinatörü
# --------------------------------------------------------------------------- #

def _parse_note_due_date(note):
    cat = note.get("category")
    raw = ""
    if cat == "appointment":
        raw = (note.get("appt_date") or "").strip()
    elif cat == "task":
        raw = (note.get("due_date") or "").strip()
    elif cat == "reminder":
        raw = (note.get("remind_at") or "").strip()
    if not raw or tr_lower(raw) == "yok":
        return None
    m_iso = _ISO_DATE_PREFIX_RE.match(raw)
    if m_iso:
        try:
            return date(int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3)))
        except ValueError:
            return None
    m_tr = _TR_DATE_RE.match(raw)
    if m_tr:
        try:
            return date(int(m_tr.group(3)), int(m_tr.group(2)), int(m_tr.group(1)))
        except ValueError:
            return None
    return None


def _is_periodic_calendar_reminder(note):
    title_low = tr_lower(note.get("title") or "")
    rep = tr_lower(note.get("repeat_frequency") or "")
    if rep in ("yillik", "aylik"):
        return True
    return "doğum günü" in title_low or "ödeme hatırlatması" in title_low


def _is_stale_meta(note):
    title = (note.get("title") or "").strip()
    desc = (note.get("description") or "").strip()
    return (
        title == "Önceki mesajın açıklaması"
        and desc.startswith("Bu, şu önceki belirsiz mesajın açıklaması:")
    )


def _format_calendar_item_tts(entry):
    tur = tr_lower(entry.get("tur") or "")
    kim = _digits_to_tr_words_in_text(entry.get("kim") or "")
    kalan = entry.get("kalan_gun", 0)
    zaman = "bugün" if kalan == 0 else ("yarın" if kalan == 1 else f"{plain_number_to_words(kalan)} gün sonra")

    if "doğum" in tur:
        return f"{zaman} {kim} doğum günü"
    if "ödeme" in tur:
        return f"{zaman} {kim} ödemesi"
    if "randevu" in tur:
        return f"{zaman} {kim} randevusu"
    return f"{zaman} {kim}"


def _format_calendar_item_tg(entry):
    tur = entry.get("tur") or "Kayıt"
    kim = entry.get("kim") or ""
    kalan = entry.get("kalan_gun", 0)
    zaman = "bugün" if kalan == 0 else ("yarın" if kalan == 1 else f"{kalan} gün sonra")
    extra = f" ({entry['not']})" if entry.get("not") else ""
    return f"[{tur}] {kim} — {zaman}{extra}"


def collect_personal_coordination_data(today=None, length_mode="balanced"):
    """Görev, takvim ve alışveriş verilerini deterministik öncelik kovalarına ayırır."""
    today_d = today or datetime.now(note_database.ISTANBUL_TZ).date()
    active_notes = [
        n for n in note_database.get_notes(include_completed=False)
        if not _is_stale_meta(n)
    ]

    # 1) Geciken işler (son 30 gün içinde tarihi geçmiş ama tamamlanmamış kayıtlar)
    overdue = []
    high_prio_undated = []
    undated_pool = []
    shopping_items = []

    for n in active_notes:
        cat = n.get("category")
        if cat == "shopping":
            label = (n.get("product_name") or n.get("title") or "").strip()
            qty = (n.get("quantity") or "").strip()
            if label:
                shopping_items.append({"label": label, "qty": qty})
            continue

        if cat not in ("appointment", "task", "reminder"):
            continue
        if _is_periodic_calendar_reminder(n):
            continue

        due_d = _parse_note_due_date(n)
        title = (n.get("title") or n.get("description") or "").strip()
        if not title:
            continue

        if due_d is not None:
            diff = (due_d - today_d).days
            if -30 <= diff < 0:
                overdue.append({"title": title, "days_overdue": abs(diff), "priority": n.get("priority", "normal")})
        else:
            if n.get("priority") == "high":
                high_prio_undated.append({"title": title})
            else:
                undated_pool.append({"id": n.get("id", 0), "title": title})

    overdue.sort(key=lambda x: (0 if x["priority"] == "high" else 1, x["days_overdue"]))
    overdue = overdue[:2]

    # 2) Birleşik takvim kayıtları (Doğum Günleri ve Randevular.md + notes.db)
    bday_horizon = 3 if length_mode == "short" else (14 if length_mode == "detailed" else 7)
    task_horizon = 2 if length_mode == "short" else (5 if length_mode == "detailed" else 3)
    cal_entries = personal_context.get_upcoming(within_days=max(bday_horizon, task_horizon), today=today_d)

    today_items = []
    upcoming_items = []

    for e in cal_entries:
        kalan = e["kalan_gun"]
        is_bday = "doğum" in tr_lower(e["tur"])
        if kalan == 0:
            today_items.append(e)
        elif is_bday and kalan <= bday_horizon:
            upcoming_items.append(e)
        elif not is_bday and kalan <= task_horizon:
            upcoming_items.append(e)

    # Bugünün öncelikleri en fazla 3 kayıt (takvimde bugün olanlar + yüksek öncelikli görevler)
    today_priorities = []
    for e in today_items[:3]:
        today_priorities.append({"kind": "calendar", "entry": e})
    for hp in high_prio_undated:
        if len(today_priorities) >= 3:
            break
        today_priorities.append({"kind": "high_task", "title": hp["title"]})

    upcoming_cap = 2 if length_mode == "short" else (5 if length_mode == "detailed" else 3)
    upcoming_items = upcoming_items[:upcoming_cap]

    # 3) Tarihsiz görevlerden günlük dönüşümlü 1-2 hatırlatma
    undated_cap = 1 if length_mode == "short" else 2
    selected_undated = []
    if undated_pool and len(today_priorities) < 3:
        undated_pool.sort(key=lambda x: x["id"])
        start_idx = today_d.toordinal() % len(undated_pool)
        for offset in range(min(undated_cap, len(undated_pool))):
            selected_undated.append(undated_pool[(start_idx + offset) % len(undated_pool)])

    # Odak cümlesi için en önemli 1 maddeyi çıkar
    primary_focus = ""
    if today_priorities:
        first = today_priorities[0]
        primary_focus = first["entry"]["kim"] if first["kind"] == "calendar" else first["title"]
    elif overdue:
        primary_focus = overdue[0]["title"]
    elif selected_undated:
        primary_focus = selected_undated[0]["title"]

    return {
        "overdue": overdue,
        "today_priorities": today_priorities,
        "upcoming": upcoming_items,
        "undated_tasks": selected_undated,
        "shopping": shopping_items,
        "primary_focus": primary_focus,
    }


def build_personal_coordination_paragraph(today=None, length_mode="balanced", for_tts=True):
    """Kişisel görev, takvim ve alışveriş koordinasyonunu tek paragrafta üretir."""
    data = collect_personal_coordination_data(today=today, length_mode=length_mode)
    overdue = data["overdue"]
    today_prio = data["today_priorities"]
    upcoming = data["upcoming"]
    undated = data["undated_tasks"]
    shopping = data["shopping"]

    if not (overdue or today_prio or upcoming or undated or shopping):
        return ""

    if for_tts:
        sentences = []
        if today_prio:
            bits = []
            for item in today_prio:
                if item["kind"] == "calendar":
                    bits.append(_format_calendar_item_tts(item["entry"]))
                else:
                    bits.append(_digits_to_tr_words_in_text(item["title"]))
            sentences.append("Bugünün önceliklerinde " + ", ".join(bits) + " var.")

        if overdue:
            obits = [
                f"{_digits_to_tr_words_in_text(o['title'])} ({plain_number_to_words(o['days_overdue'])} gün gecikti)"
                for o in overdue
            ]
            sentences.append("Geciken işlerinde " + " ve ".join(obits) + " bekliyor.")

        if upcoming:
            ubits = [_format_calendar_item_tts(e) for e in upcoming]
            sentences.append("Yaklaşan takviminde " + ", ".join(ubits) + " bulunuyor.")

        if undated:
            tbits = [_digits_to_tr_words_in_text(u["title"]) for u in undated]
            sentences.append("Unutmaman gereken işlerde " + " ve ".join(tbits) + " notun kayıtlı.")

        if shopping:
            if len(shopping) <= 3:
                sbits = [_digits_to_tr_words_in_text(s["label"]) for s in shopping]
                sentences.append("Alışveriş listende " + ", ".join(sbits) + " yer alıyor.")
            else:
                sbits = [_digits_to_tr_words_in_text(s["label"]) for s in shopping[:2]]
                rem = plain_number_to_words(len(shopping) - 2)
                sentences.append(f"Alışveriş listende {', '.join(sbits)} ve {rem} ürün daha bekliyor.")

        return " ".join(sentences)

    # Telegram yazılı biçim
    lines = ["📋 Günün Kişisel Koordinasyonu:"]
    if today_prio:
        for item in today_prio:
            if item["kind"] == "calendar":
                lines.append(f"• 🎯 Öncelik: {_format_calendar_item_tg(item['entry'])}")
            else:
                lines.append(f"• 🎯 Öncelik: {item['title']}")
    if overdue:
        for o in overdue:
            lines.append(f"• ⚠️ Geciken: {o['title']} ({o['days_overdue']} gün geçti)")
    if upcoming:
        for e in upcoming:
            lines.append(f"• 📅 Yaklaşan: {_format_calendar_item_tg(e)}")
    if undated:
        for u in undated:
            lines.append(f"• 📌 Bekleyen İş: {u['title']}")
    if shopping:
        if len(shopping) <= 3:
            names = ", ".join(f"{s['label']} ({s['qty']})" if s["qty"] else s["label"] for s in shopping)
            lines.append(f"• 🛒 Alışveriş: {names}")
        else:
            names = ", ".join(s["label"] for s in shopping[:2])
            lines.append(f"• 🛒 Alışveriş ({len(shopping)} ürün): {names} +{len(shopping) - 2} ürün")

    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Haftalık Aktif Proje Durum Özeti (Yalnızca Pazartesi)
# --------------------------------------------------------------------------- #

_NON_PROJECT_REFERENCE_TITLES = {
    "kod derleme ve yayınlama komutları",
    "masaüstü uygulaması yapmak",
    "sıfırdan mobil uygulama üretim taslağı",
    "websitelerini dark mode yapma",
    "excel - gelişmiş düşeyara",
    "play store yayınlama notları",
    "gelen kutusu",
}


def build_weekly_project_paragraph(today=None, length_mode="balanced", for_tts=True):
    """Yalnızca Pazartesi günleri 40_Teknoloji altındaki aktif projelerden
    1-2 odak adımını hatırlatır."""
    today_d = today or datetime.now(note_database.ISTANBUL_TZ).date()
    if today_d.weekday() != 0 or length_mode == "short":
        return ""

    # 1) Yapılandırılmış '40_Teknoloji/Aktif Projelerim.md' tablosu varsa oku
    tracker_md = get_allowlisted_vault_content("40_Teknoloji/Aktif Projelerim.md")
    if tracker_md:
        active_rows = []
        for raw_line in tracker_md.splitlines():
            m = _ROW_RE.match(raw_line.strip())
            if not m:
                continue
            cells = [c.strip() for c in m.group(1).split("|")]
            if len(cells) < 3:
                continue
            proj, status, next_step = cells[0], cells[1], cells[2]
            if not proj or proj.lower() in ("proje", "ad") or set(proj) <= {"-", ":"}:
                continue
            if "tamam" in tr_lower(status) or "iptal" in tr_lower(status):
                continue
            active_rows.append((proj, status, next_step))
        if active_rows:
            proj, _status, next_step = active_rows[0]
            if for_tts:
                p_tts = _digits_to_tr_words_in_text(proj)
                ns_tts = _digits_to_tr_words_in_text(next_step)
                return f"Haftalık proje özetinde bu hafta {p_tts} projesinde sıradaki adımın: {ns_tts}."
            return f"🚀 Haftalık Proje Odağı:\n• {proj} — Sıradaki adım: {next_step}"

    # 2) Yoksa 40_Teknoloji indeksindeki uygulama projelerinden haftalık 1 tanesini seç
    index_md = get_allowlisted_vault_content("40_Teknoloji/40_Teknoloji.md")
    if not index_md:
        return ""

    projects = []
    for raw_line in index_md.splitlines():
        line = raw_line.strip()
        if not line.startswith("- [["):
            continue
        m = _WIKILINK_RE.search(line)
        if not m:
            continue
        target, alias = m.group(1).strip(), (m.group(2) or "").strip()
        label = alias or target
        if tr_lower(label) in _NON_PROJECT_REFERENCE_TITLES or tr_lower(target) in _NON_PROJECT_REFERENCE_TITLES:
            continue
        projects.append(label)

    if not projects:
        return ""

    week_num = today_d.isocalendar()[1]
    picked = projects[week_num % len(projects)]
    if for_tts:
        picked_tts = _digits_to_tr_words_in_text(picked)
        return (
            f"Haftalık teknoloji odağında bu hafta {picked_tts} çalışmana küçük bir sonraki adım "
            "belirlemek için güzel bir Pazartesi."
        )
    return f"🚀 Haftalık Proje Odağı:\n• Bu hafta göz atabileceğin proje: {picked}"
