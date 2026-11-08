// src/knowledge.js
//
// vault_knowledge.py + personal_context.py + db_query_resolver.py üçlüsünün
// Cloudflare Worker (D1 + Groq) karşılığı. Telegram webhook üzerinden gelen
// "query" mesajlarında SADECE `notes` tablosuna bakmak yerine:
//   1) D1 `notes` (alışveriş, randevu, hatırlatma, genel notlar),
//   2) D1 `vault_notes` içindeki "50_Rutinler/Doğum Günleri ve Randevular.md"
//      tablosu (deterministik kalan-gün hesabıyla),
//   3) D1 `vault_notes` içindeki 145+ HAKKIMDA kasa notu (Türkçe kök bulma +
//      IDF ağırlıklı RAG aramasıyla)
// birleşik olarak taranır ve geçmiş/gelecek tarihlerin gün farkları JS'de
// deterministik hesaplanarak modele hazır verilir.

export const TR_MONTHS = [
  "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
  "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
];
export const TR_DAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"];

const TR_MONTH_NAME_TO_NUM = new Map(
  TR_MONTHS.map((name, idx) => [name.replace(/İ/g, "i").replace(/I/g, "ı").toLowerCase(), idx + 1])
);

const CATEGORY_LABELS = {
  appointment: "Randevu",
  shopping: "Alışveriş",
  reminder: "Hatırlatma / Yapılacak İş",
  task: "Görev",
  general: "Genel Not",
};

const TR_STOPWORDS = new Set([
  "ve", "ile", "bir", "bu", "şu", "o", "da", "de", "mi", "mı", "mu", "mü",
  "ne", "ki", "için", "gibi", "ama", "ya", "veya", "çok", "en", "var",
  "yok", "ben", "sen", "biz", "siz", "onlar", "benim", "senin", "bana",
  "beni", "nerede", "nasıl", "kaç", "kim", "hangi", "zaman", "notlarımda",
  "notumda", "not", "notum", "notlar", "notlarım", "takvimimde", "bilgi",
  "hakkında", "dair", "ilgili", "alakalı", "konusunda", "acaba", "mısın",
  "musun", "mısınız", "misin", "nedir", "kimdir", "kimdi", "neydi", "neler",
  "hangisi", "hangileri", "oldu", "olan", "olarak",
  "bugün", "dün", "yarın", "şimdi", "merhaba", "selam", "lütfen",
  "teşekkürler", "teşekkür", "naber", "nasılsın", "iyi", "kötü", "tamam",
  "evet", "hayır", "olur",
]);

const MULTI_CHAR_SUFFIXES = [
  "larındaki", "lerindeki", "sındaki", "sindeki", "sundaki", "sündeki",
  "larından", "lerinden", "sından", "sinden", "sundan", "sünden",
  "ndaki", "ndeki", "daki", "deki", "taki", "teki",
  "larını", "lerini", "larına", "lerine", "larının", "lerinin",
  "sının", "sinin", "sunun", "sünün",
  "mızdan", "mizden", "muzdan", "müzden",
  "nızdan", "nizden", "nuzdan", "nüzden",
  "sına", "sine", "suna", "süne",
  "sını", "sini", "sunu", "sünü",
  "ndan", "nden", "dan", "den", "tan", "ten",
  "nda", "nde", "da", "de", "ta", "te",
  "yla", "yle", "la", "le",
  "nın", "nin", "nun", "nün",
  "mız", "miz", "muz", "müz",
  "nız", "niz", "nuz", "nüz",
  "ları", "leri", "lar", "ler",
  "lık", "lik", "luk", "lük",
  "sız", "siz", "suz", "süz",
  "lı", "li", "lu", "lü",
  "ıyor", "iyor", "uyor", "üyor", "yor",
  "yacak", "yecek", "nacak", "necek", "acak", "ecek", "mak", "mek",
  "mış", "miş", "muş", "müş",
  "dım", "dim", "dum", "düm", "tım", "tim", "tum", "tüm",
  "dın", "din", "dun", "dün", "tın", "tin", "tun", "tün",
  "ın", "in", "un", "ün",
  "ım", "im", "um", "üm",
  "sı", "si", "su", "sü",
  "nı", "ni", "nu", "nü",
  "na", "ne", "ya", "ye",
];

