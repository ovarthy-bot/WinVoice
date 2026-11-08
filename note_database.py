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

CATEGORIES = ("appointment", "shopping", "reminder", "task", "general")
VALID_PRIORITIES = ("high", "normal", "low")

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
    priority TEXT NOT NULL DEFAULT 'normal',
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

CREATE TABLE IF NOT EXISTS tasks (
    note_id INTEGER PRIMARY KEY REFERENCES notes(id) ON DELETE CASCADE,
    due_date TEXT,
    context TEXT
);

CREATE TABLE IF NOT EXISTS general_notes (
    note_id INTEGER PRIMARY KEY REFERENCES notes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS seen_news (
    fingerprint TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    category TEXT,
    shown_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS learning_progress (
    word_key TEXT PRIMARY KEY,
    word TEXT NOT NULL,
    domain TEXT NOT NULL,
    box INTEGER NOT NULL DEFAULT 1,
    next_review_date TEXT NOT NULL,
    last_shown_date TEXT,
    times_shown INTEGER NOT NULL DEFAULT 0,
    times_known INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
"""

# Kategori -> (alt tablo adı, o tabloya özgü sütunlar) eşlemesi. insert_note/
# update_note/get_notes bu haritayı kullanarak doğru alt tabloyu hedefler.
_CATEGORY_TABLES = {
    "appointment": ("appointments", ("appt_date", "appt_time", "location", "related_person")),
    "shopping": ("shopping_items", ("product_name", "quantity")),
    "reminder": ("reminders", ("remind_at", "repeat_frequency", "notified_at")),
    "task": ("tasks", ("due_date", "context")),
    "general": ("general_notes", ()),
}

_migrated_paths = set()


def now_istanbul_iso():
    return datetime.now(ISTANBUL_TZ).isoformat()


def _ensure_schema_on_conn(conn):
    conn.executescript(_SCHEMA)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(notes)").fetchall()}
    if "priority" not in cols:
        conn.execute("ALTER TABLE notes ADD COLUMN priority TEXT NOT NULL DEFAULT 'normal'")


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if DB_PATH not in _migrated_paths:
        _ensure_schema_on_conn(conn)
        conn.commit()
        _migrated_paths.add(DB_PATH)
    return conn


def init_db():
    """Tabloları ve geriye dönük uyumlu şema göçlerini oluşturur. Uygulama/servis
    başlarken çağrılabilir; mevcut veritabanındaki verileri korur."""
    _migrated_paths.discard(DB_PATH)
    with _connect():
        pass


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
                 needs_review=False, extra=None, priority="normal"):
    """Yeni bir not oluşturur ve `category`'ye göre doğru alt tabloya
    (appointments/shopping_items/reminders/tasks/general_notes) `extra` sözlüğündeki
    alanları yazar. `extra`'da olmayan alanlar NULL kalır (asla tahmin edilmez)."""
    if category not in _CATEGORY_TABLES:
        raise ValueError(f"Bilinmeyen kategori: {category!r}")
    prio = str(priority or "normal").strip().lower()
    if prio not in VALID_PRIORITIES:
        prio = "normal"
    extra = extra or {}
    table_name, columns = _CATEGORY_TABLES[category]
    now = now_istanbul_iso()

    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO notes "
            "(telegram_message_id, category, title, description, confidence, priority, needs_review, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (telegram_message_id, category, title, description, confidence, prio,
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
           r.remind_at, r.repeat_frequency, r.notified_at,
           t.due_date, t.context
    FROM notes n
    LEFT JOIN appointments a ON a.note_id = n.id
    LEFT JOIN shopping_items s ON s.note_id = n.id
    LEFT JOIN reminders r ON r.note_id = n.id
    LEFT JOIN tasks t ON t.note_id = n.id
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


# --------------------------------------------------------------------------- #
# seen_news (Kişisel Haber Motoru tekrar engelleme hafızası)
# --------------------------------------------------------------------------- #

def get_seen_news_fingerprints(days=7):
    """Son `days` gün içinde brifingde gösterilmiş haber parmak izlerini döner."""
    cutoff = (datetime.now(ISTANBUL_TZ) - timedelta(days=days)).isoformat()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT fingerprint FROM seen_news WHERE shown_at >= ?",
            (cutoff,),
        ).fetchall()
        return {row["fingerprint"] for row in rows}


def mark_news_seen(items):
    """Brifinge seçilen haberlerin parmak izlerini kaydeder ve 14 günden eski
    kayıtları otomatik temizler."""
    if not items:
        return
    now_iso = now_istanbul_iso()
    prune_cutoff = (datetime.now(ISTANBUL_TZ) - timedelta(days=14)).isoformat()
    with _connect() as conn:
        conn.execute("DELETE FROM seen_news WHERE shown_at < ?", (prune_cutoff,))
        for it in items:
            fp = (it.get("fingerprint") or "").strip()
            title = (it.get("title") or "").strip()
            cat = (it.get("category") or "").strip()
            if not fp or not title:
                continue
            conn.execute(
                "INSERT INTO seen_news (fingerprint, title, category, shown_at) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(fingerprint) DO UPDATE SET shown_at = excluded.shown_at",
                (fp, title, cat, now_iso),
            )


# --------------------------------------------------------------------------- #
# learning_progress (Aralıklı Tekrar / Leitner İngilizce Kartları)
# --------------------------------------------------------------------------- #

LEITNER_INTERVAL_DAYS = {1: 1, 2: 3, 3: 7, 4: 15, 5: 30}


def get_learning_progress_map():
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM learning_progress").fetchall()
        return {row["word_key"]: dict(row) for row in rows}


def record_learning_card_shown(word_key, word, domain, today_iso):
    """Günün kartı seçildiğinde çağrılır. Aynı gün içinde tekrar çağrılırsa
    sayacı iki kez artırmaz."""
    now_iso = now_istanbul_iso()
    with _connect() as conn:
        existing = conn.execute(
            "SELECT * FROM learning_progress WHERE word_key = ?",
            (word_key,),
        ).fetchone()
        if existing:
            if existing["last_shown_date"] == today_iso:
                return dict(existing)
            box = int(existing["box"] or 1)
            interval = LEITNER_INTERVAL_DAYS.get(box, 3)
            next_due = (datetime.strptime(today_iso, "%Y-%m-%d").date() + timedelta(days=interval)).isoformat()
            conn.execute(
                "UPDATE learning_progress SET last_shown_date = ?, next_review_date = ?, "
                "times_shown = times_shown + 1, updated_at = ? WHERE word_key = ?",
                (today_iso, next_due, now_iso, word_key),
            )
        else:
            next_due = (datetime.strptime(today_iso, "%Y-%m-%d").date() + timedelta(days=2)).isoformat()
            conn.execute(
                "INSERT INTO learning_progress "
                "(word_key, word, domain, box, next_review_date, last_shown_date, times_shown, times_known, updated_at) "
                "VALUES (?, ?, ?, 1, ?, ?, 1, 0, ?)",
                (word_key, word, domain, next_due, today_iso, now_iso),
            )
        row = conn.execute("SELECT * FROM learning_progress WHERE word_key = ?", (word_key,)).fetchone()
        return dict(row) if row else None


def record_learning_feedback(word_key, word, domain, known, today_iso=None):
    """Kullanıcı kart için 'Öğrendim' (known=True) veya 'Tekrar Sor' (known=False)
    geri bildirimi verdiğinde Leitner kutusunu ve bir sonraki tekrar gününü günceller."""
    today_iso = today_iso or datetime.now(ISTANBUL_TZ).strftime("%Y-%m-%d")
    today_d = datetime.strptime(today_iso, "%Y-%m-%d").date()
    now_iso = now_istanbul_iso()

    with _connect() as conn:
        existing = conn.execute(
            "SELECT * FROM learning_progress WHERE word_key = ?",
            (word_key,),
        ).fetchone()
        cur_box = int(existing["box"]) if existing else 1
        new_box = min(5, cur_box + 1) if known else 1
        interval = LEITNER_INTERVAL_DAYS.get(new_box, 1)
        next_due = (today_d + timedelta(days=interval)).isoformat()

        if existing:
            conn.execute(
                "UPDATE learning_progress SET box = ?, next_review_date = ?, "
                "times_known = times_known + ?, updated_at = ? WHERE word_key = ?",
                (new_box, next_due, 1 if known else 0, now_iso, word_key),
            )
        else:
            conn.execute(
                "INSERT INTO learning_progress "
                "(word_key, word, domain, box, next_review_date, last_shown_date, times_shown, times_known, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
                (word_key, word, domain, new_box, next_due, today_iso, 1 if known else 0, now_iso),
            )
        return {"word_key": word_key, "box": new_box, "interval_days": interval, "next_review_date": next_due}


def sync_learning_progress_from_cloud(cloud_rows):
    """Buluttaki (D1) learning_progress kayıtlarını yerel notes.db ile eşitler.
    Yalnızca buluttaki `updated_at` zaman damgası yerelden daha yeniyse günceller."""
    if not cloud_rows:
        return 0
    updated = 0
    with _connect() as conn:
        for row in cloud_rows:
            word_key = (row.get("word_key") or "").strip()
            word = (row.get("word") or "").strip()
            if not word_key or not word:
                continue
            cloud_updated = row.get("updated_at") or ""
            local_row = conn.execute(
                "SELECT updated_at FROM learning_progress WHERE word_key = ?",
                (word_key,),
            ).fetchone()
            if local_row and (local_row["updated_at"] or "") >= cloud_updated:
                continue
            conn.execute(
                "INSERT INTO learning_progress "
                "(word_key, word, domain, box, next_review_date, last_shown_date, times_shown, times_known, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(word_key) DO UPDATE SET "
                "word = excluded.word, domain = excluded.domain, box = excluded.box, "
                "next_review_date = excluded.next_review_date, last_shown_date = excluded.last_shown_date, "
                "times_shown = excluded.times_shown, times_known = excluded.times_known, "
                "updated_at = excluded.updated_at",
                (
                    word_key,
                    word,
                    row.get("domain") or "daily",
                    int(row.get("box") or 1),
                    row.get("next_review_date") or "1970-01-01",
                    row.get("last_shown_date"),
                    int(row.get("times_shown") or 0),
                    int(row.get("times_known") or 0),
                    cloud_updated or now_istanbul_iso(),
                ),
            )
            updated += 1
    return updated
