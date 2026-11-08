// src/briefing_coordinator.js
//
// briefing_coordinator.py'nin birebir Cloudflare Worker (D1) portu:
// - Kasa İzin Listesi (VAULT_BRIEFING_ALLOWLIST): Şifrelerim.md, 10_Kişiler, 90_Arşiv
//   kesinlikle sorgulanmaz.
// - 27 günlük R1D Vardiya Motoru (2026-11-09 referanslı %100 doğruluklu R1D döngüsü
//   + /vardiya ile tek dokunuşluk manuel ezme).
// - Kişisel Görev / Takvim / Alışveriş Önceliklendirme Motoru (geciken işler, bugünün
//   max 3 önceliği, 3 gün içindeki kritik takvim, tarihsiz görev rotasyonu, alışveriş özeti).
// - Pazartesi Haftalık Aktif Proje Odağı.

import { getConfigValue } from "./common.js";
import { TR_DAYS, TR_MONTHS, isStaleMetaRow, pad2, resolveCalendarEntries, trLower, tryMakeDate } from "./knowledge.js";

export const VAULT_BRIEFING_ALLOWLIST = [
  "50_Rutinler/Doğum Günleri ve Randevular.md",
  "50_Rutinler/Çatalca İGA Servisi.md",
  "50_Rutinler/Servis Bilgileri.md",
  "50_Rutinler/Ring saatleri.md",
  "30_İş/Eksik Eğitimlerim.md",
  "60_Öğrenme/İngilizce unuttuğum kelimeler.md",
  "60_Öğrenme/Unuttuğum Kavramlar.md",
  "40_Teknoloji/Aktif Projelerim.md",
  "40_Teknoloji/40_Teknoloji.md",
];

// 2026-11-09 referans tarihli 27 günlük R1D vardiya döngüsü (r1d vardiyam.md ile %100 özdeş)
const R1D_ANCHOR_UTC_MS = Date.UTC(2026, 10, 9); // 9 Kasım 2026
const R1D_27DAY_CYCLE = [
  ...Array(5).fill("15-23"),
  ...Array(2).fill("tatil"),
  ...Array(5).fill("07-15"),
  ...Array(2).fill("tatil"),
  ...Array(5).fill("15-23"),
  ...Array(2).fill("tatil"),
  ...Array(6).fill("07-15"),
];

const SHIFT_META = {
  "07-15": {
    code: "07-15",
    label: "07-15 Vardiyası",
    wakeTime: "05:00",
    leaveTime: "05:20",
    returnTime: "16:30",
    isWorkday: true,
  },
  "15-23": {
    code: "15-23",
    label: "15-23 Vardiyası",
    wakeTime: null,
    leaveTime: "13:00",
    returnTime: "00:00",
    isWorkday: true,
  },
  tatil: {
    code: "tatil",
    label: "Tatil",
    wakeTime: null,
    leaveTime: null,
    returnTime: null,
    isWorkday: false,
  },
};

const ISO_DATE_PREFIX_RE = /^(\d{4})-(\d{2})-(\d{2})/;
const TR_DATE_RE = /^(\d{1,2})\.(\d{1,2})\.(\d{4})/;
const ROW_RE = /^\|(.+)\|\s*$/;
const WIKILINK_RE = /\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/;

const NON_PROJECT_REFERENCE_TITLES = new Set([
  "kod derleme ve yayınlama komutları",
  "masaüstü uygulaması yapmak",
  "sıfırdan mobil uygulama üretim taslağı",
  "websitelerini dark mode yapma",
  "excel - gelişmiş düşeyara",
  "play store yayınlama notları",
  "gelen kutusu",
]);

export async function fetchAllowlistedVaultMap(db) {
  const placeholders = VAULT_BRIEFING_ALLOWLIST.map(() => "?").join(", ");
  const res = await db
    .prepare(`SELECT path, title, content FROM vault_notes WHERE path IN (${placeholders})`)
    .bind(...VAULT_BRIEFING_ALLOWLIST)
    .all();
  const map = new Map();
  for (const row of res.results || []) {
    if (VAULT_BRIEFING_ALLOWLIST.includes(row.path)) {
      map.set(row.path, row.content || "");
    }
  }
  return map;
}

