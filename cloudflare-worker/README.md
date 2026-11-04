# WinVoice Telegram Not Yönetimi — Bulut Tarafı (Cloudflare Workers + D1 + Groq)

Bu klasör, bilgisayar kapalıyken de Telegram'a yazılan notların ANINDA
kategorize edilmesini sağlayan bulut servisidir. Mimari:

```
Telegram (webhook) → Cloudflare Worker → Groq (ücretsiz LLM, sınıflandırma)
                                       → Cloudflare D1 (kalıcı depo)
                                       → Telegram (onay / hatırlatma mesajı)

Cron Trigger (her dakika) → Worker → D1'den zamanı gelen hatırlatmalar → Telegram
```

PC açıldığında WinVoice (`cloud_sync.py`) `/sync` uç noktasından yeni
not/mesajları çekip yerel `notes.db`'ye yazar; Dashboard'da tüm notlar
(bulutta veya PC açıkken eklenmiş olsun) tek listede görünür.

> Önemli: Bu kuruluma geçtiğinizde yerel `telegram_service.py` (long-polling)
> ve `reminder_scheduler.py` artık dashboard'dan BAŞLATILMAZ — aynı bot için
> Telegram long-polling ve webhook birlikte çalışamaz, ve hatırlatmalar artık
> buluttaki cron tetikleyici tarafından (PC açık/kapalı fark etmeksizin)
> gönderilir.

## Kurulum

### 0) Gereksinimler
- Node.js kurulu olmalı (bu makinede zaten var).
- Ücretsiz bir [Cloudflare hesabı](https://dash.cloudflare.com/sign-up).
- Ücretsiz bir [Groq API key](https://console.groq.com/keys) (Google/GitHub ile
  anında kayıt olunabilir, kredi kartı istemez).
- Mevcut Telegram bot token'ınız (settings.json'daki `telegram_bot_token`) ve
  chat_id'niz (`telegram_chat_id`).

### 1) Cloudflare'e giriş
```bash
cd cloudflare-worker
npx wrangler login
```
Tarayıcı açılır, Cloudflare hesabınızla onaylayın.

### 2) D1 veritabanını oluştur
```bash
npx wrangler d1 create winvoice-notes
```
Çıktıda görünen `database_id` değerini kopyalayıp `wrangler.toml` dosyasındaki
`REPLACE_WITH_D1_DATABASE_ID` yerine yapıştırın.

### 3) Şemayı uygula
```bash
npx wrangler d1 execute winvoice-notes --remote --file=schema.sql
```

### 4) Gizli bilgileri (secrets) ekle
Her komut çalıştırıldığında terminalden değeri yapıştırmanız istenir
(ekrana yazılmaz, `wrangler.toml`'a da YAZILMAZ — git'e commitlenmez):
```bash
npx wrangler secret put TELEGRAM_BOT_TOKEN
npx wrangler secret put TELEGRAM_CHAT_ID
npx wrangler secret put GROQ_API_KEY
npx wrangler secret put WEBHOOK_SECRET
npx wrangler secret put SYNC_SECRET
```
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`: settings.json'dakiyle AYNI değerler.
- `GROQ_API_KEY`: console.groq.com/keys'den aldığınız key.
- `WEBHOOK_SECRET`: kendiniz üretin — rastgele uzun bir metin (ör.
  `openssl rand -hex 32` veya herhangi bir şifre üreteci). Telegram'ın
  gönderdiği her isteğin gerçekten Telegram'dan geldiğini doğrular.
- `SYNC_SECRET`: `/sync` uç noktasını korumak için başka bir rastgele metin
  (WinVoice tarafında `telegram_settings`'e aynısını gireceksiniz).

### 5) Deploy et
```bash
npx wrangler deploy
```
Çıktıda `https://winvoice-telegram-notes.<hesabınız>.workers.dev` gibi bir URL
göreceksiniz — bunu not edin, WinVoice ayarlarına gireceksiniz.

