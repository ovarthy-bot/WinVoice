// src/index.js
//
// WinVoice'un "Telegram Akıllı Not Yönetimi" modülünün bulut tarafı.
// Bilgisayar kapalıyken Telegram'a yazılan notların da ANINDA
// kategorize edilmesi için local telegram_service.py +
// note_classifier.py + note_manager.py + note_database.py
// (long-polling + Ollama + yerel SQLite) üçlüsünün burada Telegram
// WEBHOOK + Groq (ücretsiz bulut LLM) + Cloudflare D1 karşılığıdır.
//
// Mantık KASITLI OLARAK yerel Python koduyla birebir aynı tutuldu (aynı
// prompt, aynı kategori/güven kuralları, aynı açıklayıcı-soru akışı) ki
// WinVoice PC açıldığında /sync üzerinden çektiği notlar yerel akışla
// tutarlı olsun (bkz. ../README.md).

import {
  istanbulNowParts,
  nowIstanbulIso,
  sendTelegramMessage,
  registerBotCommandsAndWebhook,
} from "./common.js";
import { generateAndSendDailyBriefing, handleConfigPost } from "./briefing.js";
import { buildUnifiedQueryPrompt } from "./knowledge.js";
import {
  resolveMenuIntent,
  handleMenuIntent,
  handleCallbackQuery,
} from "./menu.js";

const CATEGORIES = ["appointment", "shopping", "reminder", "general", "query"];
const CONFIDENCES = ["high", "medium", "low"];

// Kategoriye özgü alanlar — note_classifier._CATEGORY_FIELD_MAP ile aynı eşleme.
const CATEGORY_FIELD_MAP = {
  appointment: { tarih: "appt_date", saat: "appt_time", konum: "location", ilgili_kisi: "related_person" },
  shopping: { urun_adi: "product_name", urun_miktari: "quantity" },
  reminder: { hatirlatma_zamani: "remind_at", tekrar_sikligi: "repeat_frequency" },
  general: {},
  query: {},
};

const CATEGORY_LABELS = {
  appointment: "Randevu",
  shopping: "Alışveriş",
  reminder: "Hatırlatma",
  general: "Genel Not",
};