const SINGLE_CHAR_MIN4 = ["ı", "i", "u", "ü"];
const SINGLE_CHAR_MIN3 = ["a", "e"];
const VOWELS = new Set(["a", "e", "ı", "i", "o", "ö", "u", "ü"]);
const SOFTENING_MAP = { "ğ": "k", "d": "t", "b": "p", "c": "ç" };

const WORD_RE = /[\p{L}\p{N}_]+/gu;
const FRONTMATTER_RE = /^---\s*\n[\s\S]*?\n---\s*\n/;
const TAG_LINE_RE = /^\s*(#[\p{L}\p{N}_/-]+\s*)+$/gmu;
const WIKILINK_RE = /\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g;

const ROW_RE = /^\|(.+)\|\s*$/;
const DATE_FULL_RE = /^(\d{1,2})\.(\d{1,2})\.(\d{4})$/;
const DATE_ISO_RE = /^(\d{4})-(\d{2})-(\d{2})/;
const DATE_ANNUAL_RE = /^(\d{1,2})\.(\d{1,2})$/;
const DAY_ONLY_RE = /^(\d{1,2})$/;

const MIN_MATCH_SCORE = 3.5;
const REMINDERS_VAULT_PATH = "50_Rutinler/Doğum Günleri ve Randevular.md";

export function trLower(text) {
  if (!text) return "";
  return String(text).replace(/İ/g, "i").replace(/I/g, "ı").toLowerCase().replace(/\u0307/g, "");
}

function unsoftenTail(s) {
  if (s.length >= 4) {
    const last = s[s.length - 1];
    if (SOFTENING_MAP[last]) {
      return s.slice(0, -1) + SOFTENING_MAP[last];
    }
  }
  return s;
}

export function stem(word) {
  let current = word;
  for (let pass = 0; pass < 3; pass++) {
    let matched = false;
    for (const suf of MULTI_CHAR_SUFFIXES) {
      if (current.endsWith(suf) && current.length - suf.length >= 3) {
        const vowelInitial = VOWELS.has(suf[0]);
        current = current.slice(0, -suf.length);
        if (vowelInitial) current = unsoftenTail(current);
        matched = true;
        break;
      }
    }
    if (matched) continue;

    for (const suf of ["ma", "me"]) {
      if (current.endsWith(suf) && current.length - 2 >= 4) {
        current = current.slice(0, -2);
        matched = true;
        break;
      }
    }
    if (matched) continue;

    for (const suf of SINGLE_CHAR_MIN4) {
      if (current.endsWith(suf) && current.length - 1 >= 4) {
        current = unsoftenTail(current.slice(0, -1));
        matched = true;
        break;
      }
    }
    if (matched) continue;

    for (const suf of SINGLE_CHAR_MIN3) {
      if (current.endsWith(suf) && current.length - 1 >= 3) {
        current = unsoftenTail(current.slice(0, -1));
        matched = true;
        break;
      }
    }
    if (!matched) break;
  }
  return current;
}

export function tokenize(text) {
  return trLower(text).match(WORD_RE) || [];
}

export function meaningfulTerms(text) {
  const out = new Set();
  for (const tok of tokenize(text)) {
    if (!TR_STOPWORDS.has(tok) && tok.length > 1) {
      out.add(stem(tok));
    }
  }
  return out;
}

function cleanVaultContent(rawText) {
  let text = String(rawText || "").replace(FRONTMATTER_RE, "");
  text = text.replace(WIKILINK_RE, (_, target, alias) => alias || target);
  text = text.replace(TAG_LINE_RE, "");
  return text.trim();
}

function setIntersection(a, b) {
  const res = [];
  for (const item of a) {
    if (b.has(item)) res.push(item);
  }
  return res;
}

const H2_HEADING_RE = /^##\s+(.+?)\s*$/gm;

// Notu ## (H2) başlıklarına göre ayrı parçalara böler, böylece bir dosyadaki
// birbirine benzeyen farklı bölümler (ör. iki ayrı "mail adresi" listesi)
// arama sırasında tek bir dev blok olarak karışıp LLM'in yanlış bölümden
// cevap seçmesine yol açmaz. H2 başlığı yoksa tüm içerik tek parça döner.
function splitIntoSections(content) {
  const matches = [...content.matchAll(H2_HEADING_RE)];
  if (matches.length === 0) return [[null, content]];

  const sections = [];
  const intro = content.slice(0, matches[0].index).trim();
  if (intro) sections.push([null, intro]);
  for (let i = 0; i < matches.length; i++) {
    const start = matches[i].index;
    const end = i + 1 < matches.length ? matches[i + 1].index : content.length;
    sections.push([matches[i][1].trim(), content.slice(start, end).trim()]);
  }
  return sections;
}

export function searchVaultNotes(vaultRows, queryText, topK = 8) {
  const queryTerms = meaningfulTerms(queryText);
  if (queryTerms.size === 0 || !Array.isArray(vaultRows) || vaultRows.length === 0) {
    return [];
  }

  const docs = [];
  for (const row of vaultRows) {
    const cleaned = cleanVaultContent(row.content);
    for (const [heading, sectionText] of splitIntoSections(cleaned)) {
      const title = heading ? `${row.title} — ${heading}` : row.title;
      const titleTerms = meaningfulTerms(title);
      const contentTerms = meaningfulTerms(sectionText);
      const terms = new Set([...titleTerms, ...contentTerms]);
      docs.push({
        path: row.path,
        title,
        folder: row.folder || "",
        content: sectionText,
        titleTerms,
        terms,
      });
    }
  }

  const nDocs = docs.length;
  const docFreq = new Map();
  for (const doc of docs) {
    for (const t of doc.terms) {
      docFreq.set(t, (docFreq.get(t) || 0) + 1);
    }
  }

  const idf = (term) => {
    const df = docFreq.get(term) || 0;
    return Math.log((nDocs - df + 0.5) / (df + 0.5) + 1.0);
  };

  const minScore = Math.min(MIN_MATCH_SCORE, Math.log((nDocs + 0.5) / 1.5 + 1.0) * 0.9);
  const scored = [];
  for (const doc of docs) {
    const overlap = setIntersection(queryTerms, doc.terms);
    if (overlap.length === 0) continue;

    const titleOverlap = setIntersection(queryTerms, doc.titleTerms);
    if (titleOverlap.length === 0 && overlap.length < 2) {
      const hasRareTerm = overlap.some((t) => (docFreq.get(t) || 0) <= 2);
      if (!hasRareTerm) continue;
    }

    let score = 0;
    for (const term of overlap) {
      let weight = idf(term);
      if (doc.titleTerms.has(term)) weight *= 3;
      score += weight;
    }
    if (score >= minScore) {
      scored.push({ ...doc, score });
    }
  }

  scored.sort((a, b) => b.score - a.score);
  return scored.slice(0, topK);
}

// --------------------------------------------------------------------------- //
// Tarih ve Takvim Hesaplamaları (Deterministik)
// --------------------------------------------------------------------------- //

export function tryMakeDate(y, m, d) {
  const dt = new Date(Date.UTC(y, m - 1, d));
  if (dt.getUTCFullYear() !== y || dt.getUTCMonth() !== m - 1 || dt.getUTCDate() !== d) return null;
  return dt;
}

export function daysInMonth(y, m) {
  return new Date(Date.UTC(y, m, 0)).getUTCDate();
}

export function pad2(n) {
  return String(n).padStart(2, "0");
}

function formatIso(dt) {
  return `${dt.getUTCFullYear()}-${pad2(dt.getUTCMonth() + 1)}-${pad2(dt.getUTCDate())}`;
}

function nextAnnual(day, month, todayDate) {
  let candidate = tryMakeDate(todayDate.getUTCFullYear(), month, day);
  if (!candidate) return null;
  if (candidate.getTime() < todayDate.getTime()) {
    candidate = tryMakeDate(todayDate.getUTCFullYear() + 1, month, day);
    if (!candidate) return null;
  }
  return candidate;
}

function nextMonthly(day, todayDate) {
  let y = todayDate.getUTCFullYear();
  let m = todayDate.getUTCMonth() + 1;
  let candidate = tryMakeDate(y, m, Math.min(day, daysInMonth(y, m)));
  if (candidate.getTime() < todayDate.getTime()) {
    m += 1;
    if (m > 12) {
      m = 1;
      y += 1;
    }
    candidate = tryMakeDate(y, m, Math.min(day, daysInMonth(y, m)));
  }
  return candidate;
}

function extractYmd(raw) {
  let m = DATE_ISO_RE.exec(raw);
  if (m) return { day: parseInt(m[3], 10), month: parseInt(m[2], 10), year: parseInt(m[1], 10) };
  m = DATE_FULL_RE.exec(raw);
  if (m) return { day: parseInt(m[1], 10), month: parseInt(m[2], 10), year: parseInt(m[3], 10) };
  return null;
}

function resolveCalendarDate(tarihRaw, tekrarRaw, todayDate) {
  const tRaw = String(tarihRaw || "").trim();
  const tekrar = trLower(tekrarRaw || "").trim();
  if (!tRaw || trLower(tRaw) === "yok") return null;

  if (tekrar === "aylık" || tekrar === "aylik") {
    const m = DAY_ONLY_RE.exec(tRaw);
    if (m) return nextMonthly(parseInt(m[1], 10), todayDate);
    const ymd = extractYmd(tRaw);
    if (ymd) {
      const cand = tryMakeDate(ymd.year, ymd.month, ymd.day);
      return cand && cand.getTime() >= todayDate.getTime() ? cand : nextMonthly(ymd.day, todayDate);
    }
    return null;
  }

  if (tekrar === "yıllık" || tekrar === "yillik") {
    const m = DATE_ANNUAL_RE.exec(tRaw);
    if (m) return nextAnnual(parseInt(m[1], 10), parseInt(m[2], 10), todayDate);
    const ymd = extractYmd(tRaw);
    return ymd ? nextAnnual(ymd.day, ymd.month, todayDate) : null;
  }

  const ymd = extractYmd(tRaw);
  if (ymd) {
    const cand = tryMakeDate(ymd.year, ymd.month, ymd.day);
    return cand && cand.getTime() >= todayDate.getTime() ? cand : null;
  }

  const m = DATE_ANNUAL_RE.exec(tRaw);
  if (m) return nextAnnual(parseInt(m[1], 10), parseInt(m[2], 10), todayDate);

  return null;
}

function parseMarkdownCalendarRows(markdownText) {
  if (!markdownText) return [];
  const entries = [];
  for (const rawLine of String(markdownText).split("\n")) {
    const line = rawLine.trim();
    const match = ROW_RE.exec(line);
    if (!match) continue;
    const cells = match[1].split("|").map((c) => c.trim());
    if (cells.length < 3) continue;
    const first = cells[0];
    const isSep = first.length > 0 && [...first].every((ch) => ch === "-" || ch === ":");
    if (first === "Tür" || first === "" || isSep) continue;
    if (cells.length > 1 && cells[1].includes("Örnek")) continue;
    const [tur, kim, tarih, tekrar, notVal] = [...cells, "", "", "", "", ""].slice(0, 5);
    if (!tarih) continue;
    entries.push({ tur, kim, tarihRaw: tarih, tekrar, not: notVal });
  }
  return entries;
}

function formatCalendarLine(entry, todayDate) {
  const kalanGun = Math.round((entry.tarih.getTime() - todayDate.getTime()) / 86400000);
  const d = entry.tarih.getUTCDate();
  const mName = TR_MONTHS[entry.tarih.getUTCMonth()];
  const y = entry.tarih.getUTCFullYear();
  let ifade;
  if (kalanGun === 0) ifade = `bugün (${d} ${mName} ${y})`;
  else if (kalanGun === 1) ifade = `yarın (${d} ${mName} ${y})`;
  else ifade = `${kalanGun} gün sonra (${d} ${mName} ${y})`;

  const extra = entry.not ? ` — Not: ${entry.not}` : "";
  return `- [${entry.tur}] ${entry.kim}: ${ifade}${extra}`;
}

export function resolveCalendarEntries(vaultRows, noteRows, todayDate) {
  const remindersVault = (vaultRows || []).find((r) => r.path === REMINDERS_VAULT_PATH);
  const rawEntries = parseMarkdownCalendarRows(remindersVault?.content || "");

  for (const n of noteRows || []) {
    if (n.completed || isStaleMetaRow(n)) continue;
    const title = (n.title || "").trim();
    const desc = (n.description || "").trim();
    if (n.category === "appointment" && n.appt_date) {
      let kim = title;
      if (trLower(kim).endsWith(" randevusu")) kim = kim.slice(0, -" randevusu".length).trim();
      const parts = [];
      if (n.appt_time) parts.push(`Saat: ${n.appt_time}`);
      if (n.location) parts.push(`Konum: ${n.location}`);
      if (desc && trLower(desc) !== trLower(title)) parts.push(desc);
      rawEntries.push({ tur: "Randevu", kim: kim || "Randevu", tarihRaw: n.appt_date, tekrar: "", not: parts.join(", ") });
    } else if (n.category === "task" && n.due_date && trLower(n.due_date) !== "yok") {
      rawEntries.push({ tur: "Görev", kim: title || "Görev", tarihRaw: n.due_date, tekrar: "", not: desc });
    } else if (n.category === "reminder" && n.remind_at && trLower(n.remind_at) !== "yok") {
      let kim = title;
      let tur = "Hatırlatma";
      const tLow = trLower(title);
      const dLow = trLower(desc);
      if (tLow.endsWith(" doğum günü")) {
        tur = "Doğum günü";
        kim = title.slice(0, -" doğum günü".length).trim();
      } else if (tLow.includes("doğum günü")) {
        tur = "Doğum günü";
      } else if (tLow.endsWith(" ödeme hatırlatması")) {
        tur = "Ödeme";
        kim = title.slice(0, -" ödeme hatırlatması".length).trim();
      } else if (["ödeme", "fatura", "kredi", "taksit", "aidat"].some((k) => tLow.includes(k) || dLow.includes(k))) {
        tur = "Ödeme";
      }
      rawEntries.push({ tur, kim: kim || "Hatırlatma", tarihRaw: n.remind_at, tekrar: n.repeat_frequency || "", not: desc });
    }
  }

  const seen = new Set();
  const resolved = [];
  for (const e of rawEntries) {
    const dt = resolveCalendarDate(e.tarihRaw, e.tekrar, todayDate);
    if (!dt) continue;
    const key = `${trLower(e.kim).trim()}|${formatIso(dt)}`;
    if (seen.has(key)) continue;
    seen.add(key);
    resolved.push({
      ...e,
      tarih: dt,
      kalanGun: Math.round((dt.getTime() - todayDate.getTime()) / 86400000),
    });
  }

  resolved.sort((a, b) => a.kalanGun - b.kalanGun);
  return resolved;
}

function buildCalendarBlock(vaultRows, noteRows, todayDate) {
  const resolved = resolveCalendarEntries(vaultRows, noteRows, todayDate);
  if (resolved.length === 0) return "(Yaklaşan takvim kaydı yok)";
  return resolved.map((e) => formatCalendarLine(e, todayDate)).join("\n");
}

export function extractDatesFromText(text) {
  if (!text) return [];
  const results = [];
  const seen = new Set();

  const pushDate = (d, m, y) => {
    const dt = tryMakeDate(y, m, d);
    if (!dt) return;
    const label = `${pad2(d)}.${pad2(m)}.${y}`;
    if (seen.has(label)) return;
    seen.add(label);
    results.push({ date: dt, label });
  };

  for (const m of String(text).matchAll(/\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b/g)) {
    pushDate(parseInt(m[1], 10), parseInt(m[2], 10), parseInt(m[3], 10));
  }
  for (const m of String(text).matchAll(/\b(\d{4})-(\d{2})-(\d{2})\b/g)) {
    pushDate(parseInt(m[3], 10), parseInt(m[2], 10), parseInt(m[1], 10));
  }
  const trText = trLower(text);
  for (const m of trText.matchAll(/\b(\d{1,2})\s+(ocak|şubat|mart|nisan|mayıs|haziran|temmuz|ağustos|eylül|ekim|kasım|aralık)[\s-]*(\d{4})\b/gu)) {
    const monthNum = TR_MONTH_NAME_TO_NUM.get(m[2]);
    if (monthNum) pushDate(parseInt(m[1], 10), monthNum, parseInt(m[3], 10));
  }

  return results;
}

function collectDateDiffHints(text, todayDate) {
  const found = extractDatesFromText(text);
  if (!found.length) return "";
  const hints = found.map(({ date: dt, label }) => {
    const diff = Math.round((todayDate.getTime() - dt.getTime()) / 86400000);
    if (diff > 0) return `${label} → bugün itibarıyla üzerinden ${diff} gün geçti`;
    if (diff === 0) return `${label} → bugün`;
    return `${label} → ${Math.abs(diff)} gün sonra`;
  });
  return ` [Tarih hesabı: ${hints.join("; ")}]`;
}

export function isStaleMetaRow(r) {
  const title = (r.title || "").trim();
  const desc = (r.description || "").trim();
  if (title === "Önceki mesajın açıklaması") return true;
  if (desc.includes("önceki belirsiz mesajın açıklaması:")) return true;
  if (desc.endsWith("?")) return true;
  return false;
}

export function buildUnifiedQueryPrompt(question, noteRows, vaultRows, todayParts) {
  const todayDate = tryMakeDate(todayParts.year, todayParts.month, todayParts.day);
  const todayHuman = `${pad2(todayParts.day)}.${pad2(todayParts.month)}.${todayParts.year} (${todayParts.day} ${TR_MONTHS[todayParts.month - 1]} ${todayParts.year} ${TR_DAYS[todayParts.weekdayMon0]})`;

  const cleanNotes = (noteRows || []).filter((r) => !r.completed && !isStaleMetaRow(r));

  const structuredLines = cleanNotes.map((r) => {
    const catLabel = CATEGORY_LABELS[r.category] || "Not";
    const details = [];
    if (r.description && trLower(r.description) !== trLower(r.title || "")) details.push(r.description);
    if (r.product_name) details.push(`Ürün: ${r.product_name}${r.quantity ? ` (${r.quantity})` : ""}`);
    if (r.appt_date) details.push(`Randevu tarihi: ${r.appt_date}${r.appt_time ? ` saat ${r.appt_time}` : ""}`);
    if (r.location) details.push(`Konum: ${r.location}`);
    if (r.remind_at && trLower(r.remind_at) !== "yok") details.push(`Hatırlatma zamanı: ${r.remind_at}`);
    const body = details.length ? ` — ${details.join(" | ")}` : "";
    const diffHint = collectDateDiffHints(`${r.title || ""} ${r.description || ""} ${r.appt_date || ""} ${r.remind_at || ""}`, todayDate);
    return `- [${catLabel}] ${r.title}${body}${diffHint}`;
  });

  const calendarBlock = buildCalendarBlock(vaultRows, cleanNotes, todayDate);

  const matchedVault = searchVaultNotes(vaultRows || [], question, 8);
  const vaultBlocks = matchedVault.map((v) => {
    const clipped = v.content.length > 4000 ? v.content.slice(0, 4000) + "…" : v.content;
    const diffHint = collectDateDiffHints(clipped, todayDate);
    return `### ${v.title} (${v.path})${diffHint}\n${clipped}`;
  });

  return `Sen kullanıcının kişisel notlarına ve veritabanına erişimi olan Türkçe bir asistansın.
Bugünün tarihi: ${todayHuman}

KURALLAR:
1. SADECE aşağıdaki üç bölümde ("TAKVİM VE YAKLAŞAN KAYITLAR", "AKTİF VERİTABANI NOTLARI", "İLGİLİ KİŞİSEL KASA NOTLARI") yer alan bilgilere dayanarak cevap ver. Bu bölümlerin hiçbirinde sorunun cevabı yoksa SADECE ve TAM OLARAK şunu yaz: Notlarımda bu konuda bir şey bulamadım.
2. Notlar kullanıcının kendi birinci tekil şahsıyla ("ben", "başvurdum", "alacağım") yazılmış olabilir; kullanıcıya doğrudan ikinci tekil şahısla ("sen", "başvurdun", "alacaksın", "not almışsın") hitap ederek doğal ve kısa bir Türkçe cevap ver.
3. "[Tarih hesabı: ...]" veya takvim satırlarında önceden hesaplanmış gün sayılarını ("40 gün önce", "2 gün sonra" vb.) OLDUĞU GİBİ kullan; gün sayısını kendin yeniden hesaplamaya çalışma.
4. İçsel etiketleri ("[Alışveriş]", "00_Gelen_Kutusu/..." dosya yollarını veya "(Yapılacaklar listesine ekle)" gibi ham komut parantezlerini) cevaba olduğu gibi kopyalama; temiz ve akıcı ifade et.

=== 1) TAKVİM VE YAKLAŞAN KAYITLAR ===
${calendarBlock}

=== 2) AKTİF VERİTABANI NOTLARI (${cleanNotes.length} aktif kayıt, kasada toplam ${(vaultRows || []).length} not) ===
${structuredLines.length ? structuredLines.join("\n") : "(Aktif yapılandırılmış not yok)"}

=== 3) İLGİLİ KİŞİSEL KASA NOTLARI (HAKKIMDA) ===
${vaultBlocks.length ? vaultBlocks.join("\n\n") : "(Bu soruyla doğrudan eşleşen kasa notu yok)"}

SORU: ${question}
CEVAP:`;
}
