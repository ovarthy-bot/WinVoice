# vault_knowledge.py
#
# Kişisel bilgi tabanını — hem HAKKIMDA Obsidian kasasını (vault_cache.py) hem de
# Telegram/Dashboard üzerinden yönetilen yerel SQLite veritabanını (notes.db /
# note_database.py) — birleşik bir anahtar kelime + kök (stem) aramasıyla indeksler.
# Kullanıcı notlarındaki veya veritabanındaki verilerle ilgili bir soru sorduğunda
# en ilgili kayıtları bulup LLM'e SADECE o kayıtların içeriğini vererek (RAG —
# retrieval augmented generation) cevap ürettirir; LLM kendi ezberinden/halüsinasyonla
# cevap üretmeye bırakılmaz.
#
# HAKKIMDA kasası ile Cloudflare D1'deki vault_notes tablosu ÇİFT YÖNLÜ
# senkronize (bkz. vault_sync_bidi.py); belgeler burada yerel önbellekten
# (vault_cache.py — cloud_sync.sync_vault_from_cloud tarafından açılışta
# doldurulur) okunur. Güvenlik: Şifrelerim.md ne push'ta ne pull'da hiçbir
# zaman senkronize edilmez (bkz. vault_sync_bidi.py EXCLUDE_FILENAMES /
# _is_excluded_path) — şifre ipuçları bu aramaya hiç dahil edilmez.

import math
import re
from datetime import date

import note_database
import vault_cache

TR_AYLAR = (
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
)

_DB_CATEGORY_LABELS = {
    "appointment": "Randevu",
    "shopping": "Alışveriş",
    "reminder": "Hatırlatma",
    "general": "Genel Not",
}

_TR_STOPWORDS = {
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
}

_WORD_RE = re.compile(r"\w+")
_FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)
_TAG_LINE_RE = re.compile(r"^\s*(#[\w/-]+\s*)+$", re.MULTILINE)
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
_ISO_DATE_PREFIX_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}:\d{2}))?")

MIN_MATCH_SCORE = 4.0  # IDF-ağırlıklı skor eşiği (bkz. search())

# "X'in üzerinden kaç gün geçti?" türü sorguları yakalamak için (bkz.
# answer_elapsed_days_from_vault). personal_context.py'deki ilkeyle aynı
# sebeple (gemma3:4b gibi küçük bir yerel modele tarih çıkarma/toplama işi
# bırakılmaz), bu sorgular genel answer_from_vault akışına değil, burada
# gün sayısının Python'da deterministik hesaplandığı özel bir akışa gider.
_ELAPSED_DAYS_KEYWORDS = [
    "kaç gün geçti", "kaç gün oldu", "kaç gündür", "ne kadar oldu",
    "ne kadar zaman geçti", "üzerinden kaç gün", "üzerinden ne kadar",
    "aradan kaç gün", "kaç gün önce",
]

_DATE_IN_CONTENT_RE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")

# "Kaç gün geçti" eşleşmesi için en az bu kadar örtüşen terim gerekir (başlık
# eşleşmesi +2 bonus katar — bkz. _term_overlap_score).
MIN_ELAPSED_OVERLAP_SCORE = 2

# Türkçe eklemeli bir dildir: "belgesine" / "belgesi" / "belge", "başvurum" /
# "başvuruda" / "başvuru", "banyosundaki" / "banyoda" / "banyo", "taksidi" /
# "taksit" gibi aynı kökten gelen kelimeler tek katmanlı basit soyma ile
# eşleşemez. En uzun ekler önce gelecek şekilde en fazla 3 geçişte soyulur ve
# ünlüyle başlayan bir ek soyulduğunda ünsüz yumuşaması (ğ->k, d->t, b->p, c->ç)
# geri çevrilir. Kalan kökün en az 3 harf (tek harfli dar ünlü eklerinde 4 harf)
# olması şarttır ki kısa kökler bozulmasın.
_MULTI_CHAR_SUFFIXES = (
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
)

