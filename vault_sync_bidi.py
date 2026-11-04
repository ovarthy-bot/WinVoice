# vault_sync_bidi.py
#
# HAKKIMDA (Obsidian kasası) ile Cloudflare D1'deki vault_notes tablosunu
# ÇİFT YÖNLÜ senkronize eder. ESKİ model (migrate_hakkimda_to_cloud.py'nin
# ve vault_cache.py'nin eski yorumlarının anlattığı) kasanın SADECE D1'de
# yönetildiği, yerelin donmuş bir anlık görüntü olduğu modeldi — bu artık
# GEÇERLİ DEĞİL: yerel HAKKIMDA/*.md dosyaları ve D1 ikisi de birincil kaynak
# sayılır, biri değişirse diğerine yansır.
#
# Çakışma politikası: "son yazan kazanır" — bir not hem yerelde hem D1'de
# değişmişse D1 içeriği kazanır (updated_at zaten D1'de basılan damga),
# ama kaybeden yerel içerik SESSİZCE silinmez: "<ad> (sync-conflict <ts>).md"
# olarak yerelde yedeklenir. migrate_hakkimda_to_cloud.py'nin zaten tanıdığı
# "sync-conflict" dosya adı deseni kasıtlı olarak yeniden kullanıldı, böylece
# bu yedek dosyalar bir sonraki taramada tekrar push edilmeye ÇALIŞILMAZ.
#
# Silme YAYILIR: bir not yerelde silinirse POST /vault/delete ile D1'den de
# silinir (bkz. cloudflare-worker/src/index.js handleVaultDelete); D1'de
# silinirse (vault_notes_deleted tablosundaki "mezar taşı" sayesinde)
# GET /vault/sync?since=... bunu raporlar ve yerel dosya da silinir —
# TEK istisna: silme anında yerelde henüz push edilmemiş bir düzenleme
# varsa, silme yerine düzenleme kazanır (veri kaybını önlemek için).
#
# Değişiklik tespiti: gerçek zamanlı dosya izleme (watchdog vb.) YOK —
# mevcut mimari (CloudSyncThread) tamamen poll tabanlı, bu modül de aynı
# şekilde her çağrıldığında HAKKIMDA'yı tarayıp içerik MD5'lerini son
# bilinen manifestle karşılaştırır (import_hakkimda_notes.py'nin MD5-manifest
# deseniyle AYNI fikir, ayrı bir settings.json anahtarı altında).

import hashlib
import json
import os
import re
import urllib.error
import urllib.request

import telegram_settings
import tts_engine
import vault_knowledge

VAULT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "HAKKIMDA")

# import_hakkimda_notes.py'nin "hakkimda_import_manifest" anahtarıyla
# KARIŞTIRILMAMALI — o, farklı bir tabloya (note_database.py) tek seferlik
# aktarım için kullanılan ayrı bir manifest.
_MANIFEST_KEY = "vault_bidi_sync_manifest"

_EXCLUDE_DIR_NAMES = {".obsidian", ".space", ".makemd", ".trash", "_Sistem"}
_EXCLUDE_FILENAMES = {"şifrelerim.md"}  # karşılaştırma küçük harfe çevrilerek yapılır

# cloud_sync.py'nin User-Agent notuyla AYNI neden: workers.dev'in Cloudflare
# bot-koruması, tarayıcı gibi görünmeyen isteklere 403 (error 1010) döner.
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) WinVoice-CloudSync"

# migrate_hakkimda_to_cloud.py'deki ile AYNI üst sınır — D1 batch() ve
# Worker CPU süresi için güvenli bir parti büyüklüğü.
BATCH_SIZE = 40

_CONFLICT_SUFFIX_RE = re.compile(r"\.md$", re.IGNORECASE)


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


def _is_excluded_path(rel_path):
    """D1'den PULL edilen bir not diske yazılmadan önce de aynı dışlama
    kurallarından geçirilir — D1 içeriğine "zaten temiz" diye güvenilmez
    (ör. eski bir hatadan kalma hassas/dışlanmış bir kayıt ihtimaline karşı).
    Bu guard'ın yerelde bir karşılığı yok çünkü cloud->disk yazma yolu bu
    modülden önce hiç var olmadı."""
    parts = rel_path.split("/")
    if any(p in _EXCLUDE_DIR_NAMES for p in parts[:-1]):
        return True
    filename = parts[-1] if parts else rel_path
    if filename.lower() in _EXCLUDE_FILENAMES:
        return True
    if "sync-conflict" in filename.lower():
        return True
    return False


