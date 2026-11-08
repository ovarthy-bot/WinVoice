# learning_cards.py
#
# Günlük Brifing için Aralıklı Tekrarlı (Leitner) İngilizce Öğrenme Kartı motoru.
# Birincil kaynak HAKKIMDA kasasındaki "60_Öğrenme/İngilizce unuttuğum kelimeler.md"
# tablosudur; yanına kabin içi bakım / havacılık teknik İngilizcesi (AMM / EASA)
# ve günlük B1-B2 İngilizce çekirdek kelime havuzu eklenir.
#
# Masaüstünde (for_tts=True) İngilizce kelime ve örnek cümle çift tırnak ("...")
# içine alınır ki lang_segmenter.py bu parçaları otomatik olarak Kokoro İngilizce
# ses motoruna yönlendirsin.

import re
from datetime import date, datetime, timedelta

import note_database
import vault_cache

VAULT_ENGLISH_WORDS_PATH = "60_Öğrenme/İngilizce unuttuğum kelimeler.md"
_ROW_RE = re.compile(r"^\|(.+)\|\s*$")

# Kullanıcı tablosunda örnek cümle bulunmayan kelimeler için hazır doğal örnekler
_VAULT_WORD_ENRICHMENTS = {
    "advent": {
        "meaning_tr": "ortaya çıkış, geliş, başlangıç",
        "memory_tip": "Yeni bir teknolojinin veya dönemin sahneye çıkışını anlatır.",
        "example_en": "With the advent of composite materials, aircraft cabins became much lighter.",
        "example_tr": "Kompozit malzemelerin ortaya çıkışıyla uçak kabinleri çok daha hafif hale geldi.",
    },
    "beyond": {
        "meaning_tr": "ötesinde, aşan",
        "memory_tip": "Bir sınırın veya limitin ilerisini ifade eder.",
        "example_en": "The panel scratch was beyond the allowable structural limit.",
        "example_tr": "Paneldeki çizik izin verilen yapısal limitin ötesindeydi.",
    },
}