// prompts.py NOTE_CLASSIFICATION_PROMPT ile birebir aynı metin (Python'daki
// str.format() kaçışı için kullanılan çift süslü parantezler {{ }} burada tek
// parantez olarak yazıldı; __MESSAGE_TEXT__ aşağıda gerçek mesajla değiştirilir).
const NOTE_CLASSIFICATION_PROMPT = `
Sen kullanıcının Telegram'a yazdığı serbest metin mesajları yapılandırılmış
notlara dönüştüren bir Türkçe sınıflandırma asistanısın. Görevin, mesajı
analiz edip SADECE bir JSON DİZİSİ (array) olarak cevap vermektir.

KURALLAR:
1. Mesajda birden fazla BAĞIMSIZ bilgi varsa (örn. "yarın süt alacağım, cuma
   arabayı yıkatacağım, cumartesi Ahmet'le görüşeceğim") her biri için AYRI
   bir JSON nesnesi oluştur — tek bir mesajdan birden fazla eleman dönebilir.
   Tek bir konu/bilgiyse dizide tek eleman olur.
2. Her nesnede şu alanlar MUTLAKA bulunur:
   - "kategori": SADECE "appointment" (randevu/buluşma/teslim tarihi),
     "shopping" (satın alınacak ürün), "reminder" (genel hatırlatma/yapılacak
     iş, bir tarihe/saate bağlı olsun ya da olmasın), "general" (hiçbirine
     net uymayan not) veya "query" (kullanıcı bir BİLGİ SORUYOR ya da notlarından
     bir şey hatırlamak istiyor; ör. "ne zaman...?", "kaç gün geçti?", "var mı?")
     değerlerinden biri. "query" ise not KAYDEDİLMEZ; sorunun kendisi "açıklama"ya yazılır.
   - "güven": "high" (kategori ve ana bilgi açık/net), "medium" (kategori
     muhtemel ama bazı alanlar belirsiz) veya "low" (mesaj çok belirsiz,
     kategori veya niyet net değil) değerlerinden biri.
   - "başlık": kısa (en fazla ~60 karakter), notu özetleyen bir başlık.
   - "açıklama": mesajın ilgili kısmının kendisi veya kısa bir özeti.
3. Kategoriye göre, mesajda AÇIKÇA belirtilmişse şu ek alanları da doldur;
   belirtilmemiş bir alanı ASLA TAHMİN ETME, KESİNLİKLE null bırak:
   - appointment: "tarih" ("YYYY-MM-DD" biçiminde), "saat", "konum",
     "ilgili_kisi".
   - shopping: "urun_adi", "urun_miktari".
   - reminder: "hatirlatma_zamani" (mesajda açık bir tarih varsa
     "YYYY-MM-DDTHH:MM" biçiminde; saat belirtilmemişse "09:00" kullan),
     "tekrar_sikligi" (ör. "yok", "gunluk", "haftalik", "aylik", "yillik";
     belirtilmemişse null).
   - general: ek alan yok.
   Mesajda geçmeyen kategorilerin alanlarını hiç ekleme (sadece ilgili
   kategorinin alanlarını doldur).
4. Mesaj çok belirsizse (ör. tek kelimelik, ne istediği anlaşılmayan bir
   mesaj) kategoriyi en makul tahminle doldur ama "güven"i "low" yap — yine
   de bir JSON nesnesi döndürmelisin, ASLA boş dizi döndürme ve ASLA mesajı
   yok sayma.
5. KOMUT KELİMELERİ: "ekle", "kaydet", "hatırlat", "not al" gibi komut
   kelimeleri başlığa ve açıklamaya YAZILMAZ; yalnızca asıl bilgi (ne, ne
   zaman, nerede) kaydedilir.
6. GÖRELİ TARİHLER: "yarın", "cuma", "gelecek hafta" gibi ifadeleri bugünün
   tarihine göre çöz. Bugünün tarihi: __BUGUN__
7. ÇIKTI FORMATI: Yanıtın SADECE geçerli bir JSON dizisi olmalı. Kod bloğu
   işareti (\`\`\`), açıklama, başlık veya başka hiçbir metin ekleme — ilk
   karakter "[" olmalı, son karakter "]" olmalı.

ÖRNEKLER:

Mesaj: "02.11.2026 tarihinde galley aparatını teslim etmem gerekiyor."
JSON: [{"kategori": "appointment", "güven": "high", "başlık": "Galley aparatı teslimi", "açıklama": "02.11.2026 tarihinde galley aparatını teslim etmem gerekiyor.", "tarih": "2026-11-02", "saat": null, "konum": null, "ilgili_kisi": null}]

Mesaj: "Annem için perma tarağı satın al"
JSON: [{"kategori": "shopping", "güven": "high", "başlık": "Annem için perma tarağı", "açıklama": "Annem için perma tarağı satın alınacak.", "urun_adi": "perma tarağı", "urun_miktari": null}]

Mesaj: "yarın süt alacağım, cuma arabayı yıkatacağım, cumartesi Ahmet'le görüşeceğim"
JSON: [{"kategori": "shopping", "güven": "high", "başlık": "Süt al", "açıklama": "Yarın süt alınacak.", "urun_adi": "süt", "urun_miktari": null}, {"kategori": "reminder", "güven": "medium", "başlık": "Araba yıkama", "açıklama": "Cuma günü araba yıkatılacak.", "hatirlatma_zamani": "cuma", "tekrar_sikligi": "yok"}, {"kategori": "appointment", "güven": "high", "başlık": "Ahmet ile görüşme", "açıklama": "Cumartesi Ahmet'le görüşülecek.", "tarih": "cumartesi", "saat": null, "konum": null, "ilgili_kisi": "Ahmet"}]

Mesaj: "bir şeyler var ya neyse"
JSON: [{"kategori": "general", "güven": "low", "başlık": "Belirsiz not", "açıklama": "bir şeyler var ya neyse"}]

Mesaj: "Örnek hatırlatma notum 03.11.2026 tarihinde saat 12:00'ye ekle."
JSON: [{"kategori": "reminder", "güven": "high", "başlık": "Örnek hatırlatma", "açıklama": "Örnek hatırlatma notu.", "hatirlatma_zamani": "2026-11-03T12:00", "tekrar_sikligi": "yok"}]

Mesaj: "Askere ne zaman gittim?"
JSON: [{"kategori": "query", "güven": "high", "başlık": "Askere gitme tarihi sorusu", "açıklama": "Askere ne zaman gittim?"}]

---

Mesaj: "__MESSAGE_TEXT__"
JSON:`;

// nowIstanbulIso / sendTelegramMessage artık common.js'den geliyor (briefing.js
// ile paylaşılıyor, bkz. yukarıdaki import).