### 6) Telegram webhook'unu ayarla
Kendi bot token'ınız, 5. adımdaki Worker URL'niz ve 4. adımda belirlediğiniz
`WEBHOOK_SECRET` ile (terminalde, tarayıcıda DEĞİL — token URL'de görünür):
```bash
curl -X POST "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook" \
  -d "url=https://<worker-url>/webhook" \
  -d "secret_token=<WEBHOOK_SECRET>"
```
Yanıtta `"ok":true` görmelisiniz. Bu noktadan sonra bota yazdığınız her mesaj
doğrudan Worker'a gider — yerel `telegram_service.py` artık mesaj görmez.

### 7) WinVoice'u bulut URL'si ve SYNC_SECRET ile ayarla
Dashboard > Ayarlar'dan (veya doğrudan) `telegram_settings.set_cloud_worker_url(...)`
ve `telegram_settings.set_cloud_sync_secret(...)` ile 5. ve 4. adımdaki değerleri
girin. Ayrıntı: bkz. proje köküne eklenen `cloud_sync.py`.

## Günlük Brifing (bulutta, Groq ile)

`src/briefing.js`, yerel `telegram_briefing.py` + `briefing_data.py` +
`briefing_text.py` + `persona_settings.py` + `tr_dates.py` + `tr_numbers.py`
+ `personal_context.py`'nin (sadece `build_reminder_block` kısmı) birebir
JS portudur — tek fark, yerel Ollama (`gemma3:4b`) yerine aynı Groq modelini
kullanması (bulutun kullandığı `openai/gpt-oss-120b` model, not
sınıflandırmasından çok daha büyük olduğu için brifing kalitesi artar,
düşmez).

- **Otomatik gönderim**: her gün 02:00 UTC (= 05:00 İstanbul, Türkiye sabit
  UTC+3 kullandığı için) `wrangler.toml`'daki `"0 2 * * *"` cron'u tetikler.
- **Kişisel hatırlatmalar**: "Kişisel hatırlatmalara gelirsek..." paragrafı
  (doğum günü/ödeme/randevu), `HAKKIMDA/50_Rutinler/Doğum Günleri ve
  Randevular.md` dosyasına dayanır. Bulutun bu dosyaya erişimi olmadığı için
  WinVoice her başladığında (`dashboard_ui.py` → `cloud_sync.push_config()`)
  dosyanın ham içeriğini + persona yüzdelerini `POST /config` ile
  `app_config` D1 tablosuna iter. Bu veri nadiren değiştiği için PC günler
  sonra açılsa bile brifing pratikte güncelliğini korur.
- **Manuel test**: `POST /briefing/run` (SYNC_SECRET ile korunur) brifingi
  anında üretip Telegram'a gönderir — cron'u 09:00'a kadar beklemeden test
  etmek için:
  ```bash
  curl -X POST "https://<worker-url>/briefing/run" -H "Authorization: Bearer <SYNC_SECRET>"
  ```
- **Önemli Etkinlikler** (`src/events.js`, yerel karşılığı `events_data.py`):
  film/maç/fuar/fırlatma/indirim günü/astronomi gibi dış dünya etkinliklerini
  ÖNCELİK PUANIYLA (High/Medium) etiketleyip sadece eşiği (varsayılan: sadece
  High) geçenleri brifinge ekler — bilgi bombardımanı olmasın diye. Gerekli
  (opsiyonel) secret'lar:
  ```bash
  npx wrangler secret put TMDB_API_KEY       # themoviedb.org'dan ücretsiz key
  npx wrangler secret put FOOTBALL_API_KEY   # RapidAPI "API-Football" ücretsiz katman key'i
  ```
  Bu key'ler ayarlı değilse ilgili kaynaklar (film/futbol) sessizce boş döner,
  diğer kaynaklar (fırlatma, Tüyap, indirim günleri, astronomi — hiçbiri key
  gerektirmez) normal çalışır. Eşik, `briefing_events_min_priority` ayarı
  (`telegram_settings.py` ↔ `app_config` D1 tablosu, persona yüzdeleriyle
  aynı `POST /config` yoluyla PC açıldığında senkronize edilir) ile
  `"high"`/`"medium"` arasında değiştirilebilir.

Not: Dashboard'un kendi sesli (TTS) brifing kartı ve `telegram_briefing.py`
betiği (manuel/Görev Zamanlayıcı ile çalıştırılabilir) hâlâ yerel Ollama
kullanır — bu bilerek değiştirilmedi, zaten PC açık olmayı gerektiren bir
özellik.

## Webhook'tan geri dönüş (opsiyonel)
Tekrar yerel long-polling'e dönmek isterseniz:
```bash
curl "https://api.telegram.org/bot<BOT_TOKEN>/deleteWebhook"
```
ve dashboard_ui.py'de `_start_note_management_services`'i eski haline getirin.

## HAKKIMDA (Obsidian kasası) — D1 ile çift yönlü senkron

HAKKIMDA kasası (`HAKKIMDA/*.md`) ve `vault_notes` D1 tablosu artık ÇİFT
YÖNLÜ senkronize oluyor (bkz. `vault_sync_bidi.py`), sadece PC her açıldığında
(periyodik arka plan taraması yok):

- **Yerel → D1**: `POST /vault/import` ile değişen/yeni notlar upsert edilir
  (path'e göre, yeniden çalıştırılabilir); yerelde silinen notlar
  `POST /vault/delete` ile D1'den de silinir (bkz. `vault_notes_deleted`
  "mezar taşı" tablosu — silinen path bir süre sonra tekrar eklenirse
  silme kaydı otomatik temizlenir).
- **D1 → Yerel**: `GET /vault/sync?since=<ISO zaman damgası>` son
  senkrondan beri değişen/silinen notları döner; değişenler `HAKKIMDA/`
  altına yazılır, silinenler yereldeki karşılık gelen `.md` dosyasıyla
  birlikte kaldırılır.
- **Çakışma politikası**: aynı not hem yerelde hem D1'de değişmişse D1
  kazanır, ama kaybeden yerel içerik `<ad> (sync-conflict <ts>).md` olarak
  yedeklenir — hiçbir içerik sessizce kaybolmaz. Yerelde bekleyen (henüz
  push edilmemiş) bir düzenleme varken D1'den silme geldiyse, silme yerine
  düzenleme kazanır (not bir sonraki push'ta D1'de "dirilir").
- **Manuel D1 düzenlemesi** hâlâ mümkün (artık geriye uyumlu, çünkü bir
  sonraki PC açılışında otomatik yerele iner), ör.:
  ```bash
  npx wrangler d1 execute winvoice-notes --remote --command="UPDATE vault_notes SET content = 'yeni içerik', updated_at = datetime('now') WHERE path = '50_Rutinler/Doğum Günleri ve Randevular.md'"
  ```
- **İlk kurulum / felaket kurtarma**: `python migrate_hakkimda_to_cloud.py`
  — kasanın tamamını D1'e toplu yükler (idempotent upsert). Normal
  kullanımda gerekmez, çift yönlü senkron bunu zaten kapsar.
- Ayrıca `vault_cache.py` (RAG arama önbelleği) her PC açılışında
  (`dashboard_ui.py` → `cloud_sync.sync_vault_from_cloud()`), çift yönlü
  senkrondan hemen sonra tazelenir.

## Geliştirirken
```bash
npx wrangler tail          # canlı logları izle
npx wrangler d1 execute winvoice-notes --remote --command="SELECT * FROM notes ORDER BY id DESC LIMIT 10"
```
