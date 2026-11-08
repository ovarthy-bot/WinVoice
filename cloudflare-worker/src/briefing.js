// src/briefing.js
//
// Akıllı Günlük Brifing'in bulut (Cloudflare Worker + D1 + Groq) orkestratörü.
// Masaüstü Python mimarisiyle (briefing_data.py + briefing_text.py +
// briefing_coordinator.py + learning_cards.py + persona_settings.py) %100 eşleniktir:
//   1. Kişisel Görev, Takvim ve Alışveriş Koordinatörü (D1 notes + Doğum Günleri ve Randevular.md)
//   2. R1D Vardiya & İş Günü Hazırlığı (07-15 / 15-23 / Tatil + Eksik Eğitimlerim.md)
//   3. Saatlik Hava & Kıyafet Rehberi (çıkış / gün içi / dönüş dilimleri)
//   4. Koşullu Piyasa Filtresi (<%1,5 döviz/altın/BIST ve <%3,5 BTC ise tamamen atlanır)
//   5. 3 Eksenli Kişisel Haber Motoru (Havacılık, YZ/Yazılım, TR/Dünya + seen_news hafızası)
//   6. Aralıklı Tekrarlı İngilizce Öğrenme Kartı ([✅ Öğrendim] / [🔁 Tekrar Sor] butonlu)
//   7. Haftalık Aktif Proje Odağı (Pazartesi günleri)

import {
  getConfigValue,
  httpGetJson,
  httpGetText,
  nowIstanbulIso,
  sendTelegramMessage,
  setConfigValue,
  stripHtmlTags,
} from "./common.js";
import { getPrioritizedEvents } from "./events.js";
import { tryMakeDate } from "./knowledge.js";
import {
  buildPersonalCoordinationTelegram,
  buildWeeklyProjectTelegram,
  buildWorkdayPrepTelegram,
  collectPersonalCoordinationData,
  fetchAllowlistedVaultMap,
  resolveShiftForDate,
  toIsoDateUtc,
} from "./briefing_coordinator.js";
import {
  VAULT_ENGLISH_WORDS_PATH,
  buildLearningCardInlineMarkup,
  formatLearningCardTelegram,
  selectDailyLearningCard,
} from "./learning.js";

const LATITUDE = 41.1431;
const LONGITUDE = 28.4606;
const LOCATION = "İstanbul / Çatalca";

const FEED_SOURCES = [
  { name: "AeroTime", category: "HAVACILIK", itemTag: "item", summaryTag: "description", pubTag: "pubDate", url: "https://www.aerotime.aero/feed", limit: 8 },
  { name: "HavaSosyalMedya", category: "HAVACILIK", itemTag: "item", summaryTag: "description", pubTag: "pubDate", url: "https://www.havasosyalmedya.com/feed/", limit: 6 },
  { name: "AirlineHaber", category: "HAVACILIK", itemTag: "item", summaryTag: "description", pubTag: "pubDate", url: "https://www.airlinehaber.com/feed/", limit: 6 },
  { name: "TechCrunchAI", category: "YAPAY ZEKA VE YAZILIM", itemTag: "item", summaryTag: "description", pubTag: "pubDate", url: "https://techcrunch.com/category/artificial-intelligence/feed/", limit: 6 },
  { name: "GitHubBlog", category: "YAPAY ZEKA VE YAZILIM", itemTag: "item", summaryTag: "description", pubTag: "pubDate", url: "https://github.blog/feed/", limit: 5 },
  { name: "HackerNews", category: "YAPAY ZEKA VE YAZILIM", itemTag: "item", summaryTag: "description", pubTag: "pubDate", url: "https://hnrss.org/frontpage?points=150", limit: 6 },
  { name: "NTVGundem", category: "TÜRKİYE", itemTag: "entry", summaryTag: "summary", pubTag: "published", url: "https://www.ntv.com.tr/gundem.rss", limit: 8 },
  { name: "NTVDunya", category: "DÜNYA", itemTag: "entry", summaryTag: "summary", pubTag: "published", url: "https://www.ntv.com.tr/dunya.rss", limit: 6 },
  { name: "BBCTurkce", category: "DÜNYA", itemTag: "item", summaryTag: "description", pubTag: "pubDate", url: "https://feeds.bbci.co.uk/turkce/rss.xml", limit: 6 },
];

const TCMB_RATES_URL = "https://www.tcmb.gov.tr/kurlar/today.xml";
const USDTRY_YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/TRY=X";
const BIST100_URL = "https://query1.finance.yahoo.com/v8/finance/chart/XU100.IS";
const GOLD_FUTURES_URL = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F";
const BTC_PRICE_URL =
  "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=try,usd&include_24hr_change=true";
const GRAMS_PER_OUNCE = 31.1034768;

const FX_GOLD_BIST_THRESHOLD_PCT = 1.5;
const BTC_THRESHOLD_PCT = 3.5;

const NEWS_SUMMARY_MAX_LEN = 190;

const CLICKBAIT_PATTERNS = [
  "son dakika", "açıklandı", "sorgulama", "canlı sonuç", "canlı sonuçlar",
  "çekiliş sonuçları", "kazandıran numaralar", "sorgula", "belli oldu",
  "şok karar", "bakın kim", "inanılmaz", "görenler şaşırdı",
];

const AVIATION_HIGH_KEYWORDS = [
  "airbus", "boeing", "easa", "shgm", "faa", "thy", "türk hava yolları",
  "turkish airlines", "turkish technic", "iga", "istanbul havalimanı",
  "mro", "kabin", "cabin", "maintenance", "bakım", "airworthiness",
  "a320", "a321", "a330", "a350", "b737", "b777", "b787", "777", "330",
  "escape slide", "emergency", "avionics", "hangar", "filo", "uçak",
];

const AI_DEV_HIGH_KEYWORDS = [
  "ai", "artificial intelligence", "yapay zeka", "llm", "agent", "agents",
  "claude", "anthropic", "openai", "gpt", "gemini", "ollama", "local model",
  "open source", "github", "copilot", "flutter", "dart", "python", "windows",
  "sqlite", "cloudflare", "reasoning", "coding", "developer",
];

