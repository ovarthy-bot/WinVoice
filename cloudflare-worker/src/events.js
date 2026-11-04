// src/events.js
//
// Günlük Brifing'in "Önemli Etkinlikler" bölümü için ham veri kaynakları —
// events_data.py'nin birebir JS portu (aynı kaynak URL'leri, aynı öncelik
// kuralları, aynı astronomik formül) ki yerel sesli brifing ve buluttaki
// Telegram metin brifingi tutarlı kalsın. Tüm skorlama deterministiktir
// (LLM'e hiç gitmez) — bkz. buildWeatherFinanceParagraph ile aynı mantık.

import { httpGetJson, httpGetText } from "./common.js";

const TMDB_DISCOVER_URL = "https://api.themoviedb.org/3/discover/movie";
const FOOTBALL_API_BASE = "https://v3.football.api-sports.io";
const SPACE_LAUNCHES_URL = "https://ll.thespacedevs.com/2.2.0/launch/upcoming/?limit=20";
const TUYAP_FAIR_URL = "https://tuyap.com.tr/fuarlar/uluslararasi-istanbul-kitap-fuari";

const TURKISH_BIG_TEAMS = { 611: "Galatasaray", 610: "Fenerbahçe", 549: "Beşiktaş", 607: "Trabzonspor" };
const STRONG_FOREIGN_TEAMS = {
  541: "Real Madrid", 529: "Barcelona", 157: "Bayern Münih", 50: "Manchester City",
  40: "Liverpool", 85: "Paris Saint-Germain", 496: "Juventus", 505: "Inter",
  33: "Manchester United", 49: "Chelsea", 42: "Arsenal", 165: "Borussia Dortmund", 489: "AC Milan",
};
const EUROPEAN_CUP_LEAGUE_IDS = new Set([2, 3, 848]);

const METEOR_SHOWERS = [
  ["Quadrantids", 1, 4], ["Lyrids", 4, 22], ["Eta Aquariids", 5, 6],
  ["Perseids", 8, 12], ["Orionids", 10, 21], ["Leonids", 11, 17], ["Geminids", 12, 14],
];

// NASA'nın yıllarca önce yayınladığı tutulma tarihleri — statik tablo
// (events_data.py KNOWN_ECLIPSES ile aynı), zamanı gelince genişletilmeli.
const KNOWN_ECLIPSES = [
  ["2026-02-17", "Güneş tutulması (halkasal)"],
  ["2026-08-12", "Güneş tutulması (tam)"],
  ["2026-03-03", "Ay tutulması (tam)"],
  ["2026-08-28", "Ay tutulması (parçalı)"],
  ["2027-02-06", "Güneş tutulması (halkasal)"],
  ["2027-08-02", "Güneş tutulması (tam)"],
];

function toIsoDate(d) {
  return d.toISOString().slice(0, 10);
}

function addDays(d, days) {
  const copy = new Date(d.getTime());
  copy.setUTCDate(copy.getUTCDate() + days);
  return copy;
}

async function httpGetJsonWithHeaders(url, headers) {
  const res = await fetch(url, { headers });
  if (!res.ok) throw new Error(`HTTP ${res.status} — ${url}`);
  return res.json();
}

// --------------------------------------------------------------------------- //
// Bilim kurgu filmleri (TMDb)
// --------------------------------------------------------------------------- //

async function fetchScifiMovies(apiKey, today, withinDays) {
  if (!apiKey) return [];
  const until = addDays(today, withinDays);
  const url =
    `${TMDB_DISCOVER_URL}?api_key=${apiKey}&with_genres=878&sort_by=popularity.desc` +
    `&primary_release_date.gte=${toIsoDate(today)}&primary_release_date.lte=${toIsoDate(until)}&language=tr-TR`;

  let data;
  try {
    data = await httpGetJson(url);
  } catch (e) {
    return [];
  }

  const events = [];
  for (const movie of data.results || []) {
    const release = movie.release_date;
    const popularity = movie.popularity || 0;
    const title = movie.title;
    if (!release || !title) continue;
    let priority;
    if (popularity >= 40) priority = "high";
    else if (popularity >= 15) priority = "medium";
    else continue;
    events.push({ title: `"${title}" filmi vizyona giriyor`, date: release, priority });
  }
  return events;
}

// --------------------------------------------------------------------------- //
// Futbol (derbi / Türk takımı Avrupa kupası / güçlü yabancı takım ŞL)
// --------------------------------------------------------------------------- //

async function fetchTeamFixtures(apiKey, teamId, start, end) {
  const url = `${FOOTBALL_API_BASE}/fixtures?team=${teamId}&from=${toIsoDate(start)}&to=${toIsoDate(end)}`;
  try {
    const data = await httpGetJsonWithHeaders(url, { "x-apisports-key": apiKey });
    return data.response || [];
  } catch (e) {
    return [];
  }
}

