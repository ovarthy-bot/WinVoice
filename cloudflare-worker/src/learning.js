// src/learning.js
//
// learning_cards.py'nin birebir Cloudflare Worker (D1) portu:
// - 60_Öğrenme/İngilizce unuttuğum kelimeler.md + Havacılık Teknik İngilizcesi (AMM / Kabin Bakım)
//   + Günlük B1-B2 İngilizce çekirdek kelime havuzu.
// - Leitner aralıklı tekrar (Kutu 1..5 -> 1, 3, 7, 15, 30 gün).
// - Telegram brifing mesajı altına eklenen [✅ Öğrendim] / [🔁 Tekrar Sor] satır içi butonları.

import { nowIstanbulIso } from "./common.js";

export const VAULT_ENGLISH_WORDS_PATH = "60_Öğrenme/İngilizce unuttuğum kelimeler.md";
const ROW_RE = /^\|(.+)\|\s*$/;
const LEITNER_INTERVAL_DAYS = { 1: 1, 2: 3, 3: 7, 4: 15, 5: 30 };

const VAULT_WORD_ENRICHMENTS = {
  advent: {
    meaningTr: "ortaya çıkış, geliş, başlangıç",
    memoryTip: "Yeni bir teknolojinin veya dönemin sahneye çıkışını anlatır.",
    exampleEn: "With the advent of composite materials, aircraft cabins became much lighter.",
    exampleTr: "Kompozit malzemelerin ortaya çıkışıyla uçak kabinleri çok daha hafif hale geldi.",
  },
  beyond: {
    meaningTr: "ötesinde, aşan",
    memoryTip: "Bir sınırın veya limitin ilerisini ifade eder.",
    exampleEn: "The panel scratch was beyond the allowable structural limit.",
    exampleTr: "Paneldeki çizik izin verilen yapısal limitin ötesindeydi.",
  },
};

