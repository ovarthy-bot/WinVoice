# Çevrimdışı İngilizce sözlük sorgulama (models/dictionary/dictionary.db,
# build_dictionary.py ile inşa edilir). lang_segmenter.py'nin cümle içindeki
# İngilizce kelimeleri ayırt etmesi için kullanılır.
#
# EnglishPractice projesinin app/backend/dictionary.py dosyasından uyarlanmıştır
# (https://github.com/recepyagmur/EnglishPractice) - kaynak veri Wiktionary
# (kaikki.org), CC BY-SA 4.0. EnglishPractice'in kendi sürümüne göre fark:
# yalnızca kelime kelime İngilizce/Türkçe ayrımı için gereken fonksiyonlar
# tutuldu (lookup/translate/explain ve bunların LLM/Ollama bağımlılıkları
# WinVoice için gereksiz, çıkarıldı); iter_turkish_glosses() yeni eklendi
# (orijinalde bu mantık dictionary.py'de değil, teacher_speech.py'deydi).
import json
import os
import re
import sqlite3
import threading

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "dictionary", "dictionary.db")
_local = threading.local()


def available() -> bool:
    return os.path.exists(DB_PATH)


def _conn() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        _local.conn = conn
    return conn


def normalize(word: str) -> str:
    word = word.strip().replace("’", "'")
    word = re.sub(r"^[^A-Za-z]+|[^A-Za-z]+$", "", word)
    return re.sub(r"'s$", "", word)


def _suffix_candidates(word: str) -> list[tuple[str, str]]:
    """Forms tablosunun kaçırabileceği düzenli İngilizce çekimler: (kök, nasıl)."""
    w = word.lower()
    rules = [
        ("ies", "y", "plural / 3rd person"), ("ied", "y", "past"), ("ves", "f", "plural"),
        ("es", "", "plural / 3rd person"), ("s", "", "plural / 3rd person"),
        ("ed", "", "past"), ("ed", "e", "past"), ("ing", "", "-ing form"), ("ing", "e", "-ing form"),
        ("er", "", "comparative"), ("est", "", "superlative"), ("ly", "", "adverb"),
    ]
    out = []
    for suffix, replacement, how in rules:
        if w.endswith(suffix) and len(w) - len(suffix) >= 2:
            stem = w[: -len(suffix)] + replacement
            out.append((stem, how))
            if len(stem) > 2 and stem[-1] == stem[-2] and suffix in ("ed", "ing", "er", "est"):
                out.append((stem[:-1], how))
    return out


# Sözlüğün ayrı bir girdi olarak listelemeyebileceği kısa kelimeler/kısaltmalar.
_COMMON = {"i", "a", "an", "the", "im", "ive", "ill", "id", "dont", "doesnt", "didnt", "isnt", "arent", "wasnt",
           "werent", "cant", "couldnt", "wont", "wouldnt", "shouldnt", "havent", "hasnt", "youre", "theyre", "were",
           "its", "lets", "thats", "whats", "ok", "okay", "yeah", "hi", "hello"}
_TEXT_WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")


def is_english_word(raw: str) -> bool:
    word = normalize(raw).lower()
    if not word or not word.isascii():  # ç, ş, ğ, ı, ö, ü -> İngilizce kelime değil
        return False
    if word.replace("'", "") in _COMMON:
        return True
    conn = _conn()
    if conn.execute("SELECT 1 FROM entries WHERE word = ? COLLATE NOCASE LIMIT 1", (word,)).fetchone():
        return True
    if conn.execute("SELECT 1 FROM forms WHERE form = ? COLLATE NOCASE LIMIT 1", (word,)).fetchone():
        return True
    return any(conn.execute("SELECT 1 FROM entries WHERE word = ? COLLATE NOCASE LIMIT 1", (stem,)).fetchone()
               for stem, _ in _suffix_candidates(word))


def english_share(text: str) -> float | None:
    """Kelimelerin İngilizce olan oranı (çevrimdışı sözlükle). Sözlük kurulu
    değilse None döner."""
    if not available():
        return None
    words = _TEXT_WORD.findall(text)
    if not words:
        return 0.0
    return sum(is_english_word(w) for w in words) / len(words)


def iter_turkish_glosses():
    """entries.tr_json sütunundaki her Türkçe çeviri kelimesini üretir.
    lang_segmenter.py bunu, bir kelimenin (İngilizce sözlükte de geçse) aynı
    zamanda yaygın bir Türkçe kelime olup olmadığını anlamak için kullanır
    (ayrı bir Türkçe sözlük kurmaya gerek kalmaz)."""
    if not available():
        return
    for (tr_json,) in _conn().execute("SELECT tr_json FROM entries"):
        for t in json.loads(tr_json):
            for w in re.findall(r"[^\W\d_]+", t.get("word", "")):
                yield w.lower()
