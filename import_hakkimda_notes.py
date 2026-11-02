# import_hakkimda_notes.py
#
# HAKKIMDA kasasındaki (Obsidian) iki kaynaktan Not Yönetimi'nin yeni SQLite
# deposuna TEK SEFERLİK, SALT OKUNUR bir aktarım yapar:
#   1. HAKKIMDA/00_Gelen_Kutusu/*.md — serbest metin hızlı notlar. Telegram'dan
#      gelenlerle AYNI note_classifier.classify_message() ile sınıflandırılır
#      (tutarlılık için — iki ayrı sınıflandırma mantığı icat edilmedi).
#   2. HAKKIMDA/50_Rutinler/Doğum Günleri ve Randevular.md — yapılandırılmış
#      tablo. personal_context.py'nin ZATEN var olan ayrıştırma/tarih
#      hesaplama mantığı yeniden kullanılır (LLM'e gidilmez — bu dosyadaki
#      tarih hesaplamaları personal_context.py'de de deterministik yapılır).
#
# ÖNEMLİ GÜVENCELER:
#   - HAKKIMDA/ altındaki HİÇBİR DOSYA silinmez, taşınmaz veya değiştirilmez;
#     yalnızca okunur. vault_knowledge.py / personal_context.py / eski
#     telegram_inbox.py akışı bu script'ten ETKİLENMEZ, aynen çalışmaya
#     devam eder.
#   - İdempotenttir: her dosyanın içerik özeti (hash) settings.json'da küçük
#     bir "manifest" olarak tutulur (bkz. telegram_last_update_id'nin aynı
#     settings.json üzerinden tutulma deseni); değişmemiş bir dosya tekrar
#     çalıştırıldığında ikinci kez içe aktarılmaz.
#   - Kapsam BİLİNÇLİ OLARAK SINIRLI tutuldu: HAKKIMDA/90_Arşiv/ (eski/terk
#     edilmiş sistem) ve diğer konu klasörleri (10_Kişiler, 20_Yerler, 30_İş,
#     40_Teknoloji, 60_Öğrenme, 70_Yaşam) kapsam DIŞI — bunlar eyleme
#     geçirilebilir "not" değil, serbest referans notları; appointment/
#     shopping/reminder/general şemasına doğal olarak oturmuyorlar.
#   - BİLİNEN SINIRLAMA: Doğum Günleri ve Randevular.md'deki tekrarlı
#     (yıllık/aylık) kayıtlar için hesaplanan "bir sonraki gerçekleşme"
#     tarihi, aktarım anında DONDURULUR (snapshot). Orijinal .md dosyası
#     hâlâ canlı/güncel kalır (personal_context.py sesli sorgularda onu
#     okumaya devam eder); SQLite'daki kopya ise zamanla eskiyebilir. Bu
#     script tek seferlik bir kopya oluşturur, sürekli senkronizasyon yapmaz.

import hashlib
import os
import re
from datetime import date

from tts_engine import get_setting, set_setting

import note_classifier
import note_database
import personal_context
import vault_cache

INBOX_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "HAKKIMDA", "00_Gelen_Kutusu")
MANIFEST_KEY = "hakkimda_import_manifest"

_FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)
_HEADING_RE = re.compile(r"^#\s+.+\n+", re.MULTILINE)


def _strip_markdown_wrapper(text):
    """telegram_inbox._note_content()'in eklediği YAML frontmatter ve
    '# Başlık' satırını soyup yalnızca gövde metnini bırakır."""
    text = _FRONTMATTER_RE.sub("", text, count=1)
    text = _HEADING_RE.sub("", text, count=1)
    return text.strip()


def _file_hash(content):
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def _load_manifest():
    return dict(get_setting(MANIFEST_KEY, {}) or {})


def _save_manifest(manifest):
    set_setting(MANIFEST_KEY, manifest)