# Havacılık Teknik İngilizcesi (Kabin İçi Bakım / AMM) + Günlük B1-B2 Çekirdek Havuzu
SEED_CARDS = [
    # --- Havacılık & Kabin İçi Bakım (aviation) ---
    {
        "key": "discrepancy",
        "word": "discrepancy",
        "domain": "aviation",
        "meaning_tr": "uyumsuzluk, arıza bulgusu",
        "memory_tip": "Bakımda beklenen durum ile tespit edilen kusur arasındaki farktır.",
        "example_en": "Please record any cabin discrepancy in the technical logbook.",
        "example_tr": "Lütfen kabindeki her türlü arıza bulgusunu teknik kayıt defterine işleyin.",
    },
    {
        "key": "placard",
        "word": "placard",
        "domain": "aviation",
        "meaning_tr": "uyarı etiketi, bilgi levhası",
        "memory_tip": "Kabin içinde yolcu ve ekip yönlendirme/emniyet etiketlerinin tamamıdır.",
        "example_en": "Verify that all emergency exit placards are legible and secure.",
        "example_tr": "Tüm acil çıkış etiketlerinin okunaklı ve sağlam olduğunu doğrulayın.",
    },
    {
        "key": "stowage",
        "word": "stowage",
        "domain": "aviation",
        "meaning_tr": "eşya dolabı, yerleştirme bölmesi",
        "memory_tip": "Baş üstü dolapları ve ekipman sabitleme alanları için kullanılır.",
        "example_en": "Inspect the overhead stowage bin latch mechanism for smooth operation.",
        "example_tr": "Baş üstü dolabı kilit mekanizmasının rahat çalıştığını kontrol edin.",
    },
    {
        "key": "latch",
        "word": "latch",
        "domain": "aviation",
        "meaning_tr": "mandal, kilit dili",
        "memory_tip": "Galley arabalarını, dolap kapaklarını ve masaları kapalı tutan mandaldır.",
        "example_en": "Make sure every galley container latch is fully engaged before taxi.",
        "example_tr": "Taksi öncesinde her galley konteyner mandalının tam kilitlendiğinden emin olun.",
    },
    {
        "key": "bulkhead",
        "word": "bulkhead",
        "domain": "aviation",
        "meaning_tr": "kabin bölme duvarı, perde",
        "memory_tip": "Kabin sınıflarını veya galley ile yolcu bölümünü ayıran dikey bölmedir.",
        "example_en": "Check the forward bulkhead panel for any loose fasteners.",
        "example_tr": "Ön bölme duvarı panelinde gevşek bağlantı elemanı olup olmadığını kontrol edin.",
    },
    {
        "key": "rectify",
        "word": "rectify",
        "domain": "aviation",
        "meaning_tr": "gidermek, düzeltmek, onarmak",
        "memory_tip": "Tespit edilen bir arızayı kurallara uygun şekilde gidermek demektir.",
        "example_en": "The seat recline fault was rectified during the turnaround check.",
        "example_tr": "Koltuk yatırma arızası sefer arası kontrolde giderildi.",
    },
    {
        "key": "wear_and_tear",
        "word": "wear and tear",
        "domain": "aviation",
        "meaning_tr": "olağan aşınma ve yıpranma",
        "memory_tip": "Normal kullanım sonucu koltuk, halı ve panellerde oluşan yıpranmadır.",
        "example_en": "Replace the cabin carpet if it shows excessive wear and tear.",
        "example_tr": "Aşırı aşınma ve yıpranma gösteriyorsa kabin halısını değiştirin.",
    },
    {
        "key": "corrosion",
        "word": "corrosion",
        "domain": "aviation",
        "meaning_tr": "korozyon, paslanma, aşınma",
        "memory_tip": "Özellikle galley ve lavatory ıslak zeminlerinin altında dikkatle aranır.",
        "example_en": "Inspect the seat tracks beneath the galley area for signs of corrosion.",
        "example_tr": "Galley bölgesinin altındaki koltuk raylarını korozyon belirtilerine karşı inceleyin.",
    },
    {
        "key": "clearance",
        "word": "clearance",
        "domain": "aviation",
        "meaning_tr": "boşluk payı, çalışma aralığı",
        "memory_tip": "Hareketli iki parça arasında sürtünmeyi önleyen emniyet mesafesidir.",
        "example_en": "Ensure adequate clearance between the Escape Slide pack and the door frame.",
        "example_tr": "Tahliye kaydırağı paketi ile kapı çerçevesi arasında yeterli boşluk olduğundan emin olun.",
    },
    {
        "key": "fastener",
        "word": "fastener",
        "domain": "aviation",
        "meaning_tr": "bağlantı elemanı (vida, perçin, cıvata)",
        "memory_tip": "Panelleri ve kaplamaları gövdeye sabitleyen tüm bağlantı parçalarıdır.",
        "example_en": "Never mix different types of panel fasteners during reinstallation.",
        "example_tr": "Yeniden montaj sırasında farklı tip panel bağlantı elemanlarını asla karıştırmayın.",
    },
    {
        "key": "serviceable",
        "word": "serviceable",
        "domain": "aviation",
        "meaning_tr": "kullanılabilir, faal durumda",
        "memory_tip": "Parçanın uçuşa elverişli ve etiketli (sarı/yeşil kartlı) olduğunu belirtir.",
        "example_en": "Install a serviceable life vest under the passenger seat.",
        "example_tr": "Yolcu koltuğunun altına faal durumda bir can yeleği takın.",
    },
    {
        "key": "inoperative",
        "word": "inoperative",
        "domain": "aviation",
        "meaning_tr": "gayrifaal, çalışmaz durumda",
        "memory_tip": "MEL kapsamında devre dışı bırakılan sistem veya koltuklara INOP etiketi takılır.",
        "example_en": "Place an inoperative placard on the affected reading light.",
        "example_tr": "Arızalı okuma lambasının üzerine çalışmaz etiketi yerleştirin.",
    },
    {
        "key": "upholstery",
        "word": "upholstery",
        "domain": "aviation",
        "meaning_tr": "koltuk döşemesi, kumaş/deri kaplama",
        "memory_tip": "Yolcu ve ekip koltuklarının kılıf ve minder kaplamalarını ifade eder.",
        "example_en": "The torn seat upholstery was replaced before boarding.",
        "example_tr": "Yırtılan koltuk döşemesi yolcu alımından önce değiştirildi.",
    },
    {
        "key": "shroud",
        "word": "shroud",
        "domain": "aviation",
        "meaning_tr": "koruyucu kapak, çerçeve maskesi",
        "memory_tip": "Pencere çevresi (window shroud) veya koltuk alt mekanizma koruyucu kapağıdır.",
        "example_en": "Carefully align the window shroud clips before pressing the sidewall panel.",
        "example_tr": "Yan duvar paneline bastırmadan önce pencere çerçeve klipslerini dikkatlice hizalayın.",
    },
    {
        "key": "sealant",
        "word": "sealant",
        "domain": "aviation",
        "meaning_tr": "sızdırmazlık macunu, mastik",
        "memory_tip": "Islak hacimlerde su sızıntısını ve korozyonu önlemek için çekilir.",
        "example_en": "Apply fresh moisture sealant around the lavatory floor edges.",
        "example_tr": "Tuvalet zemin kenarlarının etrafına taze nem sızdırmazlık mastiği uygulayın.",
    },
    {
        "key": "fairing",
        "word": "fairing",
        "domain": "aviation",
        "meaning_tr": "aerodinamik kaplama, geçiş kapağı",
        "memory_tip": " Hava akışını yumuşatan veya boşlukları kapatan düzgün yüzey kaplamasıdır.",
        "example_en": "Check the external door fairing for cracks or missing screws.",
        "example_tr": "Dış kapı kaplamasını çatlak veya eksik vidalara karşı kontrol edin.",
    },
    {
        "key": "armrest",
        "word": "armrest",
        "domain": "aviation",
        "meaning_tr": "kolçak, kol dayama yeri",
        "memory_tip": "Yolcu koltuklarındaki hareketli ve kumanda barındıran kol dayama parçasıdır.",
        "example_en": "Tighten the loose pivot bolt on the aisle seat armrest.",
        "example_tr": "Koridor koltuğu kolçağındaki gevşek mafsal cıvatasını sıkın.",
    },
    {
        "key": "galley",
        "word": "galley",
        "domain": "aviation",
        "meaning_tr": "uçak mutfağı",
        "memory_tip": "Fırın, kahve makinesi ve servis arabalarının bulunduğu ikram hazırlık alanıdır.",
        "example_en": "Ensure the galley floor drain is completely clear of debris.",
        "example_tr": "Uçak mutfağı zemin giderinin kalıntılardan tamamen arındırıldığından emin olun.",
    },
    # --- Günlük B1-B2 İngilizce (daily) ---
    {
        "key": "feasible",
        "word": "feasible",
        "domain": "daily",
        "meaning_tr": "uygulanabilir, yapılabilir, makul",
        "memory_tip": "Eldeki zaman ve imkanlarla pratikte gerçekleştirilebilir demektir.",
        "example_en": "Finishing both tasks before noon looks completely feasible.",
        "example_tr": "Öğleden önce her iki işi de bitirmek tamamen uygulanabilir görünüyor.",
    },
    {
        "key": "thorough",
        "word": "thorough",
        "domain": "daily",
        "meaning_tr": "kapsamlı, titiz, eksiksiz",
        "memory_tip": "Yüzeysel değil, hiçbir detayı atlamadan yapılan incelemedir.",
        "example_en": "He did a thorough check before closing the panel.",
        "example_tr": "Paneli kapatmadan önce titiz ve eksiksiz bir kontrol yaptı.",
    },
    {
        "key": "postpone",
        "word": "postpone",
        "domain": "daily",
        "meaning_tr": "ertelemek, sonraya bırakmak",
        "memory_tip": "Planlanan bir işi iptal etmeyip ileri bir tarihe almaktır.",
        "example_en": "We had to postpone our outdoor plan because of heavy wind.",
        "example_tr": "Şiddetli rüzgar yüzünden dışarı planımızı ertelemek zorunda kaldık.",
    },
    {
        "key": "accurate",
        "word": "accurate",
        "domain": "daily",
        "meaning_tr": "doğru, isabetli, hatasız",
        "memory_tip": "Ölçümün, saatin veya bilginin gerçeğe tam uymasıdır.",
        "example_en": "Hourly weather forecasts are much more accurate for planning your outfit.",
        "example_tr": "Saatlik hava tahminleri kıyafet planlamak için çok daha isabetlidir.",
    },
    {
        "key": "precaution",
        "word": "precaution",
        "domain": "daily",
        "meaning_tr": "önlem, tedbir",
        "memory_tip": "Olumsuz bir durum yaşanmadan önce alınan koruyucu tedbirdir.",
        "example_en": "Take a waterproof jacket just as a precaution against evening rain.",
        "example_tr": "Akşam yağmuruna karşı tedbir olarak yanına su geçirmez bir ceket al.",
    },
    {
        "key": "overlook",
        "word": "overlook",
        "domain": "daily",
        "meaning_tr": "gözden kaçırmak, fark etmemek",
        "memory_tip": "Acele ederken küçük ama önemli bir detayı atlamak anlamındadır.",
        "example_en": "It is easy to overlook small details when you are in a rush.",
        "example_tr": "Acele ettiğinde küçük detayları gözden kaçırmak kolaydır.",
    },
    {
        "key": "durable",
        "word": "durable",
        "domain": "daily",
        "meaning_tr": "dayanıklı, sağlam, uzun ömürlü",
        "memory_tip": "Zorlu kullanıma uzun süre dayanan malzemeleri tanımlar.",
        "example_en": "Choose a durable tool bag that can handle daily use.",
        "example_tr": "Günlük kullanıma dayanabilecek sağlam bir takım çantası seç.",
    },
    {
        "key": "crucial",
        "word": "crucial",
        "domain": "daily",
        "meaning_tr": "hayati, çok kritik, belirleyici",
        "memory_tip": "Sonucu doğrudan etkileyen en önemli adımı vurgular.",
        "example_en": "Clear communication between shifts is crucial for safety.",
        "example_tr": "Vardiyalar arasında net iletişim emniyet için çok kritiktir.",
    },
    {
        "key": "consistent",
        "word": "consistent",
        "domain": "daily",
        "meaning_tr": "tutarlı, istikrarlı",
        "memory_tip": "Her gün küçük de olsa aynı disiplini sürdürmeyi anlatır.",
        "example_en": "Learning one new word every morning brings consistent progress.",
        "example_tr": "Her sabah yeni bir kelime öğrenmek istikrarlı bir gelişim sağlar.",
    },
    {
        "key": "reluctant",
        "word": "reluctant",
        "domain": "daily",
        "meaning_tr": "isteksiz, gönülsüz, çekimser",
        "memory_tip": "Bir şeyi yapmaya pek gönlü olmamak, tereddüt etmektir.",
        "example_en": "People are often reluctant to go outside on cold windy mornings.",
        "example_tr": "İnsanlar soğuk ve rüzgarlı sabahlarda dışarı çıkmaya genelde isteksizdir.",
    },
    {
        "key": "inevitable",
        "word": "inevitable",
        "domain": "daily",
        "meaning_tr": "kaçınılmaz",
        "memory_tip": "Ne yapılırsa yapılsın gerçekleşmesi kesin olan durumdur.",
        "example_en": "Traffic delays are almost inevitable during heavy fog.",
        "example_tr": "Yoğun siste trafik gecikmeleri neredeyse kaçınılmazdır.",
    },
    {
        "key": "subtle",
        "word": "subtle",
        "domain": "daily",
        "meaning_tr": "ince, ilk bakışta fark edilmeyen, hafif",
        "memory_tip": "Dikkatli bakınca anlaşılan ince ses, fark veya işarettir.",
        "example_en": "There was a subtle vibration in the cabin sidewall panel.",
        "example_tr": "Kabin yan duvar panelinde ilk anda zor fark edilen hafif bir titreşim vardı.",
    },
    {
        "key": "obstacle",
        "word": "obstacle",
        "domain": "daily",
        "meaning_tr": "engel, mani",
        "memory_tip": "Yolu veya ilerlemeyi kapatan fiziksel ya da soyut engeldir.",
        "example_en": "Keep the emergency exit path free of any obstacle.",
        "example_tr": "Acil çıkış yolunu her türlü engelden uzak tutun.",
    },
    {
        "key": "fragile",
        "word": "fragile",
        "domain": "daily",
        "meaning_tr": "kırılgan, hassas",
        "memory_tip": "Kargo paketlerinde ve ince plastik/cam parçalarda sıkça yazar.",
        "example_en": "Handle the reading light lens carefully because it is fragile.",
        "example_tr": "Kırılgan olduğu için okuma lambası merceğini dikkatle tutun.",
    },
    {
        "key": "gradually",
        "word": "gradually",
        "domain": "daily",
        "meaning_tr": "kademeli olarak, yavaş yavaş",
        "memory_tip": "Aniden değil, zamana yayılarak adım adım değişmektir.",
        "example_en": "The temperature will gradually rise toward the afternoon.",
        "example_tr": "Sıcaklık öğleden sonraya doğru kademeli olarak yükselecek.",
    },
    {
        "key": "adequate",
        "word": "adequate",
        "domain": "daily",
        "meaning_tr": "yeterli, ihtiyacı karşılayan",
        "memory_tip": "Eksik kalmayacak kadar yeterli miktarda veya seviyede olmaktır.",
        "example_en": "Make sure you get adequate sleep before an early morning shift.",
        "example_tr": "Sabah erken vardiyasından önce yeterli uyku aldığından emin ol.",
    },
    {
        "key": "versatile",
        "word": "versatile",
        "domain": "daily",
        "meaning_tr": "çok yönlü, çok amaçlı",
        "memory_tip": "Farklı işlere ve koşullara kolayca uyum sağlayan araç veya kişidir.",
        "example_en": "A lightweight windbreaker is a versatile choice for spring and autumn.",
        "example_tr": "Hafif bir rüzgarlık ilkbahar ve sonbahar için çok yönlü bir tercihtir.",
    },
    {
        "key": "outcome",
        "word": "outcome",
        "domain": "daily",
        "meaning_tr": "sonuç, netice",
        "memory_tip": "Bir sürecin veya çalışmanın sonunda ortaya çıkan neticedir.",
        "example_en": "Good preparation directly improves the outcome of your workday.",
        "example_tr": "İyi hazırlık iş gününün sonucunu doğrudan iyileştirir.",
    },
]


