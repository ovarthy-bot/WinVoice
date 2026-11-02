# note_database.py
#
# Telegram Akıllı Not Yönetimi modülünün SQLite veri katmanı. PyQt5, Telegram
# ve Ollama'dan tamamen bağımsızdır — yalnızca stdlib (sqlite3, zoneinfo)
# kullanır ki hem dashboard'dan hem de ileride telegram_briefing.py gibi
# bağımsız script'lerden içe aktarılabilsin (bkz. llm_settings.py'nin aynı
# gerekçeyle tts_engine'den doğrudan import etmesi).
#
# HAKKIMDA/ (Obsidian kasası) burada HİÇ kullanılmaz ve değiştirilmez — bu,
# ondan tamamen ayrı, paralel bir depo. notes.db proje kökünde oluşturulur
# ve settings.json gibi .gitignore'dadır.

import os
import sqlite3
from datetime import datetime, timedelta, timezone

# zoneinfo.ZoneInfo("Europe/Istanbul") Windows'ta ek bir "tzdata" paketi
# gerektirir (IANA veritabanı işletim sistemiyle gelmez). Türkiye 2016'dan
# beri yaz saati uygulamadan sabit UTC+3 kullandığı için ek bağımlılık
# eklemek yerine sabit bir offset yeterli ve doğru.
ISTANBUL_TZ = timezone(timedelta(hours=3))

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notes.db")

CATEGORIES = ("appointment", "shopping", "reminder", "general")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS telegram_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_update_id INTEGER UNIQUE,
    telegram_message_id INTEGER,
    chat_id TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    received_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    clarification_question TEXT
);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_message_id INTEGER REFERENCES telegram_messages(id),
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    confidence TEXT NOT NULL,
    needs_review INTEGER NOT NULL DEFAULT 0,
    completed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS appointments (
    note_id INTEGER PRIMARY KEY REFERENCES notes(id) ON DELETE CASCADE,
    appt_date TEXT,
    appt_time TEXT,
    location TEXT,
    related_person TEXT
);

CREATE TABLE IF NOT EXISTS shopping_items (
    note_id INTEGER PRIMARY KEY REFERENCES notes(id) ON DELETE CASCADE,
    product_name TEXT,
    quantity TEXT
);

CREATE TABLE IF NOT EXISTS reminders (
    note_id INTEGER PRIMARY KEY REFERENCES notes(id) ON DELETE CASCADE,
    remind_at TEXT,
    repeat_frequency TEXT,
    notified_at TEXT
);

CREATE TABLE IF NOT EXISTS general_notes (
    note_id INTEGER PRIMARY KEY REFERENCES notes(id) ON DELETE CASCADE
);
"""

# Kategori -> (alt tablo adı, o tabloya özgü sütunlar) eşlemesi. insert_note/
# update_note/get_notes bu haritayı kullanarak doğru alt tabloyu hedefler.
_CATEGORY_TABLES = {
    "appointment": ("appointments", ("appt_date", "appt_time", "location", "related_person")),
    "shopping": ("shopping_items", ("product_name", "quantity")),
    "reminder": ("reminders", ("remind_at", "repeat_frequency", "notified_at")),
    "general": ("general_notes", ()),
}


def now_istanbul_iso():
    return datetime.now(ISTANBUL_TZ).isoformat()


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Tabloları (yoksa) oluşturur. Uygulama/servis başlarken bir kez
    çağrılması yeterlidir; mevcut veritabanına dokunmaz."""
    with _connect() as conn:
        conn.executescript(_SCHEMA)


# --------------------------------------------------------------------------- #
# telegram_messages
# --------------------------------------------------------------------------- #

def insert_telegram_message(chat_id, raw_text, telegram_update_id=None, telegram_message_id=None):
    """Ham Telegram mesajını HEMEN (sınıflandırmadan önce) kaydeder — bir
    mesajın hiçbir aşamada sessizce kaybolmamasının güvencesi budur. Aynı
    telegram_update_id tekrar gelirse (UNIQUE kısıtı), var olan satırın id'si
    döner — mesaj ikinci kez eklenmez."""
    received_at = now_istanbul_iso()
    with _connect() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO telegram_messages "
                "(telegram_update_id, telegram_message_id, chat_id, raw_text, received_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (telegram_update_id, telegram_message_id, str(chat_id), raw_text, received_at),
            )
            return cur.lastrowid
        except sqlite3.IntegrityError:
            row = conn.execute(
                "SELECT id FROM telegram_messages WHERE telegram_update_id = ?",
                (telegram_update_id,),
            ).fetchone()
            return row["id"] if row else None