export function normalizeShiftCode(raw) {
  const low = trLower(raw || "").trim();
  if (low.includes("07-15") || low.includes("07_15") || low.includes("sabah")) return "07-15";
  if (low.includes("15-23") || low.includes("15_23") || low.includes("öğle") || low.includes("oglen")) return "15-23";
  if (low.includes("tatil") || low.includes("izin") || low.includes("off")) return "tatil";
  return null;
}

export function toIsoDateUtc(dateObj) {
  return `${dateObj.getUTCFullYear()}-${pad2(dateObj.getUTCMonth() + 1)}-${pad2(dateObj.getUTCDate())}`;
}

function parseShiftOverride(overrideStr, targetDateIso) {
  const raw = String(overrideStr || "").trim();
  if (!raw || ["auto", "otomatik"].includes(raw.toLowerCase())) return null;
  if (raw.includes(":")) {
    const [dPart, codePart] = raw.split(":", 2);
    if (dPart.trim() === targetDateIso) return normalizeShiftCode(codePart);
    return null;
  }
  return normalizeShiftCode(raw);
}

export function resolveShiftForDate(targetDateUtc, overrideStr = "") {
  const iso = toIsoDateUtc(targetDateUtc);
  const ov = parseShiftOverride(overrideStr, iso);
  if (ov && SHIFT_META[ov]) {
    return { ...SHIFT_META[ov], source: "override", date: iso };
  }
  const diffDays = Math.round((targetDateUtc.getTime() - R1D_ANCHOR_UTC_MS) / 86400000);
  const idx = ((diffDays % R1D_27DAY_CYCLE.length) + R1D_27DAY_CYCLE.length) % R1D_27DAY_CYCLE.length;
  const code = R1D_27DAY_CYCLE[idx];
  return { ...SHIFT_META[code], source: "r1d_cycle", date: iso };
}

function extractPendingTrainings(vaultMap) {
  const content = vaultMap.get("30_İş/Eksik Eğitimlerim.md") || "";
  if (!content) return [];
  const items = [];
  let inSection = false;
  for (const rawLine of content.split("\n")) {
    const line = rawLine.trim();
    if (line.startsWith("## ")) {
      const low = trLower(line);
      inSection = low.includes("eksik") || low.includes("eğitim");
      continue;
    }
    if (inSection && line.startsWith("- ") && !line.includes("[[")) {
      const cleaned = line.slice(2).trim().replace(/\*\*/g, "");
      if (cleaned) items.push(cleaned);
    }
  }
  return items;
}

function addDaysUtc(dateObj, days) {
  const d = new Date(dateObj.getTime());
  d.setUTCDate(d.getUTCDate() + days);
  return d;
}

function dayOrdinal(dateObj) {
  return Math.floor(dateObj.getTime() / 86400000);
}

export function buildWorkdayPrepTelegram(todayDateUtc, currentHour, weekdayMon0, overrideStr, lengthMode, vaultMap) {
  const todayShift = resolveShiftForDate(todayDateUtc, overrideStr);
  const tomorrowShift = resolveShiftForDate(addDaysUtc(todayDateUtc, 1), "");
  const code = todayShift.code;
  const tmrCode = tomorrowShift.code;

  const lines = ["🛫 Vardiya & İş Günü:"];
  if (code === "07-15") {
    lines.push("• Bugün: 07-15 Vardiyası (05:00 uyanış, 05:20 evden çıkış, 16:30 dönüş)");
  } else if (code === "15-23") {
    lines.push("• Bugün: 15-23 Vardiyası (13:00 evden çıkış, 00:00 eve dönüş)");
  } else {
    lines.push("• Bugün: Vardiya Tatili 🏖️");
  }

  if (code === "tatil" && tmrCode === "07-15") {
    lines.push("• Yarın: 07-15 Vardiyası başlıyor (sabah 05:20 çıkış)");
  } else if (currentHour >= 16) {
    lines.push(`• Yarın: ${tomorrowShift.label}`);
  }

  // Salı (1) ve Cuma (4) iş günlerinde eksik eğitim hatırlatması
  if (todayShift.isWorkday && lengthMode !== "short" && (weekdayMon0 === 1 || weekdayMon0 === 4)) {
    const trainings = extractPendingTrainings(vaultMap);
    if (trainings.length) {
      const pick = trainings[dayOrdinal(todayDateUtc) % trainings.length];
      lines.push(`• Eğitim Hatırlatması: ${pick}`);
    }
  }

  return lines.join("\n");
}