def _file_hash(content):
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def _load_manifest():
    # settings.json'da genel anahtar-değer deposu (bkz. tts_engine.get_setting/
    # set_setting) — telegram_settings.py'nin sarmaladığı anahtarlardan biri
    # değil çünkü bu Telegram'a değil kasa senkronuna özgü, bu yüzden
    # doğrudan tts_engine üzerinden okunur/yazılır.
    return dict(tts_engine.get_setting(_MANIFEST_KEY, {}))


def _save_manifest(manifest):
    tts_engine.set_setting(_MANIFEST_KEY, manifest)


def _conflict_backup_path(abs_path):
    """Çakışmada kaybeden yerel içeriği '<ad> (sync-conflict <ts>).md' olarak
    yedekler — bu dosya adı deseni _iter_vault_files/_is_excluded_path
    tarafından zaten tanınıyor, yani bir sonraki taramada push edilmeye
    ÇALIŞILMAZ (sync loop riski yok)."""
    from datetime import datetime

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = _CONFLICT_SUFFIX_RE.sub("", abs_path)
    candidate = f"{base} (sync-conflict {ts}).md"
    i = 2
    while os.path.exists(candidate):
        candidate = f"{base} (sync-conflict {ts}-{i}).md"
        i += 1
    return candidate


def _scan_local_changes(manifest):
    """Döner: (changed_notes [{path,title,content,folder,_hash}], seen_paths,
    deleted_paths). Manifest'e henüz yazılmaz — bu çağıranın sorumluluğu,
    çünkü push başarısız olursa manifest güncellenmemeli (yoksa gönderilemeyen
    bir değişiklik 'senkronize edildi' sanılır)."""
    changed = []
    seen_paths = set()
    for abs_path in _iter_vault_files():
        rel_path = os.path.relpath(abs_path, VAULT_DIR).replace(os.sep, "/")
        seen_paths.add(rel_path)
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                raw = f.read()
        except Exception as e:
            print(f"⚠️ Okunamadı: {abs_path} ({e})")
            continue

        cleaned = vault_knowledge._clean_content(raw)
        if not cleaned:
            continue
        content_hash = _file_hash(cleaned)
        if manifest.get(rel_path) == content_hash:
            continue  # değişmemiş

        fallback_title = os.path.splitext(os.path.basename(abs_path))[0]
        title = vault_knowledge._title_from(cleaned, fallback_title)
        parts = rel_path.split("/")
        folder = parts[0] if len(parts) > 1 else ""
        changed.append({
            "path": rel_path, "title": title, "content": cleaned,
            "folder": folder, "_hash": content_hash,
        })

    deleted_paths = [p for p in manifest if p not in seen_paths]
    return changed, seen_paths, deleted_paths


