# migrate_hakkimda_to_cloud.py
#
# HAKKIMDA (Obsidian kasası) notlarını Cloudflare D1'deki vault_notes
# tablosuna (bkz. cloudflare-worker/schema.sql) TOPLU olarak taşır. ESKİDEN
# bu, kasayı D1'e geçirmek için TEK SEFERLİK bir araçtı; artık kasa ile D1
# vault_sync_bidi.py üzerinden ÇİFT YÖNLÜ senkronize oluyor (yerel düzenleme/
# silme D1'e, D1 düzenleme/silme yerele yansıyor) — bu script o akışın
# YERİNE geçmedi, sadece ilk kurulum / felaket kurtarma (ör. D1 sıfırdan
# oluşturulduğunda kasayı tek seferde doldurmak) için zararsız bir araç
# olarak kaldı. Normal kullanımda bunu elle çalıştırmaya gerek yoktur.
#
# import_hakkimda_notes.py'nin güvencesiyle AYNI ilke: HAKKIMDA/ altındaki
# HİÇBİR DOSYA silinmez, taşınmaz veya değiştirilmez; yalnızca okunur.
# Dışlama kuralları vault_sync_bidi.py'deki ile AYNI: Obsidian/MakeMD'nin iç
# klasörleri ve Şifrelerim.md hiçbir zaman buluta gönderilmez.
#
# Yeniden çalıştırılabilir (idempotent): /vault/import, path'e göre upsert
# yapar (bkz. index.js handleVaultImport) — ikinci bir çalıştırma sadece
# içeriği güncel olanları tekrar yazar, çift kayıt oluşturmaz.

import json
import os
import urllib.error
import urllib.request

import telegram_settings
import vault_knowledge

VAULT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "HAKKIMDA")

_EXCLUDE_DIR_NAMES = {".obsidian", ".space", ".makemd", ".trash", "_Sistem"}
_EXCLUDE_FILENAMES = {"şifrelerim.md"}  # karşılaştırma küçük harfe çevrilerek yapılır

# cloud_sync.py'nin User-Agent notuyla AYNI neden: workers.dev'in Cloudflare
# bot-koruması, tarayıcı gibi görünmeyen isteklere 403 (error 1010) döner.
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) WinVoice-CloudSync"

# Tek istekte gönderilen not sayısı — D1 batch() ve Worker CPU süresi için
# küçük, güvenli bir üst sınır (kasa ~130 not, bu da 4-5 istek demek).
BATCH_SIZE = 40


def _iter_vault_files():
    for root, dirs, files in os.walk(VAULT_DIR):
        dirs[:] = [d for d in dirs if d not in _EXCLUDE_DIR_NAMES]
        for fn in files:
            if not fn.lower().endswith(".md"):
                continue
            if "sync-conflict" in fn.lower():
                continue
            if fn.lower() in _EXCLUDE_FILENAMES:
                continue
            yield os.path.join(root, fn)


def collect_notes():
    """Göç edilecek notları [{path, title, content, folder}, ...] olarak
    döner. İçerik/başlık temizliği vault_knowledge.py'deki (_clean_content/
    _title_from) AYNI mantıkla yapılır — D1'deki içerik, önceki yerel RAG
    aramasının gördüğü içerikle birebir aynı olsun diye."""
    notes = []
    for path in _iter_vault_files():
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = f.read()
        except Exception as e:
            print(f"⚠️ Okunamadı: {path} ({e})")
            continue

        cleaned = vault_knowledge._clean_content(raw)
        if not cleaned:
            continue

        fallback_title = os.path.splitext(os.path.basename(path))[0]
        title = vault_knowledge._title_from(cleaned, fallback_title)

        rel_path = os.path.relpath(path, VAULT_DIR).replace(os.sep, "/")
        parts = rel_path.split("/")
        folder = parts[0] if len(parts) > 1 else ""

        notes.append({"path": rel_path, "title": title, "content": cleaned, "folder": folder})
    return notes


def _post_batch(worker_url, sync_secret, notes_batch):
    req = urllib.request.Request(
        f"{worker_url}/vault/import",
        data=json.dumps({"notes": notes_batch}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {sync_secret}",
            "User-Agent": _USER_AGENT,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def run_migration():
    if not telegram_settings.is_cloud_sync_configured():
        print("❌ Bulut senkronizasyonu ayarlanmamış (worker URL / sync secret eksik). Önce telegram_settings ile ayarlayın.")
        return 0

    worker_url = telegram_settings.get_cloud_worker_url()
    sync_secret = telegram_settings.get_cloud_sync_secret()

    notes = collect_notes()
    print(f"📂 {len(notes)} not bulundu, Cloudflare D1'e gönderiliyor...")

    total_imported = 0
    for i in range(0, len(notes), BATCH_SIZE):
        batch = notes[i : i + BATCH_SIZE]
        try:
            result = _post_batch(worker_url, sync_secret, batch)
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            print(f"❌ Parti {i // BATCH_SIZE + 1} gönderilemedi: {e}")
            continue
        imported = result.get("imported", 0)
        total_imported += imported
        print(f"  ✅ Parti {i // BATCH_SIZE + 1}: {imported} not")

    print(f"✅ Göç tamamlandı: toplam {total_imported}/{len(notes)} not Cloudflare D1'e aktarıldı.")
    return total_imported


if __name__ == "__main__":
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    run_migration()