const GENERAL_IMPORTANCE_KEYWORDS = [
  "safety", "directive", "recall", "release", "launched", "announces",
  "merkez bankası", "faiz", "enflasyon", "istanbul", "çatalca", "deprem",
  "savunma", "teknofest", "uzay", "anlaşma", "yönetmelik",
];

const NEWS_STOPWORDS = new Set([
  "the", "and", "for", "with", "from", "that", "this", "into", "over", "after",
  "new", "how", "why", "bir", "ile", "için", "olan", "göre", "daha", "yeni",
  "olarak", "sonra", "kadar", "üzerine", "ilgili",
]);

const WEATHER_CODES = {
  0: "Açık", 1: "Az bulutlu", 2: "Parçalı Bulutlu", 3: "Kapalı",
  45: "Sisli", 48: "Kırağı sisi",
  51: "Hafif çisenti", 53: "Çisenti", 55: "Yoğun çisenti",
  61: "Hafif Yağmur", 63: "Yağmur", 65: "Şiddetli yağmur",
  71: "Hafif kar", 73: "Kar", 75: "Yoğun kar",
  80: "Sağanak", 81: "Kuvvetli sağanak", 82: "Şiddetli sağanak",
  95: "Gök gürültülü fırtına", 96: "Dolu ile fırtına", 99: "Şiddetli dolu fırtınası",
};

const RAIN_CODES = new Set([51, 53, 55, 61, 63, 65, 80, 81, 82, 95, 96, 99]);
const SNOW_CODES = new Set([71, 73, 75]);
const FOG_CODES = new Set([45, 48]);

const TR_MONTHS = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"];
const TR_DAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"];

const KNOWN_SECTION_HEADER_RE =
  /^\s*[\*_#]{0,3}\s*(giriş|hava\s*&\s*piyasa|hava\s+ve\s+piyasa|seçilmiş\s+gündem|havacılık|yapay\s+zeka|türkiye\s+gündemi|dünya\s+turu|teknoloji|kapanış)\s*[:：]\s*[\*_#]{0,3}\s*/i;

// --------------------------------------------------------------------------- //
// RSS Okuma + 3 Eksenli Haber Puanlama + seen_news Hafızası
// --------------------------------------------------------------------------- //

function isClickbait(title) {
  const lower = title.toLowerCase().trim();
  if (lower.endsWith("?")) return true;
  return CLICKBAIT_PATTERNS.some((p) => lower.includes(p));
}

function truncate(text, maxLen = NEWS_SUMMARY_MAX_LEN) {
  if (!text) return "";
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen).replace(/\s+$/, "") + "…";
}

function extractBlocks(xml, tagName) {
  const re = new RegExp(`<${tagName}(?:\\s[^>]*)?>([\\s\\S]*?)</${tagName}>`, "gi");
  const blocks = [];
  let m;
  while ((m = re.exec(xml)) !== null) blocks.push(m[1]);
  return blocks;
}

function extractTag(block, tagName) {
  const re = new RegExp(`<${tagName}(?:\\s[^>]*)?>([\\s\\S]*?)</${tagName}>`, "i");
  const m = block.match(re);
  if (!m) return "";
  let content = m[1].trim();
  const cdata = content.match(/^<!\[CDATA\[([\s\S]*)\]\]>$/);
  if (cdata) content = cdata[1];
  return content;
}

function titleTokens(title) {
  const cleaned = String(title || "")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, " ");
  const out = new Set();
  for (const tok of cleaned.split(/\s+/)) {
    if (tok.length >= 3 && !NEWS_STOPWORDS.has(tok) && !/^\d+$/.test(tok)) {
      out.add(tok);
    }
  }
  return out;
}

function newsFingerprint(title) {
  const sorted = [...titleTokens(title)].sort();
  const basis = sorted.length ? sorted.slice(0, 8).join(" ") : String(title || "").toLowerCase().trim();
  // FNV-1a çift 32-bit deterministik özet
  let h1 = 0x811c9dc5;
  let h2 = 0x01000193;
  for (let i = 0; i < basis.length; i++) {
    const ch = basis.charCodeAt(i);
    h1 ^= ch;
    h1 = Math.imul(h1, 0x01000193) >>> 0;
    h2 ^= ch + i;
    h2 = Math.imul(h2, 0x85ebca6b) >>> 0;
  }
  return h1.toString(16).padStart(8, "0") + h2.toString(16).padStart(8, "0");
}

function jaccardSimilarity(setA, setB) {
  if (!setA.size || !setB.size) return 0;
  let inter = 0;
  for (const x of setA) {
    if (setB.has(x)) inter++;
  }
  const union = setA.size + setB.size - inter;
  return union ? inter / union : 0;
}

async function fetchSingleFeed(source) {
  try {
    const xml = await httpGetText(source.url);
    const results = [];
    for (const block of extractBlocks(xml, source.itemTag)) {
      const title = stripHtmlTags(extractTag(block, "title"));
      if (!title || isClickbait(title)) continue;
      const summary = truncate(stripHtmlTags(extractTag(block, source.summaryTag)));
      const linkMatch = block.match(/<link[^>]+href=["']([^"']+)["']/i);
      const link = (linkMatch ? linkMatch[1] : extractTag(block, "link") || "").trim();
      const pubRaw = extractTag(block, source.pubTag) || extractTag(block, "updated") || "";
      const pubMs = pubRaw ? Date.parse(pubRaw) : NaN;
      results.push({
        title,
        summary,
        link,
        category: source.category,
        source: source.name,
        pubMs: Number.isFinite(pubMs) ? pubMs : null,
      });
      if (results.length >= source.limit) break;
    }
    return results;
  } catch (e) {
    console.error(`RSS alınamadı (${source.name}):`, e);
    return [];
  }
}