export const SEED_CARDS = [
  // --- Havacılık & Kabin İçi Bakım (aviation) ---
  {
    key: "discrepancy",
    word: "discrepancy",
    domain: "aviation",
    meaningTr: "uyumsuzluk, arıza bulgusu",
    memoryTip: "Bakımda beklenen durum ile tespit edilen kusur arasındaki farktır.",
    exampleEn: "Please record any cabin discrepancy in the technical logbook.",
    exampleTr: "Lütfen kabindeki her türlü arıza bulgusunu teknik kayıt defterine işleyin.",
  },
  {
    key: "placard",
    word: "placard",
    domain: "aviation",
    meaningTr: "uyarı etiketi, bilgi levhası",
    memoryTip: "Kabin içinde yolcu ve ekip yönlendirme/emniyet etiketlerinin tamamıdır.",
    exampleEn: "Verify that all emergency exit placards are legible and secure.",
    exampleTr: "Tüm acil çıkış etiketlerinin okunaklı ve sağlam olduğunu doğrulayın.",
  },
  {
    key: "stowage",
    word: "stowage",
    domain: "aviation",
    meaningTr: "eşya dolabı, yerleştirme bölmesi",
    memoryTip: "Baş üstü dolapları ve ekipman sabitleme alanları için kullanılır.",
    exampleEn: "Inspect the overhead stowage bin latch mechanism for smooth operation.",
    exampleTr: "Baş üstü dolabı kilit mekanizmasının rahat çalıştığını kontrol edin.",
  },
  {
    key: "latch",
    word: "latch",
    domain: "aviation",
    meaningTr: "mandal, kilit dili",
    memoryTip: "Galley arabalarını, dolap kapaklarını ve masaları kapalı tutan mandaldır.",
    exampleEn: "Make sure every galley container latch is fully engaged before taxi.",
    exampleTr: "Taksi öncesinde her galley konteyner mandalının tam kilitlendiğinden emin olun.",
  },
  {
    key: "bulkhead",
    word: "bulkhead",
    domain: "aviation",
    meaningTr: "kabin bölme duvarı, perde",
    memoryTip: "Kabin sınıflarını veya galley ile yolcu bölümünü ayıran dikey bölmedir.",
    exampleEn: "Check the forward bulkhead panel for any loose fasteners.",
    exampleTr: "Ön bölme duvarı panelinde gevşek bağlantı elemanı olup olmadığını kontrol edin.",
  },
  {
    key: "rectify",
    word: "rectify",
    domain: "aviation",
    meaningTr: "gidermek, düzeltmek, onarmak",
    memoryTip: "Tespit edilen bir arızayı kurallara uygun şekilde gidermek demektir.",
    exampleEn: "The seat recline fault was rectified during the turnaround check.",
    exampleTr: "Koltuk yatırma arızası sefer arası kontrolde giderildi.",
  },
  {
    key: "wear_and_tear",
    word: "wear and tear",
    domain: "aviation",
    meaningTr: "olağan aşınma ve yıpranma",
    memoryTip: "Normal kullanım sonucu koltuk, halı ve panellerde oluşan yıpranmadır.",
    exampleEn: "Replace the cabin carpet if it shows excessive wear and tear.",
    exampleTr: "Aşırı aşınma ve yıpranma gösteriyorsa kabin halısını değiştirin.",
  },
  {
    key: "corrosion",
    word: "corrosion",
    domain: "aviation",
    meaningTr: "korozyon, paslanma, aşınma",
    memoryTip: "Özellikle galley ve lavatory ıslak zeminlerinin altında dikkatle aranır.",
    exampleEn: "Inspect the seat tracks beneath the galley area for signs of corrosion.",
    exampleTr: "Galley bölgesinin altındaki koltuk raylarını korozyon belirtilerine karşı inceleyin.",
  },
  {
    key: "clearance",
    word: "clearance",
    domain: "aviation",
    meaningTr: "boşluk payı, çalışma aralığı",
    memoryTip: "Hareketli iki parça arasında sürtünmeyi önleyen emniyet mesafesidir.",
    exampleEn: "Ensure adequate clearance between the Escape Slide pack and the door frame.",
    exampleTr: "Tahliye kaydırağı paketi ile kapı çerçevesi arasında yeterli boşluk olduğundan emin olun.",
  },
  {
    key: "fastener",
    word: "fastener",
    domain: "aviation",
    meaningTr: "bağlantı elemanı (vida, perçin, cıvata)",
    memoryTip: "Panelleri ve kaplamaları gövdeye sabitleyen tüm bağlantı parçalarıdır.",
    exampleEn: "Never mix different types of panel fasteners during reinstallation.",
    exampleTr: "Yeniden montaj sırasında farklı tip panel bağlantı elemanlarını asla karıştırmayın.",
  },
  {
    key: "serviceable",
    word: "serviceable",
    domain: "aviation",
    meaningTr: "kullanılabilir, faal durumda",
    memoryTip: "Parçanın uçuşa elverişli ve etiketli olduğunu belirtir.",
    exampleEn: "Install a serviceable life vest under the passenger seat.",
    exampleTr: "Yolcu koltuğunun altına faal durumda bir can yeleği takın.",
  },
  {
    key: "inoperative",
    word: "inoperative",
    domain: "aviation",
    meaningTr: "gayrifaal, çalışmaz durumda",
    memoryTip: "MEL kapsamında devre dışı bırakılan sistem veya koltuklara INOP etiketi takılır.",
    exampleEn: "Place an inoperative placard on the affected reading light.",
    exampleTr: "Arızalı okuma lambasının üzerine çalışmaz etiketi yerleştirin.",
  },
  {
    key: "upholstery",
    word: "upholstery",
    domain: "aviation",
    meaningTr: "koltuk döşemesi, kumaş/deri kaplama",
    memoryTip: "Yolcu ve ekip koltuklarının kılıf ve minder kaplamalarını ifade eder.",
    exampleEn: "The torn seat upholstery was replaced before boarding.",
    exampleTr: "Yırtılan koltuk döşemesi yolcu alımından önce değiştirildi.",
  },
  {
    key: "shroud",
    word: "shroud",
    domain: "aviation",
    meaningTr: "koruyucu kapak, çerçeve maskesi",
    memoryTip: "Pencere çevresi (window shroud) veya koltuk alt mekanizma koruyucu kapağıdır.",
    exampleEn: "Carefully align the window shroud clips before pressing the sidewall panel.",
    exampleTr: "Yan duvar paneline bastırmadan önce pencere çerçeve klipslerini dikkatlice hizalayın.",
  },
  {
    key: "sealant",
    word: "sealant",
    domain: "aviation",
    meaningTr: "sızdırmazlık macunu, mastik",
    memoryTip: "Islak hacimlerde su sızıntısını ve korozyonu önlemek için çekilir.",
    exampleEn: "Apply fresh moisture sealant around the lavatory floor edges.",
    exampleTr: "Tuvalet zemin kenarlarının etrafına taze nem sızdırmazlık mastiği uygulayın.",
  },
  {
    key: "fairing",
    word: "fairing",
    domain: "aviation",
    meaningTr: "aerodinamik kaplama, geçiş kapağı",
    memoryTip: "Hava akışını yumuşatan veya boşlukları kapatan düzgün yüzey kaplamasıdır.",
    exampleEn: "Check the external door fairing for cracks or missing screws.",
    exampleTr: "Dış kapı kaplamasını çatlak veya eksik vidalara karşı kontrol edin.",
  },
  {
    key: "armrest",
    word: "armrest",
    domain: "aviation",
    meaningTr: "kolçak, kol dayama yeri",
    memoryTip: "Yolcu koltuklarındaki hareketli ve kumanda barındıran kol dayama parçasıdır.",
    exampleEn: "Tighten the loose pivot bolt on the aisle seat armrest.",
    exampleTr: "Koridor koltuğu kolçağındaki gevşek mafsal cıvatasını sıkın.",
  },
  {
    key: "galley",
    word: "galley",
    domain: "aviation",
    meaningTr: "uçak mutfağı",
    memoryTip: "Fırın, kahve makinesi ve servis arabalarının bulunduğu ikram hazırlık alanıdır.",
    exampleEn: "Ensure the galley floor drain is completely clear of debris.",
    exampleTr: "Uçak mutfağı zemin giderinin kalıntılardan tamamen arındırıldığından emin olun.",
  },
  // --- Günlük B1-B2 İngilizce (daily) ---
  {
    key: "feasible",
    word: "feasible",
    domain: "daily",
    meaningTr: "uygulanabilir, yapılabilir, makul",
    memoryTip: "Eldeki zaman ve imkanlarla pratikte gerçekleştirilebilir demektir.",
    exampleEn: "Finishing both tasks before noon looks completely feasible.",
    exampleTr: "Öğleden önce her iki işi de bitirmek tamamen uygulanabilir görünüyor.",
  },
  {
    key: "thorough",
    word: "thorough",
    domain: "daily",
    meaningTr: "kapsamlı, titiz, eksiksiz",
    memoryTip: "Yüzeysel değil, hiçbir detayı atlamadan yapılan incelemedir.",
    exampleEn: "He did a thorough check before closing the panel.",
    exampleTr: "Paneli kapatmadan önce titiz ve eksiksiz bir kontrol yaptı.",
  },
  {
    key: "postpone",
    word: "postpone",
    domain: "daily",
    meaningTr: "ertelemek, sonraya bırakmak",
    memoryTip: "Planlanan bir işi iptal etmeyip ileri bir tarihe almaktır.",
    exampleEn: "We had to postpone our outdoor plan because of heavy wind.",
    exampleTr: "Şiddetli rüzgar yüzünden dışarı planımızı ertelemek zorunda kaldık.",
  },
  {
    key: "accurate",
    word: "accurate",
    domain: "daily",
    meaningTr: "doğru, isabetli, hatasız",
    memoryTip: "Ölçümün, saatin veya bilginin gerçeğe tam uymasıdır.",
    exampleEn: "Hourly weather forecasts are much more accurate for planning your outfit.",
    exampleTr: "Saatlik hava tahminleri kıyafet planlamak için çok daha isabetlidir.",
  },
  {
    key: "precaution",
    word: "precaution",
    domain: "daily",
    meaningTr: "önlem, tedbir",
    memoryTip: "Olumsuz bir durum yaşanmadan önce alınan koruyucu tedbirdir.",
    exampleEn: "Take a waterproof jacket just as a precaution against evening rain.",
    exampleTr: "Akşam yağmuruna karşı tedbir olarak yanına su geçirmez bir ceket al.",
  },
  {
    key: "overlook",
    word: "overlook",
    domain: "daily",
    meaningTr: "gözden kaçırmak, fark etmemek",
    memoryTip: "Acele ederken küçük ama önemli bir detayı atlamak anlamındadır.",
    exampleEn: "It is easy to overlook small details when you are in a rush.",
    exampleTr: "Acele ettiğinde küçük detayları gözden kaçırmak kolaydır.",
  },
  {
    key: "durable",
    word: "durable",
    domain: "daily",
    meaningTr: "dayanıklı, sağlam, uzun ömürlü",
    memoryTip: "Zorlu kullanıma uzun süre dayanan malzemeleri tanımlar.",
    exampleEn: "Choose a durable tool bag that can handle daily use.",
    exampleTr: "Günlük kullanıma dayanabilecek sağlam bir takım çantası seç.",
  },
  {
    key: "crucial",
    word: "crucial",
    domain: "daily",
    meaningTr: "hayati, çok kritik, belirleyici",
    memoryTip: "Sonucu doğrudan etkileyen en önemli adımı vurgular.",
    exampleEn: "Clear communication between shifts is crucial for safety.",
    exampleTr: "Vardiyalar arasında net iletişim emniyet için çok kritiktir.",
  },
  {
    key: "consistent",
    word: "consistent",
    domain: "daily",
    meaningTr: "tutarlı, istikrarlı",
    memoryTip: "Her gün küçük de olsa aynı disiplini sürdürmeyi anlatır.",
    exampleEn: "Learning one new word every morning brings consistent progress.",
    exampleTr: "Her sabah yeni bir kelime öğrenmek istikrarlı bir gelişim sağlar.",
  },
  {
    key: "reluctant",
    word: "reluctant",
    domain: "daily",
    meaningTr: "isteksiz, gönülsüz, çekimser",
    memoryTip: "Bir şeyi yapmaya pek gönlü olmamak, tereddüt etmektir.",
    exampleEn: "People are often reluctant to go outside on cold windy mornings.",
    exampleTr: "İnsanlar soğuk ve rüzgarlı sabahlarda dışarı çıkmaya genelde isteksizdir.",
  },
  {
    key: "inevitable",
    word: "inevitable",
    domain: "daily",
    meaningTr: "kaçınılmaz",
    memoryTip: "Ne yapılırsa yapılsın gerçekleşmesi kesin olan durumdur.",
    exampleEn: "Traffic delays are almost inevitable during heavy fog.",
    exampleTr: "Yoğun siste trafik gecikmeleri neredeyse kaçınılmazdır.",
  },
  {
    key: "subtle",
    word: "subtle",
    domain: "daily",
    meaningTr: "ince, ilk bakışta fark edilmeyen, hafif",
    memoryTip: "Dikkatli bakınca anlaşılan ince ses, fark veya işarettir.",
    exampleEn: "There was a subtle vibration in the cabin sidewall panel.",
    exampleTr: "Kabin yan duvar panelinde ilk anda zor fark edilen hafif bir titreşim vardı.",
  },
  {
    key: "obstacle",
    word: "obstacle",
    domain: "daily",
    meaningTr: "engel, mani",
    memoryTip: "Yolu veya ilerlemeyi kapatan fiziksel ya da soyut engeldir.",
    exampleEn: "Keep the emergency exit path free of any obstacle.",
    exampleTr: "Acil çıkış yolunu her türlü engelden uzak tutun.",
  },
  {
    key: "fragile",
    word: "fragile",
    domain: "daily",
    meaningTr: "kırılgan, hassas",
    memoryTip: "Kargo paketlerinde ve ince plastik/cam parçalarda sıkça yazar.",
    exampleEn: "Handle the reading light lens carefully because it is fragile.",
    exampleTr: "Kırılgan olduğu için okuma lambası merceğini dikkatle tutun.",
  },
  {
    key: "gradually",
    word: "gradually",
    domain: "daily",
    meaningTr: "kademeli olarak, yavaş yavaş",
    memoryTip: "Aniden değil, zamana yayılarak adım adım değişmektir.",
    exampleEn: "The temperature will gradually rise toward the afternoon.",
    exampleTr: "Sıcaklık öğleden sonraya doğru kademeli olarak yükselecek.",
  },
  {
    key: "adequate",
    word: "adequate",
    domain: "daily",
    meaningTr: "yeterli, ihtiyacı karşılayan",
    memoryTip: "Eksik kalmayacak kadar yeterli miktarda veya seviyede olmaktır.",
    exampleEn: "Make sure you get adequate sleep before an early morning shift.",
    exampleTr: "Sabah erken vardiyasından önce yeterli uyku aldığından emin ol.",
  },
  {
    key: "versatile",
    word: "versatile",
    domain: "daily",
    meaningTr: "çok yönlü, çok amaçlı",
    memoryTip: "Farklı işlere ve koşullara kolayca uyum sağlayan araç veya kişidir.",
    exampleEn: "A lightweight windbreaker is a versatile choice for spring and autumn.",
    exampleTr: "Hafif bir rüzgarlık ilkbahar ve sonbahar için çok yönlü bir tercihtir.",
  },
  {
    key: "outcome",
    word: "outcome",
    domain: "daily",
    meaningTr: "sonuç, netice",
    memoryTip: "Bir sürecin veya çalışmanın sonunda ortaya çıkan neticedir.",
    exampleEn: "Good preparation directly improves the outcome of your workday.",
    exampleTr: "İyi hazırlık iş gününün sonucunu doğrudan iyileştirir.",
  },
];

