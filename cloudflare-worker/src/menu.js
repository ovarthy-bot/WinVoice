// src/menu.js
//
// Telegram botu için etkileşimli hızlı menü, deterministik takvim/alışveriş/iş/özet
// görünümleri ve tek dokunuşla tamamlama (inline button callback_query) yönetimi.

import {
  MAIN_MENU_KEYBOARD,
  sendTelegramMessage,
  editTelegramMessage,
  answerCallbackQuery,
  nowIstanbulIso,
  setConfigValue,
} from "./common.js";
import {
  TR_MONTHS,
  tryMakeDate,
  pad2,
  trLower,
  resolveCalendarEntries,
  extractDatesFromText,
  isStaleMetaRow,
} from "./knowledge.js";
import { generateAndSendDailyBriefing } from "./briefing.js";
import { normalizeShiftCode, renderShiftMenu, toIsoDateUtc } from "./briefing_coordinator.js";
import { recordLearningFeedbackD1 } from "./learning.js";

export const NOTES_SELECT = `
  SELECT n.*,
         a.appt_date, a.appt_time, a.location, a.related_person,
         s.product_name, s.quantity,
         r.remind_at, r.repeat_frequency, r.notified_at,
         t.due_date, t.context,
         m.telegram_update_id
  FROM notes n
  LEFT JOIN appointments a ON a.note_id = n.id
  LEFT JOIN shopping_items s ON s.note_id = n.id
  LEFT JOIN reminders r ON r.note_id = n.id
  LEFT JOIN tasks t ON t.note_id = n.id
  LEFT JOIN telegram_messages m ON m.id = n.telegram_message_id
`;

// --------------------------------------------------------------------------- //
// Menü Niyetlerini Çözümleme (Zero-LLM / Deterministik)
// --------------------------------------------------------------------------- //

export function resolveMenuIntent(rawText) {
  if (!rawText) return null;
  let text = String(rawText).trim();
  let argText = "";

  // Komut formatındaki bot etiketini temizle: "/menu@OnurBriefBot" -> "/menu"
  if (text.startsWith("/")) {
    const parts = text.split(/\s+/);
    text = parts[0].split("@")[0];
    argText = parts.slice(1).join(" ").trim();
  }

  const clean = trLower(text).trim();

  if (["/start", "/menu", "/help", "menü", "menu", "yardım", "yardim"].includes(clean)) {
    return "welcome";
  }
  if (["/vardiya", "vardiya", "vardiyam", "🛫 vardiyam"].includes(clean)) {
    if (argText) {
      const lowArg = trLower(argText);
      if (["auto", "otomatik", "sıfırla", "sifirla"].includes(lowArg)) return "shift:auto";
      const code = normalizeShiftCode(argText);
      if (code) return `shift:${code}`;
    }
    return "shift";
  }
  if (["🛒 alışveriş listem", "alışveriş listem", "alisveris listem", "/alisveris", "alisveris"].includes(clean)) {
    return "shopping";
  }
  if (["📅 bu ay takvimim", "bu ay takvimim", "/takvim", "takvim"].includes(clean)) {
    return "cal:m0";
  }
  if (["📌 tüm randevularım", "tüm randevularım", "tum randevularim", "/randevular", "randevular"].includes(clean)) {
    return "appointments";
  }
  if (["✅ bekleyen işlerim", "bekleyen işlerim", "bekleyen islerim", "/isler", "isler"].includes(clean)) {
    return "todos";
  }
  if (["🗄️ veritabanı özeti", "veritabanı özeti", "veritabani ozeti", "/ozet", "ozet"].includes(clean)) {
    return "summary";
  }
  if (["⏳ geçen gün hesapla", "geçen gün hesapla", "gecen gun hesapla", "/gecengun", "gecengun"].includes(clean)) {
    return "elapsed";
  }
  if (["/brifing", "brifing", "📰 anlık brifing", "anlık brifing", "anlik brifing"].includes(clean)) {
    return "briefing";
  }

  return null;
}