// --------------------------------------------------------------------------- //
// Groq ile sınıflandırma — note_classifier.classify_message()'ın bulut karşılığı.
// Groq'tan beklenmeyen/bozuk bir yanıt gelirse ASLA exception fırlatmaz — mesajı
// tek, düşük-güvenli "general" bir nota düşürür (bkz. yerel _fallback_note).
// --------------------------------------------------------------------------- //

function fallbackNote(messageText) {
  const firstLine = (messageText || "").trim().split("\n")[0] || "";
  const title = firstLine.slice(0, 60) || "Telegram Notu";
  return [{ kategori: "general", güven: "low", başlık: title, açıklama: messageText }];
}

function extractJsonArray(raw) {
  let text = (raw || "").trim();
  if (text.startsWith("```")) {
    text = text.replace(/`/g, "");
    if (text.toLowerCase().startsWith("json")) {
      text = text.slice(4);
    }
  }
  const match = text.match(/\[[\s\S]*\]/);
  return match ? match[0] : text;
}

function normalizeItem(item) {
  if (!item || typeof item !== "object") return null;

  let category = String(item.kategori || "general").trim().toLowerCase();
  if (!CATEGORIES.includes(category)) category = "general";

  let confidence = String(item.güven || item.guven || "low").trim().toLowerCase();
  if (!CONFIDENCES.includes(confidence)) confidence = "low";

  const title = (item.başlık || item.baslik || "").trim() || "Telegram Notu";
  const description = (item.açıklama || item.aciklama || "").trim() || null;

  const extra = {};
  const fieldMap = CATEGORY_FIELD_MAP[category] || {};
  for (const [sourceKey, dbColumn] of Object.entries(fieldMap)) {
    const value = item[sourceKey];
    if (value !== null && value !== undefined && !["", "null", "none"].includes(String(value).trim().toLowerCase())) {
      extra[dbColumn] = String(value).trim();
    }
  }

  if (extra.appt_date) extra.appt_date = normalizeDate(extra.appt_date);
  if (extra.remind_at) extra.remind_at = normalizeRemindAt(extra.remind_at);

  return { category, confidence, title, description, extra };
}

// note_classifier.py'deki _normalize_date / _normalize_remind_at'in karşılığı.
// Hatırlatma zamanı 'YYYY-MM-DDTHH:MM:SS+03:00' biçimine çevrilir ki D1'deki
// `remind_at <= ?` karşılaştırması (ISO string) doğru çalışsın.
function parseDateParts(value) {
  const text = String(value);
  const toNum = (s) => (s === undefined ? null : Number(s));
  const tr = text.match(/(\d{1,2})\.(\d{1,2})\.(\d{4})(?:\D+?(\d{1,2})[:.](\d{2}))?/);
  if (tr) return { year: toNum(tr[3]), month: toNum(tr[2]), day: toNum(tr[1]), hour: toNum(tr[4]), minute: toNum(tr[5]) };
  const iso = text.match(/(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/);
  if (iso) return { year: toNum(iso[1]), month: toNum(iso[2]), day: toNum(iso[3]), hour: toNum(iso[4]), minute: toNum(iso[5]) };
  return null;
}

function isValidDate(year, month, day) {
  const d = new Date(Date.UTC(year, month - 1, day));
  return d.getUTCFullYear() === year && d.getUTCMonth() === month - 1 && d.getUTCDate() === day;
}

function pad2(n) {
  return String(n).padStart(2, "0");
}

function normalizeDate(value) {
  const p = parseDateParts(value);
  if (!p || !isValidDate(p.year, p.month, p.day)) return value;
  return `${p.year}-${pad2(p.month)}-${pad2(p.day)}`;
}

function normalizeRemindAt(value) {
  const p = parseDateParts(value);
  if (!p) return value;
  const hour = p.hour ?? 9;
  const minute = p.minute ?? 0;
  if (!isValidDate(p.year, p.month, p.day) || hour > 23 || minute > 59) return value;
  return `${p.year}-${pad2(p.month)}-${pad2(p.day)}T${pad2(hour)}:${pad2(minute)}:00+03:00`;
}

function currentDateHint() {
  const now = new Date();
  const ymd = now.toLocaleDateString("en-CA", { timeZone: "Europe/Istanbul" });
  const weekday = now.toLocaleDateString("tr-TR", { weekday: "long", timeZone: "Europe/Istanbul" });
  return `${ymd} (${weekday})`;
}

async function callGroq(env, prompt) {
  const res = await fetch("https://api.groq.com/openai/v1/chat/completions", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${env.GROQ_API_KEY}`,
    },
    body: JSON.stringify({
      model: env.GROQ_MODEL || "openai/gpt-oss-120b",
      messages: [{ role: "user", content: prompt }],
      temperature: 0.2,
    }),
  });
  const data = await res.json();
  const content = data?.choices?.[0]?.message?.content;
  if (!content) throw new Error("Groq boş yanıt döndürdü: " + JSON.stringify(data));
  return content;
}