def _normalize_key(word):
    return re.sub(r"[^a-z0-9]+", "_", word.lower()).strip("_")


def load_vault_english_cards(markdown_text=None):
    """60_Öğrenme/İngilizce unuttuğum kelimeler.md tablosundaki satırları kart
    yapısına dönüştürür."""
    if markdown_text is None:
        note = vault_cache.get_note_by_path(VAULT_ENGLISH_WORDS_PATH)
        markdown_text = note["content"] if note else ""
    if not markdown_text:
        return []

    cards = []
    for raw_line in markdown_text.splitlines():
        line = raw_line.strip()
        m = _ROW_RE.match(line)
        if not m:
            continue
        cells = [c.strip() for c in m.group(1).split("|")]
        if len(cells) < 2:
            continue
        word, meaning = cells[0], cells[1]
        if not word or word.lower() in ("kelime", "word") or set(word) <= {"-", ":"}:
            continue
        key = _normalize_key(word)
        if not key:
            continue
        enrich = _VAULT_WORD_ENRICHMENTS.get(key, {})
        example_col = cells[2].strip() if len(cells) >= 3 and cells[2].strip() else ""
        cards.append({
            "key": key,
            "word": word.strip(),
            "domain": "vault",
            "meaning_tr": enrich.get("meaning_tr") or meaning.strip(),
            "memory_tip": enrich.get("memory_tip") or "Kendi kelime listene eklediğin özel tekrar kelimesi.",
            "example_en": example_col or enrich.get("example_en") or f"Try using the word {word.strip()} in a short sentence today.",
            "example_tr": enrich.get("example_tr") or "",
        })
    return cards