_SINGLE_CHAR_SUFFIXES_MIN3 = ("a", "e")
_SINGLE_CHAR_SUFFIXES_MIN4 = ("ı", "i", "u", "ü")

_VOWELS = frozenset("aeıioöuü")
_SOFTENING_MAP = {"ğ": "k", "d": "t", "b": "p", "c": "ç"}

_NOT_FOUND_MARKERS = (
    "bilgi bulamadım",
    "bir şey bulamadım",
    "kayıt bulamadım",
)


def tr_lower(text: str) -> str:
    """Python'un standart str.lower() metodu Türkçe 'İ' harfini 'i\\u0307' (iki
    karakter) ve 'I' harfini 'i' yapar; bu da 'İptal'/'BİLGİSAYAR'/'ALIŞVERİŞ'
    gibi kelimelerde tüm alt-string ve token eşleşmelerini bozar."""
    if not text:
        return ""
    return text.replace("İ", "i").replace("I", "ı").lower().replace("\u0307", "")


def _tokenize(text):
    return _WORD_RE.findall(tr_lower(text))


def _unsoften_tail(stem):
    if len(stem) >= 4 and stem[-1] in _SOFTENING_MAP:
        return stem[:-1] + _SOFTENING_MAP[stem[-1]]
    return stem


def _stem(word):
    current = word
    stripped_vowel_initial = False

    for _ in range(3):
        matched = False
        for suf in _MULTI_CHAR_SUFFIXES:
            if current.endswith(suf) and len(current) - len(suf) >= 3:
                stripped_vowel_initial = suf[0] in _VOWELS
                current = current[: -len(suf)]
                if stripped_vowel_initial:
                    current = _unsoften_tail(current)
                matched = True
                break
        if matched:
            continue

        for suf in ("ma", "me"):
            if current.endswith(suf) and len(current) - 2 >= 4:
                current = current[:-2]
                matched = True
                break
        if matched:
            continue

        for suf in _SINGLE_CHAR_SUFFIXES_MIN4:
            if current.endswith(suf) and len(current) - 1 >= 4:
                current = _unsoften_tail(current[:-1])
                matched = True
                break
        if matched:
            continue

        for suf in _SINGLE_CHAR_SUFFIXES_MIN3:
            if current.endswith(suf) and len(current) - 1 >= 3:
                current = _unsoften_tail(current[:-1])
                matched = True
                break
        if not matched:
            break

    return current


def _meaningful_terms(text):
    # Her kelime için SADECE kökünü (orijinal halini değil) terime çevirir:
    # orijinal + kök ikisini birden eklemek, aynı tek kelimenin "iki farklı
    # terim" gibi sayılmasına yol açar ve search() içindeki "en az iki
    # farklı terim örtüşmesi" güvenlik kuralını yanlışlıkla atlatır.
    return {
        _stem(t) for t in _tokenize(text)
        if t not in _TR_STOPWORDS and len(t) > 1
    }


def _clean_content(raw_text):
    text = _FRONTMATTER_RE.sub("", raw_text, count=1)
    text = _WIKILINK_RE.sub(lambda m: m.group(2) or m.group(1), text)
    text = _TAG_LINE_RE.sub("", text)
    return text.strip()


def _title_from(cleaned_text, fallback):
    for line in cleaned_text.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def _format_iso_date_for_rag(raw_value):
    """notes.db'deki 'YYYY-MM-DD' veya 'YYYY-MM-DDTHH:MM...' tarihlerini hem
    GG.AA.YYYY hem de Türkçe 'G Ay YYYY' biçiminde döndürür. Böylece hem
    resolve_date_hint() hem _DATE_IN_CONTENT_RE hem de LLM tarihi doğru okur."""
    if not raw_value:
        return None
    val = str(raw_value).strip()
    if not val or val.lower() == "yok":
        return None
    m = _ISO_DATE_PREFIX_RE.match(val)
    if not m:
        return val
    yil, ay, gun = int(m.group(1)), int(m.group(2)), int(m.group(3))
    saat = m.group(4)
    if not (1 <= ay <= 12 and 1 <= gun <= 31):
        return val
    tr_tarih = f"{gun:02d}.{ay:02d}.{yil} ({gun} {TR_AYLAR[ay - 1]} {yil})"
    if saat and saat != "00:00":
        tr_tarih += f" saat {saat}"
    return tr_tarih