function scoreNewsItem(item, nowMs, duplicateCount = 1) {
  const haystack = `${item.title} ${item.summary || ""}`.toLowerCase();
  const cat = item.category;

  const aviHits = AVIATION_HIGH_KEYWORDS.filter((kw) => haystack.includes(kw)).length;
  const aiHits = AI_DEV_HIGH_KEYWORDS.filter((kw) => haystack.includes(kw)).length;

  let interest;
  if (cat === "HAVACILIK" || aviHits >= 1) interest = Math.min(50, 34 + aviHits * 6);
  else if (cat === "YAPAY ZEKA VE YAZILIM" || aiHits >= 1) interest = Math.min(48, 30 + aiHits * 5);
  else if (cat === "TÜRKİYE") interest = 24;
  else interest = 20;

  const impHits = GENERAL_IMPORTANCE_KEYWORDS.filter((kw) => haystack.includes(kw)).length;
  const multiBoost = Math.min(14, (duplicateCount - 1) * 8);
  const summaryBonus = (item.summary || "").length >= 50 ? 4 : 0;
  const importance = Math.min(30, 8 + impHits * 5 + multiBoost + summaryBonus);

  let recency = 10;
  if (item.pubMs !== null) {
    const ageHours = Math.max(0, (nowMs - item.pubMs) / 3600000);
    if (ageHours > 36) return -1;
    if (ageHours <= 6) recency = 20;
    else if (ageHours <= 14) recency = 15;
    else if (ageHours <= 24) recency = 10;
    else recency = 5;
  }

  return interest + importance + recency;
}

function selectPersonalizedNews(rawItems, seenFingerprints, lengthMode = "balanced") {
  const nowMs = Date.now();
  const clusters = [];

  for (const item of rawItems) {
    const tokens = titleTokens(item.title);
    const fp = newsFingerprint(item.title);
    let merged = false;
    for (const cl of clusters) {
      if (cl.fingerprint === fp || jaccardSimilarity(tokens, cl.tokens) >= 0.42) {
        cl.count += 1;
        if ((item.summary || "").length > (cl.rep.summary || "").length) {
          cl.rep = item;
        }
        merged = true;
        break;
      }
    }
    if (!merged) {
      clusters.push({ rep: item, tokens, fingerprint: fp, count: 1 });
    }
  }

  const scored = [];
  for (const cl of clusters) {
    if (seenFingerprints.has(cl.fingerprint)) continue;
    const score = scoreNewsItem(cl.rep, nowMs, cl.count);
    if (score < 0) continue;
    scored.push({ ...cl.rep, fingerprint: cl.fingerprint, score });
  }
  scored.sort((a, b) => b.score - a.score);

  const targetTotal = lengthMode === "short" ? 3 : lengthMode === "detailed" ? 6 : 4;
  const selected = [];
  const usedFps = new Set();

  const preferredBuckets = [
    ["HAVACILIK"],
    ["YAPAY ZEKA VE YAZILIM"],
    ["TÜRKİYE", "DÜNYA"],
  ];

  for (const allowed of preferredBuckets) {
    if (selected.length >= targetTotal) break;
    const found = scored.find((c) => !usedFps.has(c.fingerprint) && allowed.includes(c.category));
    if (found) {
      selected.push(found);
      usedFps.add(found.fingerprint);
    }
  }

  const catCounts = {};
  for (const s of selected) catCounts[s.category] = (catCounts[s.category] || 0) + 1;

  for (const cand of scored) {
    if (selected.length >= targetTotal) break;
    if (usedFps.has(cand.fingerprint)) continue;
    if ((catCounts[cand.category] || 0) >= 2 && lengthMode !== "detailed") continue;
    selected.push(cand);
    usedFps.add(cand.fingerprint);
    catCounts[cand.category] = (catCounts[cand.category] || 0) + 1;
  }

  return selected;
}

async function getSeenNewsSet(db) {
  try {
    const cutoff = new Date(Date.now() - 7 * 86400000 + 3 * 3600000).toISOString();
    const rows = await db.prepare("SELECT fingerprint FROM seen_news WHERE shown_at >= ?").bind(cutoff).all();
    return new Set((rows.results || []).map((r) => r.fingerprint));
  } catch (_) {
    return new Set();
  }
}

async function recordSeenNews(db, selectedItems) {
  if (!selectedItems || !selectedItems.length) return;
  try {
    const nowIso = nowIstanbulIso();
    const pruneCutoff = new Date(Date.now() - 14 * 86400000).toISOString();
    await db.prepare("DELETE FROM seen_news WHERE shown_at < ?").bind(pruneCutoff).run();
    for (const it of selectedItems) {
      await db
        .prepare(
          "INSERT INTO seen_news (fingerprint, title, category, shown_at) VALUES (?, ?, ?, ?) " +
            "ON CONFLICT(fingerprint) DO UPDATE SET shown_at = excluded.shown_at"
        )
        .bind(it.fingerprint, it.title, it.category, nowIso)
        .run();
    }
  } catch (e) {
    console.error("seen_news güncellenemedi:", e);
  }
}

async function fetchNewsItemsText(db, lengthMode = "balanced") {
  const feedArrays = await Promise.all(FEED_SOURCES.map((src) => fetchSingleFeed(src)));
  const rawItems = feedArrays.flat();
  const seenSet = await getSeenNewsSet(db);

  let selected = selectPersonalizedNews(rawItems, seenSet, lengthMode);
  if (!selected.length && rawItems.length) {
    selected = selectPersonalizedNews(rawItems, new Set(), lengthMode);
  }
  if (!selected.length) return "(Haber akışı alınamadı.)";

  await recordSeenNews(db, selected);

  return selected
    .map((item) => {
      let line = `[${item.category}] ${item.title}`;
      if (item.summary) line += ` — ${item.summary}`;
      if (item.link) line += ` (Kaynak: ${item.link})`;
      return line;
    })
    .join("\n");
}

// --------------------------------------------------------------------------- //
// Saatlik Hava Durumu & Vardiya Uyumlu Kıyafet Rehberi
// --------------------------------------------------------------------------- //