async function classifyMessage(env, messageText) {
  if (!messageText || !messageText.trim()) return [];

  // Fonksiyon biçimli replace: mesajdaki "$&" gibi dizgiler özel anlam taşımasın.
  const prompt = NOTE_CLASSIFICATION_PROMPT
    .replace("__BUGUN__", () => currentDateHint())
    .replace("__MESSAGE_TEXT__", () => messageText);
  let rawResponse = null;
  try {
    rawResponse = await callGroq(env, prompt);
  } catch (e) {
    console.error("Groq sınıflandırma hatası:", e);
    return fallbackNote(messageText).map(normalizeItem).filter(Boolean);
  }

  let items;
  try {
    const jsonText = extractJsonArray(rawResponse);
    items = JSON.parse(jsonText);
    if (!Array.isArray(items) || items.length === 0) throw new Error("Beklenen JSON dizisi dönmedi.");
  } catch (e) {
    console.error("Groq JSON ayrıştırma hatası, genel nota düşürülüyor:", e);
    items = fallbackNote(messageText);
  }

  const normalized = items.map(normalizeItem).filter(Boolean);
  return normalized.length ? normalized : fallbackNote(messageText).map(normalizeItem).filter(Boolean);
}

// --------------------------------------------------------------------------- //
// D1 veri katmanı — note_database.py'nin bulut karşılığı (aynı şema/sorgular).
// --------------------------------------------------------------------------- //

async function insertTelegramMessage(db, chatId, rawText, updateId, messageId) {
  const receivedAt = nowIstanbulIso();
  try {
    const res = await db
      .prepare(
        "INSERT INTO telegram_messages (telegram_update_id, telegram_message_id, chat_id, raw_text, received_at) VALUES (?, ?, ?, ?, ?)"
      )
      .bind(updateId, messageId, String(chatId), rawText, receivedAt)
      .run();
    return res.meta.last_row_id;
  } catch (e) {
    const row = await db
      .prepare("SELECT id FROM telegram_messages WHERE telegram_update_id = ?")
      .bind(updateId)
      .first();
    return row ? row.id : null;
  }
}

async function getPendingClarification(db, chatId) {
  return db
    .prepare(
      "SELECT * FROM telegram_messages WHERE chat_id = ? AND status = 'awaiting_clarification' ORDER BY id DESC LIMIT 1"
    )
    .bind(String(chatId))
    .first();
}

async function markMessageStatus(db, messageId, status, clarificationQuestion) {
  await db
    .prepare("UPDATE telegram_messages SET status = ?, clarification_question = ? WHERE id = ?")
    .bind(status, clarificationQuestion ?? null, messageId)
    .run();
}

const CATEGORY_TABLES = {
  appointment: ["appointments", ["appt_date", "appt_time", "location", "related_person"]],
  shopping: ["shopping_items", ["product_name", "quantity"]],
  reminder: ["reminders", ["remind_at", "repeat_frequency", "notified_at"]],
  general: ["general_notes", []],
};

async function insertNote(db, { category, title, description, confidence, telegramMessageId, needsReview, extra }) {
  const now = nowIstanbulIso();
  const [tableName, columns] = CATEGORY_TABLES[category];

  const res = await db
    .prepare(
      "INSERT INTO notes (telegram_message_id, category, title, description, confidence, needs_review, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
    )
    .bind(telegramMessageId, category, title, description, confidence, needsReview ? 1 : 0, now, now)
    .run();
  const noteId = res.meta.last_row_id;

  if (tableName === "general_notes") {
    await db.prepare("INSERT INTO general_notes (note_id) VALUES (?)").bind(noteId).run();
  } else {
    const values = columns.map((col) => (extra && extra[col] !== undefined ? extra[col] : null));
    const placeholders = columns.map(() => "?").join(", ");
    await db
      .prepare(`INSERT INTO ${tableName} (note_id, ${columns.join(", ")}) VALUES (?, ${placeholders})`)
      .bind(noteId, ...values)
      .run();
  }
  return noteId;
}