function parseNoteDueDate(note) {
  const cat = note.category;
  let raw = "";
  if (cat === "appointment") raw = (note.appt_date || "").trim();
  else if (cat === "task") raw = (note.due_date || "").trim();
  else if (cat === "reminder") raw = (note.remind_at || "").trim();

  if (!raw || trLower(raw) === "yok") return null;
  let m = ISO_DATE_PREFIX_RE.exec(raw);
  if (m) return tryMakeDate(parseInt(m[1], 10), parseInt(m[2], 10), parseInt(m[3], 10));
  m = TR_DATE_RE.exec(raw);
  if (m) return tryMakeDate(parseInt(m[3], 10), parseInt(m[2], 10), parseInt(m[1], 10));
  return null;
}

function isPeriodicCalendarReminder(note) {
  const titleLow = trLower(note.title || "");
  const rep = trLower(note.repeat_frequency || "");
  if (rep === "yillik" || rep === "aylik" || rep === "yıllık" || rep === "aylık") return true;
  return titleLow.includes("doğum günü") || titleLow.endsWith("ödeme hatırlatması");
}

function formatCalendarItemTg(entry) {
  const tur = entry.tur || "Kayıt";
  const kim = entry.kim || "";
  const kalan = entry.kalanGun ?? 0;
  const zaman = kalan === 0 ? "bugün" : kalan === 1 ? "yarın" : `${kalan} gün sonra`;
  const extra = entry.not ? ` (${entry.not})` : "";
  return `[${tur}] ${kim} — ${zaman}${extra}`;
}

