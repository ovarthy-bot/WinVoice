# Türkçe cümle içindeki İngilizce kelime/ifadeleri ayırt eder, böylece
# tts_engine.py her parçayı doğru sesle (Türkçe parçaları EMA/pyttsx3,
# İngilizce parçaları Kokoro ile) okutabilir.
#
# EnglishPractice projesinin app/backend/teacher_speech.py dosyasından
# uyarlanmıştır (https://github.com/recepyagmur/EnglishPractice). Fark:
# öğretmenin "- İngilizce cümle (Türkçe çevirisi)" madde-işareti biçimine
# özel ayrıştırma (EXAMPLE regex'i ve segments()'teki bullet dalı) kaldırıldı
# — WinVoice'ta asistan cevapları bu biçimde gelmiyor, her satır doğrudan
# _inline() ile işleniyor. _turkish_words(), orijinalde dictionary._conn()'a
# doğrudan eriştiği yerde artık english_dictionary.iter_turkish_glosses()
# kullanıyor.
import json
import os
import re
import threading

import english_dictionary

VOCAB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "vocab")
VOCAB_FILES = ("A1.json", "A2.json", "B1.json", "B2.json", "C1.json", "top3000.json")

TURKISH_LETTERS = re.compile(r"[çğıöşüÇĞİÖŞÜ]")
QUOTED = re.compile(r"\*\*(.+?)\*\*|\"([^\"]+)\"|“([^”]+)”")
TOKEN = re.compile(r"([^\W\d_]+(?:['’][^\W\d_]+)*)|([^\w]+|\d+)")

_turkish: set | None = None
_english_lists: set | None = None
_lock = threading.Lock()


def _list_words() -> set:
    """models/vocab/*.json'daki seviye kelime listeleri: sözlüğün
    kaçırabileceği İngilizce kelimeler ("homework" gibi)."""
    global _english_lists
    with _lock:
        if _english_lists is None:
            words = set()
            for name in VOCAB_FILES:
                path = os.path.join(VOCAB_DIR, name)
                if not os.path.exists(path):
                    continue
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    words.update(w["w"].lower() for w in data.get("words", []))
                except Exception:
                    continue
            _english_lists = words
    return _english_lists


def _turkish_words() -> set:
    """İngilizce->Türkçe sözlüğün Türkçe çevirilerinden türetilen, yaygın
    Türkçe kelimeler kümesi (ayrı bir Türkçe sözlüğe gerek kalmadan)."""
    global _turkish
    with _lock:
        if _turkish is None:
            _turkish = set(english_dictionary.iter_turkish_glosses())
    return _turkish


def _word_kind(word: str) -> str:
    """"en": sadece İngilizce; "amb": her iki dilde de var ("do", "a", "for",
    "son"); "tr": diğer her şey — Türkçe harfler, Türkçe kelimeler ve hiçbir
    tarafın bilmediği kelimeler (çoğunlukla çekimli Türkçe: "demelisin")."""
    w = word.lower().replace("’", "'")
    if TURKISH_LETTERS.search(word):
        return "tr"
    english = english_dictionary.is_english_word(w) or w in _list_words()
    turkish = w in _turkish_words() or w.split("'")[0] in _turkish_words()
    if english:
        return "amb" if turkish else "en"
    return "tr"


def _english_text(text: str) -> bool:
    if TURKISH_LETTERS.search(text):
        return False
    share = english_dictionary.english_share(text)
    return share is not None and share >= 0.5


def _plain(text: str, out: list) -> None:
    """Alıntı olmayan metin, kelime kelime (İngilizce kök + Türkçe ek:
    "since'den" -> since + den)."""
    for word, other in TOKEN.findall(text):
        if not word:
            out.append([None, other])
            continue
        base, apostrophe, suffix = word.replace("’", "'").partition("'")
        kind = _word_kind(word)
        if kind != "en" and apostrophe and _word_kind(base) == "en":
            out += [["en", base], ["tr", suffix]]
        else:
            out.append([kind, word])


def _resolve(items: list) -> None:
    """Her iki dilde de olan bir kelime, komşularının dilini alır: her iki
    taraftaki en yakın belirlenmiş kelime İngilizce (ya da bir taraf satır
    sonu) ise İngilizce."""
    words = [i for i, (kind, _) in enumerate(items) if kind is not None]
    decided = [items[i][0] if items[i][0] != "amb" else None for i in range(len(items))]
    for n, i in enumerate(words):
        if items[i][0] != "amb":
            continue
        left = next((decided[j] for j in reversed(words[:n]) if decided[j]), None)
        right = next((decided[j] for j in words[n + 1:] if decided[j]), None)
        items[i][0] = "en" if {left, right} <= {"en", None} and "en" in (left, right) else "tr"


def _inline(text: str, out: list) -> None:
    items, pos = [], 0
    for m in QUOTED.finditer(text):
        _plain(text[pos:m.start()], items)
        inner = next(g for g in m.groups() if g is not None)
        if _english_text(inner):
            items.append(["en", inner])
        else:
            _plain(inner, items)
        pos = m.end()
    _plain(text[pos:], items)
    _resolve(items)
    out += items


def segments(reply: str) -> list[dict]:
    """[{"lang": "tr" | "en", "text"}] okunma sırasıyla. Sözlük henüz
    kurulmadıysa (english_dictionary.available() False), tüm metin tek bir
    Türkçe segment olarak döner — mevcut davranış değişmez."""
    if not english_dictionary.available():
        return [{"lang": "tr", "text": reply}] if reply.strip() else []

    out: list = []
    for raw in reply.split("\n"):
        line = raw.strip()
        if not line:
            continue
        _inline(line, out)
        out.append([None, "\n"])

    merged: list = []
    for lang, text in out:
        if lang is None:
            if merged:
                merged[-1][1] += " " if text == "\n" else text
            continue
        if merged and merged[-1][0] == lang:
            merged[-1][1] += text
        else:
            merged.append([lang, text])

    result = []
    for lang, text in merged:
        text = re.sub(r"\s+", " ", text.replace("**", "")).strip()
        if re.search(r"[^\W\d_]|\d", text):
            result.append({"lang": lang, "text": text})
    return result
