-- D1 şeması — note_database.py'deki SQLite şemasıyla aynı yapı (bkz. o dosyadaki
-- yorumlar). Bu, buluttaki (Cloudflare D1) birincil veri deposu; WinVoice yerel
-- notes.db'si PC açıkken buradan tek yönlü senkronize olur (bkz. cloud_sync.py).

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

CREATE INDEX IF NOT EXISTS idx_notes_telegram_message_id ON notes(telegram_message_id);
CREATE INDEX IF NOT EXISTS idx_telegram_messages_chat_status ON telegram_messages(chat_id, status);

-- Küçük, nadiren değişen ayarlar için genel anahtar-değer deposu — ör.
-- persona yüzdeleri ve "Doğum Günleri ve Randevular.md" kasa dosyasının ham
-- içeriği (bkz. src/briefing.js, cloud_sync.py push_config()). WinVoice PC'de
-- açıldığında bu değerleri /config üzerinden buraya iter; bulut günlük
-- brifing üretirken en son itilen değeri kullanır.
CREATE TABLE IF NOT EXISTS app_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- HAKKIMDA (Obsidian kasası) notlarının bulut kopyası. Yerel HAKKIMDA/*.md
-- dosyaları ve bu tablo ÇİFT YÖNLÜ senkronize edilir (bkz. vault_sync_bidi.py):
-- biri yerelde düzenlerse POST /vault/import, D1'de değişirse GET
-- /vault/sync?since=... ile yerele iner. WinVoice (vault_knowledge.py /
-- personal_context.py) ayrıca bunu salt-okunur bir RAG önbelleğine de çeker
-- (bkz. vault_cache.py, cloud_sync.py).
CREATE TABLE IF NOT EXISTS vault_notes (
    path TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    folder TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- vault_notes'tan silinen notların "mezar taşı" kaydı. Silme işlemi bir
-- satırı yok ederken bu bilgiyi de kaybeder; GET /vault/sync?since=...
-- çağıran taraf "bu path artık yok" bilgisini SADECE bu tablo üzerinden
-- öğrenebilir (bkz. handleVaultDelete, handleVaultSync içindeki deletes
-- sorgusu). Bir path yeniden eklenirse (handleVaultImport) buradaki kaydı
-- temizler — diriltilen bir not bir daha "silinmiş" diye raporlanmasın.
CREATE TABLE IF NOT EXISTS vault_notes_deleted (
    path TEXT PRIMARY KEY,
    deleted_at TEXT NOT NULL
);
