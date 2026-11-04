// src/briefing.js
//
// Günlük Brifing'in bulut tarafı — telegram_briefing.py (+ briefing_data.py,
// briefing_text.py, persona_settings.py, tr_dates.py, tr_numbers.py,
// personal_context.py'nin build_reminder_block'u) buradaki JS karşılığına
// birebir port edildi. Tek fark: yerel Ollama (gemma3:4b) yerine Groq
// kullanılıyor (bkz. index.js'teki not sınıflandırmasıyla AYNI Groq
// çağrısı) — bu yüzden PC kapalıyken de her gün saat 05:00'te (cron
// "0 2 * * *", UTC+3) brifing Telegram'a gönderilebiliyor.
//
// "Kişisel hatırlatmalara gelirsek..." paragrafı (doğum günü/ödeme/randevu)
// "Doğum Günleri ve Randevular.md" notuna dayanıyor. HAKKIMDA artık SADECE
// Cloudflare D1'de (vault_notes tablosu, bkz. index.js handleVaultImport/
// migrate_hakkimda_to_cloud.py) yönetildiği için bu, aynı D1 binding'inden
// doğrudan okunur — WinVoice'tan ayrıca bir şey itilmesine gerek yok.

import { getConfigValue, httpGetJson, httpGetText, sendTelegramMessage, setConfigValue, stripHtmlTags } from "./common.js";
import { getPrioritizedEvents } from "./events.js";

// --------------------------------------------------------------------------- //
// briefing_data.py portu — hava/piyasa/haber ham veri kaynakları
// --------------------------------------------------------------------------- //

const LATITUDE = 41.1431;
const LONGITUDE = 28.4606;
const LOCATION = "İstanbul / Çatalca";

const NEWS_AI_RSS_URL = "https://techcrunch.com/category/artificial-intelligence/feed/";
const NEWS_TURKEY_RSS_URL = "https://www.ntv.com.tr/gundem.rss";
const NEWS_WORLD_RSS_URL = "https://www.ntv.com.tr/dunya.rss";

const TCMB_RATES_URL = "https://www.tcmb.gov.tr/kurlar/today.xml";
const BIST100_URL = "https://query1.finance.yahoo.com/v8/finance/chart/XU100.IS";
const GOLD_FUTURES_URL = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F";
const BTC_PRICE_URL = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=try,usd";
const GRAMS_PER_OUNCE = 31.1034768;

const NEWS_SUMMARY_MAX_LEN = 200;

const CLICKBAIT_PATTERNS = [
  "son dakika", "açıklandı", "sorgulama", "canlı sonuç", "canlı sonuçlar",
  "çekiliş sonuçları", "kazandıran numaralar", "sorgula",
];

const WEATHER_CODES = {
  0: "Açık", 1: "Az bulutlu", 2: "Parçalı Bulutlu", 3: "Kapalı",
  45: "Sisli", 48: "Kırağı sisi",
  51: "Hafif çisenti", 53: "Çisenti", 55: "Yoğun çisenti",
  61: "Hafif Yağmur", 63: "Yağmur", 65: "Şiddetli yağmur",
  71: "Hafif kar", 73: "Kar", 75: "Yoğun kar",
  80: "Sağanak", 81: "Kuvvetli sağanak", 82: "Şiddetli sağanak",
  95: "Gök gürültülü fırtına", 96: "Dolu ile fırtına", 99: "Şiddetli dolu fırtınası",
};

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

async function fetchItemsFromFeed(url, itemTag, summaryTag, limit) {
  try {
    const xml = await httpGetText(url);
    const results = [];
    for (const block of extractBlocks(xml, itemTag)) {
      const title = stripHtmlTags(extractTag(block, "title"));
      if (!title || isClickbait(title)) continue;
      const summary = truncate(stripHtmlTags(extractTag(block, summaryTag)));
      results.push({ title, summary });
      if (results.length >= limit) break;
    }
    return results;
  } catch (e) {
    console.error(`RSS alınamadı (${url}):`, e);
    return [];
  }
}

function formatNewsBlock(categoryLabel, items) {
  return items.map((item) => {
    let line = `[${categoryLabel}] ${item.title}`;
    if (item.summary) line += ` — ${item.summary}`;
    return line;
  });
}

