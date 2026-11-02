// src/common.js
//
// index.js (not yönetimi) ve briefing.js (günlük brifing) arasında paylaşılan
// küçük yardımcılar.

const TELEGRAM_MAX_MESSAGE_LEN = 4000;

// note_database.now_istanbul_iso() ile uyumlu format (Türkiye 2016'dan beri
// yaz saati uygulamadan sabit UTC+3 kullanıyor, bkz. local note_database.py).
export function nowIstanbulIso() {
  const shifted = new Date(Date.now() + 3 * 60 * 60 * 1000);
  const iso = shifted.toISOString(); // "2026-10-31T17:23:45.123Z"
  return iso.replace("Z", "") + "000+03:00";
}

// Istanbul "duvar saati" tarih/saat alanlarını döner (date hesaplamaları ve
// brifing metnindeki {time} için, bkz. briefing.js).
export function istanbulNowParts() {
  const shifted = new Date(Date.now() + 3 * 60 * 60 * 1000);
  return {
    year: shifted.getUTCFullYear(),
    month: shifted.getUTCMonth() + 1,
    day: shifted.getUTCDate(),
    hour: shifted.getUTCHours(),
    minute: shifted.getUTCMinutes(),
    // Python date.weekday(): Pazartesi=0 ... Pazar=6. JS getUTCDay(): Pazar=0 ... Cumartesi=6.
    weekdayMon0: (shifted.getUTCDay() + 6) % 7,
  };
}

// telegram_notify._split_text()'in JS karşılığı — mesajı, mümkünse paragraf
// sınırlarından bölerek max_len karakterlik parçalara ayırır.
function splitText(text, maxLen) {
  if (text.length <= maxLen) return [text];
  const parts = [];
  let remaining = text;
  while (remaining.length > maxLen) {
    let splitAt = remaining.lastIndexOf("\n\n", maxLen);
    if (splitAt === -1) splitAt = remaining.lastIndexOf(" ", maxLen);
    if (splitAt === -1) splitAt = maxLen;
    parts.push(remaining.slice(0, splitAt).trim());
    remaining = remaining.slice(splitAt).trim();
  }
  if (remaining) parts.push(remaining);
  return parts;
}

export const MAIN_MENU_KEYBOARD = {
  keyboard: [
    [{ text: "🛒 Alışveriş Listem" }, { text: "📅 Bu Ay Takvimim" }],
    [{ text: "📌 Tüm Randevularım" }, { text: "✅ Bekleyen İşlerim" }],
    [{ text: "🗄️ Veritabanı Özeti" }, { text: "⏳ Geçen Gün Hesapla" }],
  ],
  resize_keyboard: true,
  is_persistent: true,
  input_field_placeholder: "Not yazın, soru sorun veya menüden seçin…",
};

export const BOT_COMMANDS = [
  { command: "menu", description: "📋 Hızlı seçenek menüsünü göster" },
  { command: "alisveris", description: "🛒 Alışveriş listemde ne var?" },
  { command: "takvim", description: "📅 Aylık takvimimde ne var? (Tekilleştirilmiş)" },
  { command: "randevular", description: "📌 Tüm randevularımı listele (>30 gün dahil)" },
  { command: "isler", description: "✅ Bekleyen işler listemde ne var?" },
  { command: "ozet", description: "🗄️ Veritabanı özetini ver" },
  { command: "gecengun", description: "⏳ Geçen gün hesabı sorgula" },
  { command: "brifing", description: "📰 Anlık günlük brifing al" },
];

export async function sendTelegramMessage(env, chatId, text, options = {}) {
  const url = `https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`;
  const chunks = splitText(text, TELEGRAM_MAX_MESSAGE_LEN);
  const replyMarkup = options.replyMarkup !== undefined ? options.replyMarkup : MAIN_MENU_KEYBOARD;

  for (let i = 0; i < chunks.length; i++) {
    const isLast = i === chunks.length - 1;
    const payload = { chat_id: chatId, text: chunks[i] };
    if (isLast && replyMarkup) {
      payload.reply_markup = replyMarkup;
    }
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await res.json();
    if (!result.ok) {
      console.error("Telegram sendMessage hatası:", JSON.stringify(result));
    }
  }
}