const NOTES_SELECT = `
  SELECT n.*,
         a.appt_date, a.appt_time, a.location, a.related_person,
         s.product_name, s.quantity,
         r.remind_at, r.repeat_frequency, r.notified_at
  FROM notes n
  LEFT JOIN appointments a ON a.note_id = n.id
  LEFT JOIN shopping_items s ON s.note_id = n.id
  LEFT JOIN reminders r ON r.note_id = n.id
`;

async function getNote(db, noteId) {
  return db.prepare(NOTES_SELECT + " WHERE n.id = ?").bind(noteId).first();
}

// --------------------------------------------------------------------------- //
// note_manager.process_telegram_message() + notification_service'in bulut karşılığı.
// --------------------------------------------------------------------------- //

function buildClarifyingQuestion(unclearItems) {
  if (unclearItems.length === 1) {
    return `Şunu tam anlayamadım: "${unclearItems[0].description}" — biraz açar mısın?`;
  }
  const titles = unclearItems.map((i) => `"${i.description}"`).join(", ");
  return `Şunları tam anlayamadım: ${titles} — biraz açar mısın?`;
}

// note_manager.py'deki _answer_query'nin bulut karşılığı. D1'deki yapılandırılmış
// `notes` tablosuna EK OLARAK `vault_notes` tablosundaki 145+ HAKKIMDA kasa notunu
// (Türkçe kök bulma + IDF ağırlıklı arama ile) ve "Doğum Günleri ve Randevular.md"
// takvim kayıtlarını (deterministik gün farkı hesabıyla) birleşik olarak tarar.
async function answerQuery(env, db, question) {
  const [noteRows, vaultRows] = await Promise.all([
    db.prepare(NOTES_SELECT + " WHERE n.completed = 0 ORDER BY n.created_at DESC LIMIT 200").all(),
    db.prepare("SELECT path, title, content, folder FROM vault_notes").all(),
  ]);

  const prompt = buildUnifiedQueryPrompt(
    question,
    noteRows.results || [],
    vaultRows.results || [],
    istanbulNowParts()
  );

  try {
    const answer = (await callGroq(env, prompt)).trim();
    return answer || "Notlarımda bu konuda bir şey bulamadım.";
  } catch (e) {
    console.error("Sorgu cevaplama hatası:", e);
    return "Notlarımda bu konuda bir şey bulamadım.";
  }
}

async function saveItems(env, db, chatId, items, telegramMessageId, allowClarification) {
  const unclear = [];
  for (const item of items) {
    if (item.category === "query") {
      const answer = await answerQuery(env, db, item.description || item.title);
      await sendTelegramMessage(env, chatId, `💬 ${answer}`);
      continue;
    }
    if (item.confidence === "low" && allowClarification) {
      unclear.push(item);
      continue;
    }
    const needsReview = item.confidence === "low" || item.confidence === "medium";
    const noteId = await insertNote(db, {
      category: item.category,
      title: item.title,
      description: item.description,
      confidence: item.confidence,
      telegramMessageId,
      needsReview,
      extra: item.extra,
    });
    const savedNote = await getNote(db, noteId);
    const label = CATEGORY_LABELS[savedNote.category] || "Not";
    const reviewHint = savedNote.needs_review ? " (kategoriyi kontrol et — düşük/orta güven)" : "";
    await sendTelegramMessage(env, chatId, `✅ ${label} eklendi: ${savedNote.title}${reviewHint}`);
  }

  if (unclear.length) {
    const question = buildClarifyingQuestion(unclear);
    await sendTelegramMessage(env, chatId, `❓ ${question}`);
    await markMessageStatus(db, telegramMessageId, "awaiting_clarification", question);
  } else {
    await markMessageStatus(db, telegramMessageId, "classified");
  }
}

async function processTelegramMessage(env, db, chatId, rawText, telegramMessageId) {
  const pending = await getPendingClarification(db, chatId);

  if (pending && pending.id !== telegramMessageId && !rawText.trim().endsWith("?")) {
    const combinedText = `${rawText}\n(Bu, şu önceki belirsiz mesajın açıklaması: "${pending.raw_text}")`;
    const items = await classifyMessage(env, combinedText);
    await saveItems(env, db, chatId, items, pending.id, false);
    await markMessageStatus(db, pending.id, "classified");
    await markMessageStatus(db, telegramMessageId, "classified");
    return;
  }

  const items = await classifyMessage(env, rawText);
  await saveItems(env, db, chatId, items, telegramMessageId, true);
}