// --------------------------------------------------------------------------- //
// 1) Alışveriş Listesi Görünümü ([✓ Tamamla] Butonlu)
// --------------------------------------------------------------------------- //

export async function renderShoppingList(db) {
  const rows = await db
    .prepare(
      "SELECT n.id, s.product_name, n.title, s.quantity, n.description " +
        "FROM notes n " +
        "LEFT JOIN shopping_items s ON s.note_id = n.id " +
        "WHERE n.category = 'shopping' AND n.completed = 0 " +
        "ORDER BY n.created_at ASC"
    )
    .all();

  const cleanRows = (rows.results || []).filter((r) => !isStaleMetaRow(r));

  if (!cleanRows.length) {
    return {
      text: "🛒 Alışveriş listenizde şu an bekleyen bir ürün yok.\n\nYeni bir ürün eklemek için doğrudan buraya yazabilirsiniz (örn: \"2 litre süt al\").",
      inlineMarkup: null,
    };
  }

  const lines = cleanRows.map((r, i) => {
    const name = (r.product_name || r.title || "Ürün").trim();
    const qty = r.quantity ? ` (${r.quantity})` : "";
    const desc = r.description && trLower(r.description) !== trLower(name) ? ` — ${r.description}` : "";
    return `${i + 1}. ${name}${qty}${desc}`;
  });

  const text =
    `🛒 Alışveriş Listeniz (${cleanRows.length} ürün):\n\n` +
    lines.join("\n") +
    "\n\nTek dokunuşla tamamlandı işaretlemek için aşağıdaki butonlara dokunabilirsiniz:";

  // Telegram satır içi butonları (en fazla 10 kalem)
  const buttons = cleanRows.slice(0, 10).map((r) => {
    const rawName = (r.product_name || r.title || "Ürün").trim();
    const shortName = rawName.length > 25 ? rawName.slice(0, 24) + "…" : rawName;
    return [{ text: `✓ Tamamla: ${shortName}`, callback_data: `done:shop:${r.id}` }];
  });

  return {
    text,
    inlineMarkup: { inline_keyboard: buttons },
  };
}

// --------------------------------------------------------------------------- //
// 2) Aylık Takvim Görünümü (Sekmeli / Hızlı Geçiş Butonlu)
// --------------------------------------------------------------------------- //