async function fetchFootballEvents(apiKey, today, withinDays) {
  if (!apiKey) return [];
  const until = addDays(today, withinDays);
  const events = [];

  for (const [teamIdStr, teamName] of Object.entries(TURKISH_BIG_TEAMS)) {
    const teamId = Number(teamIdStr);
    const fixtures = await fetchTeamFixtures(apiKey, teamId, today, until);
    for (const fx of fixtures) {
      const homeId = fx.teams.home.id;
      const awayId = fx.teams.away.id;
      const homeName = fx.teams.home.name;
      const awayName = fx.teams.away.name;
      const matchDate = fx.fixture.date.slice(0, 10);
      const leagueId = fx.league.id;

      const isDerby = TURKISH_BIG_TEAMS[homeId] && TURKISH_BIG_TEAMS[awayId];
      const isEuroCup = EUROPEAN_CUP_LEAGUE_IDS.has(leagueId);
      if (isDerby) {
        events.push({ title: `${homeName} - ${awayName} derbisi`, date: matchDate, priority: "high" });
      } else if (isEuroCup) {
        const opponent = homeId === teamId ? awayName : homeName;
        events.push({ title: `${teamName}, ${fx.league.name}'de ${opponent} ile oynuyor`, date: matchDate, priority: "high" });
      }
    }
  }

  for (const [teamIdStr, teamName] of Object.entries(STRONG_FOREIGN_TEAMS)) {
    const teamId = Number(teamIdStr);
    const fixtures = await fetchTeamFixtures(apiKey, teamId, today, until);
    for (const fx of fixtures) {
      if (fx.league.id !== 2) continue; // sadece Şampiyonlar Ligi
      const opponent = fx.teams.home.id === teamId ? fx.teams.away.name : fx.teams.home.name;
      const matchDate = fx.fixture.date.slice(0, 10);
      events.push({ title: `${teamName}, Şampiyonlar Ligi'nde ${opponent} ile oynuyor`, date: matchDate, priority: "medium" });
    }
  }

  const seen = new Set();
  return events.filter((e) => {
    const key = `${e.title}|${e.date}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

// --------------------------------------------------------------------------- //
// SpaceX / NASA fırlatmaları — rutin Falcon 9/Starlink fırlatmaları elenir.
// --------------------------------------------------------------------------- //

const NOTABLE_LAUNCH_KEYWORDS = ["starship", "artemis", "crew-", "crew dragon"];

async function fetchSpaceLaunches(today, withinDays) {
  const until = addDays(today, withinDays);
  let data;
  try {
    data = await httpGetJson(SPACE_LAUNCHES_URL);
  } catch (e) {
    return [];
  }

  const events = [];
  for (const launch of data.results || []) {
    const name = (launch.name || "").trim();
    const net = launch.net;
    if (!name || !net) continue;
    const launchDate = new Date(net);
    if (Number.isNaN(launchDate.getTime())) continue;
    if (launchDate < today || launchDate > until) continue;
    if (!NOTABLE_LAUNCH_KEYWORDS.some((kw) => name.toLowerCase().includes(kw))) continue;
    events.push({ title: `${name} fırlatması`, date: toIsoDate(launchDate), priority: "medium" });
  }
  return events;
}

// --------------------------------------------------------------------------- //
// Tüyap İstanbul Kitap Fuarı — resmi API yok, sayfadaki "TAKVİME EKLE"
// bloğundaki makine-okunur tarih (statik HTML) regex ile çekilir.
// --------------------------------------------------------------------------- //

const TUYAP_DATE_RE = /(\d{4}-\d{2}-\d{2}) \d{2}:\d{2}:\d{2}/;

async function fetchTuyapFair(today, withinDays) {
  const until = addDays(today, withinDays);
  let html;
  try {
    html = await httpGetText(TUYAP_FAIR_URL);
  } catch (e) {
    return [];
  }

  const match = TUYAP_DATE_RE.exec(html);
  if (!match) return [];
  const startDate = new Date(match[1] + "T00:00:00Z");
  if (Number.isNaN(startDate.getTime()) || startDate < today || startDate > until) return [];
  return [{ title: "İstanbul Kitap Fuarı (Tüyap) başlıyor", date: match[1], priority: "high" }];
}

// --------------------------------------------------------------------------- //
// Black Friday / Siber Pazartesi / Kara Cuma — tarih kuralıyla hesaplanır.
// --------------------------------------------------------------------------- //

function nthWeekdayOfNovember(year, weekday, n) {
  // weekday: Pazar=0 ... Cumartesi=6 (JS Date.getUTCDay() ile aynı).
  let d = new Date(Date.UTC(year, 10, 1));
  let count = 0;
  while (true) {
    if (d.getUTCDay() === weekday) {
      count += 1;
      if (count === n) return d;
    }
    d = addDays(d, 1);
  }
}

function computeFlashSaleDates(today) {
  const events = [];
  for (const y of [today.getUTCFullYear(), today.getUTCFullYear() + 1]) {
    const blackFriday = addDays(nthWeekdayOfNovember(y, 4, 4), 1); // 4. Perşembe (4) + 1 gün
    const cyberMonday = addDays(blackFriday, 3);
    events.push({ title: "Black Friday / Kara Cuma indirimleri", date: toIsoDate(blackFriday), priority: "high" });
    events.push({ title: "Siber Pazartesi (Cyber Monday) indirimleri", date: toIsoDate(cyberMonday), priority: "high" });
  }
  return events;
}

// --------------------------------------------------------------------------- //
// Meteor yağmurları — sabit yıllık takvim.
// --------------------------------------------------------------------------- //

function computeMeteorShowers(today) {
  const events = [];
  for (const [name, month, day] of METEOR_SHOWERS) {
    for (const y of [today.getUTCFullYear(), today.getUTCFullYear() + 1]) {
      const peak = new Date(Date.UTC(y, month - 1, day));
      events.push({ title: `${name} meteor yağmuru zirvesi`, date: toIsoDate(peak), priority: "medium" });
    }
  }
  return events;
}

// --------------------------------------------------------------------------- //
// Ay/Güneş tutulması (statik tablo) + süper ay (astronomik hesap).
// --------------------------------------------------------------------------- //

function julianDay(date) {
  // Meeus düşük-hassasiyet Julian gün formülü (events_data.py._julian_day ile
  // birebir aynı — UTC gece yarısı referanslı).
  let y = date.getUTCFullYear();
  let m = date.getUTCMonth() + 1;
  const d = date.getUTCDate() + (date.getUTCHours() + date.getUTCMinutes() / 60) / 24;
  if (m <= 2) {
    y -= 1;
    m += 12;
  }
  const a = Math.floor(y / 100);
  const b = 2 - a + Math.floor(a / 4);
  return Math.floor(365.25 * (y + 4716)) + Math.floor(30.6001 * (m + 1)) + d + b - 1524.5;
}

function moonPhaseAndDistance(date) {
  const jd = julianDay(date);
  const daysSinceNew = jd - 2451550.1;
  const newMoons = daysSinceNew / 29.530588853;
  const phase = newMoons - Math.floor(newMoons);

  const anomalyDays = jd - 2451534.7;
  const anomalyCycles = anomalyDays / 27.55455;
  const anomalyPhase = (anomalyCycles - Math.floor(anomalyCycles)) * 2 * Math.PI;
  const distanceKm = 385000 - 21000 * Math.cos(anomalyPhase);
  return { phase, distanceKm };
}

function computeSupermoons(today, withinDays = 60) {
  const events = [];
  for (let offset = 0; offset < withinDays; offset++) {
    const day = addDays(today, offset);
    const noon = new Date(Date.UTC(day.getUTCFullYear(), day.getUTCMonth(), day.getUTCDate(), 12));
    const { phase, distanceKm } = moonPhaseAndDistance(noon);
    const isFullMoon = Math.abs(phase - 0.5) < 1 / 29.530588853;
    const isSuper = distanceKm < 361000;
    if (isFullMoon && isSuper) {
      events.push({ title: "Süper ay (dolunay, Dünya'ya en yakın konumunda)", date: toIsoDate(day), priority: "medium" });
    }
  }
  return events;
}

function computeAstroEvents(today) {
  const events = KNOWN_ECLIPSES.map(([d, desc]) => ({ title: desc, date: d, priority: "high" }));
  events.push(...computeSupermoons(today));
  return events;
}

// --------------------------------------------------------------------------- //
// Toplayıcı
// --------------------------------------------------------------------------- //

const PRIORITY_RANK = { high: 2, medium: 1, low: 0 };

export async function getPrioritizedEvents({ minPriority = "high", withinDays = 14, today, tmdbApiKey, footballApiKey }) {
  const bugun = today || new Date(new Date().toISOString().slice(0, 10) + "T00:00:00Z");
  const until = addDays(bugun, withinDays);

  const fetchers = [
    () => fetchScifiMovies(tmdbApiKey, bugun, withinDays),
    () => fetchFootballEvents(footballApiKey, bugun, withinDays),
    () => fetchSpaceLaunches(bugun, withinDays),
    () => fetchTuyapFair(bugun, withinDays),
    () => computeFlashSaleDates(bugun),
    () => computeMeteorShowers(bugun),
    () => computeAstroEvents(bugun),
  ];

  const results = await Promise.all(
    fetchers.map(async (fn) => {
      try {
        return await fn();
      } catch (e) {
        console.error("events.js kaynak hatası:", e);
        return [];
      }
    })
  );
  const allEvents = results.flat();

  const minRank = PRIORITY_RANK[minPriority] ?? 2;
  const filtered = allEvents
    .map((e) => ({ ...e, _date: new Date(e.date + "T00:00:00Z") }))
    .filter((e) => !Number.isNaN(e._date.getTime()) && e._date >= bugun && e._date <= until)
    .filter((e) => (PRIORITY_RANK[e.priority] ?? 0) >= minRank)
    .sort((a, b) => a._date - b._date)
    .map(({ _date, ...rest }) => rest);

  return filtered;
}