async function fetchNewsItemsText() {
  const turkeyItems = await fetchItemsFromFeed(NEWS_TURKEY_RSS_URL, "entry", "summary", 6);
  const worldItems = await fetchItemsFromFeed(NEWS_WORLD_RSS_URL, "entry", "summary", 5);
  const aiItems = await fetchItemsFromFeed(NEWS_AI_RSS_URL, "item", "description", 3);

  const seenTitles = new Set();
  const dedupe = (items) =>
    items.filter((item) => {
      const key = item.title.toLowerCase().trim();
      if (seenTitles.has(key)) return false;
      seenTitles.add(key);
      return true;
    });

  const lines = [
    ...formatNewsBlock("TÜRKİYE", dedupe(turkeyItems)),
    ...formatNewsBlock("DÜNYA", dedupe(worldItems)),
    ...formatNewsBlock("TEKNOLOJİ", dedupe(aiItems)),
  ];
  return lines.length ? lines.join("\n") : "(Haber akışı alınamadı.)";
}

async function fetchWeatherForBriefing() {
  const url =
    "https://api.open-meteo.com/v1/forecast" +
    `?latitude=${LATITUDE}&longitude=${LONGITUDE}` +
    "&current=temperature_2m,relative_humidity_2m,surface_pressure,wind_speed_10m,weather_code" +
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
  return {
    sicaklik_c: current.temperature_2m,
    aciklama: WEATHER_CODES[current.weather_code] ?? "Bilinmiyor",
    nem_yuzde: current.relative_humidity_2m,
    ruzgar_kmh: current.wind_speed_10m,
    bugun_max_c: today.tmax,
    bugun_min_c: today.tmin,
  };
}

async function fetchFinance() {
  const result = {};
  let usdTry = null;

  try {
    const xml = await httpGetText(TCMB_RATES_URL);
    const usdBlockMatch = xml.match(/<Currency[^>]*Kod="USD"[^>]*>([\s\S]*?)<\/Currency>/i);
    if (usdBlockMatch) {
      const forexSelling = extractTag(usdBlockMatch[1], "ForexSelling");
      usdTry = parseFloat(forexSelling);
      if (Number.isFinite(usdTry)) result.usd_try_satis = Math.round(usdTry * 10000) / 10000;
    }
  } catch (e) {
    console.error("Dolar kuru alınamadı:", e);
  }

  try {
    const data = await httpGetJson(BIST100_URL);
    const meta = data.chart.result[0].meta;
    result.bist100 = Math.round(meta.regularMarketPrice * 100) / 100;
    result.bist100_gunluk_yuzde_degisim = Math.round((meta.regularMarketChangePercent || 0) * 100) / 100;
  } catch (e) {
    console.error("BIST100 verisi alınamadı:", e);
  }

  try {
    const data = await httpGetJson(GOLD_FUTURES_URL);
    const goldUsdOz = data.chart.result[0].meta.regularMarketPrice;
    if (usdTry) result.gram_altin_try = Math.round(((goldUsdOz * usdTry) / GRAMS_PER_OUNCE) * 100) / 100;
  } catch (e) {
    console.error("Altın verisi alınamadı:", e);
  }

  try {
    const data = await httpGetJson(BTC_PRICE_URL);
    result.btc_try = data.bitcoin.try;
    result.btc_usd = data.bitcoin.usd;
  } catch (e) {
    console.error("BTC verisi alınamadı:", e);
  }

  return result;
}

// --------------------------------------------------------------------------- //
// tr_numbers.py portu
// --------------------------------------------------------------------------- //