async function fetchWeatherForBriefing() {
  const url =
    "https://api.open-meteo.com/v1/forecast" +
    `?latitude=${LATITUDE}&longitude=${LONGITUDE}` +
    "&current=temperature_2m,apparent_temperature,relative_humidity_2m,surface_pressure,wind_speed_10m,weather_code" +
    "&hourly=temperature_2m,apparent_temperature,precipitation_probability,wind_gusts_10m,weather_code" +
    "&daily=weather_code,temperature_2m_max,temperature_2m_min" +
    "&timezone=Europe%2FIstanbul&forecast_days=7";

  const data = await httpGetJson(url);
  const current = data.current || {};
  const today = (data.daily?.time || []).length
    ? {
        code: data.daily.weather_code[0],
        tmax: data.daily.temperature_2m_max[0],
        tmin: data.daily.temperature_2m_min[0],
      }
    : {};

  const hourlyRaw = data.hourly || {};
  const hTimes = hourlyRaw.time || [];
  const hourly = [];
  for (let i = 0; i < Math.min(32, hTimes.length); i++) {
    hourly.push({
      hourIndex: i,
      temp: hourlyRaw.temperature_2m?.[i] ?? null,
      apparent: hourlyRaw.apparent_temperature?.[i] ?? null,
      precipProb: hourlyRaw.precipitation_probability?.[i] ?? 0,
      windGust: hourlyRaw.wind_gusts_10m?.[i] ?? 0,
      code: hourlyRaw.weather_code?.[i] ?? 0,
    });
  }

  return {
    sicaklik_c: current.temperature_2m,
    hissedilen_c: current.apparent_temperature,
    aciklama: WEATHER_CODES[current.weather_code] ?? "Bilinmiyor",
    nem_yuzde: current.relative_humidity_2m,
    ruzgar_kmh: current.wind_speed_10m,
    bugun_max_c: today.tmax,
    bugun_min_c: today.tmin,
    hourly,
  };
}

function getShiftWeatherWindows(shiftCode) {
  if (shiftCode === "07-15") {
    return [
      { spokenLbl: "sabah çıkarken", tgLbl: "Sabah çıkış (05-07)", start: 5, end: 7 },
      { spokenLbl: "öğle saatlerinde", tgLbl: "Gün içi (11-14)", start: 11, end: 14 },
      { spokenLbl: "akşamüstü dönerken", tgLbl: "Dönüş (16-18)", start: 16, end: 18 },
    ];
  }
  if (shiftCode === "15-23") {
    return [
      { spokenLbl: "öğlen çıkarken", tgLbl: "Öğlen çıkış (12-14)", start: 12, end: 14 },
      { spokenLbl: "akşam saatlerinde", tgLbl: "Akşam (17-20)", start: 17, end: 20 },
      { spokenLbl: "gece dönerken", tgLbl: "Gece dönüş (23-00)", start: 23, end: 25 },
    ];
  }
  return [
    { spokenLbl: "sabah saatlerinde", tgLbl: "Sabah (07-10)", start: 7, end: 10 },
    { spokenLbl: "gün ortasında", tgLbl: "Öğle (12-16)", start: 12, end: 16 },
    { spokenLbl: "akşam saatlerinde", tgLbl: "Akşam (18-21)", start: 18, end: 21 },
  ];
}

function summarizeHourlyWindow(hourly, startIdx, endIdx) {
  const pts = (hourly || []).filter(
    (p) => p.hourIndex >= startIdx && p.hourIndex <= endIdx && p.temp !== null && p.temp !== undefined
  );
  if (!pts.length) return null;
  const avgTemp = Math.round(pts.reduce((s, p) => s + p.temp, 0) / pts.length);
  const avgApparent = Math.round(pts.reduce((s, p) => s + (p.apparent ?? p.temp), 0) / pts.length);
  const maxPrecip = Math.max(...pts.map((p) => Number(p.precipProb || 0)));
  const maxGust = Math.round(Math.max(...pts.map((p) => Number(p.windGust || 0))));
  const hasRain = pts.some((p) => RAIN_CODES.has(Number(p.code))) || maxPrecip >= 45;
  const hasSnow = pts.some((p) => SNOW_CODES.has(Number(p.code)));
  const hasFog = pts.some((p) => FOG_CODES.has(Number(p.code)));
  return { temp: avgTemp, apparent: avgApparent, maxPrecip, maxGust, hasRain, hasSnow, hasFog };
}

function topClothingAdvice(minApp, maxApp) {
  if (minApp <= 4) return "kalın mont veya kabanla çık";
  if (minApp <= 11) {
    if (maxApp >= 18) return "sabah serinliği için ceket veya mont giy, öğlen ısınacağı için içine ince katman seç";
    return "mont veya kalın bir ceket tercih et";
  }
  if (maxApp < 21) return "ince bir ceket veya uzun kollu katman yeterli olur";
  return "hafif gömlek veya tişörtle rahat edersin";
}

function buildSmartWeatherTelegram(weatherData, shiftCode = "tatil") {
  const w = weatherData || {};
  const windows = getShiftWeatherWindows(shiftCode);
  const winStats = [];

  for (const win of windows) {
    const st = summarizeHourlyWindow(w.hourly, win.start, win.end);
    if (st) winStats.push({ ...win, ...st });
  }

  if (!winStats.length) {
    if (w.sicaklik_c === undefined || w.sicaklik_c === null) return "";
    const cur = Math.round(w.sicaklik_c);
    const low = Math.round(w.bugun_min_c ?? cur);
    const high = Math.round(w.bugun_max_c ?? cur);
    const advice = topClothingAdvice(low, high);
    return `🌤️ Hava & Hazırlık:\n• Çatalca: ${w.aciklama || ""}, ${cur}°C (${low}°C / ${high}°C)\n• Öneri: ${advice}.`;
  }

  const minApp = Math.min(...winStats.map((x) => x.apparent));
  const maxApp = Math.max(...winStats.map((x) => x.apparent));
  const maxGust = Math.max(...winStats.map((x) => x.maxGust));
  const rainWindows = winStats.filter((x) => x.hasRain);
  const snowWindows = winStats.filter((x) => x.hasSnow);
  const fogOut = winStats[0].hasFog;

  const tips = [topClothingAdvice(minApp, maxApp)];
  if (maxApp - minApp >= 7 && !tips[0].includes("katman")) {
    tips.push("hissedilen sıcaklık gün içinde belirgin değişeceği için katmanlı giyin");
  }
  if (snowWindows.length) {
    tips.push("kar beklentisi nedeniyle su geçirmez bot ve eldiven al");
  } else if (rainWindows.length) {
    const whenLbl = rainWindows.slice(0, 2).map((x) => x.spokenLbl).join(" ve ");
    const peakP = Math.max(...rainWindows.map((x) => x.maxPrecip));
    tips.push(`${whenLbl} yağış ihtimali %${peakP}, yanına şemsiye veya yağmurluk al`);
  }
  if (maxGust >= 38) {
    tips.push(`rüzgar hamlesi ${maxGust} km/s, rüzgar kesici dış katman iyi olur`);
  }
  if (fogOut) {
    tips.push("çıkış saatinde sis beklendiği için birkaç dakika erken çıkmakta fayda var");
  }

  const winSummary = winStats
    .map((x) => `${x.tgLbl}: ${x.apparent}°C` + (x.maxPrecip >= 30 ? ` (🌧️%${x.maxPrecip})` : ""))
    .join(" | ");

  return `🌤️ Saatlik Hava & Kıyafet Rehberi:\n• ${winSummary}\n• Hazırlık: ${tips.join("; ")}.`;
}

