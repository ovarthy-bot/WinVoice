# hakkimda_note_writer.py
#
# notes.db'de (note_database.py) Telegram'dan sınıflandırılmış bir not
# oluşturulduğunda (bkz. note_manager._save_items), AYNI notu
# HAKKIMDA/00_Gelen_Kutusu'na da bir .md dosyası olarak yazar — kasadaki
# mevcut "Hızlı Yakala / Gelen Kutusu" akışıyla aynı dosya adı/frontmatter
# kuralları (bkz. eski telegram_inbox.py, artık Telegram offset'ini
# TelegramPollThread ile paylaştığı için pratikte tetiklenmiyor).
#
# notes.db ile HAKKIMDA bilerek iki ayrı, paralel depo (bkz. note_database.py
# üst yorumu); bu modül aralarında TEK YÖNLÜ (db -> kasa) bir köprü kurar,
# notes.db'yi veya mevcut kasa senkronunu (vault_sync_bidi.py) hiç değiştirmez.
# Not Dashboard'dan silinse/düzenlense bile burada yazılan .md dosyası
# otomatik güncellenmez (kullanıcı isterse kasadaki dosyayı kendisi düzenler/
# taşır — "Gelen Kutusunu İşle" akışıyla aynı felsefe).
import os
import re

import shift_reminder_utils

INBOX_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "HAKKIMDA", "00_Gelen_Kutusu",
)

TITLE_MAX_LEN = 60
_INVALID_FS_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WHITESPACE_RE = re.compile(r"\s+")

_CATEGORY_LABELS = {
    "appointment": "randevu",
    "shopping": "alışveriş",
    "reminder": "hatırlatma",
    "task": "görev",
    "general": "not",
}

# note_database._CATEGORY_TABLES'daki sütunlarla AYNI isimler; get_note()'un
# LEFT JOIN ile döndürdüğü sözlükten doğrudan okunabilsinler diye.
_CATEGORY_EXTRA_COLUMNS = {
    "appointment": ("appt_date", "appt_time", "location", "related_person"),
    "shopping": ("product_name", "quantity"),
    "reminder": ("remind_at", "repeat_frequency"),
    "task": ("due_date", "context"),
    "general": (),
}

_EXTRA_LABELS = {
    "appt_date": "Tarih", "appt_time": "Saat", "location": "Yer", "related_person": "Kişi",
    "product_name": "Ürün", "quantity": "Adet",
    "remind_at": "Hatırlatma zamanı", "repeat_frequency": "Tekrar",
    "due_date": "Son tarih", "context": "Bağlam",
}


def _sanitize_filename(name):
    name = _INVALID_FS_CHARS_RE.sub(" ", name)
    name = _WHITESPACE_RE.sub(" ", name).strip().strip(".")
    return name or "Telegram Notu"


def _unique_note_path(title):
    base = _sanitize_filename(title)
    if len(base) > TITLE_MAX_LEN:
        base = base[:TITLE_MAX_LEN].rsplit(" ", 1)[0].strip() or base[:TITLE_MAX_LEN]
    candidate = os.path.join(INBOX_DIR, f"{base}.md")
    counter = 2
    while os.path.exists(candidate):
        candidate = os.path.join(INBOX_DIR, f"{base} ({counter}).md")
        counter += 1
    return candidate


def _format_extra_value(col, value):
    if col == "repeat_frequency" and shift_reminder_utils.is_shift_repeat(value):
        shift_code = shift_reminder_utils.shift_code_from_repeat(value)
        return f"{shift_code} vardiyasında olduğum her gün"
    return value


def _note_content(note):
    category = note.get("category", "general")
    lines = [
        "---",
        "tür: not",
        f'kategori: "{_CATEGORY_LABELS.get(category, category)}"',
        "tags: [telegram]",
        "---",
        "",
        f"# {note['title']}",
    ]

    details = [
        f"- **{_EXTRA_LABELS.get(col, col)}:** {_format_extra_value(col, note[col])}"
        for col in _CATEGORY_EXTRA_COLUMNS.get(category, ())
        if note.get(col)
    ]
    if details:
        lines.append("")
        lines.extend(details)

    description = (note.get("description") or "").strip()
    if description:
        lines.append("")
        lines.append(description)

    lines.append("")
    return "\n".join(lines)


def write_note(note):
    """`note_database.get_note()`'un döndürdüğü sözlüğü HAKKIMDA/00_Gelen_Kutusu'na
    yeni bir .md dosyası olarak yazar. Döner: yazılan dosyanın yolu."""
    os.makedirs(INBOX_DIR, exist_ok=True)
    path = _unique_note_path(note["title"])
    with open(path, "w", encoding="utf-8") as f:
        f.write(_note_content(note))
    return path