export async function renderCalendarView(db, mode = "m0", todayParts) {
  const noteRows = await db
    .prepare(
      NOTES_SELECT + " WHERE n.completed = 0"
    )
    .all();

  const vaultRows = await db
    .prepare("SELECT path, title, content FROM vault_notes")
    .all();

  const todayDate = tryMakeDate(todayParts.year, todayParts.month, todayParts.day);
  const allEntries = resolveCalendarEntries(vaultRows.results || [], noteRows.results || [], todayDate);

  const curY = todayParts.year;
  const curM = todayParts.month;
  let nextY = curY;
  let nextM = curM + 1;
  if (nextM > 12) {
    nextM = 1;
    nextY += 1;
  }

  let filtered = [];
  let header = "";

  if (mode === "week") {
    header = "📅 Bu Hafta Takviminiz (Önümüzdeki 7 Gün)";
    filtered = allEntries.filter((e) => e.kalanGun >= 0 && e.kalanGun <= 7);
  } else if (mode === "m1") {
    header = `⏭️ ${TR_MONTHS[nextM - 1]} ${nextY} Ayı Takviminiz`;
    filtered = allEntries.filter(
      (e) => e.tarih.getUTCFullYear() === nextY && e.tarih.getUTCMonth() + 1 === nextM
    );
  } else if (mode === "bday") {
    header = "🎂 Yaklaşan Doğum Günleri (1 Yıllık Döngü)";
    filtered = allEntries.filter(
      (e) => trLower(e.tur).includes("doğum") && e.kalanGun >= 0 && e.kalanGun <= 366
    );
  } else if (mode === "pay") {
    header = "💳 Yaklaşan Ödemeler ve Faturalar (1 Yıllık Döngü)";
    const payWords = ["ödeme", "fatura", "kredi", "taksit", "aidat"];
    filtered = allEntries.filter(
      (e) =>
        payWords.some((k) => trLower(e.tur).includes(k) || trLower(e.kim).includes(k)) &&
        e.kalanGun >= 0 &&
        e.kalanGun <= 366
    );
  } else {
    // default: "m0" - bu ayın kalanı
    header = `📅 ${TR_MONTHS[curM - 1]} ${curY} Ayı Takviminiz (Kalan Günler)`;
    filtered = allEntries.filter(
      (e) => e.tarih.getUTCFullYear() === curY && e.tarih.getUTCMonth() + 1 === curM
    );
  }

  let body = "";
  if (!filtered.length) {
    body = "\nBu görünümde yaklaşan bir takvim kaydı bulunmuyor.\n";
  } else {
    const lines = filtered.map((e) => {
      const d = e.tarih.getUTCDate();
      const mName = TR_MONTHS[e.tarih.getUTCMonth()];
      const y = e.tarih.getUTCFullYear();
      let diffStr;
      if (e.kalanGun === 0) diffStr = "bugün";
      else if (e.kalanGun === 1) diffStr = "yarın";
      else diffStr = `${e.kalanGun} gün sonra`;

      const extra = e.not ? ` — ${e.not}` : "";
      return `• ${pad2(d)} ${mName} ${y} (${diffStr}) — [${e.tur}] ${e.kim}${extra}`;
    });
    body = "\n" + lines.join("\n") + "\n";
  }

  const text = `${header} (${filtered.length} kayıt):${body}\nFarklı bir takvim görünümüne geçmek için dokunun:`;

  const row1 = [
    { text: mode === "week" ? "• 📅 Bu Hafta •" : "📅 Bu Hafta", callback_data: "cal:week" },
    { text: mode === "m0" ? "• 📅 Bu Ay •" : "📅 Bu Ay", callback_data: "cal:m0" },
    { text: mode === "m1" ? "• ⏭️ Gelecek Ay •" : "⏭️ Gelecek Ay", callback_data: "cal:m1" },
  ];
  const row2 = [
    { text: mode === "bday" ? "• 🎂 Doğum Günleri •" : "🎂 Doğum Günleri", callback_data: "cal:bday" },
    { text: mode === "pay" ? "• 💳 Ödemeler •" : "💳 Ödemeler", callback_data: "cal:pay" },
  ];

  return {
    text,
    inlineMarkup: { inline_keyboard: [row1, row2] },
  };
}

// --------------------------------------------------------------------------- //
// 3) Tüm Randevular Listesi (>30 Gün Dahil)
// --------------------------------------------------------------------------- //

export async function renderAllAppointments(db, todayParts) {
  const noteRows = await db
    .prepare(
      NOTES_SELECT + " WHERE n.completed = 0"
    )
    .all();

  const vaultRows = await db
    .prepare("SELECT path, title, content FROM vault_notes")
    .all();

  const todayDate = tryMakeDate(todayParts.year, todayParts.month, todayParts.day);
  const allEntries = resolveCalendarEntries(vaultRows.results || [], noteRows.results || [], todayDate);

  const appointments = allEntries.filter(
    (e) => trLower(e.tur).includes("randevu") && e.kalanGun >= 0 && e.kalanGun <= 3650
  );

  if (!appointments.length) {
    return {
      text: "📌 Kayıtlı yaklaşan bir randevunuz bulunmuyor.\n\nYeni bir randevu eklemek için doğrudan buraya yazabilirsiniz (örn: \"15 Aralık saat 14:00 diş randevusu\").",
      inlineMarkup: null,
    };
  }

  const lines = appointments.map((e, i) => {
    const d = e.tarih.getUTCDate();
    const mName = TR_MONTHS[e.tarih.getUTCMonth()];
    const y = e.tarih.getUTCFullYear();
    let diffStr;
    if (e.kalanGun === 0) diffStr = "bugün";
    else if (e.kalanGun === 1) diffStr = "yarın";
    else diffStr = `${e.kalanGun} gün sonra`;

    const details = e.not ? `\n   ℹ️ ${e.not}` : "";
    return `${i + 1}. ${e.kim}\n   📅 ${pad2(d)} ${mName} ${y} (${diffStr})${details}`;
  });

  const text =
    `📌 Tüm Randevularınız (>30 Gün Dahil) (${appointments.length} randevu):\n\n` +
    lines.join("\n\n");

  return {
    text,
    inlineMarkup: null,
  };
}