// --------------------------------------------------------------------------- //
// Koşullu Piyasa Filtresi (<%1,5 döviz/altın/BIST ve <%3,5 BTC ise tamamen atlanır)
// --------------------------------------------------------------------------- //

async function yahooPriceAndPct(url) {
  const data = await httpGetJson(url);
  const meta = data.chart.result[0].meta;
  const price = meta.regularMarketPrice;
  let pct = meta.regularMarketChangePercent;
  if (pct === undefined || pct === null) {
    const prev = meta.chartPreviousClose || meta.previousClose;
    if (price && prev) pct = ((price - prev) / prev) * 100;
  }
  return { price, pct: Number.isFinite(pct) ? Math.round(pct * 100) / 100 : 0 };
}

async function fetchFinance() {
  const result = {};
  let usdTry = null;
  let usdPct = 0;

  try {
    const xml = await httpGetText(TCMB_RATES_URL);
    const usdBlockMatch = xml.match(/<Currency[^>]*Kod="USD"[^>]*>([\s\S]*?)<\/Currency>/i);
    if (usdBlockMatch) {
      const forexSelling = extractTag(usdBlockMatch[1], "ForexSelling");
      usdTry = parseFloat(forexSelling);
      if (Number.isFinite(usdTry)) result.usd_try_satis = Math.round(usdTry * 10000) / 10000;
    }
  } catch (e) {
    console.error("TCMB dolar kuru alınamadı:", e);
  }

  try {
    const { price, pct } = await yahooPriceAndPct(USDTRY_YAHOO_URL);
    usdPct = pct;
    result.usd_try_gunluk_yuzde_degisim = usdPct;
    if (!usdTry && price) {
      usdTry = price;
      result.usd_try_satis = Math.round(usdTry * 10000) / 10000;
    }
  } catch (e) {
    console.error("USD/TRY değişim yüzdesi alınamadı:", e);
  }

  try {
    const { price, pct } = await yahooPriceAndPct(BIST100_URL);
    if (price) {
      result.bist100 = Math.round(price * 100) / 100;
      result.bist100_gunluk_yuzde_degisim = pct;
    }
  } catch (e) {
    console.error("BIST100 verisi alınamadı:", e);
  }

  try {
    const { price: goldUsdOz, pct: goldUsdPct } = await yahooPriceAndPct(GOLD_FUTURES_URL);
    if (goldUsdOz && usdTry) {
      result.gram_altin_try = Math.round(((goldUsdOz * usdTry) / GRAMS_PER_OUNCE) * 100) / 100;
      result.gram_altin_gunluk_yuzde_degisim = Math.round((goldUsdPct + usdPct) * 100) / 100;
    }
  } catch (e) {
    console.error("Altın verisi alınamadı:", e);
  }

  try {
    const data = await httpGetJson(BTC_PRICE_URL);
    const btc = data.bitcoin || {};
    result.btc_try = btc.try;
    result.btc_usd = btc.usd;
    const btcPct = btc.try_24h_change ?? btc.usd_24h_change;
    if (Number.isFinite(btcPct)) {
      result.btc_gunluk_yuzde_degisim = Math.round(btcPct * 100) / 100;
    }
  } catch (e) {
    console.error("BTC verisi alınamadı:", e);
  }

  return result;
}

function signPct(pct) {
  return pct > 0 ? `+%${pct.toFixed(2)}` : `%${pct.toFixed(2)}`;
}

function buildConditionalFinanceTelegram(financeData, financeMode = "significant") {
  if (financeMode === "off" || !financeData) return "";

  const f = financeData;
  const usdVal = f.usd_try_satis;
  const usdPct = f.usd_try_gunluk_yuzde_degisim || 0;
  const goldVal = f.gram_altin_try;
  const goldPct = f.gram_altin_gunluk_yuzde_degisim || 0;
  const bistVal = f.bist100;
  const bistPct = f.bist100_gunluk_yuzde_degisim || 0;
  const btcUsd = f.btc_usd;
  const btcPct = f.btc_gunluk_yuzde_degisim || 0;

  const includeAll = financeMode === "always";
  const movers = [];

  if (usdVal !== undefined && (includeAll || Math.abs(usdPct) >= FX_GOLD_BIST_THRESHOLD_PCT)) {
    movers.push(Math.abs(usdPct) >= 0.05 ? `USD/TRY: ${usdVal.toFixed(2)} ₺ (${signPct(usdPct)})` : `USD/TRY: ${usdVal.toFixed(2)} ₺`);
  }
  if (goldVal !== undefined && (includeAll || Math.abs(goldPct) >= FX_GOLD_BIST_THRESHOLD_PCT)) {
    movers.push(Math.abs(goldPct) >= 0.05 ? `Gram Altın: ${Math.round(goldVal)} ₺ (${signPct(goldPct)})` : `Gram Altın: ${Math.round(goldVal)} ₺`);
  }
  if (bistVal !== undefined && (includeAll || Math.abs(bistPct) >= FX_GOLD_BIST_THRESHOLD_PCT)) {
    movers.push(`BIST 100: ${Math.round(bistVal)} (${signPct(bistPct)})`);
  }
  if (btcUsd !== undefined && (includeAll || Math.abs(btcPct) >= BTC_THRESHOLD_PCT)) {
    movers.push(`BTC: ${Math.round(btcUsd).toLocaleString("tr-TR")} USD (${signPct(btcPct)})`);
  }

  if (!movers.length) return "";
  const header = financeMode === "significant" ? "📈 Piyasa Hareketi:" : "📈 Piyasa Özeti:";
  return `${header}\n• ${movers.join(" | ")}`;
}