// --------------------------------------------------------------------------- //
// Hatırlatmalar — reminder_scheduler.py'nin cron tetikleyicili bulut karşılığı.
// --------------------------------------------------------------------------- //

async function checkDueReminders(env, db) {
  const nowIso = nowIstanbulIso();
  const due = await db
    .prepare(
      NOTES_SELECT +
        " WHERE n.category = 'reminder' AND r.remind_at IS NOT NULL AND r.remind_at <= ? AND r.notified_at IS NULL"
    )
    .bind(nowIso)
    .all();

  for (const note of due.results) {
    const text = `⏰ Hatırlatma: ${note.title}` + (note.description ? `\n${note.description}` : "");
    await sendTelegramMessage(env, env.TELEGRAM_CHAT_ID, text);
    await db
      .prepare("UPDATE reminders SET notified_at = ? WHERE note_id = ?")
      .bind(nowIstanbulIso(), note.id)
      .run();
  }
}

// --------------------------------------------------------------------------- //
// HTTP giriş noktaları
// --------------------------------------------------------------------------- //

function unauthorized() {
  return new Response("unauthorized", { status: 401 });
}

async function handleWebhook(request, env) {
  const secretHeader = request.headers.get("X-Telegram-Bot-Api-Secret-Token");
  if (secretHeader !== env.WEBHOOK_SECRET) {
    return unauthorized();
  }

  const update = await request.json();

  // Telegram satır içi buton tıklamaları ([✓ Tamamla], [📅 Takvim Sekmeleri])
  if (update.callback_query) {
    try {
      await handleCallbackQuery(update.callback_query, env);
    } catch (err) {
      console.error("handleCallbackQuery hatası:", err);
    }
    return new Response("ok");
  }

  const message = update.message || {};
  const chatId = String(message?.chat?.id || "");
  const text = message.text;

  // Yalnızca ayarlı chat_id'den gelen YAZILI mesajlar işlenir (bkz. yerel
  // telegram_service.py'deki aynı güvenlik kuralı).
  if (chatId !== String(env.TELEGRAM_CHAT_ID) || !text) {
    return new Response("ok");
  }

  // Menü butonu veya menü slash komutu tıklandıysa: LLM çağırmadan ve
  // veritabanını kirletmeden anında ve deterministik cevapla!
  const menuIntent = resolveMenuIntent(text);
  if (menuIntent) {
    try {
      await handleMenuIntent(menuIntent, env, env.DB, chatId, istanbulNowParts());
    } catch (err) {
      console.error("handleMenuIntent hatası:", err);
      try {
        await sendTelegramMessage(env, chatId, "⚠️ Menü işlemi sırasında bir hata oluştu: " + (err.message || String(err)));
      } catch (_) {}
    }
    return new Response("ok");
  }

  // ÖNCE ham mesajı kaydet (kaybolmama güvencesi), SONRA sınıflandır.
  const msgId = await insertTelegramMessage(env.DB, chatId, text, update.update_id, message.message_id);
  try {
    await processTelegramMessage(env, env.DB, chatId, text, msgId);
  } catch (e) {
    console.error("Not işlenemedi (mesaj yine de kayıtlı, id=" + msgId + "):", e);
    await markMessageStatus(env.DB, msgId, "error");
  }

  return new Response("ok");
}