// --------------------------------------------------------------------------- //
// 4) Bekleyen İşler Listesi ([✓ Tamamla] Butonlu)
// --------------------------------------------------------------------------- //

export async function renderPendingTasks(db) {
  const rows = await db
    .prepare(
      NOTES_SELECT +
        " WHERE n.category IN ('reminder', 'task') AND n.completed = 0 " +
        "ORDER BY CASE WHEN n.priority = 'high' THEN 0 ELSE 1 END, n.created_at ASC"
    )
    .all();

  const cleanRows = (rows.results || []).filter((r) => {
    if (isStaleMetaRow(r)) return false;
    const t = trLower(r.title || "");
    const d = trLower(r.description || "");
    // Doğum günü veya periyodik fatura hatırlatmalarını takvime bırak
    if (t.includes("doğum günü") || d.includes("doğum günü")) return false;
    if (t.endsWith(" ödeme hatırlatması") || (t.includes("ödeme") && t.includes("fatura"))) return false;
    return true;
  });

  if (!cleanRows.length) {
    return {
      text: "✅ Harika! Bekleyen hiçbir işiniz veya göreviniz yok.\n\nYeni bir iş eklemek için doğrudan buraya yazabilirsiniz (örn: \"Banyodaki ampulü değiştir\").",
      inlineMarkup: null,
    };
  }

  const lines = cleanRows.map((r, i) => {
    const title = (r.title || "İş").trim();
    const prio = r.priority === "high" ? "🔴 " : "";
    const ctx = r.context ? ` [${r.context}]` : "";
    const desc = r.description && trLower(r.description) !== trLower(title) ? ` — ${r.description}` : "";
    let timeHint = "";
    if (r.due_date && trLower(r.due_date) !== "yok") {
      timeHint = `\n   📅 Son tarih: ${r.due_date}`;
    } else if (r.remind_at && trLower(r.remind_at) !== "yok") {
      timeHint = `\n   🕒 Hatırlatma: ${r.remind_at}`;
    }
    return `${i + 1}. ${prio}${title}${ctx}${desc}${timeHint}`;
  });

  const text =
    `✅ Bekleyen İşleriniz (${cleanRows.length} görev):\n\n` +
    lines.join("\n\n") +
    "\n\nTamamladığınız işi listeden düşürmek için aşağıdaki butonlara dokunabilirsiniz:";

  // Telegram satır içi butonları (en fazla 10 görev)
  const buttons = cleanRows.slice(0, 10).map((r) => {
    const rawTitle = (r.title || "İş").trim();
    const shortTitle = rawTitle.length > 25 ? rawTitle.slice(0, 24) + "…" : rawTitle;
    return [{ text: `✓ Tamamla: ${shortTitle}`, callback_data: `done:todo:${r.id}` }];
  });

  return {
    text,
    inlineMarkup: { inline_keyboard: buttons },
  };
}

// --------------------------------------------------------------------------- //
// 5) Veritabanı ve Kasa Özeti
// --------------------------------------------------------------------------- //

