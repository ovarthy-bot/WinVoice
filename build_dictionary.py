# Çevrimdışı İngilizce->Türkçe sözlüğü (models/dictionary/dictionary.db)
# Wiktionary'den inşa eder. Tek seferlik, elle çalıştırılan bir kurulum
# betiğidir (python build_dictionary.py); uygulama açılışında OTOMATİK
# çalışmaz çünkü ~520 MB'lık bir indirme gerektirir.
#
# Kaynak: kaikki.org'un makine-okunur İngilizce Wiktionary verisi (CC BY-SA
# 4.0). ~520 MB'lık indirme akış halinde filtrelenir: sadece Türkçe çevirisi
# olan kelimeler (IPA, kısa İngilizce tanımlar ve bir örnekle birlikte)
# tutulur, ayrıca çekimli formlar ("went" -> "go") da eklenir. Ham dosya
# işlem bitince silinir (--keep-raw ile saklanabilir). Sonuç: ~13 MB,
# ~26.000 kelime + ~53.000 çekim.
#
# EnglishPractice projesinin setup/build_dictionary.py dosyasından uyarlanmıştır
# (https://github.com/recepyagmur/EnglishPractice) - mantık aynı, yalnızca
# yol sabitleri WinVoice'un kendi klasör yapısına uyarlandı.
#
# Kullanım: python build_dictionary.py [--source DOSYA] [--keep-raw]
#
# Aynı betik, lang_segmenter.py'nin _list_words() için kullandığı
# models/vocab/*.json kelime listelerini de indirir (küçük, doğrudan dosya).

import argparse
import gzip
import json
import os
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path
from typing import Callable

ROOT = Path(os.path.dirname(os.path.abspath(__file__)))
DICT_DIR = ROOT / "models" / "dictionary"
VOCAB_DIR = ROOT / "models" / "vocab"
URL = "https://kaikki.org/dictionary/English/kaikki.org-dictionary-English.jsonl.gz"
DOWNLOAD_PATH = DICT_DIR / "_downloads" / "kaikki.org-dictionary-English.jsonl.gz"
DB_PATH = DICT_DIR / "dictionary.db"
SOURCE_NOTE = "Wiktionary (kaikki.org), CC BY-SA 4.0"

VOCAB_BASE_URL = "https://raw.githubusercontent.com/recepyagmur/EnglishPractice/main/app/content/vocab/"
VOCAB_FILES = ("A1.json", "A2.json", "B1.json", "B2.json", "C1.json", "top3000.json", "README.md")

MAX_TR = 10
MAX_DEFS = 3
MAX_EXAMPLE_CHARS = 140
SKIP_TAGS = {"obsolete", "archaic", "dated", "rare", "historical"}
SKIP_FORM_TAGS = SKIP_TAGS | {"alternative", "misspelling", "nonstandard", "dialectal", "pronunciation-spelling",
                              "romanization", "abbreviation", "table-tags", "inflection-template"}
MAX_DEF_CHARS = 160

SCHEMA = """
CREATE TABLE entries (
    id INTEGER PRIMARY KEY,
    word TEXT NOT NULL,
    pos TEXT,
    ipa TEXT,
    tr_json TEXT NOT NULL,          -- [{"word", "sense"}]
    definitions_json TEXT NOT NULL, -- ["short English gloss", ...]
    example TEXT
);
CREATE TABLE forms (
    form TEXT NOT NULL,
    lemma TEXT NOT NULL,
    tags TEXT
);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
"""
INDEXES = """
CREATE INDEX idx_entries_word ON entries(word COLLATE NOCASE);
CREATE INDEX idx_forms_form ON forms(form COLLATE NOCASE);
"""

Progress = Callable[[str, float], None]


def _print_progress(stage: str, fraction: float) -> None:
    print(f"\r{stage}: {fraction * 100:5.1f}%", end="", flush=True)


def download(progress: Progress = _print_progress) -> Path:
    """Devam edebilen indirme (kesilen indirme sonraki çalıştırmada kaldığı yerden sürer)."""
    DOWNLOAD_PATH.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(urllib.request.Request(URL, method="HEAD"), timeout=30) as r:
        total = int(r.headers["Content-Length"])
    have = DOWNLOAD_PATH.stat().st_size if DOWNLOAD_PATH.exists() else 0
    if have < total:
        req = urllib.request.Request(URL, headers={"Range": f"bytes={have}-"})
        with urllib.request.urlopen(req, timeout=60) as r, open(DOWNLOAD_PATH, "ab") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
                have += len(chunk)
                progress("İndiriliyor", have / total)
    return DOWNLOAD_PATH


def download_vocab_lists() -> None:
    VOCAB_DIR.mkdir(parents=True, exist_ok=True)
    for name in VOCAB_FILES:
        dest = VOCAB_DIR / name
        if dest.exists():
            continue
        urllib.request.urlretrieve(VOCAB_BASE_URL + name, dest)
        print(f"İndirildi: {name}")


def _ipa(entry: dict) -> str | None:
    sounds = [s for s in entry.get("sounds", []) if s.get("ipa")]
    for pref in ("General-American", "US", "Received-Pronunciation", "UK"):
        for s in sounds:
            if pref in (s.get("tags") or []):
                return s["ipa"]
    return sounds[0]["ipa"] if sounds else None