def _format_db_note_document(n):
    """notes.db satırını, RAG aramasına ve LLM okumasına uygun yapılandırılmış
    bir metin belgesine dönüştürür."""
    title = (n.get("title") or "").strip()
    desc = (n.get("description") or "").strip()

    # Eski belirsiz-mesaj birleştirme kalıntılarını (gerçek bilgi taşımayan
    # meta satırları) aramayı kirletmemesi için atla.
    if title == "Önceki mesajın açıklaması" and desc.startswith("Bu, şu önceki belirsiz mesajın açıklaması:"):
        return None

    cat = n.get("category") or "general"
    cat_label = _DB_CATEGORY_LABELS.get(cat, "Not")
    durum = "Tamamlandı" if n.get("completed") else "Aktif"

    lines = [f"Kategori: {cat_label} ({durum})"]
    if desc:
        lines.append(f"Açıklama: {desc}")
    if n.get("product_name"):
        urun = n["product_name"]
        if n.get("quantity"):
            urun += f" (Miktar: {n['quantity']})"
        lines.append(f"Alınacak Ürün: {urun}")
    if n.get("appt_date"):
        lines.append(f"Randevu Tarihi: {_format_iso_date_for_rag(n['appt_date'])}")
    if n.get("appt_time"):
        lines.append(f"Saat: {n['appt_time']}")
    if n.get("location"):
        lines.append(f"Konum: {n['location']}")
    if n.get("related_person"):
        lines.append(f"İlgili Kişi/Konu: {n['related_person']}")
    if n.get("remind_at") and str(n.get("remind_at")).lower() != "yok":
        lines.append(f"Hatırlatma Zamanı: {_format_iso_date_for_rag(n['remind_at'])}")
    if n.get("repeat_frequency") and str(n.get("repeat_frequency")).lower() != "yok":
        lines.append(f"Tekrar Sıklığı: {n['repeat_frequency']}")

    content = "\n".join(lines)
    display_title = title or f"{cat_label} Kaydı"
    title_terms = _meaningful_terms(display_title)
    return {
        "path": f"notes.db::note/{n.get('id')}",
        "title": display_title,
        "content": content,
        "title_terms": title_terms,
        "terms": title_terms | _meaningful_terms(content),
    }


def _load_documents():
    """Her çağrıda hem yerel kasa önbelleğini (vault_cache.py — HAKKIMDA) hem de
    yerel SQLite veritabanındaki (note_database.py — notes.db) notları birleşik
    olarak yükler."""
    docs = []
    try:
        vault_notes = vault_cache.get_all_notes()
    except Exception:
        vault_notes = []

    for note in vault_notes:
        title_terms = _meaningful_terms(note["title"])
        docs.append({
            "path": note["path"],
            "title": note["title"],
            "content": note["content"],
            "title_terms": title_terms,
            "terms": title_terms | _meaningful_terms(note["content"]),
        })

    try:
        db_notes = note_database.get_notes(category="all", include_completed=True)
    except Exception:
        db_notes = []

    for n in db_notes:
        doc = _format_db_note_document(n)
        if doc is not None:
            docs.append(doc)

    return docs


