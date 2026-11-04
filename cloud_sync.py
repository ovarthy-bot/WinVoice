# cloud_sync.py
#
# PC açıldığında, bilgisayar kapalıyken Cloudflare Worker (bkz.
# cloudflare-worker/) tarafından Telegram'dan alınıp Groq ile sınıflandırılmış
# ve D1'e yazılmış not/mesajları çekip yerel notes.db'ye (note_database.py)
# yazar. TEK YÖNLÜ senkronizasyondur (bulut → yerel) — tüm yeni mesajlar artık
# webhook üzerinden doğrudan buluta gittiği için yerelde ayrıca sınıflandırma
# yapılmaz, sadece zaten sınıflandırılmış sonuç kopyalanır.
#
# PyQt5'ten bağımsızdır; dashboard_ui.py'deki CloudSyncThread bunu bir arka
# plan iş parçacığından periyodik olarak çağırır (bkz. telegram_service.py'nin
# eski TelegramPollThread'i — aynı rolü artık bu üstleniyor).

import json
import urllib.error
import urllib.request

import note_database
import persona_settings
import telegram_settings
import vault_cache

# cloud_sync.py'nin User-Agent notuyla AYNI neden: workers.dev'in Cloudflare
# bot-koruması, tarayıcı gibi görünmeyen isteklere 403 (error 1010) döner.
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) WinVoice-CloudSync"

# note_database._CATEGORY_TABLES ile aynı eşleme — /sync yanıtındaki LEFT JOIN
# sütunlarından hangilerinin, hangi kategori için `extra` sözlüğüne gireceğini
# belirler.
_CATEGORY_COLUMNS = {
    "appointment": ("appt_date", "appt_time", "location", "related_person"),
    "shopping": ("product_name", "quantity"),
    "reminder": ("remind_at", "repeat_frequency", "notified_at"),
    "general": (),
}


class CloudSyncError(Exception):
    """Buluttan senkronizasyon başarısız olduğunda fırlatılır."""


def _fetch_sync_payload(since_message_id, since_note_id):
    worker_url = telegram_settings.get_cloud_worker_url()
    sync_secret = telegram_settings.get_cloud_sync_secret()
    url = f"{worker_url}/sync?since_message_id={since_message_id}&since_note_id={since_note_id}"
    # workers.dev alan adları Cloudflare'in kendi bot-koruması (WAF) arkasında;
    # urllib'in varsayılan "Python-urllib/x.y" User-Agent'ı 403 (error 1010)
    # ile engelleniyor, o yüzden normal bir tarayıcı User-Agent'ı gönderilir.
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {sync_secret}", "User-Agent": _USER_AGENT},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise CloudSyncError(f"Senkronizasyon hatası ({e.code}): {body}") from e
    except urllib.error.URLError as e:
        raise CloudSyncError(f"Worker'a bağlanılamadı: {e}") from e


def _apply_note(cloud_note, local_message_id):
    category = cloud_note["category"]
    columns = _CATEGORY_COLUMNS.get(category, ())
    extra = {col: cloud_note.get(col) for col in columns if cloud_note.get(col) is not None}

    note_id = note_database.insert_note(
        category=category,
        title=cloud_note["title"],
        description=cloud_note.get("description"),
        confidence=cloud_note["confidence"],
        telegram_message_id=local_message_id,
        needs_review=bool(cloud_note.get("needs_review")),
        extra=extra,
    )
    if cloud_note.get("completed"):
        note_database.set_completed(note_id, True)