export async function renderDatabaseSummary(db) {
  const catStats = await db
    .prepare("SELECT category, completed, COUNT(*) as cnt FROM notes GROUP BY category, completed")
    .all();

  const vaultCount = await db
    .prepare("SELECT COUNT(*) as cnt FROM vault_notes")
    .first();

  const msgCount = await db
    .prepare("SELECT COUNT(*) as cnt FROM telegram_messages")
    .first();

  const recentNotes = await db
    .prepare(
      "SELECT category, title, created_at FROM notes WHERE completed = 0 ORDER BY id DESC LIMIT 5"
    )
    .all();

  const counts = {
    shopping: { active: 0, done: 0 },
    task: { active: 0, done: 0 },
    reminder: { active: 0, done: 0 },
    appointment: { active: 0, done: 0 },
    general: { active: 0, done: 0 },
  };

  for (const row of catStats.results || []) {
    const cat = counts[row.category];
    if (cat) {
      if (row.completed) cat.done += row.cnt;
      else cat.active += row.cnt;
    }
  }

  const totalActive = Object.values(counts).reduce((s, c) => s + c.active, 0);
  const totalDone = Object.values(counts).reduce((s, c) => s + c.done, 0);

  const iconMap = {
    shopping: "🛒",
    task: "✅",
    reminder: "⏰",
    appointment: "📌",
    general: "📝",
  };

  const recentLines = (recentNotes.results || []).map((n, i) => {
    const icon = iconMap[n.category] || "•";
    return `${i + 1}. ${icon} ${n.title}`;
  });

  const text =
    `🗄️ Veritabanı Özeti & Sistem Durumu:\n\n` +
    `📊 Aktif Notlar Dağılımı:\n` +
    `• 🛒 Alışveriş: ${counts.shopping.active} aktif (${counts.shopping.done} tamamlanan)\n` +
    `• ✅ Görevler: ${counts.task.active} aktif (${counts.task.done} tamamlanan)\n` +
    `• ⏰ Hatırlatmalar: ${counts.reminder.active} aktif (${counts.reminder.done} tamamlanan)\n` +
    `• 📌 Randevular: ${counts.appointment.active} aktif (${counts.appointment.done} tamamlanan)\n` +
    `• 📝 Genel Notlar: ${counts.general.active} aktif\n` +
    `────────────────────\n` +
    `📦 Toplam Aktif Not: ${totalActive}\n` +
    `✓ Toplam Tamamlanan: ${totalDone}\n` +
    `📚 Kişisel Kasa (HAKKIMDA): ${vaultCount?.cnt || 0} not\n` +
    `💬 Telegram Mesaj Arşivi: ${msgCount?.cnt || 0} kayıt\n\n` +
    `🕒 Son Eklenen Aktif Notlar:\n` +
    (recentLines.length ? recentLines.join("\n") : "Kayıt yok.");

  return {
    text,
    inlineMarkup: null,
  };
}

// --------------------------------------------------------------------------- //
// 6) Geçen Gün Hesabı (Önemli Tarihler / Kilometre Taşları)
// --------------------------------------------------------------------------- //