def get_merged_deck(vault_markdown=None):
    """Kullanıcının kendi kasasındaki kelimeler + çekirdek havuz birleşimi."""
    vault_cards = load_vault_english_cards(vault_markdown)
    seen = set()
    deck = []
    for c in vault_cards + SEED_CARDS:
        if c["key"] in seen:
            continue
        seen.add(c["key"])
        deck.append(c)
    return deck


def select_daily_learning_card(today=None, vault_markdown=None, record_shown=True):
    """Bugün için tek bir İngilizce öğrenme kartı seçer. Aynı gün içinde birden
    fazla kez çağrılırsa günün seçilmiş kartını değiştirmeden döner."""
    today_d = today or datetime.now(note_database.ISTANBUL_TZ).date()
    today_iso = today_d.isoformat()
    yesterday_iso = (today_d - timedelta(days=1)).isoformat()

    deck = get_merged_deck(vault_markdown)
    if not deck:
        return None
    deck_by_key = {c["key"]: c for c in deck}
    progress_map = note_database.get_learning_progress_map()

    # 1) Bugün zaten gösterilmiş kart varsa tutarlılık için aynı kartı döndür
    for key, row in progress_map.items():
        if row.get("last_shown_date") == today_iso and key in deck_by_key:
            return {**deck_by_key[key], "box": int(row.get("box") or 1)}

    # 2) Dün gösterilen kartın alanını bul (havacılık <-> günlük/vault dönüşümü için)
    yesterday_domain = None
    for row in progress_map.values():
        if row.get("last_shown_date") == yesterday_iso:
            yesterday_domain = row.get("domain")
            break

    due_cards = []
    unseen_cards = []
    future_cards = []

    for idx, card in enumerate(deck):
        prog = progress_map.get(card["key"])
        if not prog:
            unseen_cards.append((idx, card))
        else:
            next_rev = prog.get("next_review_date") or "1970-01-01"
            box = int(prog.get("box") or 1)
            if next_rev <= today_iso:
                due_cards.append((box, next_rev, idx, card))
            else:
                future_cards.append((next_rev, box, idx, card))

    def _domain_preferred(card):
        if card["domain"] == "vault":
            return True
        if yesterday_domain == "aviation":
            return card["domain"] != "aviation"
        if yesterday_domain in ("daily", "vault"):
            return card["domain"] == "aviation"
        return True

    chosen = None
    # Önce vadesi gelenler (tercih edilen alan > kutu numarası küçük olan)
    if due_cards:
        due_cards.sort(key=lambda t: (0 if _domain_preferred(t[3]) else 1, 0 if t[3]["domain"] == "vault" else 1, t[0], t[1], t[2]))
        chosen = due_cards[0][3]
    elif unseen_cards:
        unseen_cards.sort(key=lambda t: (0 if _domain_preferred(t[1]) else 1, 0 if t[1]["domain"] == "vault" else 1, t[0]))
        chosen = unseen_cards[0][1]
    elif future_cards:
        future_cards.sort(key=lambda t: (t[0], t[1], t[2]))
        chosen = future_cards[0][3]

    if not chosen:
        return None

    prog_row = None
    if record_shown:
        prog_row = note_database.record_learning_card_shown(
            chosen["key"], chosen["word"], chosen["domain"], today_iso,
        )
    box = int((prog_row or progress_map.get(chosen["key"]) or {}).get("box") or 1)
    return {**chosen, "box": box}