// WinVoice'un (cloud_sync.py) PC açıldığında yeni not/mesajları çekmesi için.
// İKİ bağımsız watermark kullanılır (since_message_id, since_note_id): bir
// mesaj (açıklayıcı soru nedeniyle) önce "awaiting_clarification" olarak
// senkronize edilip notu DAHA SONRA (kullanıcı cevap verince) oluşabilir —
// o zaman notun telegram_message_id'si zaten senkronize edilmiş, "eski" bir
// mesaja işaret eder. Notları SADECE mesaj id'sine göre filtrelersek böyle bir
// not asla çekilemez; bu yüzden notlar kendi id'sine göre, mesajlar da hem
// kendi watermark'ına hem de o notların işaret ettiği (zaten geçilmiş olsa
// bile) mesaj id'lerine göre seçilir.
async function handleSync(request, env) {
  const auth = request.headers.get("Authorization") || "";
  if (auth !== `Bearer ${env.SYNC_SECRET}`) {
    return unauthorized();
  }

  const url = new URL(request.url);
  const sinceMessageId = parseInt(url.searchParams.get("since_message_id") || "0", 10) || 0;
  const sinceNoteId = parseInt(url.searchParams.get("since_note_id") || "0", 10) || 0;

  const notes = await env.DB.prepare(NOTES_SELECT + " WHERE n.id > ? ORDER BY n.id ASC LIMIT 200")
    .bind(sinceNoteId)
    .all();

  const referencedMessageIds = [...new Set(notes.results.map((n) => n.telegram_message_id))];
  let messages;
  if (referencedMessageIds.length) {
    const placeholders = referencedMessageIds.map(() => "?").join(", ");
    messages = await env.DB.prepare(
      `SELECT * FROM telegram_messages WHERE id > ? OR id IN (${placeholders}) ORDER BY id ASC LIMIT 200`
    )
      .bind(sinceMessageId, ...referencedMessageIds)
      .all();
  } else {
    messages = await env.DB.prepare("SELECT * FROM telegram_messages WHERE id > ? ORDER BY id ASC LIMIT 200")
      .bind(sinceMessageId)
      .all();
  }

  const completedRows = await env.DB.prepare(
    "SELECT n.category, n.title, m.telegram_update_id " +
      "FROM notes n " +
      "LEFT JOIN telegram_messages m ON m.id = n.telegram_message_id " +
      "WHERE n.completed = 1 " +
      "ORDER BY n.updated_at DESC LIMIT 100"
  ).all();

  return new Response(
    JSON.stringify({
      telegram_messages: messages.results,
      notes: notes.results,
      completed_notes: completedRows.results || [],
    }),
    { headers: { "Content-Type": "application/json" } }
  );
}

// --------------------------------------------------------------------------- //
// HAKKIMDA (Obsidian kasası) notlarının bulut kopyası D1'de — bkz.
// schema.sql vault_notes/vault_notes_deleted, vault_sync_bidi.py (yerel
// tarafta çift yönlü senkronu yöneten modül), vault_cache.py (RAG önbelleği).
// --------------------------------------------------------------------------- //

async function handleVaultImport(request, env) {
  const auth = request.headers.get("Authorization") || "";
  if (auth !== `Bearer ${env.SYNC_SECRET}`) {
    return unauthorized();
  }

  const body = await request.json();
  const notes = Array.isArray(body.notes) ? body.notes : [];
  const now = nowIstanbulIso();

  // D1'in tek bir prepared statement'ı tekrar tekrar .bind() ile toplu
  // çalıştırabilen batch() API'si — tek tek await'lemekten daha hızlı,
  // index.js'teki diğer akışlarda (webhook) tek satırlık yazımlar olduğu
  // için şimdiye kadar buna gerek yoktu.
  const stmt = env.DB.prepare(
    "INSERT INTO vault_notes (path, title, content, folder, updated_at) VALUES (?, ?, ?, ?, ?) " +
      "ON CONFLICT(path) DO UPDATE SET title = excluded.title, content = excluded.content, " +
      "folder = excluded.folder, updated_at = excluded.updated_at"
  );
  const batch = notes.map((n) => stmt.bind(n.path, n.title, n.content, n.folder, now));
  // Upsert edilen her path için (varsa) eski silme kaydı temizlenir —
  // "silinmiş ama sonra geri eklenmiş" durumunda /vault/sync'in deletes
  // listesi bu path'i bir daha asla döndürmemeli (bkz. vault_notes_deleted
  // yorumu, schema.sql).
  const clearTombstoneStmt = env.DB.prepare("DELETE FROM vault_notes_deleted WHERE path = ?");
  for (const n of notes) {
    batch.push(clearTombstoneStmt.bind(n.path));
  }
  if (batch.length) await env.DB.batch(batch);

  return new Response(JSON.stringify({ ok: true, imported: notes.length }), {
    headers: { "Content-Type": "application/json" },
  });
}

async function handleVaultDelete(request, env) {
  const auth = request.headers.get("Authorization") || "";
  if (auth !== `Bearer ${env.SYNC_SECRET}`) {
    return unauthorized();
  }

  const body = await request.json();
  const paths = Array.isArray(body.paths) ? body.paths : [];
  const now = nowIstanbulIso();

  // Silme işlemi iki adımlı: satır vault_notes'tan silinir VE
  // vault_notes_deleted'e bir "mezar taşı" eklenir — aksi halde GET
  // /vault/sync?since=... bu path'in artık var olmadığını hiçbir zaman
  // öğrenemez (silinen satırın kendisi bu bilgiyi taşımıyor).
  const delStmt = env.DB.prepare("DELETE FROM vault_notes WHERE path = ?");
  const tombStmt = env.DB.prepare(
    "INSERT INTO vault_notes_deleted (path, deleted_at) VALUES (?, ?) " +
      "ON CONFLICT(path) DO UPDATE SET deleted_at = excluded.deleted_at"
  );
  const batch = [];
  for (const p of paths) {
    batch.push(delStmt.bind(p));
    batch.push(tombStmt.bind(p, now));
  }
  if (batch.length) await env.DB.batch(batch);

  return new Response(JSON.stringify({ ok: true, deleted: paths.length }), {
    headers: { "Content-Type": "application/json" },
  });
}