export async function renderElapsedDaysMenu(db, todayParts) {
  const todayDate = tryMakeDate(todayParts.year, todayParts.month, todayParts.day);

  // Kasa notlarından önemli tarih tablolarını al
  const vaultRows = await db
    .prepare(
      "SELECT path, title, content FROM vault_notes " +
        "WHERE path LIKE '%Önemli tarihler%' OR path LIKE '%kurs%' OR path LIKE '%Rutinler%' OR path LIKE '%İş%'"
    )
    .all();

  const noteRows = await db
    .prepare(NOTES_SELECT + " WHERE n.completed = 0")
    .all();

  const events = [];
  const seenTopics = new Set();

  const addEvent = (topic, dt, note = "") => {
    if (!dt || dt.getTime() > todayDate.getTime()) return;
    const diff = Math.round((todayDate.getTime() - dt.getTime()) / 86400000);
    if (diff < 0) return;
    const key = trLower(topic).trim();
    if (seenTopics.has(key)) return;
    seenTopics.add(key);
    events.push({ topic, date: dt, diffDays: diff, note });
  };

  // 1) 50_Rutinler/Önemli tarihler.md tablosunu tara
  for (const v of vaultRows.results || []) {
    const lines = (v.content || "").split("\n");
    for (const rawLine of lines) {
      const line = rawLine.trim();
      if (!line.startsWith("|") || line.includes("---")) continue;
      const cells = line.split("|").map((c) => c.trim()).filter(Boolean);
      if (cells.length < 2) continue;
      const topic = cells.length >= 2 ? cells[1] : cells[0];
      if (topic === "Konu" || topic === "Kategori") continue;
      const foundDates = extractDatesFromText(line);
      const pastDates = foundDates.filter((f) => f.date.getTime() <= todayDate.getTime());
      if (pastDates.length) {
        // En güncel geçmiş tarihi al
        pastDates.sort((a, b) => b.date.getTime() - a.date.getTime());
        addEvent(topic, pastDates[0].date, cells[3] || "");
      }
    }
  }

  // 2) Aktif notes tablosundan geçmiş randevu/hatırlatma varsa ekle
  for (const n of noteRows.results || []) {
    const textBlob = `${n.title || ""} ${n.description || ""} ${n.appt_date || ""} ${n.remind_at || ""}`;
    const foundDates = extractDatesFromText(textBlob);
    const pastDates = foundDates.filter((f) => f.date.getTime() <= todayDate.getTime());
    if (pastDates.length) {
      pastDates.sort((a, b) => b.date.getTime() - a.date.getTime());
      addEvent(n.title, pastDates[0].date);
    }
  }

  // En yakın geçmiş olaydan en uzağa doğru sırala
  events.sort((a, b) => a.diffDays - b.diffDays);
  const topEvents = events.slice(0, 12);

  if (!topEvents.length) {
    return {
      text: "⏳ Kayıtlı geçmiş önemli bir tarih bulunamadı.\n\nHerhangi bir olayın üzerinden geçen zamanı sormak için doğrudan yazabilirsiniz (örn: \"Kabine geçeli kaç gün oldu?\").",
      inlineMarkup: null,
    };
  }

  const lines = topEvents.map((e) => {
    const d = e.date.getUTCDate();
    const mName = TR_MONTHS[e.date.getUTCMonth()];
    const y = e.date.getUTCFullYear();
    const dateStr = `${pad2(d)} ${mName} ${y}`;
    const yearStr = e.diffDays >= 365 ? ` (~${(e.diffDays / 365.25).toFixed(1)} yıl)` : "";
    const noteStr = e.note ? ` (${e.note})` : "";
    return `• ${e.topic}${noteStr} (${dateStr})\n  → ${e.diffDays} gün geçti${yearStr}`;
  });

  const text =
    `⏳ Geçen Gün Hesabı (Kayıtlı Önemli Tarihler):\n\n` +
    lines.join("\n\n") +
    `\n\n💡 İpucu: Belirli bir olayı doğrudan sorabilirsiniz.\nÖrn: "Kabine geçeli kaç gün oldu?", "B1 yetkisi üzerinden ne kadar geçti?"`;

  return {
    text,
    inlineMarkup: null,
  };
}

// --------------------------------------------------------------------------- //
// Menü İşleyicileri
// --------------------------------------------------------------------------- //