// --------------------------------------------------------------------------- //
// Persona / Zaman / Uzunluk Yardımcıları ve Prompt İnşası
// --------------------------------------------------------------------------- //

function pad2(n) {
  return String(n).padStart(2, "0");
}

function formatTrDateTime(parts) {
  const dateStr = `${parts.day} ${TR_MONTHS[parts.month - 1]} ${parts.year} ${TR_DAYS[parts.weekdayMon0]}`;
  return `${dateStr} ${pad2(parts.hour)}:${pad2(parts.minute)}`;
}

function espriTalimati(pct) {
  if (pct <= 20) return "Neredeyse hiç espri yapma; ciddi ve sade bir üslup kullan.";
  if (pct <= 40) return "Çok nadiren, sadece uygun olduğunda hafif bir espri yap.";
  if (pct <= 60) return "Ara sıra, ölçülü bir espri/şaka ekleyebilirsin.";
  if (pct <= 80) return "Sık sık hafif espirili, eğlenceli bir ton kullan.";
  return "Çok esprili, şakacı ve eğlenceli bir üslup kullan; fırsat buldukça espri yap.";
}

function arkadaslikTalimati(pct) {
  if (pct <= 20) return "Resmi, mesafeli ve kısa bir üslup kullan.";
  if (pct <= 40) return "Biraz resmi ama kibar bir üslup kullan.";
  if (pct <= 60) return "Sıcak ama ölçülü, dengeli bir üslup kullan.";
  if (pct <= 80) return "Samimi, sıcak ve arkadaş canlısı bir üslup kullan.";
  return "Çok samimi, yakın bir arkadaş gibi sıcak ve içten bir üslup kullan.";
}

function hitapTalimati(hitapMode) {
  if (hitapMode === "patron") {
    return 'Kullanıcıya "Patron" diye hitap et; ancak metin boyunca en fazla bir veya iki kez kullan.';
  }
  if (hitapMode === "hitapsiz") {
    return 'Kullanıcıya "Patron", "Onur" gibi herhangi bir özel isim veya unvan kullanmadan doğrudan ve doğal hitap et.';
  }
  return 'Kullanıcıya ismiyle ("Onur") doğal şekilde hitap et (yalnızca selamlamada ve uygunsa kapanışta bir kez kullan; her cümlede tekrarlama ve asla "Patron" deme).';
}

function lengthTalimati(lengthMode) {
  if (lengthMode === "short") {
    return "KISA MOD: Haber özetlerini çok öz tut; toplamda yalnızca en kritik 2 haberi birer kısa cümleyle aktar.";
  }
  if (lengthMode === "detailed") {
    return "DETAYLI MOD: Seçilmiş haberlerin her birini bir veya iki doyurucu cümleyle, bağlamını da vererek aktar (toplam 5-6 haber).";
  }
  return "DENGELİ MOD: Seçilmiş haberlerden en önemli 3-4 gelişmeyi sıkmadan, net ve akıcı birer cümleyle özetle.";
}

function briefingTimeContext(hour) {
  if (hour >= 4 && hour < 12) {
    return {
      greeting: "Günaydın",
      roleDesc: "Kullanıcıya güne başlarken kişisel sabah yaşam koordinasyonu brifingi hazırlıyorsun.",
      closingHint: "Sabah enerjisine uygun, bugünkü ana odağı destekleyen net ve sıcak tek bir kapanış cümlesi kur.",
    };
  }
  if (hour >= 12 && hour < 18) {
    return {
      greeting: "Tünaydın",
      roleDesc: "Kullanıcıya gün ortası kişisel durum ve gündem koordinasyonu brifingi hazırlıyorsun.",
      closingHint: "Günün kalan yarısı için odaklayıcı ve kısa tek bir kapanış cümlesi kur.",
    };
  }
  if (hour >= 18 && hour < 22) {
    return {
      greeting: "İyi akşamlar",
      roleDesc: "Kullanıcıya akşam değerlendirmesi ve yarına hazırlık brifingi hazırlıyorsun.",
      closingHint: "Günü toparlayan ve yarına sakin bir geçiş sağlayan tek bir kapanış cümlesi kur.",
    };
  }
  return {
    greeting: "İyi geceler",
    roleDesc: "Kullanıcıya gece sonu kısa özet ve yarına hazırlık brifingi hazırlıyorsun.",
    closingHint: "Dinlenmeyi hatırlatan ve yarınki güne huzurlu bir başlangıç dileyen kısa tek bir kapanış cümlesi kur.",
  };
}

function stripKnownSectionHeaders(text) {
  return String(text || "")
    .split("\n")
    .map((line) => line.replace(KNOWN_SECTION_HEADER_RE, ""))
    .join("\n");
}

function buildEventsTelegram(events, lengthMode = "balanced") {
  if (!events || !events.length) return "";
  const cap = lengthMode === "short" ? 1 : lengthMode === "detailed" ? 3 : 2;
  const seen = new Set();
  const unique = [];
  for (const e of events) {
    const t = String(e.title || "").trim();
    if (!t || seen.has(t.toLowerCase())) continue;
    seen.add(t.toLowerCase());
    unique.push(t);
    if (unique.length >= cap) break;
  }
  if (!unique.length) return "";
  return "🎟️ Öne Çıkan Etkinlikler:\n" + unique.map((t) => `• ${t}`).join("\n");
}