const ONES = ["", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz"];
const TENS = ["", "on", "yirmi", "otuz", "kırk", "elli", "altmış", "yetmiş", "seksen", "doksan"];
const SCALES = ["", "bin", "milyon", "milyar", "trilyon"];

function threeDigitsToWords(n) {
  const hundreds = Math.floor(n / 100);
  const remainder = n % 100;
  const tens = Math.floor(remainder / 10);
  const ones = remainder % 10;
  const parts = [];
  if (hundreds) parts.push(hundreds === 1 ? "yüz" : `${ONES[hundreds]} yüz`);
  if (tens) parts.push(TENS[tens]);
  if (ones) parts.push(ONES[ones]);
  return parts.join(" ");
}

function numberToWords(value) {
  let n = Math.round(value);
  if (n === 0) return "sıfır";
  const negative = n < 0;
  n = Math.abs(n);
  const groups = [];
  while (n > 0) {
    groups.push(n % 1000);
    n = Math.floor(n / 1000);
  }
  const parts = [];
  for (let i = groups.length - 1; i >= 0; i--) {
    const group = groups[i];
    if (group === 0) continue;
    if (i === 1 && group === 1) parts.push(SCALES[i]);
    else if (i > 0) parts.push(`${threeDigitsToWords(group)} ${SCALES[i]}`);
    else parts.push(threeDigitsToWords(group));
  }
  const result = parts.join(" ");
  return negative ? `eksi ${result}` : result;
}

function currencyToWords(amount, unit = "lira", subunit = "kuruş") {
  const negative = amount < 0;
  amount = Math.abs(amount);
  let lira = Math.trunc(amount);
  let kurus = Math.round((amount - lira) * 100);
  if (kurus >= 100) {
    lira += 1;
    kurus -= 100;
  }
  let text = `${numberToWords(lira)} ${unit}`;
  if (kurus > 0) text += ` ${numberToWords(kurus)} ${subunit}`;
  return negative ? `eksi ${text}` : text;
}

function percentToWords(value) {
  const negative = value < 0;
  value = Math.abs(value);
  let integerPart = Math.trunc(value);
  let decimalPart = Math.round((value - integerPart) * 100);
  if (decimalPart >= 100) {
    integerPart += 1;
    decimalPart -= 100;
  }
  let text = `yüzde ${numberToWords(integerPart)}`;
  if (decimalPart > 0) {
    const spokenDecimal = decimalPart % 10 === 0 ? Math.floor(decimalPart / 10) : decimalPart;
    text += ` virgül ${numberToWords(spokenDecimal)}`;
  }
  return negative ? `eksi ${text}` : text;
}

const plainNumberToWords = numberToWords;

// --------------------------------------------------------------------------- //
// tr_dates.py + persona_settings.py portu
// --------------------------------------------------------------------------- //

const TR_MONTHS = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"];
const TR_DAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"];

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

// --------------------------------------------------------------------------- //
// personal_context.py (SADECE build_reminder_block kısmı) portu
// --------------------------------------------------------------------------- //

const ROW_RE = /^\|(.+)\|\s*$/;
const DATE_FULL_RE = /^(\d{1,2})\.(\d{1,2})\.(\d{4})$/;
const DATE_ANNUAL_RE = /^(\d{1,2})\.(\d{1,2})$/;
const DAY_ONLY_RE = /^(\d{1,2})$/;

function parseTableRows(markdownText) {
  const rows = [];
  for (const rawLine of markdownText.split("\n")) {
    const line = rawLine.trim();
    const match = ROW_RE.exec(line);
    if (!match) continue;
    const cells = match[1].split("|").map((c) => c.trim());
    if (cells.length < 3) continue;
    const first = cells[0];
    const isSeparator = first.length > 0 && [...first].every((ch) => ch === "-" || ch === ":");
    if (first === "Tür" || first === "" || isSeparator) continue;
    if (cells.length > 1 && cells[1].includes("Örnek")) continue;
    rows.push(cells);
  }
  return rows;
}

function loadEntries(markdownText) {
  if (!markdownText) return [];
  const entries = [];
  for (const cellsRaw of parseTableRows(markdownText)) {
    const cells = [...cellsRaw, "", "", "", "", ""].slice(0, 5);
    const [tur, kim, tarih, tekrar, not_] = cells.map((c) => c.trim());
    if (!tarih) continue;
    entries.push({ tur, kim, tarihRaw: tarih, tekrar: tekrar.toLowerCase(), not: not_ });
  }
  return entries;
}

function tryMakeDate(y, m, d) {
  const dt = new Date(Date.UTC(y, m - 1, d));
  if (dt.getUTCFullYear() !== y || dt.getUTCMonth() !== m - 1 || dt.getUTCDate() !== d) return null;
  return dt;
}

function daysInMonth(y, m) {
  return new Date(Date.UTC(y, m, 0)).getUTCDate();
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

function resolveEntryDate(entry, todayDate) {
  const { tarihRaw, tekrar } = entry;

  if (tekrar === "aylık") {
    const m = DAY_ONLY_RE.exec(tarihRaw);
    return m ? nextMonthly(parseInt(m[1], 10), todayDate) : null;
  }
  if (tekrar === "yıllık") {
    const m = DATE_ANNUAL_RE.exec(tarihRaw) || DATE_FULL_RE.exec(tarihRaw);
    return m ? nextAnnual(parseInt(m[1], 10), parseInt(m[2], 10), todayDate) : null;
  }

  let m = DATE_FULL_RE.exec(tarihRaw);
  if (m) {
    const candidate = tryMakeDate(parseInt(m[3], 10), parseInt(m[2], 10), parseInt(m[1], 10));
    return candidate && candidate.getTime() >= todayDate.getTime() ? candidate : null;
  }
  m = DATE_ANNUAL_RE.exec(tarihRaw);
  if (m) return nextAnnual(parseInt(m[1], 10), parseInt(m[2], 10), todayDate);

  return null;
}

function getUpcoming(markdownText, withinDays, todayDate) {
  const result = [];
  for (const entry of loadEntries(markdownText)) {
    const target = resolveEntryDate(entry, todayDate);
    if (!target) continue;
    const kalanGun = Math.round((target.getTime() - todayDate.getTime()) / 86400000);
    if (kalanGun >= 0 && kalanGun <= withinDays) result.push({ ...entry, tarih: target, kalanGun });
  }
  result.sort((a, b) => a.kalanGun - b.kalanGun);
  return result;
}

function tarihIfadesi(kalanGun, tarih) {
  if (kalanGun === 0) return "bugün";
  if (kalanGun === 1) return "yarın";
  return `${kalanGun} gün sonra (${tarih.getUTCDate()} ${TR_MONTHS[tarih.getUTCMonth()]})`;
}

function cumle(entry) {
  const ifade = tarihIfadesi(entry.kalanGun, entry.tarih);
  const tur = entry.tur.toLowerCase();
  const kim = entry.kim || "Bir kayıt";
  const notVal = entry.not;

  if (tur.includes("doğum")) return `${kim}'in doğum günü ${ifade}.`;
  if (tur.includes("ödeme") || tur.includes("fatura") || tur.includes("kredi")) {
    return `${kim} son ödeme tarihi ${ifade}${notVal ? ` (${notVal})` : ""}.`;
  }
  if (tur.includes("randevu")) {
    return `${kim} randevunuz ${ifade}${notVal ? ` (${notVal})` : ""}.`;
  }
  return `${kim}: ${ifade}${notVal ? ` — ${notVal}` : ""}.`;
}

function buildPersonalRemindersParagraph(remindersMd, todayDate, withinDays = 14) {
  const olaylar = getUpcoming(remindersMd, withinDays, todayDate);
  if (!olaylar.length) return "";
  return "Kişisel hatırlatmalara gelirsek; " + olaylar.map(cumle).join(" ");
}

// --------------------------------------------------------------------------- //
// briefing_text.py portu
// --------------------------------------------------------------------------- //

const KNOWN_SECTION_HEADER_RE =
  /^\s*[*_#]{0,3}\s*(giriş|hava\s*&\s*piyasa|hava\s+ve\s+piyasa|türkiye\s+gündemi|dünya\s+turu|teknoloji|kapanış)\s*[:：]\s*[*_#]{0,3}\s*/i;

function weatherPhrases(w) {
  w = w || {};
  const phrases = {};
  if (w.sicaklik_c != null) phrases.sicaklik = `${plainNumberToWords(w.sicaklik_c)} derece`;
  if (w.aciklama) phrases.havaDurumuAciklamasi = w.aciklama;
  if (w.nem_yuzde != null) phrases.nemOrani = percentToWords(w.nem_yuzde);
  if (w.ruzgar_kmh != null) phrases.ruzgarHizi = `saatte ${plainNumberToWords(w.ruzgar_kmh)} kilometre`;
  if (w.bugun_max_c != null) phrases.bugunEnYuksekSicaklik = `${plainNumberToWords(w.bugun_max_c)} derece`;
  if (w.bugun_min_c != null) phrases.bugunEnDusukSicaklik = `${plainNumberToWords(w.bugun_min_c)} derece`;
  return phrases;
}

function financePhrases(f) {
  f = f || {};
  const phrases = {};
  if (f.usd_try_satis != null) phrases.dolarTlSatisKuru = currencyToWords(f.usd_try_satis);
  if (f.bist100 != null) phrases.bist100Endeksi = `${plainNumberToWords(f.bist100)} puan`;
  if (f.bist100_gunluk_yuzde_degisim != null) phrases.bist100GunlukDegisim = percentToWords(f.bist100_gunluk_yuzde_degisim);
  if (f.gram_altin_try != null) phrases.gramAltinFiyati = currencyToWords(f.gram_altin_try);
  if (f.btc_try != null) phrases.bitcoinTlKarsiligi = `${plainNumberToWords(f.btc_try)} lira`;
  if (f.btc_usd != null) phrases.bitcoinDolarKarsiligi = `${plainNumberToWords(f.btc_usd)} dolar`;
  return phrases;
}

// briefing_text.py'deki build_outfit_sentence'ın birebir karşılığı: erkek
// kullanıcı için hava verisine göre "bugün ne giysem" önerisi (kadın kıyafeti yok).
function topClothing(low, high) {
  if (low < 5) return "üstüne kalın bir mont ya da kaban, altına kazak";
  if (high < 15) return "üstüne mont ya da kalın bir ceket, altına sweatshirt";
  if (high < 22) return "üstüne ince bir ceket ya da uzun kollu gömlek";
  return "tişört ya da hafif bir gömlek";
}

function bottomClothing(high) {
  if (high >= 27) return "kısa pantolon ya da ince chino";
  return "uzun pantolon, chino ya da kot";
}

function buildOutfitSentence(weatherData) {
  const w = weatherData || {};
  const high = w.bugun_max_c ?? w.sicaklik_c;
  const low = w.bugun_min_c ?? w.sicaklik_c;
  if (high == null || low == null) return "";

  const description = (w.aciklama || "").toLowerCase();
  const wind = w.ruzgar_kmh ?? 0;

  const items = [topClothing(low, high), bottomClothing(high)];
  if (high - low >= 10) items.push("gün içinde hava çok değişecek, katmanlı giyin");
  if (["yağmur", "çisenti", "sağanak", "fırtına", "dolu"].some((word) => description.includes(word))) {
    items.push("yanına yağmurluk ya da su geçirmez bir mont al");
  } else if (description.includes("kar")) {
    items.push("su geçirmez bot ve eldiven tercih et");
  }
  if (wind >= 30) items.push("rüzgar sert, rüzgarlık da işine yarar");
  if (high >= 22 && (description.includes("açık") || description.includes("az bulutlu"))) {
    items.push("güneş gözlüğü de al");
  }
  return `Bugün ne giysen; ${items.join("; ")}.`;
}

function buildWeatherFinanceParagraph(weatherData, financeData) {
  const w = weatherPhrases(weatherData);
  const f = financePhrases(financeData);
  const sentences = [];

  if (w.havaDurumuAciklamasi && w.sicaklik) {
    let sentence = `Hava durumuna gelirsek; İstanbul Çatalca'da hava ${w.havaDurumuAciklamasi.toLowerCase()}, sıcaklık ${w.sicaklik}`;
    if (w.nemOrani) sentence += `, nem oranı ${w.nemOrani}`;
    if (w.ruzgarHizi) sentence += `, rüzgar hızı ${w.ruzgarHizi}`;
    sentences.push(sentence + ".");
  }

  const outfitSentence = buildOutfitSentence(weatherData);
  if (outfitSentence) sentences.push(outfitSentence);

  const financeBits = [];
  if (f.dolarTlSatisKuru) financeBits.push(`dolar ${f.dolarTlSatisKuru} seviyesinde`);
  if (f.bist100Endeksi) {
    let bistBit = `BIST 100 endeksi ${f.bist100Endeksi}`;
    if (f.bist100GunlukDegisim) bistBit += ` ile günü ${f.bist100GunlukDegisim} değişimle tamamlıyor`;
    financeBits.push(bistBit);
  }
  if (f.gramAltinFiyati) financeBits.push(`gram altın ${f.gramAltinFiyati}`);
  if (f.bitcoinTlKarsiligi) {
    let btcBit = `Bitcoin ${f.bitcoinTlKarsiligi}`;
    if (f.bitcoinDolarKarsiligi) btcBit += ` (${f.bitcoinDolarKarsiligi})`;
    financeBits.push(btcBit);
  }
  if (financeBits.length) sentences.push("Piyasalara bakacak olursak; " + financeBits.join(", ") + ".");

  return sentences.join(" ");
}

function buildEventsParagraph(events) {
  if (!events || !events.length) return "";
  const bits = events.map((e) => e.title);
  return "Öne çıkan etkinliklere gelirsek; " + bits.join(", ") + ".";
}

function stripKnownSectionHeaders(text) {
  return text
    .split("\n")
    .map((line) => line.replace(KNOWN_SECTION_HEADER_RE, ""))
    .join("\n");
}

function assembleFinalBriefing(llmText, weatherData, financeData, remindersMd, todayDate, events) {
  const text = stripKnownSectionHeaders(llmText);
  const paragraphs = text.split("\n\n").map((p) => p.trim()).filter(Boolean);

  const weatherFinanceParagraph = buildWeatherFinanceParagraph(weatherData, financeData);
  const personalRemindersParagraph = remindersMd ? buildPersonalRemindersParagraph(remindersMd, todayDate) : "";
  const eventsParagraph = buildEventsParagraph(events);

  let insertAt = 1;
  if (paragraphs.length && weatherFinanceParagraph) {
    paragraphs.splice(insertAt, 0, weatherFinanceParagraph);
    insertAt += 1;
  } else if (weatherFinanceParagraph) {
    paragraphs.push(weatherFinanceParagraph);
  }

  if (paragraphs.length && personalRemindersParagraph) {
    paragraphs.splice(insertAt, 0, personalRemindersParagraph);
    insertAt += 1;
  } else if (personalRemindersParagraph) {
    paragraphs.push(personalRemindersParagraph);
  }

  if (paragraphs.length && eventsParagraph) {
    paragraphs.splice(insertAt, 0, eventsParagraph);
  } else if (eventsParagraph) {
    paragraphs.push(eventsParagraph);
  }

  return paragraphs.join("\n\n");
}

// --------------------------------------------------------------------------- //
// prompts.DAILY_BRIEFING_PROMPT portu
// --------------------------------------------------------------------------- //

function buildBriefingPrompt({ location, time, newsItemsText, espriTalimatiText, arkadaslikTalimatiText }) {
  return `
Sen kişisel bir sesli asistansın. Kullanıcıya gün sonu sesli brifingi hazırlayacaksın.

GİRDİLER:
- Kullanıcı Konumu ve Saat: ${location}, ${time}
- Ham Haber Akışı (bazı başlıklar İngilizce olabilir): ${newsItemsText}

ÖNEMLİ — Hava durumu ve piyasa (dolar, altın, BIST, Bitcoin) bilgisi SANA
VERİLMİYOR ve bu yüzden onlardan HİÇ bahsetmeyeceksin. "Hava & Piyasa" bölümü
tamamen senin çıktının dışında, ayrıca ve zaten doğru şekilde seslendirilmiş
olarak otomatik eklenecek. Sakın hava durumu, sıcaklık, dolar, altın, BIST
veya Bitcoin ile ilgili tek bir kelime bile yazma — bu konuda elindeki tek
bilgi bu paragraftır, başka hiçbir veri yok.

KURALLAR:
1. SESLENDİRME (TTS) UYUMLULUĞU: Metin sesli okunacağı için ham haber akışından
   aktardığın bilgilerdeki RAKAM, FİYAT VE YÜZDELERİ YAZIYLA YAZ (haberlerde geçen
   tarih/sayı/para birimi gibi değerler dahil). Çıktıda hiçbir rakam (0-9) veya
   sembol (%, ₺, $, TL) ham haliyle YER ALMAMALI.
   - Örnek: "49.61 TL" yerine "kırk dokuz lira altmış bir kuruş"
   - Örnek: "%1.5" yerine "yüzde bir virgül beş"
   - Örnek: "6588" yerine "altı bin beş yüz seksen sekiz"
2. TIK TUZAĞI (CLICKBAIT) FİLTRESİ: Ham haber akışı zaten önceden filtrelenmiştir, ama
   yine de belirsizlik içeren veya gerçek bir bilgi taşımayan başlıklar varsa bunları
   da ele. Yalnızca net bilgi içeren haberleri seç; her bölüm için aşağıda belirtilen
   sayıya uy.
3. DİL: Nihai çıktının TAMAMI Türkçe olmalı. İngilizce bir haber başlığı/özeti
   görürsen onu kendi cümlelerinle Türkçeye çevirerek anlat; İngilizce tek kelime
   bile bırakma (özel isimler/şirket adları hariç).
4. PERSONA & TON: Dashboard > Ayarlar sayfasındaki yüzde kaydırıcılarından gelen şu
   kişilik talimatlarına uy:
   - Espri: ${espriTalimatiText}
   - Arkadaş canlısı yaklaşım: ${arkadaslikTalimatiText}
   Kullanıcıya doğrudan "Patron" diye hitap et (örn. "Patron, piyasalarda bugün...").
   "Patron" kelimesi metin boyunca en az iki kez geçmeli.
   - ZAMANA UYGUN SELAMLAMA: Girdideki saat değerinden saati belirle ve selamlamada
     SADECE o saat aralığına uyan ifadeyi kullan — asla sabit olarak "Günaydın" yazma:
       * 05:00–11:59 arası: "Günaydın"
       * 12:00–17:59 arası: "Tünaydın"
       * 18:00–21:59 arası: "İyi akşamlar"
       * 22:00–04:59 arası: "İyi geceler"
5. İÇERİK AKIŞI: Aşağıdaki sırayla ve içerikle TEK, akıcı bir metin kur. Bu başlıkları
   (Giriş:, Hava & Piyasa: vb.) çıktıya YAZMA — bunlar sadece senin iç kurgun için bir
   sıralama rehberidir:
   - Giriş: Yukarıdaki ZAMANA UYGUN SELAMLAMA kuralına göre seçtiğin selamlama
     ifadesiyle başlayan, "Patron" hitabı içeren hafif espritüel bir selamlama.
     SADECE selamla; hava durumu veya piyasadan hiç bahsetme (bkz. yukarıdaki ÖNEMLİ not).
   - Türkiye Gündemi: Ham haber akışındaki "TÜRKİYE" etiketli haberlerden en önemli
     2-3 gelişmenin 1'er cümlelik özeti.
   - Dünya Turu: Ham haber akışındaki "DÜNYA" etiketli haberlerden çarpıcı 2 gelişme.
   - Teknoloji: Ham haber akışındaki "TEKNOLOJİ" etiketli haberlerden yapay zeka veya
     teknoloji dünyasından 1-2 gelişme.
   - Kapanış: Zamana uygun, espritüel bir kapanış cümlesi. Saate göre:
       * Öğleden sonra (12:00–17:59): "Günün ikinci yarısı bizi bekliyor, kolay gelsin
         Patron." benzeri enerji verici bir ifade kullan.
       * Gece (22:00–04:59): "Vücudunu artık dinlendirmelisin, geç oldu Patron."
         benzeri dinlenmeyi hatırlatan bir ifade kullan.
       * Diğer saatlerde (sabah/akşam) duruma uygun, benzer ruhta espritüel bir
         kapanış cümlesi üret.
6. ÇIKTI FORMATI: Sadece seslendirilecek düz metni yaz. Başlık, madde işareti,
   markdown, emoji veya açıklama ekleme. Bölümler arasında birer boş satır
   bırakarak doğal duraklama noktaları oluştur.

Brifing:`;
}

// --------------------------------------------------------------------------- //
// Groq çağrısı — index.js'teki classifyMessage ile AYNI model/endpoint,
// burada düz metin (JSON değil) döndüğü için küçük bir yeniden deneme eklendi
// (telegram_briefing.generate_daily_briefing'in Ollama bekleme mantığının
// Groq için sadeleştirilmiş karşılığı).
// --------------------------------------------------------------------------- //

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
          temperature: 0.7,
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

// --------------------------------------------------------------------------- //
// Orkestrasyon — telegram_briefing.py main()/build_briefing_text() portu.
// --------------------------------------------------------------------------- //

export async function generateAndSendDailyBriefing(env) {
  let weatherData = {};
  try {
    weatherData = await fetchWeatherForBriefing();
  } catch (e) {
    console.error("Hava durumu alınamadı, brifing havasız devam edecek:", e);
  }

  let financeData = {};
  try {
    financeData = await fetchFinance();
  } catch (e) {
    console.error("Piyasa verisi alınamadı, brifing piyasasız devam edecek:", e);
  }

  let newsItemsText = "(Haber akışı alınamadı.)";
  try {
    newsItemsText = await fetchNewsItemsText();
  } catch (e) {
    console.error("Haber akışı alınamadı:", e);
  }

  const remindersRow = await env.DB.prepare(
    "SELECT content FROM vault_notes WHERE path = ?"
  )
    .bind("50_Rutinler/Doğum Günleri ve Randevular.md")
    .first();
  const remindersMd = remindersRow?.content || "";
  const espriPct = parseInt(await getConfigValue(env.DB, "persona_espri_pct", "50"), 10);
  const arkadasPct = parseInt(await getConfigValue(env.DB, "persona_arkadas_pct", "50"), 10);
  const eventsMinPriority = await getConfigValue(env.DB, "briefing_events_min_priority", "high");

  let events = [];
  try {
    events = await getPrioritizedEvents({
      minPriority: eventsMinPriority,
      tmdbApiKey: env.TMDB_API_KEY,
      footballApiKey: env.FOOTBALL_API_KEY,
    });
  } catch (e) {
    console.error("Önemli etkinlikler alınamadı, brifing bu bölümsüz devam edecek:", e);
  }

  const now = new Date(Date.now() + 3 * 60 * 60 * 1000); // Istanbul duvar saati (UTC+3)
  const todayParts = {
    year: now.getUTCFullYear(),
    month: now.getUTCMonth() + 1,
    day: now.getUTCDate(),
    hour: now.getUTCHours(),
    minute: now.getUTCMinutes(),
    weekdayMon0: (now.getUTCDay() + 6) % 7,
  };
  const todayDate = tryMakeDate(todayParts.year, todayParts.month, todayParts.day);
  const timeStr = formatTrDateTime(todayParts);

  const prompt = buildBriefingPrompt({
    location: LOCATION,
    time: timeStr,
    newsItemsText,
    espriTalimatiText: espriTalimati(espriPct),
    arkadaslikTalimatiText: arkadaslikTalimati(arkadasPct),
  });

  try {
    const llmText = await callGroqPlainText(env, prompt);
    const finalText = assembleFinalBriefing(llmText, weatherData, financeData, remindersMd, todayDate, events);
    await sendTelegramMessage(env, env.TELEGRAM_CHAT_ID, finalText);
  } catch (e) {
    console.error("Brifing üretilemedi:", e);
    await sendTelegramMessage(env, env.TELEGRAM_CHAT_ID, `⚠️ Günlük brifing oluşturulamadı: ${e}`);
  }
}

// --------------------------------------------------------------------------- //
// POST /config — WinVoice'un (cloud_sync.push_config()) persona ayarlarını
// PC açıldığında buraya itmesi için.
// --------------------------------------------------------------------------- //

export async function handleConfigPost(request, env) {
  const auth = request.headers.get("Authorization") || "";
  if (auth !== `Bearer ${env.SYNC_SECRET}`) {
    return new Response("unauthorized", { status: 401 });
  }

  const body = await request.json();
  if (body.persona_espri_pct !== undefined) {
    await setConfigValue(env.DB, "persona_espri_pct", String(body.persona_espri_pct));
  }
  if (body.persona_arkadas_pct !== undefined) {
    await setConfigValue(env.DB, "persona_arkadas_pct", String(body.persona_arkadas_pct));
  }
  if (body.briefing_events_min_priority !== undefined) {
    await setConfigValue(env.DB, "briefing_events_min_priority", String(body.briefing_events_min_priority));
  }

  return new Response(JSON.stringify({ ok: true }), { headers: { "Content-Type": "application/json" } });
}