def get_telegram_message(message_id):
    with _connect() as conn:
        row = conn.execute("SELECT * FROM telegram_messages WHERE id = ?", (message_id,)).fetchone()
        return dict(row) if row else None


def get_pending_clarification(chat_id):
    """O sohbetten, cevap bekleyen (status='awaiting_clarification') en son
    mesajı döner — bulunursa bir sonraki gelen mesaj onun cevabı sayılır."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM telegram_messages WHERE chat_id = ? AND status = 'awaiting_clarification' "
            "ORDER BY id DESC LIMIT 1",
            (str(chat_id),),
        ).fetchone()
        return dict(row) if row else None


def mark_message_status(message_id, status, clarification_question=None):
    with _connect() as conn:
        conn.execute(
            "UPDATE telegram_messages SET status = ?, clarification_question = ? WHERE id = ?",
            (status, clarification_question, message_id),
        )


# --------------------------------------------------------------------------- #
# notes (+ kategoriye özgü alt tablolar)
# --------------------------------------------------------------------------- #

def insert_note(category, title, description, confidence, telegram_message_id=None,
                 needs_review=False, extra=None):
    """Yeni bir not oluşturur ve `category`'ye göre doğru alt tabloya
    (appointments/shopping_items/reminders/general_notes) `extra` sözlüğündeki
    alanları yazar. `extra`'da olmayan alanlar NULL kalır (asla tahmin edilmez)."""
    if category not in _CATEGORY_TABLES:
        raise ValueError(f"Bilinmeyen kategori: {category!r}")
    extra = extra or {}
    table_name, columns = _CATEGORY_TABLES[category]
    now = now_istanbul_iso()

    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO notes "
            "(telegram_message_id, category, title, description, confidence, needs_review, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (telegram_message_id, category, title, description, confidence,
             1 if needs_review else 0, now, now),
        )
        note_id = cur.lastrowid

        if table_name == "general_notes":
            conn.execute("INSERT INTO general_notes (note_id) VALUES (?)", (note_id,))
        else:
            values = [extra.get(col) for col in columns]
            placeholders = ", ".join("?" for _ in columns)
            col_list = ", ".join(columns)
            conn.execute(
                f"INSERT INTO {table_name} (note_id, {col_list}) VALUES (?, {placeholders})",
                (note_id, *values),
            )
        return note_id


_NOTES_SELECT = """
    SELECT n.*,
           a.appt_date, a.appt_time, a.location, a.related_person,
           s.product_name, s.quantity,
           r.remind_at, r.repeat_frequency, r.notified_at
    FROM notes n
    LEFT JOIN appointments a ON a.note_id = n.id
    LEFT JOIN shopping_items s ON s.note_id = n.id
    LEFT JOIN reminders r ON r.note_id = n.id
"""

_SORT_COLUMNS = {
    "date_desc": "n.created_at DESC",
    "date_asc": "n.created_at ASC",
}


def get_notes(category=None, search=None, sort="date_desc", include_completed=True):
    """Filtrelenmiş/sıralanmış not listesini, her satırda kategoriye uygun
    ek alanlar (LEFT JOIN ile) doldurulmuş sözlükler olarak döner."""
    where = []
    params = []
    if category and category != "all":
        where.append("n.category = ?")
        params.append(category)
    if search:
        where.append("(n.title LIKE ? OR n.description LIKE ?)")
        like = f"%{search}%"
        params.extend([like, like])
    if not include_completed:
        where.append("n.completed = 0")

    query = _NOTES_SELECT
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY " + _SORT_COLUMNS.get(sort, _SORT_COLUMNS["date_desc"])

    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]


def get_note(note_id):
    with _connect() as conn:
        row = conn.execute(_NOTES_SELECT + " WHERE n.id = ?", (note_id,)).fetchone()
        return dict(row) if row else None


