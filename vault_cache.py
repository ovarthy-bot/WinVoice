# vault_cache.py
#
# HAKKIMDA (Obsidian kasası) notlarının yerel, SALT OKUNUR RAG önbelleği.
# Kasa artık D1 ile HAKKIMDA/*.md arasında ÇİFT YÖNLÜ senkronize oluyor
# (bkz. vault_sync_bidi.py) — bu modül o senkronun bir PARÇASI değil, ayrı
# bir amaca hizmet ediyor: vault_knowledge.py'nin arama yapabilmesi için
# D1'in HIZLI, yerel bir salt-okunur kopyası.
#
# cloud_sync.sync_vault_from_cloud() bu tabloyu açılışta D1'den yeniden
# doldurur (bkz. dashboard_ui._start_note_management_services, vault_sync_bidi
# çağrısından HEMEN SONRA — böylece önbellek her zaman en güncel D1 verisini
# yansıtır); vault_knowledge.py ve personal_context.py SADECE buradan okur —
# internet kesilse bile sesli asistan son senkronize edilen veriyle çalışmaya
# devam eder (note_database.py'nin Telegram notları için kullandığı AYNI "D1
# birincil kaynak, yerel SQLite önbellek" deseni).
#
# PyQt5'ten bağımsızdır; sadece stdlib (sqlite3) kullanır (bkz.
# note_database.py'nin aynı gerekçesi).

import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notes.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS vault_notes (
    path TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    folder TEXT NOT NULL
);
"""


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _connect() as conn:
        conn.executescript(_SCHEMA)


def replace_all(notes):
    """Önbelleği, D1'den gelen `notes` ([{path, title, content, folder}, ...])
    listesiyle TAMAMEN değiştirir. Kasa küçük olduğu için (bkz. vault_knowledge.py
    yorumu, ~130 not) kısmi/artımlı senkronizasyona gerek yok — tek transaction
    içinde DELETE + INSERT, silinen/yeniden adlandırılan notların önbellekte
    öksüz kalmamasını da otomatik garanti eder."""
    with _connect() as conn:
        conn.execute("DELETE FROM vault_notes")
        conn.executemany(
            "INSERT INTO vault_notes (path, title, content, folder) VALUES (?, ?, ?, ?)",
            [(n["path"], n["title"], n["content"], n["folder"]) for n in notes],
        )


def get_all_notes():
    with _connect() as conn:
        rows = conn.execute("SELECT path, title, content, folder FROM vault_notes").fetchall()
        return [dict(row) for row in rows]


def get_note_by_path(path):
    with _connect() as conn:
        row = conn.execute(
            "SELECT path, title, content, folder FROM vault_notes WHERE path = ?", (path,)
        ).fetchone()
        return dict(row) if row else None