def search(query_text, top_k=3):
    """Sorguyla en çok anlamlı terim örtüşen notları (HAKKIMDA + notes.db),
    puana göre azalan sırada döner. Her sonuç {title, path, content, score}
    içerir.

    Skor, IDF (ters belge sıklığı) ağırlıklı: "hava", "bugün" gibi çoğu
    notta rastgele geçen genel kelimeler düşük puan alır; bir kişinin adı,
    ürün adı veya özel bir konu yüksek puan alır. Başlıkta geçen terimler
    ek olarak 3 katına çıkarılır."""
    query_terms = _meaningful_terms(query_text)
    if not query_terms:
        return []

    docs = _load_documents()
    n_docs = len(docs)
    if n_docs == 0:
        return []

    doc_freq = {}
    for doc in docs:
        for term in doc["terms"]:
            doc_freq[term] = doc_freq.get(term, 0) + 1

    def idf(term):
        df = doc_freq.get(term, 0)
        return math.log((n_docs - df + 0.5) / (df + 0.5) + 1.0)

    scored = []
    for doc in docs:
        overlap = query_terms & doc["terms"]
        if not overlap:
            continue
        title_overlap_check = query_terms & doc["title_terms"]
        if not title_overlap_check and len(overlap) < 2:
            # Başlıkla eşleşmeyen tek kelimelik örtüşmede terimin yeterince
            # ayırt edici (en fazla 2 belgede geçen özgül bir kelime) olması
            # istenir; "hava", "saat" gibi yaygın kelimeler tek başına elenir.
            if not any(doc_freq.get(t, 0) <= 2 for t in overlap):
                continue
        score = 0.0
        for term in overlap:
            weight = idf(term)
            if term in doc["title_terms"]:
                weight *= 3
            score += weight
        scored.append((score, doc))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        {"title": d["title"], "path": d["path"], "content": d["content"], "score": s}
        for s, d in scored[:top_k]
    ]


# Notlar kullanıcının kendi birinci şahıs sesiyle yazıldığından (bkz.
# VAULT_QA_PROMPT KURAL 2), LLM'den bunları ikinci şahsa çevirmesi istenir.
# gemma3:4b gibi küçük bir yerel model bu dönüşümde (prompt talimatına
# rağmen) ara sıra bazı kalıpları atlıyor — bu yüzden en sık kaçan birinci
# şahıs kalıpları deterministik bir son işlemle ikinci şahsa çevrilir.
_FIRST_TO_SECOND_PERSON_FIXUPS = [
    (r"\bbenim\b", "senin"),
    (r"\bbana\b", "sana"),
    (r"\bbeni\b", "seni"),
    (r"\bbende\b", "sende"),
    (r"\bbenden\b", "senden"),
    (r"\bben\b", "sen"),
    (r"\byanımda\b", "yanında"),
    (r"\byanıma\b", "yanına"),
    (r"\bkendim\b", "kendin"),
    (r"\bkendime\b", "kendine"),
    (r"\bkendimi\b", "kendini"),
    (r"\bsürecimde\b", "sürecinde"),
    (r"\bsürecime\b", "sürecine"),
]
_FIRST_TO_SECOND_PERSON_RE = [
    (re.compile(pattern, re.IGNORECASE), replacement)
    for pattern, replacement in _FIRST_TO_SECOND_PERSON_FIXUPS
]


def _soften_to_second_person(cevap):
    def _case_preserving_sub(match, replacement):
        matched = match.group(0)
        if matched[0].isupper():
            return replacement[0].upper() + replacement[1:]
        return replacement

    for compiled_re, replacement in _FIRST_TO_SECOND_PERSON_RE:
        cevap = compiled_re.sub(lambda m, r=replacement: _case_preserving_sub(m, r), cevap)
    return cevap


def is_not_found_answer(text: str) -> bool:
    low = tr_lower(text or "")
    return any(marker in low for marker in _NOT_FOUND_MARKERS)