def update_note(note_id, fields=None, extra=None):
    """`fields`: notes tablosundaki sütunlar (title/description/category/
    needs_review/completed) için {sütun: değer}. `extra`: notun kategorisine
    özgü alt tablo sütunları için {sütun: değer} (UPDATE, INSERT OR REPLACE
    ile de olur ki satır hiç yoksa bile çalışsın)."""
    fields = dict(fields or {})
    with _connect() as conn:
        if fields:
            fields["updated_at"] = now_istanbul_iso()
            set_clause = ", ".join(f"{col} = ?" for col in fields)
            conn.execute(
                f"UPDATE notes SET {set_clause} WHERE id = ?",
                (*fields.values(), note_id),
            )
        if extra:
            note_row = conn.execute("SELECT category FROM notes WHERE id = ?", (note_id,)).fetchone()
            if not note_row:
                return
            category = fields.get("category", note_row["category"])
            if category not in _CATEGORY_TABLES:
                return
            table_name, columns = _CATEGORY_TABLES[category]
            if table_name == "general_notes":
                return
            cols = [c for c in extra if c in columns]
            if not cols:
                return
            existing = conn.execute(
                f"SELECT 1 FROM {table_name} WHERE note_id = ?", (note_id,)
            ).fetchone()
            if existing:
                set_clause = ", ".join(f"{col} = ?" for col in cols)
                conn.execute(
                    f"UPDATE {table_name} SET {set_clause} WHERE note_id = ?",
                    (*(extra[c] for c in cols), note_id),
                )
            else:
                col_list = ", ".join(cols)
                placeholders = ", ".join("?" for _ in cols)
                conn.execute(
                    f"INSERT INTO {table_name} (note_id, {col_list}) VALUES (?, {placeholders})",
                    (note_id, *(extra[c] for c in cols)),
                )


def delete_note(note_id):
    """Notu ve (ON DELETE CASCADE ile) kategoriye özgü alt tablo satırını
    siler. HAKKIMDA/ dosyalarına HİÇ dokunmaz — bu, tamamen ayrı bir depo."""
    with _connect() as conn:
        conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))


def set_completed(note_id, completed):
    with _connect() as conn:
        conn.execute(
            "UPDATE notes SET completed = ?, updated_at = ? WHERE id = ?",
            (1 if completed else 0, now_istanbul_iso(), note_id),
        )


def mark_completed_from_cloud(completed_items):
    """Bulutta Telegram üzerinden (örneğin [✓ Tamamla] inline butonu ile)
    tamamlandı işaretlenen notları yerel notes.db ile eşitler.
    completed_items: [{category, title, telegram_update_id}]
    Döner: yeni tamamlanan satır sayısı.
    """
    if not completed_items:
        return 0
    now_iso = now_istanbul_iso()
    updated_count = 0
    with _connect() as conn:
        for item in completed_items:
            cat = item.get("category")
            title = (item.get("title") or "").strip()
            update_id = item.get("telegram_update_id")
            if not title:
                continue

            # 1) telegram_update_id varsa onunla eşleşen yerel aktif kaydı tamamla
            if update_id:
                cur = conn.execute(
                    "UPDATE notes SET completed = 1, updated_at = ? "
                    "WHERE completed = 0 AND title = ? AND telegram_message_id IN "
                    "(SELECT id FROM telegram_messages WHERE telegram_update_id = ?)",
                    (now_iso, title, update_id),
                )
                if cur.rowcount > 0:
                    updated_count += cur.rowcount
                    continue

            # 2) telegram_update_id yoksa kategori + başlık ile aktif kaydı tamamla
            if cat:
                cur = conn.execute(
                    "UPDATE notes SET completed = 1, updated_at = ? "
                    "WHERE completed = 0 AND category = ? AND title = ?",
                    (now_iso, cat, title),
                )
            else:
                cur = conn.execute(
                    "UPDATE notes SET completed = 1, updated_at = ? "
                    "WHERE completed = 0 AND title = ?",
                    (now_iso, title),
                )
            if cur.rowcount > 0:
                updated_count += cur.rowcount

    return updated_count


# --------------------------------------------------------------------------- #
# Hatırlatmalar (reminder_scheduler.py tarafından kullanılır)
# --------------------------------------------------------------------------- #

def get_due_reminders(now_iso=None):
    """Zamanı gelmiş (remind_at <= now) ve henüz bildirilmemiş
    (notified_at IS NULL) hatırlatma notlarını döner."""
    now_iso = now_iso or now_istanbul_iso()
    with _connect() as conn:
        rows = conn.execute(
            _NOTES_SELECT + " WHERE n.category = 'reminder' AND r.remind_at IS NOT NULL "
            "AND r.remind_at <= ? AND r.notified_at IS NULL",
            (now_iso,),
        ).fetchall()
        return [dict(row) for row in rows]


def mark_reminder_notified(note_id, notified_at=None):
    notified_at = notified_at or now_istanbul_iso()
    with _connect() as conn:
        conn.execute(
            "UPDATE reminders SET notified_at = ? WHERE note_id = ?",
            (notified_at, note_id),
        )