export function collectPersonalCoordinationData(activeNotes, vaultMap, todayDateUtc, lengthMode = "balanced") {
  const cleanNotes = (activeNotes || []).filter((n) => !n.completed && !isStaleMetaRow(n));

  const overdue = [];
  const highPrioUndated = [];
  const undatedPool = [];
  const shopping = [];

  for (const n of cleanNotes) {
    const cat = n.category;
    if (cat === "shopping") {
      const label = (n.product_name || n.title || "").trim();
      const qty = (n.quantity || "").trim();
      if (label) shopping.push({ label, qty });
      continue;
    }

    if (!["appointment", "task", "reminder"].includes(cat)) continue;
    if (isPeriodicCalendarReminder(n)) continue;

    const dueDate = parseNoteDueDate(n);
    const title = (n.title || n.description || "").trim();
    if (!title) continue;

    if (dueDate) {
      const diff = Math.round((dueDate.getTime() - todayDateUtc.getTime()) / 86400000);
      if (diff >= -30 && diff < 0) {
        overdue.push({ title, daysOverdue: Math.abs(diff), priority: n.priority || "normal" });
      }
    } else {
      if (n.priority === "high") highPrioUndated.push({ title });
      else undatedPool.push({ id: n.id || 0, title });
    }
  }

  overdue.sort((a, b) => (a.priority === "high" ? 0 : 1) - (b.priority === "high" ? 0 : 1) || a.daysOverdue - b.daysOverdue);
  const topOverdue = overdue.slice(0, 2);

  const bdayHorizon = lengthMode === "short" ? 3 : lengthMode === "detailed" ? 14 : 7;
  const taskHorizon = lengthMode === "short" ? 2 : lengthMode === "detailed" ? 5 : 3;
  const maxHorizon = Math.max(bdayHorizon, taskHorizon);

  const remindersMd = vaultMap.get("50_Rutinler/Doğum Günleri ve Randevular.md") || "";
  const vaultRowsForCal = remindersMd
    ? [{ path: "50_Rutinler/Doğum Günleri ve Randevular.md", content: remindersMd }]
    : [];
  const allCal = resolveCalendarEntries(vaultRowsForCal, cleanNotes, todayDateUtc).filter(
    (e) => e.kalanGun >= 0 && e.kalanGun <= maxHorizon
  );

  const todayItems = [];
  const upcomingItems = [];
  for (const e of allCal) {
    const isBday = trLower(e.tur).includes("doğum");
    if (e.kalanGun === 0) todayItems.push(e);
    else if (isBday && e.kalanGun <= bdayHorizon) upcomingItems.push(e);
    else if (!isBday && e.kalanGun <= taskHorizon) upcomingItems.push(e);
  }

  const todayPriorities = [];
  for (const e of todayItems.slice(0, 3)) todayPriorities.push({ kind: "calendar", entry: e });
  for (const hp of highPrioUndated) {
    if (todayPriorities.length >= 3) break;
    todayPriorities.push({ kind: "high_task", title: hp.title });
  }

  const upcomingCap = lengthMode === "short" ? 2 : lengthMode === "detailed" ? 5 : 3;
  const topUpcoming = upcomingItems.slice(0, upcomingCap);

  const undatedCap = lengthMode === "short" ? 1 : 2;
  const selectedUndated = [];
  if (undatedPool.length && todayPriorities.length < 3) {
    undatedPool.sort((a, b) => a.id - b.id);
    const startIdx = dayOrdinal(todayDateUtc) % undatedPool.length;
    const count = Math.min(undatedCap, undatedPool.length);
    for (let i = 0; i < count; i++) {
      selectedUndated.push(undatedPool[(startIdx + i) % undatedPool.length]);
    }
  }

  let primaryFocus = "";
  if (todayPriorities.length) {
    const first = todayPriorities[0];
    primaryFocus = first.kind === "calendar" ? first.entry.kim : first.title;
  } else if (topOverdue.length) {
    primaryFocus = topOverdue[0].title;
  } else if (selectedUndated.length) {
    primaryFocus = selectedUndated[0].title;
  }

  return {
    overdue: topOverdue,
    todayPriorities,
    upcoming: topUpcoming,
    undatedTasks: selectedUndated,
    shopping,
    primaryFocus,
  };
}

export function buildPersonalCoordinationTelegram(coordData) {
  const { overdue, todayPriorities, upcoming, undatedTasks, shopping } = coordData;
  if (!overdue.length && !todayPriorities.length && !upcoming.length && !undatedTasks.length && !shopping.length) {
    return "";
  }

  const lines = ["📋 Günün Kişisel Koordinasyonu:"];
  for (const item of todayPriorities) {
    if (item.kind === "calendar") {
      lines.push(`• 🎯 Öncelik: ${formatCalendarItemTg(item.entry)}`);
    } else {
      lines.push(`• 🎯 Öncelik: ${item.title}`);
    }
  }
  for (const o of overdue) {
    lines.push(`• ⚠️ Geciken: ${o.title} (${o.daysOverdue} gün geçti)`);
  }
  for (const e of upcoming) {
    lines.push(`• 📅 Yaklaşan: ${formatCalendarItemTg(e)}`);
  }
  for (const u of undatedTasks) {
    lines.push(`• 📌 Bekleyen İş: ${u.title}`);
  }
  if (shopping.length) {
    if (shopping.length <= 3) {
      const names = shopping.map((s) => (s.qty ? `${s.label} (${s.qty})` : s.label)).join(", ");
      lines.push(`• 🛒 Alışveriş: ${names}`);
    } else {
      const names = shopping.slice(0, 2).map((s) => s.label).join(", ");
      lines.push(`• 🛒 Alışveriş (${shopping.length} ürün): ${names} +${shopping.length - 2} ürün`);
    }
  }
  return lines.join("\n");
}