def import_inbox_notes(llm):
    """Gelen Kutusu'ndaki her .md notu note_classifier ile sınıflandırıp
    note_database'e ekler. Döner: eklenen not sayısı."""
    if not os.path.isdir(INBOX_DIR):
        print("ℹ️ HAKKIMDA/00_Gelen_Kutusu bulunamadı, atlanıyor.")
        return 0

    manifest = _load_manifest()
    added = 0
    folder_note_name = os.path.basename(INBOX_DIR) + ".md"  # Obsidian "klasör notu"

    for filename in sorted(os.listdir(INBOX_DIR)):
        if not filename.endswith(".md") or filename == folder_note_name:
            continue
        path = os.path.join(INBOX_DIR, filename)
        manifest_key = f"inbox::{filename}"
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = f.read()
        except Exception as e:
            print(f"⚠️ Okunamadı: {filename} ({e})")
            continue

        content_hash = _file_hash(raw)
        if manifest.get(manifest_key) == content_hash:
            continue

        body = _strip_markdown_wrapper(raw)
        if not body:
            manifest[manifest_key] = content_hash
            continue

        items = note_classifier.classify_message(llm, body)
        for item in items:
            note_database.insert_note(
                category=item["category"],
                title=item["title"],
                description=item["description"],
                confidence=item["confidence"],
                telegram_message_id=None,
                needs_review=item["confidence"] in ("low", "medium"),
                extra=item["extra"],
            )
            added += 1
        print(f"📥 İçe aktarıldı: {filename} → {len(items)} not")
        manifest[manifest_key] = content_hash

    _save_manifest(manifest)
    return added


def import_appointments_table():
    """Doğum Günleri ve Randevular.md tablosunu personal_context.py'nin
    mevcut ayrıştırma/tarih çözümleme mantığıyla okuyup note_database'e
    appointment/reminder notları olarak ekler. LLM kullanılmaz (deterministik
    tarih hesaplaması için bkz. personal_context.py modül başı yorumu).
    Not artık dosya sisteminden değil, personal_context.py ile AYNI yerel
    önbellekten (vault_cache.py) okunur — bkz. o modülün güncellenmiş yorumu."""
    note = vault_cache.get_note_by_path(personal_context.REMINDERS_VAULT_PATH)
    if not note:
        print("ℹ️ Doğum Günleri ve Randevular.md bulunamadı, atlanıyor.")
        return 0

    raw = note["content"]
    content_hash = _file_hash(raw)
    manifest = _load_manifest()
    manifest_key = "appointments_table"
    if manifest.get(manifest_key) == content_hash:
        return 0

    today = date.today()
    added = 0
    for entry in personal_context._load_entries(include_db=False):
        resolved = personal_context._resolve_date(entry, today)
        if resolved is None:
            continue  # biçimi tanınmayan ya da geçmişte kalmış tek seferlik kayıt

        tur_lower = entry["tur"].lower()
        kim = entry["kim"] or "İsimsiz kayıt"
        not_ = entry["not"] or None
        iso_date = resolved.isoformat()

        if "randevu" in tur_lower:
            category = "appointment"
            extra = {"appt_date": iso_date, "related_person": kim}
            title = f"{kim} randevusu"
        elif "doğum" in tur_lower:
            category = "reminder"
            extra = {"remind_at": iso_date, "repeat_frequency": "yillik"}
            title = f"{kim} doğum günü"
        elif any(k in tur_lower for k in ("ödeme", "fatura", "kredi", "aidat")):
            category = "reminder"
            extra = {"remind_at": iso_date, "repeat_frequency": entry["tekrar"] or "yok"}
            title = f"{kim} ödeme hatırlatması"
        else:
            category = "general"
            extra = {}
            title = kim or entry["tur"] or "Hatırlatma"

        note_database.insert_note(
            category=category, title=title, description=not_,
            confidence="high", telegram_message_id=None, needs_review=False, extra=extra,
        )
        added += 1

    manifest[manifest_key] = content_hash
    _save_manifest(manifest)
    print(f"📅 İçe aktarıldı: Doğum Günleri ve Randevular.md → {added} kayıt")
    return added


def run_import(llm):
    note_database.init_db()
    total = import_inbox_notes(llm) + import_appointments_table()
    print(f"✅ HAKKIMDA içe aktarımı tamamlandı: toplam {total} not eklendi.")
    return total


if __name__ == "__main__":
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    from langchain_ollama.llms import OllamaLLM
    from llm_settings import get_llm_model

    run_import(OllamaLLM(model=get_llm_model()))