def sync_from_cloud():
    """Son senkronizasyondan beri buluta eklenmiş tüm mesaj+notları yerel
    notes.db'ye yazar. Döner: işlenen mesaj sayısı (0 ise yeni bir şey yoktu)."""
    if not telegram_settings.is_cloud_sync_configured():
        return 0

    since_message_id = telegram_settings.get_cloud_sync_last_message_id() or 0
    since_note_id = telegram_settings.get_cloud_sync_last_note_id() or 0
    payload = _fetch_sync_payload(since_message_id, since_note_id)

    cloud_messages = payload.get("telegram_messages", [])
    cloud_notes = payload.get("notes", [])
    completed_notes = payload.get("completed_notes", [])
    newly_completed = note_database.mark_completed_from_cloud(completed_notes) if completed_notes else 0

    if not cloud_messages and not cloud_notes:
        return newly_completed

    notes_by_message = {}
    for note in cloud_notes:
        notes_by_message.setdefault(note["telegram_message_id"], []).append(note)

    highest_message_id = since_message_id
    for message in cloud_messages:
        local_message_id = note_database.insert_telegram_message(
            message["chat_id"], message["raw_text"],
            telegram_update_id=message.get("telegram_update_id"),
            telegram_message_id=message.get("telegram_message_id"),
        )
        note_database.mark_message_status(
            local_message_id, message["status"], message.get("clarification_question"),
        )
        for cloud_note in notes_by_message.get(message["id"], []):
            _apply_note(cloud_note, local_message_id)
        highest_message_id = max(highest_message_id, message["id"])

    highest_note_id = max([since_note_id] + [n["id"] for n in cloud_notes])

    telegram_settings.set_cloud_sync_last_message_id(highest_message_id)
    telegram_settings.set_cloud_sync_last_note_id(highest_note_id)
    return len(cloud_messages) + newly_completed


def push_config():
    """Günlük brifingin bulutta (bkz. cloudflare-worker/src/briefing.js)
    yerelle aynı persona tonunu kullanması için, WinVoice her başladığında
    persona yüzdelerini Worker'ın app_config tablosuna iter. ('Doğum Günleri
    ve Randevular.md' artık yerelden itilmiyor — HAKKIMDA SADECE D1'de
    yönetildiği için briefing.js bu notu doğrudan vault_notes'tan okuyor,
    bkz. sync_vault_from_cloud.) Ayarlar nadiren değiştiği için PC günler
    sonra açılsa bile veri pratikte güncel kalır — ağ hatası sessizce yutulur
    (brifing bir önceki değerlerle de çalışabilir, bu kritik bir hata
    değildir)."""
    if not telegram_settings.is_cloud_sync_configured():
        return False

    payload = {
        "persona_espri_pct": persona_settings.get_espri_pct(),
        "persona_arkadas_pct": persona_settings.get_arkadaslik_pct(),
        "briefing_events_min_priority": telegram_settings.get_briefing_events_min_priority(),
    }

    worker_url = telegram_settings.get_cloud_worker_url()
    sync_secret = telegram_settings.get_cloud_sync_secret()
    req = urllib.request.Request(
        f"{worker_url}/config",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {sync_secret}",
            "User-Agent": _USER_AGENT,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            response.read()
        return True
    except (urllib.error.HTTPError, urllib.error.URLError) as e:
        print(f"⚠️ Bulut ayarları gönderilemedi (brifing bir önceki değerlerle çalışır): {e}")
        return False


def sync_vault_from_cloud():
    """HAKKIMDA (Obsidian kasası) notlarının yerel önbelleğini (bkz.
    vault_cache.py) Cloudflare D1'deki vault_notes tablosuyla (birincil
    kaynak — kasa artık SADECE orada yönetiliyor) tamamen değiştirir.
    sync_from_cloud()'dan farklı olarak watermark/artımlı mantık yok: kasa
    küçük (~130 not) ve notlar artık sadece buluttan değiştiği için her
    seferinde tam liste çekip yerel önbelleği baştan kurmak basit ve yeterli.
    Döner: çekilen not sayısı (başarısızsa/ayarlanmamışsa 0 — ağ hatası
    sessizce yutulur, sesli asistan önbellekteki son bilinen veriyle
    çalışmaya devam eder)."""
    if not telegram_settings.is_cloud_sync_configured():
        return 0

    worker_url = telegram_settings.get_cloud_worker_url()
    sync_secret = telegram_settings.get_cloud_sync_secret()
    req = urllib.request.Request(
        f"{worker_url}/vault/sync",
        headers={"Authorization": f"Bearer {sync_secret}", "User-Agent": _USER_AGENT},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError) as e:
        print(f"⚠️ Kasa senkronizasyonu alınamadı (önbellek son bilinen veriyle çalışır): {e}")
        return 0

    notes = payload.get("notes", [])
    vault_cache.init_db()
    vault_cache.replace_all(notes)
    return len(notes)