export function buildWeeklyProjectTelegram(todayDateUtc, weekdayMon0, lengthMode, vaultMap) {
  if (weekdayMon0 !== 0 || lengthMode === "short") return "";

  const trackerMd = vaultMap.get("40_Teknoloji/Aktif Projelerim.md") || "";
  if (trackerMd) {
    for (const rawLine of trackerMd.split("\n")) {
      const m = ROW_RE.exec(rawLine.trim());
      if (!m) continue;
      const cells = m[1].split("|").map((c) => c.trim());
      if (cells.length < 3) continue;
      const [proj, status, nextStep] = cells;
      const isSep = proj.length > 0 && [...proj].every((ch) => ch === "-" || ch === ":");
      if (!proj || ["proje", "ad"].includes(proj.toLowerCase()) || isSep) continue;
      if (trLower(status).includes("tamam") || trLower(status).includes("iptal")) continue;
      return `🚀 Haftalık Proje Odağı:\n• ${proj} — Sıradaki adım: ${nextStep}`;
    }
  }

  const indexMd = vaultMap.get("40_Teknoloji/40_Teknoloji.md") || "";
  if (!indexMd) return "";

  const projects = [];
  for (const rawLine of indexMd.split("\n")) {
    const line = rawLine.trim();
    if (!line.startsWith("- [[")) continue;
    const m = WIKILINK_RE.exec(line);
    if (!m) continue;
    const target = m[1].trim();
    const alias = (m[2] || "").trim();
    const label = alias || target;
    if (NON_PROJECT_REFERENCE_TITLES.has(trLower(label)) || NON_PROJECT_REFERENCE_TITLES.has(trLower(target))) {
      continue;
    }
    projects.push(label);
  }
  if (!projects.length) return "";

  const weekIndex = Math.floor(dayOrdinal(todayDateUtc) / 7);
  const picked = projects[weekIndex % projects.length];
  return `🚀 Haftalık Proje Odağı:\n• Bu hafta göz atabileceğin proje: ${picked}`;
}

export async function renderShiftMenu(db, todayParts) {
  const overrideStr = (await getConfigValue(db, "shift_manual_override", "")) || "";
  const todayDate = tryMakeDate(todayParts.year, todayParts.month, todayParts.day);
  const todayShift = resolveShiftForDate(todayDate, overrideStr);

  const lines = [];
  for (let offset = 0; offset < 7; offset++) {
    const d = addDaysUtc(todayDate, offset);
    const sh = resolveShiftForDate(d, offset === 0 ? overrideStr : "");
    const dayName = TR_DAYS[(todayParts.weekdayMon0 + offset) % 7];
    const dateLabel = `${pad2(d.getUTCDate())} ${TR_MONTHS[d.getUTCMonth()]} ${dayName}`;
    const icon = sh.code === "07-15" ? "🌅" : sh.code === "15-23" ? "🌆" : "🏖️";
    const prefix = offset === 0 ? "👉 Bugün" : `• ${dateLabel}`;
    const ovBadge = sh.source === "override" ? " (Manuel)" : "";
    lines.push(`${prefix} (${offset === 0 ? dateLabel : sh.label}): ${icon} ${offset === 0 ? sh.label : ""}${ovBadge}`.replace(":  ", ": "));
  }

  const detail =
    todayShift.code === "07-15"
      ? "05:00 uyanış · 05:20 evden çıkış · 16:30 dönüş"
      : todayShift.code === "15-23"
      ? "13:00 evden çıkış · 00:00 eve dönüş"
      : "İzin / Tatil günü";

  const text =
    `🛫 R1D Vardiya Programınız (7 Günlük Görünüm):\n\n` +
    `Bugünkü Durum: ${todayShift.label} (${detail})\n\n` +
    lines.join("\n") +
    `\n\nBugünkü vardiyada anlık değişiklik olduysa aşağıdan tek dokunuşla güncelleyebilirsiniz:`;

  const inlineMarkup = {
    inline_keyboard: [
      [
        { text: "🌅 Bugün: 07-15", callback_data: "shift:07-15" },
        { text: "🌆 Bugün: 15-23", callback_data: "shift:15-23" },
      ],
      [
        { text: "🏖️ Bugün: Tatil", callback_data: "shift:tatil" },
        { text: "🔄 Otomatik R1D", callback_data: "shift:auto" },
      ],
    ],
  };

  return { text, inlineMarkup };
}