async function handleVaultSync(request, env) {
  const auth = request.headers.get("Authorization") || "";
  if (auth !== `Bearer ${env.SYNC_SECRET}`) {
    return unauthorized();
  }

  // ?since=<ISO zaman damgası> — verilmezse tüm kasa döner (ilk senkron/
  // vault_cache.py'nin tam yenileme ihtiyacı için geriye dönük uyumlu).
  // /sync uç noktasındaki since_message_id/since_note_id ile aynı artımlı
  // çekme deseni, burada sayaç yerine updated_at/deleted_at zaman damgası
  // kullanılıyor (vault_notes'ta autoincrement id yok).
  const since = new URL(request.url).searchParams.get("since") || "1970-01-01T00:00:00.000Z";
  const notes = await env.DB.prepare(
    "SELECT path, title, content, folder, updated_at FROM vault_notes WHERE updated_at > ? ORDER BY updated_at ASC"
  )
    .bind(since)
    .all();
  const deletes = await env.DB.prepare(
    "SELECT path, deleted_at FROM vault_notes_deleted WHERE deleted_at > ? ORDER BY deleted_at ASC"
  )
    .bind(since)
    .all();

  return new Response(
    JSON.stringify({
      notes: notes.results,
      deletes: deletes.results.map((d) => d.path),
    }),
    { headers: { "Content-Type": "application/json" } }
  );
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "POST" && url.pathname === "/webhook") {
      return handleWebhook(request, env);
    }
    if (request.method === "GET" && url.pathname === "/sync") {
      return handleSync(request, env);
    }
    if (request.method === "POST" && url.pathname === "/config") {
      return handleConfigPost(request, env);
    }
    if (request.method === "POST" && url.pathname === "/vault/import") {
      return handleVaultImport(request, env);
    }
    if (request.method === "GET" && url.pathname === "/vault/sync") {
      return handleVaultSync(request, env);
    }
    if (request.method === "POST" && url.pathname === "/vault/delete") {
      return handleVaultDelete(request, env);
    }
    if (request.method === "POST" && url.pathname === "/telegram/setup-menu") {
      const auth = request.headers.get("Authorization") || "";
      if (auth !== `Bearer ${env.SYNC_SECRET}`) return unauthorized();
      const webhookUrl = `${url.origin}/webhook`;
      const setupResults = await registerBotCommandsAndWebhook(env, webhookUrl);
      await handleMenuIntent("welcome", env, env.DB, env.TELEGRAM_CHAT_ID, istanbulNowParts());
      return new Response(JSON.stringify({ ok: true, setup: setupResults }), {
        headers: { "Content-Type": "application/json" },
      });
    }
    // Normalde cron ile (her gün 09:00 UTC) tetiklenir; manuel test/anında
    // brifing istemek için SYNC_SECRET ile korunan bu uç nokta da kullanılabilir.
    if (request.method === "POST" && url.pathname === "/briefing/run") {
      const auth = request.headers.get("Authorization") || "";
      if (auth !== `Bearer ${env.SYNC_SECRET}`) return unauthorized();
      await generateAndSendDailyBriefing(env);
      return new Response(JSON.stringify({ ok: true }), { headers: { "Content-Type": "application/json" } });
    }
    return new Response("not found", { status: 404 });
  },

  // wrangler.toml'daki iki cron'u ayırt eder: her dakika çalışan hatırlatma
  // kontrolü (reminder_scheduler.py'nin bulut karşılığı) ve her gün 02:00 UTC
  // (05:00 İstanbul) çalışan günlük brifing (telegram_briefing.py'nin bulut
  // karşılığı, bkz. briefing.js).
  async scheduled(event, env) {
    if (event.cron === "0 2 * * *") {
      await generateAndSendDailyBriefing(env);
    } else {
      await checkDueReminders(env, env.DB);
    }
  },
};