def answer_from_vault(llm, user_text, qa_prompt_template, top_k=3, extra_search_terms=None):
    """En ilgili `top_k` kaydı (HAKKIMDA + notes.db) bulup SADECE onların
    içeriğine dayanarak LLM'den kısa bir cevap üretir. Hiçbir aday yoksa,
    en iyi eşleşme çok zayıfsa ya da LLM aday notlarda sorunun cevabının
    bulunmadığını bildirirse None döner — çağıran taraf bir sonraki katmana
    veya normal sohbet akışına devam etmeli."""
    search_text = user_text
    if extra_search_terms:
        search_text = f"{user_text} {extra_search_terms}"

    results = search(search_text, top_k=top_k)
    if not results or results[0]["score"] < MIN_MATCH_SCORE:
        return None

    blocks = []
    for item in results:
        content = item["content"]
        if len(content) > 1500:
            content = content[:1500]
        blocks.append(f"### {item['title']}\n{content}")
    notlar = "\n\n".join(blocks)

    prompt = qa_prompt_template.format(notlar=notlar, soru=user_text)
    cevap = llm.invoke(prompt).strip()
    if not cevap or is_not_found_answer(cevap):
        return None
    return _soften_to_second_person(cevap)


def _most_recent_past_date(content, bugun):
    """Not içeriğinde geçen GG.AA.YYYY tarihlerinden bugüne kalmış (bugün
    dahil) olanların en yakınını (en büyük/en son) döner; hiçbiri yoksa None."""
    gecmis_tarihler = []
    for m in _DATE_IN_CONTENT_RE.finditer(content):
        gun, ay, yil = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            aday = date(yil, ay, gun)
        except ValueError:
            continue
        if aday <= bugun:
            gecmis_tarihler.append(aday)
    return max(gecmis_tarihler) if gecmis_tarihler else None


def _term_overlap_score(query_terms, title, content):
    overlap = query_terms & (_meaningful_terms(title) | _meaningful_terms(content))
    if not overlap:
        return 0
    score = len(overlap)
    if query_terms & _meaningful_terms(title):
        score += 2
    return score


def answer_elapsed_days_from_vault(llm, user_text, elapsed_days_prompt_template, today=None):
    """Kullanıcı HAKKIMDA kasasındaki ya da notes.db'deki bir notta geçen bir
    olayın üzerinden kaç gün geçtiğini sorduğunda ("... başvurumun üzerinden
    kaç gün geçti?" gibi) deterministik bir cevap üretir."""
    user_text_lower = tr_lower(user_text)
    if not any(kw in user_text_lower for kw in _ELAPSED_DAYS_KEYWORDS):
        return None

    query_terms = _meaningful_terms(user_text)
    if not query_terms:
        return None

    # _load_documents() artık hem HAKKIMDA'yı hem de notes.db'yi (ISO tarihleri
    # GG.AA.YYYY biçimine çevrilmiş olarak) içerir.
    candidates = _load_documents()

    best, best_score = None, 0
    for cand in candidates:
        score = _term_overlap_score(query_terms, cand["title"], cand["content"])
        if score > best_score:
            best, best_score = cand, score

    if best is None or best_score < MIN_ELAPSED_OVERLAP_SCORE:
        return None

    bugun = today or date.today()
    hedef_tarih = _most_recent_past_date(best["content"], bugun)
    if hedef_tarih is None:
        return None

    gun_sayisi = (bugun - hedef_tarih).days
    tarih_metni = f"{hedef_tarih.day:02d}.{hedef_tarih.month:02d}.{hedef_tarih.year}"
    not_icerigi = best["content"]
    if len(not_icerigi) > 1500:
        not_icerigi = not_icerigi[:1500]

    prompt = elapsed_days_prompt_template.format(
        not_icerigi=not_icerigi, soru=user_text,
        gun_sayisi=gun_sayisi, tarih=tarih_metni,
    )
    cevap = llm.invoke(prompt).strip()
    if not cevap or is_not_found_answer(cevap):
        return None
    return _soften_to_second_person(cevap)