function normalizeKey(word) {
  return String(word || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function addDaysIso(isoDateStr, days) {
  const dt = new Date(isoDateStr + "T00:00:00Z");
  dt.setUTCDate(dt.getUTCDate() + days);
  return dt.toISOString().slice(0, 10);
}

export function parseVaultEnglishCards(markdownText) {
  if (!markdownText) return [];
  const cards = [];
  for (const rawLine of String(markdownText).split("\n")) {
    const m = ROW_RE.exec(rawLine.trim());
    if (!m) continue;
    const cells = m[1].split("|").map((c) => c.trim());
    if (cells.length < 2) continue;
    const [word, meaning] = cells;
    const isSep = word.length > 0 && [...word].every((ch) => ch === "-" || ch === ":");
    if (!word || ["kelime", "word"].includes(word.toLowerCase()) || isSep) continue;
    const key = normalizeKey(word);
    if (!key) continue;
    const enrich = VAULT_WORD_ENRICHMENTS[key] || {};
    const exampleCol = cells[2] ? cells[2].trim() : "";
    cards.push({
      key,
      word: word.trim(),
      domain: "vault",
      meaningTr: enrich.meaningTr || meaning.trim(),
      memoryTip: enrich.memoryTip || "Kendi kelime listene eklediğin özel tekrar kelimesi.",
      exampleEn: exampleCol || enrich.exampleEn || `Try using the word ${word.trim()} in a short sentence today.`,
      exampleTr: enrich.exampleTr || "",
    });
  }
  return cards;
}

export function getMergedDeck(vaultMarkdown) {
  const vaultCards = parseVaultEnglishCards(vaultMarkdown);
  const seen = new Set();
  const deck = [];
  for (const c of [...vaultCards, ...SEED_CARDS]) {
    if (seen.has(c.key)) continue;
    seen.add(c.key);
    deck.push(c);
  }
  return deck;
}

export async function selectDailyLearningCard(db, todayIso, vaultMarkdown = "") {
  const deck = getMergedDeck(vaultMarkdown);
  if (!deck.length) return null;

  const deckByKey = new Map(deck.map((c) => [c.key, c]));
  let progRows = [];
  try {
    const res = await db.prepare("SELECT * FROM learning_progress").all();
    progRows = res.results || [];
  } catch (_) {
    progRows = [];
  }

  const progMap = new Map(progRows.map((r) => [r.word_key, r]));

  // 1) Bugün zaten seçilmiş kart varsa tutarlılık için aynı kartı döndür
  for (const [key, row] of progMap.entries()) {
    if (row.last_shown_date === todayIso && deckByKey.has(key)) {
      return { ...deckByKey.get(key), box: Number(row.box || 1) };
    }
  }

  const yesterdayIso = addDaysIso(todayIso, -1);
  let yesterdayDomain = null;
  for (const row of progMap.values()) {
    if (row.last_shown_date === yesterdayIso) {
      yesterdayDomain = row.domain;
      break;
    }
  }

  const domainPreferred = (card) => {
    if (card.domain === "vault") return true;
    if (yesterdayDomain === "aviation") return card.domain !== "aviation";
    if (yesterdayDomain === "daily" || yesterdayDomain === "vault") return card.domain === "aviation";
    return true;
  };

  const dueCards = [];
  const unseenCards = [];
  const futureCards = [];

  deck.forEach((card, idx) => {
    const prog = progMap.get(card.key);
    if (!prog) {
      unseenCards.push({ idx, card });
    } else {
      const nextRev = prog.next_review_date || "1970-01-01";
      const box = Number(prog.box || 1);
      if (nextRev <= todayIso) dueCards.push({ box, nextRev, idx, card });
      else futureCards.push({ nextRev, box, idx, card });
    }
  });

  let chosen = null;
  if (dueCards.length) {
    dueCards.sort((a, b) => {
      const pa = domainPreferred(a.card) ? 0 : 1;
      const pb = domainPreferred(b.card) ? 0 : 1;
      if (pa !== pb) return pa - pb;
      const va = a.card.domain === "vault" ? 0 : 1;
      const vb = b.card.domain === "vault" ? 0 : 1;
      if (va !== vb) return va - vb;
      if (a.box !== b.box) return a.box - b.box;
      if (a.nextRev !== b.nextRev) return a.nextRev.localeCompare(b.nextRev);
      return a.idx - b.idx;
    });
    chosen = dueCards[0].card;
  } else if (unseenCards.length) {
    unseenCards.sort((a, b) => {
      const pa = domainPreferred(a.card) ? 0 : 1;
      const pb = domainPreferred(b.card) ? 0 : 1;
      if (pa !== pb) return pa - pb;
      const va = a.card.domain === "vault" ? 0 : 1;
      const vb = b.card.domain === "vault" ? 0 : 1;
      if (va !== vb) return va - vb;
      return a.idx - b.idx;
    });
    chosen = unseenCards[0].card;
  } else if (futureCards.length) {
    futureCards.sort((a, b) => a.nextRev.localeCompare(b.nextRev) || a.box - b.box || a.idx - b.idx);
    chosen = futureCards[0].card;
  }

  if (!chosen) return null;

  // Gösterimi D1'e kaydet
  const existing = progMap.get(chosen.key);
  const nowIso = nowIstanbulIso();
  const box = existing ? Number(existing.box || 1) : 1;
  const interval = existing ? LEITNER_INTERVAL_DAYS[box] || 3 : 2;
  const nextDue = addDaysIso(todayIso, interval);

  try {
    if (existing) {
      await db
        .prepare(
          "UPDATE learning_progress SET last_shown_date = ?, next_review_date = ?, times_shown = times_shown + 1, updated_at = ? WHERE word_key = ?"
        )
        .bind(todayIso, nextDue, nowIso, chosen.key)
        .run();
    } else {
      await db
        .prepare(
          "INSERT INTO learning_progress (word_key, word, domain, box, next_review_date, last_shown_date, times_shown, times_known, updated_at) VALUES (?, ?, ?, 1, ?, ?, 1, 0, ?)"
        )
        .bind(chosen.key, chosen.word, chosen.domain, nextDue, todayIso, nowIso)
        .run();
    }
  } catch (e) {
    console.error("learning_progress güncellenemedi:", e);
  }

  return { ...chosen, box };
}

export function formatLearningCardTelegram(card) {
  if (!card) return "";
  const domainLabel =
    card.domain === "aviation"
      ? "havacılık teknik İngilizcesi"
      : card.domain === "vault"
      ? "kendi kelime notların"
      : "günlük İngilizce";

  const lines = [
    `🇬🇧 Günün İngilizce Kartı (${domainLabel} · Kutu ${card.box || 1}):`,
    `• Kelime: "${card.word}" — ${card.meaningTr}`,
  ];
  if (card.memoryTip) lines.push(`• İpucu: ${card.memoryTip}`);
  if (card.exampleEn) {
    let exLine = `• Örnek: "${card.exampleEn}"`;
    if (card.exampleTr) exLine += ` (${card.exampleTr})`;
    lines.push(exLine);
  }
  return lines.join("\n");
}

export function buildLearningCardInlineMarkup(card) {
  if (!card) return null;
  return {
    inline_keyboard: [
      [
        { text: `✅ Öğrendim: ${card.word}`, callback_data: `learn:ok:${card.key}` },
        { text: "🔁 Tekrar Sor", callback_data: `learn:again:${card.key}` },
      ],
    ],
  };
}

export async function recordLearningFeedbackD1(db, wordKey, known, todayIso) {
  const nowIso = nowIstanbulIso();
  const existing = await db.prepare("SELECT * FROM learning_progress WHERE word_key = ?").bind(wordKey).first();
  const seed = SEED_CARDS.find((c) => c.key === wordKey);
  const word = existing?.word || seed?.word || wordKey;
  const domain = existing?.domain || seed?.domain || "daily";

  const curBox = existing ? Number(existing.box || 1) : 1;
  const newBox = known ? Math.min(5, curBox + 1) : 1;
  const interval = LEITNER_INTERVAL_DAYS[newBox] || 1;
  const nextDue = addDaysIso(todayIso, interval);

  if (existing) {
    await db
      .prepare(
        "UPDATE learning_progress SET box = ?, next_review_date = ?, times_known = times_known + ?, updated_at = ? WHERE word_key = ?"
      )
      .bind(newBox, nextDue, known ? 1 : 0, nowIso, wordKey)
      .run();
  } else {
    await db
      .prepare(
        "INSERT INTO learning_progress (word_key, word, domain, box, next_review_date, last_shown_date, times_shown, times_known, updated_at) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)"
      )
      .bind(wordKey, word, domain, newBox, nextDue, todayIso, known ? 1 : 0, nowIso)
      .run();
  }

  return { word, box: newBox, intervalDays: interval, nextReviewDate: nextDue };
}