def _translations(entry: dict) -> list[dict]:
    """Anlam sırasıyla Türkçe çeviriler. Çoğu her anlamın altında yaşar; eski
    girdiler en üst seviyede tutar."""
    out, seen = [], set()
    candidates = list(entry.get("translations", []))
    for sense in entry.get("senses", []):
        if SKIP_TAGS & set(sense.get("tags") or []):
            continue
        gloss = (sense.get("glosses") or [""])[-1]
        for t in sense.get("translations") or []:
            candidates.append({**t, "sense": t.get("sense") or gloss[:80]})
    for t in candidates:
        if t.get("code") != "tr" and t.get("lang_code") != "tr":
            continue
        word = (t.get("word") or "").strip()
        if not word or word.lower() in seen or SKIP_TAGS & set(t.get("tags") or []):
            continue
        seen.add(word.lower())
        out.append({"word": word, "sense": (t.get("sense") or "").strip()})
    return out[:MAX_TR]


def _shorten(gloss: str) -> str:
    if len(gloss) <= MAX_DEF_CHARS:
        return gloss
    first = gloss.split(". ")[0]
    return first if len(first) <= MAX_DEF_CHARS else first[:MAX_DEF_CHARS].rsplit(" ", 1)[0] + "…"


def _definitions(entry: dict) -> tuple[list[str], str | None]:
    defs, example = [], None
    word_stem = entry.get("word", "").lower()[:max(3, len(entry.get("word", "")) - 2)]
    for sense in entry.get("senses", []):
        if SKIP_TAGS & set(sense.get("tags") or []):
            continue
        glosses = sense.get("glosses") or []
        if glosses:
            gloss = _shorten(glosses[-1].strip())
            if gloss and gloss not in defs:
                defs.append(gloss)
        if example is None:
            for ex in sense.get("examples") or []:
                text = " ".join((ex.get("text") or "").split())
                if (ex.get("type") == "example" and 15 < len(text) <= MAX_EXAMPLE_CHARS
                        and text[-1] in ".!?\"" and word_stem in text.lower()):
                    example = text
                    break
        if len(defs) >= MAX_DEFS and example:
            break
    return defs[:MAX_DEFS], example


def _form_of(entry: dict) -> list[tuple[str, str]]:
    """Sadece bir çekimi anlatan girdiler için ("bake", "simple past") çiftleri."""
    out = []
    for sense in entry.get("senses", []):
        if SKIP_FORM_TAGS & set(sense.get("tags") or []):
            continue
        for f in sense.get("form_of") or []:
            lemma = (f.get("word") or "").strip()
            if lemma:
                gloss = (sense.get("glosses") or [""])[0]
                out.append((lemma, gloss.split(" of ")[0][:40]))
    return out


def build(source: Path, progress: Progress = _print_progress) -> dict:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = DB_PATH.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    db = sqlite3.connect(tmp)
    db.executescript(SCHEMA)
    total_bytes = source.stat().st_size
    entries = forms = lines = 0
    with open(source, "rb") as raw, gzip.open(raw, "rt", encoding="utf-8") as f:
        for line in f:
            lines += 1
            if lines % 20000 == 0:
                progress("İşleniyor", raw.tell() / total_bytes)
            e = json.loads(line)
            if e.get("lang_code") != "en":
                continue
            word = e.get("word", "")
            for lemma, tags in _form_of(e):
                if lemma.lower() != word.lower():
                    db.execute("INSERT INTO forms VALUES (?, ?, ?)", (word, lemma, tags))
                    forms += 1
            tr = _translations(e)
            if not tr:
                continue
            for form in e.get("forms") or []:
                text = (form.get("form") or "").strip()
                if SKIP_FORM_TAGS & set(form.get("tags") or []):
                    continue
                if text and " " not in text and text.lower() != word.lower():
                    db.execute("INSERT INTO forms VALUES (?, ?, ?)", (text, word, ",".join(form.get("tags") or [])))
                    forms += 1
            defs, example = _definitions(e)
            db.execute(
                "INSERT INTO entries (word, pos, ipa, tr_json, definitions_json, example) VALUES (?, ?, ?, ?, ?, ?)",
                (word, e.get("pos"), _ipa(e), json.dumps(tr, ensure_ascii=False), json.dumps(defs, ensure_ascii=False),
                 example),
            )
            entries += 1
    progress("İşleniyor", 1.0)

    db.executescript(INDEXES)
    db.execute("DELETE FROM forms WHERE lemma COLLATE NOCASE NOT IN (SELECT word FROM entries)")
    db.execute("CREATE TABLE forms_unique AS SELECT DISTINCT form, lemma, tags FROM forms")
    db.execute("DROP TABLE forms")
    db.execute("ALTER TABLE forms_unique RENAME TO forms")
    db.executescript("CREATE INDEX idx_forms_form ON forms(form COLLATE NOCASE);")
    stats = {
        "entries": db.execute("SELECT COUNT(*) FROM entries").fetchone()[0],
        "words": db.execute("SELECT COUNT(DISTINCT word) FROM entries").fetchone()[0],
        "forms": db.execute("SELECT COUNT(*) FROM forms").fetchone()[0],
    }
    for k, v in {"source": SOURCE_NOTE, "built_at": time.strftime("%Y-%m-%d"), **stats}.items():
        db.execute("INSERT INTO meta VALUES (?, ?)", (k, str(v)))
    db.commit()
    db.execute("VACUUM")
    db.close()
    os.replace(tmp, DB_PATH)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, help="Zaten indirilmiş .jsonl.gz")
    parser.add_argument("--keep-raw", action="store_true")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    print("Kelime listeleri indiriliyor...")
    download_vocab_lists()

    source = args.source or download()
    print()
    started = time.time()
    stats = build(source)
    size_mb = DB_PATH.stat().st_size / 1e6
    print(f"\nSözlük hazır: {stats['words']} kelime, {stats['entries']} kayıt, {stats['forms']} çekim, "
          f"{size_mb:.1f} MB ({time.time() - started:.0f} sn)")
    if not args.keep_raw and source == DOWNLOAD_PATH:
        source.unlink()
        print("Ham indirme dosyası silindi.")


if __name__ == "__main__":
    main()