def format_learning_card_paragraph(card, for_tts=True):
    """Seçilen kartı masaüstü TTS veya Telegram metni için biçimlendirir."""
    if not card:
        return ""
    domain_label = (
        "havacılık teknik İngilizcesinden"
        if card["domain"] == "aviation"
        else ("kendi kelime notlarından" if card["domain"] == "vault" else "günlük İngilizceden")
    )
    tip = (card.get("memory_tip") or "").strip()
    ex_en = (card.get("example_en") or "").strip()
    ex_tr = (card.get("example_tr") or "").strip()

    if for_tts:
        # Çift tırnak içindeki İngilizce ifadeler lang_segmenter.py tarafından
        # otomatik olarak Kokoro İngilizce ses motoruna yönlendirilir.
        parts = [
            f'Günün İngilizce kartında {domain_label} bugünkü kelimen "{card["word"]}", '
            f'Türkçe karşılığı {card["meaning_tr"]}.'
        ]
        if tip:
            parts.append(tip)
        if ex_en:
            parts.append(f'Örnek cümle: "{ex_en}"')
        return " ".join(parts)

    lines = [
        f"🇬🇧 Günün İngilizce Kartı ({domain_label}):",
        f"• Kelime: \"{card['word']}\" — {card['meaning_tr']}",
    ]
    if tip:
        lines.append(f"• İpucu: {tip}")
    if ex_en:
        ex_line = f"• Örnek: \"{ex_en}\""
        if ex_tr:
            ex_line += f" ({ex_tr})"
        lines.append(ex_line)
    return "\n".join(lines)