export async function handleMenuIntent(intent, env, db, chatId, todayParts) {
  if (intent === "welcome") {
    const text =
      `👋 Merhaba! Ben Onur Brief asistanınız.\n\n` +
      `Aşağıdaki hızlı menü butonlarını kullanarak bilgilerinize anında ulaşabilirsiniz:\n` +
      `• 🛒 Alışveriş Listem — Bekleyen ürünler & tek dokunuşla tamamlama\n` +
      `• 📅 Bu Ay Takvimim — Tekilleştirilmiş randevu, doğum günü ve ödemeler\n` +
      `• 📌 Tüm Randevularım — >30 gün dahil tüm gelecek randevular\n` +
      `• ✅ Bekleyen İşlerim — Yapılacaklar & tek dokunuşla tamamlama\n` +
      `• 🗄️ Veritabanı Özeti — Not sayıları ve arşiv durumu\n` +
      `• ⏳ Geçen Gün Hesapla — Önemli olayların üzerinden geçen gün hesabı\n\n` +
      `📰 Anlık günlük brifing için /brifing, R1D vardiya durumunuzu görmek veya değiştirmek için /vardiya komutunu kullanabilirsiniz.\n\n` +
      `Ayrıca bana doğrudan ses kaydı veya metin göndererek yeni not ekleyebilir, soru sorabilirsiniz!`;

    await sendTelegramMessage(env, chatId, text, { replyMarkup: MAIN_MENU_KEYBOARD });
    return;
  }

  if (intent === "briefing") {
    await sendTelegramMessage(env, chatId, "⏳ Anlık günlük brifing hazırlanıyor, lütfen birkaç saniye bekleyin…");
    await generateAndSendDailyBriefing(env);
    return;
  }

  let rendered;
  if (intent === "shopping") {
    rendered = await renderShoppingList(db);
  } else if (intent === "appointments") {
    rendered = await renderAllAppointments(db, todayParts);
  } else if (intent === "todos") {
    rendered = await renderPendingTasks(db);
  } else if (intent === "summary") {
    rendered = await renderDatabaseSummary(db);
  } else if (intent === "elapsed") {
    rendered = await renderElapsedDaysMenu(db, todayParts);
  } else if (intent === "shift" || intent.startsWith("shift:")) {
    if (intent.startsWith("shift:")) {
      const arg = intent.slice("shift:".length);
      const todayDate = tryMakeDate(todayParts.year, todayParts.month, todayParts.day);
      const todayIso = toIsoDateUtc(todayDate);
      const newVal = arg === "auto" ? "" : `${todayIso}:${arg}`;
      await setConfigValue(db, "shift_manual_override", newVal);
    }
    rendered = await renderShiftMenu(db, todayParts);
  } else if (intent.startsWith("cal:")) {
    const mode = intent.slice(4) || "m0";
    rendered = await renderCalendarView(db, mode, todayParts);
  } else {
    rendered = await renderCalendarView(db, "m0", todayParts);
  }

  const options = rendered.inlineMarkup ? { replyMarkup: rendered.inlineMarkup } : {};
  await sendTelegramMessage(env, chatId, rendered.text, options);
}