def push_local_changes():
    """Yerelde değişen/yeni notları /vault/import'a, silinmiş notları
    /vault/delete'e gönderir. Döner: (pushed_count, deleted_count)."""
    if not telegram_settings.is_cloud_sync_configured():
        return 0, 0

    manifest = _load_manifest()
    changed, _seen_paths, deleted_paths = _scan_local_changes(manifest)

    worker_url = telegram_settings.get_cloud_worker_url()
    sync_secret = telegram_settings.get_cloud_sync_secret()

    pushed = 0
    for i in range(0, len(changed), BATCH_SIZE):
        batch = changed[i:i + BATCH_SIZE]
        payload = [
            {"path": n["path"], "title": n["title"], "content": n["content"], "folder": n["folder"]}
            for n in batch
        ]
        req = urllib.request.Request(
            f"{worker_url}/vault/import",
            data=json.dumps({"notes": payload}).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {sync_secret}",
                "User-Agent": _USER_AGENT,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                response.read()
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            print(f"⚠️ Yerel kasa değişiklikleri gönderilemedi: {e}")
            continue  # bu parti manifest'e YAZILMAZ, bir sonraki turda tekrar denenir
        for n in batch:
            manifest[n["path"]] = n["_hash"]
        pushed += len(batch)

    deleted = 0
    if deleted_paths:
        req = urllib.request.Request(
            f"{worker_url}/vault/delete",
            data=json.dumps({"paths": deleted_paths}).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {sync_secret}",
                "User-Agent": _USER_AGENT,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                response.read()
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            print(f"⚠️ Yerel kasa silmeleri D1'e bildirilemedi: {e}")
        else:
            for p in deleted_paths:
                manifest.pop(p, None)
            deleted = len(deleted_paths)

    _save_manifest(manifest)
    return pushed, deleted


def pull_cloud_changes():
    """D1'deki son senkronizasyondan beri değişen/silinen notları çekip
    HAKKIMDA/'ya yazar/siler. Döner: (written_count, deleted_count)."""
    if not telegram_settings.is_cloud_sync_configured():
        return 0, 0

    since = telegram_settings.get_cloud_sync_last_vault_sync_at()
    worker_url = telegram_settings.get_cloud_worker_url()
    sync_secret = telegram_settings.get_cloud_sync_secret()

    req = urllib.request.Request(
        f"{worker_url}/vault/sync?since={since}",
        headers={"Authorization": f"Bearer {sync_secret}", "User-Agent": _USER_AGENT},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError) as e:
        print(f"⚠️ Bulut kasa değişiklikleri alınamadı: {e}")
        return 0, 0

    notes = payload.get("notes", [])
    deletes = payload.get("deletes", [])
    if not notes and not deletes:
        return 0, 0

    manifest = _load_manifest()
    max_updated_at = since

    deleted = 0
    for rel_path in deletes:
        if _is_excluded_path(rel_path):
            continue
        abs_path = os.path.join(VAULT_DIR, rel_path.replace("/", os.sep))
        if os.path.exists(abs_path):
            with open(abs_path, "r", encoding="utf-8") as f:
                local_raw = f.read()
            local_cleaned = vault_knowledge._clean_content(local_raw)
            local_hash = _file_hash(local_cleaned) if local_cleaned else None
            if manifest.get(rel_path) == local_hash:
                # Yerelde push edilmemiş bir değişiklik yok — silme uygulanır.
                os.remove(abs_path)
                deleted += 1
            # else: yerelde bekleyen bir düzenleme var — silme yerine
            # düzenleme kazanır (dosya silinmez), bir sonraki
            # push_local_changes() bu notu D1'de "diriltir".
        manifest.pop(rel_path, None)

    written = 0
    for note in notes:
        rel_path = note["path"]
        if _is_excluded_path(rel_path):
            continue
        abs_path = os.path.join(VAULT_DIR, rel_path.replace("/", os.sep))
        cloud_hash = _file_hash(note["content"])

        if os.path.exists(abs_path):
            with open(abs_path, "r", encoding="utf-8") as f:
                local_raw = f.read()
            local_cleaned = vault_knowledge._clean_content(local_raw)
            local_hash = _file_hash(local_cleaned) if local_cleaned else None

            if local_hash == cloud_hash:
                # D1'deki içerik yereldekiyle (temizlenmiş hâliyle) ZATEN
                # aynı — bu notun aslında yeni bir değişikliği yok, sadece
                # az önce biz push ettiğimiz için /vault/sync listesinde
                # geri geldi (ya da ilk pull'da tüm tablo döndüğü için
                # göründü). Dosyayı YAZMIYORUZ: aksi halde yerel dosyanın
                # orijinal biçimlendirmesi (frontmatter, [[wikilink]]'ler)
                # D1'in temizlenmiş sürümüyle sessizce üzerine yazılır ve
                # kalıcı olarak kaybolur — bir önceki hatalı davranış buydu.
                manifest[rel_path] = cloud_hash
                if note.get("updated_at", "") > max_updated_at:
                    max_updated_at = note["updated_at"]
                continue

            if manifest.get(rel_path) != local_hash:
                # Yerelde de, D1'de de değişmiş (gerçek çakışma) — D1
                # kazanır, kaybeden yerel içerik sessizce silinmez, yedeklenir.
                backup_path = _conflict_backup_path(abs_path)
                with open(backup_path, "w", encoding="utf-8") as f:
                    f.write(local_raw)

        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(note["content"])
        manifest[rel_path] = cloud_hash
        written += 1
        if note.get("updated_at", "") > max_updated_at:
            max_updated_at = note["updated_at"]

    _save_manifest(manifest)
    telegram_settings.set_cloud_sync_last_vault_sync_at(max_updated_at)
    return written, deleted


def sync():
    """Tek bir tur: önce yerel değişiklikleri it, sonra bulut değişikliklerini
    çek. Sıra önemli — önce push edilirse, az sonra pull edilen 'since'
    penceresi (push anında D1'in bastığı updated_at, bizim eski 'since'
    değerimizden büyük olduğu için) kendi az önce gönderdiğimiz notu 'yeni
    değişiklik' diye geri getirmez."""
    pushed, local_deleted = push_local_changes()
    written, cloud_deleted = pull_cloud_changes()
    if pushed or local_deleted or written or cloud_deleted:
        print(
            f"🔄 Kasa senkronu: {pushed} not gönderildi, {local_deleted} silme bildirildi, "
            f"{written} not alındı, {cloud_deleted} dosya silindi."
        )
    return pushed, local_deleted, written, cloud_deleted


if __name__ == "__main__":
    import io
    import sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sync()