export async function editTelegramMessage(env, chatId, messageId, text, replyMarkup = null) {
  const url = `https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/editMessageText`;
  const clipped = text.length > TELEGRAM_MAX_MESSAGE_LEN ? text.slice(0, TELEGRAM_MAX_MESSAGE_LEN - 1) + "…" : text;
  const payload = {
    chat_id: chatId,
    message_id: messageId,
    text: clipped,
  };
  if (replyMarkup) {
    payload.reply_markup = replyMarkup;
  }
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const result = await res.json();
  if (!result.ok && !String(result.description || "").includes("message is not modified")) {
    console.error("Telegram editMessageText hatası:", JSON.stringify(result));
  }
  return result;
}

export async function answerCallbackQuery(env, callbackQueryId, text = "", showAlert = false) {
  const url = `https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/answerCallbackQuery`;
  const payload = { callback_query_id: callbackQueryId };
  if (text) payload.text = text;
  if (showAlert) payload.show_alert = true;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}

export async function registerBotCommandsAndWebhook(env, webhookUrl = null) {
  const baseUrl = `https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}`;
  const results = {};

  const cmdRes = await fetch(`${baseUrl}/setMyCommands`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ commands: BOT_COMMANDS }),
  });
  results.setMyCommands = await cmdRes.json();

  const menuBtnRes = await fetch(`${baseUrl}/setChatMenuButton`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      chat_id: env.TELEGRAM_CHAT_ID,
      menu_button: { type: "commands" },
    }),
  });
  results.setChatMenuButton = await menuBtnRes.json();

  if (webhookUrl && env.WEBHOOK_SECRET) {
    // Webhook'u sıfırlayıp yeniden bağlamak Telegram'ın 500 hata sonrası
    // exponential backoff cezasını anında sıfırlar ve bekleyen güncellemeleri iletir.
    await fetch(`${baseUrl}/deleteWebhook`, { method: "POST" });
    const whRes = await fetch(`${baseUrl}/setWebhook`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: webhookUrl,
        secret_token: env.WEBHOOK_SECRET,
        allowed_updates: ["message", "callback_query"],
      }),
    });
    results.setWebhook = await whRes.json();
  }

  return results;
}

const HTML_ENTITIES = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " " };

export function decodeHtmlEntities(text) {
  if (!text) return "";
  return text.replace(/&(#x?[0-9a-fA-F]+|[a-zA-Z]+);/g, (match, entity) => {
    if (entity[0] === "#") {
      const code = entity[1]?.toLowerCase() === "x" ? parseInt(entity.slice(2), 16) : parseInt(entity.slice(1), 10);
      return Number.isFinite(code) ? String.fromCodePoint(code) : match;
    }
    return HTML_ENTITIES[entity] ?? match;
  });
}

export function stripHtmlTags(text) {
  if (!text) return "";
  let out = text.replace(/<[^>]+>/g, " ");
  out = decodeHtmlEntities(out);
  out = out.replace(/\s+/g, " ").trim();
  return out;
}

export async function httpGetText(url) {
  const res = await fetch(url, { headers: { "User-Agent": "Mozilla/5.0" } });
  if (!res.ok) throw new Error(`HTTP ${res.status} — ${url}`);
  return res.text();
}

export async function httpGetJson(url) {
  const res = await fetch(url, { headers: { "User-Agent": "Mozilla/5.0" } });
  if (!res.ok) throw new Error(`HTTP ${res.status} — ${url}`);
  return res.json();
}

// --------------------------------------------------------------------------- //
// Genel ayar deposu — bkz. schema.sql app_config tablosu.
// --------------------------------------------------------------------------- //

export async function getConfigValue(db, key, fallback = null) {
  const row = await db.prepare("SELECT value FROM app_config WHERE key = ?").bind(key).first();
  return row ? row.value : fallback;
}

export async function setConfigValue(db, key, value) {
  await db
    .prepare(
      "INSERT INTO app_config (key, value, updated_at) VALUES (?, ?, ?) " +
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at"
    )
    .bind(key, value, nowIstanbulIso())
    .run();
}