export async function handleCallbackQuery(callbackQuery, env) {
  const chatId = callbackQuery?.message?.chat?.id;
  const messageId = callbackQuery?.message?.message_id;
  const data = String(callbackQuery?.data || "").trim();

  // Güvenlik doğrulaması
  if (String(chatId || "") !== String(env.TELEGRAM_CHAT_ID)) {
    await answerCallbackQuery(env, callbackQuery.id, "Yetkisiz istek.");
    return;
  }

  const shifted = new Date(Date.now() + 3 * 60 * 60 * 1000);
  const todayParts = {
    year: shifted.getUTCFullYear(),
    month: shifted.getUTCMonth() + 1,
    day: shifted.getUTCDate(),
    hour: shifted.getUTCHours(),
    minute: shifted.getUTCMinutes(),
    weekdayMon0: (shifted.getUTCDay() + 6) % 7,
  };

  // 1) Takvim Görünümü Sekme Değişimi
  if (data.startsWith("cal:")) {
    const mode = data.slice(4);
    const rendered = await renderCalendarView(env.DB, mode, todayParts);
    await editTelegramMessage(env, chatId, messageId, rendered.text, rendered.inlineMarkup);
    await answerCallbackQuery(env, callbackQuery.id);
    return;
  }

  // 2) R1D Vardiya Manuel Değiştirme (/vardiya inline butonları)
  if (data.startsWith("shift:")) {
    const code = data.slice("shift:".length);
    const todayDate = tryMakeDate(todayParts.year, todayParts.month, todayParts.day);
    const todayIso = toIsoDateUtc(todayDate);
    const newVal = code === "auto" ? "" : `${todayIso}:${code}`;
    await setConfigValue(env.DB, "shift_manual_override", newVal);
    const rendered = await renderShiftMenu(env.DB, todayParts);
    await editTelegramMessage(env, chatId, messageId, rendered.text, rendered.inlineMarkup);
    const toast =
      code === "auto"
        ? "🔄 Otomatik R1D vardiya döngüsüne dönüldü."
        : `✅ Bugünkü vardiya '${code}' olarak güncellendi!`;
    await answerCallbackQuery(env, callbackQuery.id, toast);
    return;
  }

  // 3) Günün İngilizce Kartı Aralıklı Tekrar Geri Bildirimi ([✅ Öğrendim] / [🔁 Tekrar Sor])
  if (data.startsWith("learn:ok:") || data.startsWith("learn:again:")) {
    const known = data.startsWith("learn:ok:");
    const wordKey = data.slice(known ? "learn:ok:".length : "learn:again:".length);
    const todayDate = tryMakeDate(todayParts.year, todayParts.month, todayParts.day);
    const todayIso = toIsoDateUtc(todayDate);
    const res = await recordLearningFeedbackD1(env.DB, wordKey, known, todayIso);
    const badgeText = known
      ? `✅ Öğrenildi: ${res.word} (Kutu ${res.box} · ${res.intervalDays}g sonra)`
      : `🔁 Tekrar sorulacak: ${res.word} (Yarın)`;
    const updatedMarkup = {
      inline_keyboard: [[{ text: badgeText, callback_data: "noop" }]],
    };
    if (callbackQuery?.message?.text) {
      await editTelegramMessage(env, chatId, messageId, callbackQuery.message.text, updatedMarkup);
    }
    const toast = known
      ? `Harika! "${res.word}" Kutu ${res.box}'e taşındı (${res.intervalDays} gün sonra tekrar).`
      : `"${res.word}" Kutu 1'de tutuldu, yarın tekrar sorulacak.`;
    await answerCallbackQuery(env, callbackQuery.id, toast);
    return;
  }

  // 4) Alışveriş Kalemi Tamamlama
  if (data.startsWith("done:shop:")) {
    const noteId = parseInt(data.slice("done:shop:".length), 10);
    if (noteId) {
      await env.DB
        .prepare("UPDATE notes SET completed = 1, updated_at = ? WHERE id = ?")
        .bind(nowIstanbulIso(), noteId)
        .run();
    }
    const rendered = await renderShoppingList(env.DB);
    await editTelegramMessage(env, chatId, messageId, rendered.text, rendered.inlineMarkup);
    await answerCallbackQuery(env, callbackQuery.id, "✅ Ürün tamamlandı olarak işaretlendi!");
    return;
  }

  // 3) Bekleyen İş / Görev Tamamlama
  if (data.startsWith("done:todo:")) {
    const noteId = parseInt(data.slice("done:todo:".length), 10);
    if (noteId) {
      await env.DB
        .prepare("UPDATE notes SET completed = 1, updated_at = ? WHERE id = ?")
        .bind(nowIstanbulIso(), noteId)
        .run();
    }
    const rendered = await renderPendingTasks(env.DB);
    await editTelegramMessage(env, chatId, messageId, rendered.text, rendered.inlineMarkup);
    await answerCallbackQuery(env, callbackQuery.id, "✅ Görev tamamlandı olarak işaretlendi!");
    return;
  }

  await answerCallbackQuery(env, callbackQuery.id);
}