function buildBriefingPrompt({
  location,
  time,
  newsItemsText,
  espriTalimatiText,
  arkadaslikTalimatiText,
  hitapTalimatiText,
  lengthTalimatiText,
  timeCtx,
  focusHint,
}) {
  return `
Sen kişisel bir yaşam koordinatörü asistansın. ${timeCtx.roleDesc}

GİRDİLER:
- Kullanıcı Konumu ve Saat: ${location}, ${time}
- Bugünün Somut Odağı (kapanış cümlesi için ipucu): ${focusHint}
- Önceliklendirilmiş Seçilmiş Haber Akışı (bazı başlıklar İngilizce olabilir):
${newsItemsText}

ÖNEMLİ — Hava durumu, piyasa, kişisel görevler, vardiya ve İngilizce kartı bölümleri
SANA VERİLMİYOR ve senin çıktının arasına deterministik olarak kod tarafından eklenecek.
Sakın hava durumu, sıcaklık, dolar, altın, BIST, Bitcoin, vardiya saati veya uydurma bir
görev hakkında tek bir kelime bile yazma.

KURALLAR:
1. SAYI VE SEMBOLLER: Telegram ekranında okunacağı için tarih, yüzde ve sayıları doğal, okunaklı biçimde yazabilirsin.
2. DİL VE HABER SEÇİMİ: Nihai çıktının TAMAMI akıcı, doğal Türkçe olmalı. İngilizce başlıkları (ör. Airbus, Boeing, yapay zeka veya yazılım haberlerini) doğal Türkçeye çevirerek özetle; şirket/model/özel isimler dışında İngilizce kelime bırakma. ${lengthTalimatiText}
   KAYNAK BAĞLANTILARI VE REFERANS KURALI:
   Metindeki her bağımsız haber cümlesinin veya paragrafının sonuna, o haberin referans alındığı kaynağın URL'sini içeren numaralandırılmış bir tıklanabilir bağlantı (buton) ekle. Numaralandırma 1'den başlamalı ve sırayla artmalıdır:
   [Haberin veya bilginin metni.] [[Numara]](Kaynak_URL)
   Örnek kullanım:
   Bugün küresel piyasalarda teknoloji hisseleri rekor seviyelere ulaştı. [[1]](https://ornek-finans-haberi.com/hisse-rekor) Ayrıca, güneş enerjisi yatırımlarında yeni bir teşvik paketi duyuruldu. [[2]](https://ornek-enerji-haberi.com/tesvik)
   Haberleri kendi cümlelerinle özetle ve ilgili referans butonunu tam olarak cümlenin bitimine (noktadan hemen sonra) yerleştir.
3. PERSONA VE HİTAP:
   - Hitap kuralı: ${hitapTalimatiText}
   - Espri: ${espriTalimatiText}
   - Arkadaş canlısı yaklaşım: ${arkadaslikTalimatiText}
   - Selamlama ifadesi olarak "${timeCtx.greeting}" ile başla.
4. İÇERİK AKIŞI (Aralarında birer boş satır bırakarak TAM OLARAK 3 bölüm yaz; bölüm başlıklarını çıktıya ASLA yazma):
   - 1. Paragraf (Giriş): "${timeCtx.greeting}" ile başlayan, hitap kuralına uyan tek cümlelik kısa ve doğal bir açılış.
   - 2. Paragraf (Seçilmiş Gündem): Yukarıdaki önceliklendirilmiş haberleri (Havacılık, Yapay Zeka/Yazılım ve Türkiye/Dünya gündemi) tekrar etmeden, tek veya en fazla iki akıcı paragrafta özetle.
   - Son Paragraf (Odaklı Kapanış): Basmakalıp motivasyon sözleri yerine "${focusHint}" odağına atıf yapan ${timeCtx.closingHint}
5. ÇIKTI FORMATI: Başlık, madde işareti veya gereksiz emoji ekleme (kaynak bağlantısı için [[Numara]](URL) formatı hariç); bölümler arasında yalnızca birer boş satır bırak.

Brifing:`;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function callGroqPlainText(env, prompt, retries = 3) {
  let lastError;
  for (let attempt = 0; attempt < retries; attempt++) {
    try {
      const res = await fetch("https://api.groq.com/openai/v1/chat/completions", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${env.GROQ_API_KEY}`,
        },
        body: JSON.stringify({
          model: env.GROQ_MODEL || "openai/gpt-oss-120b",
          messages: [{ role: "user", content: prompt }],
          temperature: 0.65,
        }),
      });
      const data = await res.json();
      const text = data?.choices?.[0]?.message?.content;
      if (!text) throw new Error("Groq boş yanıt döndürdü: " + JSON.stringify(data));
      return text.trim();
    } catch (e) {
      lastError = e;
      if (attempt < retries - 1) await sleep(2000);
    }
  }
  throw lastError;
}

const BRIEFING_NOTES_SELECT = `
  SELECT n.*,
         a.appt_date, a.appt_time, a.location, a.related_person,
         s.product_name, s.quantity,
         r.remind_at, r.repeat_frequency, r.notified_at,
         t.due_date, t.context
  FROM notes n
  LEFT JOIN appointments a ON a.note_id = n.id
  LEFT JOIN shopping_items s ON s.note_id = n.id
  LEFT JOIN reminders r ON r.note_id = n.id
  LEFT JOIN tasks t ON t.note_id = n.id
  WHERE n.completed = 0
`;

// --------------------------------------------------------------------------- //
// Orkestrasyon — sabah 05:00 cron'u ve /brifing komutu
// --------------------------------------------------------------------------- //

export async function generateAndSendDailyBriefing(env) {
  const espriPct = parseInt(await getConfigValue(env.DB, "persona_espri_pct", "50"), 10);
  const arkadasPct = parseInt(await getConfigValue(env.DB, "persona_arkadas_pct", "50"), 10);
  const hitapMode = (await getConfigValue(env.DB, "persona_hitap_sekli", "onur")) || "onur";
  const lengthMode = (await getConfigValue(env.DB, "briefing_length_mode", "balanced")) || "balanced";
  const financeMode = (await getConfigValue(env.DB, "briefing_finance_mode", "significant")) || "significant";
  const learningEnabledRaw = await getConfigValue(env.DB, "briefing_learning_card_enabled", "1");
  const learningEnabled = learningEnabledRaw !== "0" && learningEnabledRaw !== "false";
  const shiftOverride = (await getConfigValue(env.DB, "shift_manual_override", "")) || "";
  const eventsMinPriority = (await getConfigValue(env.DB, "briefing_events_min_priority", "high")) || "high";

  const now = new Date(Date.now() + 3 * 60 * 60 * 1000);
  const todayParts = {
    year: now.getUTCFullYear(),
    month: now.getUTCMonth() + 1,
    day: now.getUTCDate(),
    hour: now.getUTCHours(),
    minute: now.getUTCMinutes(),
    weekdayMon0: (now.getUTCDay() + 6) % 7,
  };
  const todayDate = tryMakeDate(todayParts.year, todayParts.month, todayParts.day);
  const todayIso = toIsoDateUtc(todayDate);
  const timeStr = formatTrDateTime(todayParts);

  const [weatherRes, financeRes, newsRes, eventsRes, vaultMapRes, activeNotesRes] = await Promise.allSettled([
    fetchWeatherForBriefing(),
    fetchFinance(),
    fetchNewsItemsText(env.DB, lengthMode),
    getPrioritizedEvents({
      minPriority: eventsMinPriority,
      withinDays: 7,
      tmdbApiKey: env.TMDB_API_KEY,
      footballApiKey: env.FOOTBALL_API_KEY,
    }),
    fetchAllowlistedVaultMap(env.DB),
    env.DB.prepare(BRIEFING_NOTES_SELECT).all(),
  ]);

  const weatherData = weatherRes.status === "fulfilled" ? weatherRes.value : {};
  const financeData = financeRes.status === "fulfilled" ? financeRes.value : {};
  const newsItemsText = newsRes.status === "fulfilled" ? newsRes.value : "(Haber akışı alınamadı.)";
  const events = eventsRes.status === "fulfilled" ? eventsRes.value : [];
  const vaultMap = vaultMapRes.status === "fulfilled" ? vaultMapRes.value : new Map();
  const activeNotes = activeNotesRes.status === "fulfilled" ? activeNotesRes.value?.results || [] : [];

  const shiftInfo = resolveShiftForDate(todayDate, shiftOverride);
  const coordData = collectPersonalCoordinationData(activeNotes, vaultMap, todayDate, lengthMode);
  const focusHint = coordData.primaryFocus || shiftInfo.label;
  const timeCtx = briefingTimeContext(todayParts.hour);

  const prompt = buildBriefingPrompt({
    location: LOCATION,
    time: timeStr,
    newsItemsText,
    espriTalimatiText: espriTalimati(espriPct),
    arkadaslikTalimatiText: arkadaslikTalimati(arkadasPct),
    hitapTalimatiText: hitapTalimati(hitapMode),
    lengthTalimatiText: lengthTalimati(lengthMode),
    timeCtx,
    focusHint,
  });

  try {
    const llmRaw = await callGroqPlainText(env, prompt);
    const cleaned = stripKnownSectionHeaders(llmRaw);
    const llmParagraphs = cleaned
      .split("\n\n")
      .map((p) => p.trim())
      .filter(Boolean);

    const greetingP = llmParagraphs[0] || "";
    let closingP = llmParagraphs.length >= 2 ? llmParagraphs[llmParagraphs.length - 1] : "";
    let newsParagraphs =
      llmParagraphs.length >= 3
        ? llmParagraphs.slice(1, -1)
        : llmParagraphs.length === 2
        ? [llmParagraphs[1]]
        : [];
    if (llmParagraphs.length === 2 && llmParagraphs[1].length <= 180) {
      newsParagraphs = [];
    } else if (llmParagraphs.length === 2 && llmParagraphs[1].length > 180) {
      closingP = "";
    }

    const personalP = buildPersonalCoordinationTelegram(coordData);
    const workdayP = buildWorkdayPrepTelegram(
      todayDate,
      todayParts.hour,
      todayParts.weekdayMon0,
      shiftOverride,
      lengthMode,
      vaultMap
    );
    const weatherP = buildSmartWeatherTelegram(weatherData, shiftInfo.code);
    const financeP = buildConditionalFinanceTelegram(financeData, financeMode);
    const eventsP = buildEventsTelegram(events, lengthMode);
    const weeklyProjP = buildWeeklyProjectTelegram(todayDate, todayParts.weekdayMon0, lengthMode, vaultMap);

    let learningP = "";
    let learningMarkup = null;
    if (learningEnabled) {
      const vaultEngMd = vaultMap.get(VAULT_ENGLISH_WORDS_PATH) || "";
      const card = await selectDailyLearningCard(env.DB, todayIso, vaultEngMd);
      if (card) {
        learningP = formatLearningCardTelegram(card);
        learningMarkup = buildLearningCardInlineMarkup(card);
      }
    }

    const blocks = [];
    if (greetingP) blocks.push(greetingP);
    for (const b of [personalP, workdayP, weatherP, financeP, eventsP]) {
      if (b) blocks.push(b);
    }
    if (newsParagraphs.length) {
      blocks.push("🗞️ Seçilmiş Gündem:\n" + newsParagraphs.join("\n\n"));
    }
    if (learningP) blocks.push(learningP);
    if (weeklyProjP) blocks.push(weeklyProjP);
    if (closingP) blocks.push(closingP);

    const finalText = blocks.join("\n\n");
    const msgOptions = learningMarkup ? { replyMarkup: learningMarkup } : {};
    await sendTelegramMessage(env, env.TELEGRAM_CHAT_ID, finalText, msgOptions);
  } catch (e) {
    console.error("Brifing üretilemedi:", e);
    await sendTelegramMessage(env, env.TELEGRAM_CHAT_ID, `⚠️ Günlük brifing oluşturulamadı: ${e}`);
  }
}

// --------------------------------------------------------------------------- //
// POST /config — Masaüstü WinVoice ayarlarının buluta senkronizasyonu
// --------------------------------------------------------------------------- //

export async function handleConfigPost(request, env) {
  const auth = request.headers.get("Authorization") || "";
  if (auth !== `Bearer ${env.SYNC_SECRET}`) {
    return new Response("unauthorized", { status: 401 });
  }

  const body = await request.json();
  const allowedKeys = [
    "persona_espri_pct",
    "persona_arkadas_pct",
    "persona_hitap_sekli",
    "briefing_length_mode",
    "briefing_finance_mode",
    "briefing_learning_card_enabled",
    "shift_manual_override",
    "briefing_events_min_priority",
  ];

  for (const key of allowedKeys) {
    if (body[key] !== undefined) {
      await setConfigValue(env.DB, key, String(body[key]));
    }
  }

  return new Response(JSON.stringify({ ok: true }), { headers: { "Content-Type": "application/json" } });
}
