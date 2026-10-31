# vault_knowledge.py
#
# HAKKIMDA Obsidian kasasındaki kişisel notları (kişiler, iş, teknoloji,
# öğrenme, rutinler vb.) basit bir anahtar kelime aramasıyla indeksler.
# Kullanıcı "X kimdir", "Y ne zaman oldu" gibi bir şey sorduğunda en ilgili
# notu bulup LLM'e SADECE o notun içeriğini vererek (RAG — retrieval
# augmented generation) cevap ürettirir; LLM kendi ezberinden/halüsinasyonla
# cevap üretmeye bırakılmaz.
#
# Güvenlik: HAKKIMDA/50_Rutinler/Şifrelerim.md kasıtlı olarak HARİÇ tutulur
# (kullanıcı tercihi) — şifre ipuçları bu aramaya hiç dahil edilmez. Obsidian/
# MakeMD'nin kendi iç/ayar klasörleri de (.obsidian, .space, .makemd, .trash,
# _Sistem) hariç tutulur; onlar kişisel içerik değil, kasa yapılandırmasıdır.

import math
import os
import re

VAULT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "HAKKIMDA")

_EXCLUDE_DIR_NAMES = {".obsidian", ".space", ".makemd", ".trash", "_Sistem"}
_EXCLUDE_FILENAMES = {"şifrelerim.md"}  # karşılaştırma küçük harfe çevrilerek yapılır

_TR_STOPWORDS = {
    "ve", "ile", "bir", "bu", "şu", "o", "da", "de", "mi", "mı", "mu", "mü",
    "ne", "ki", "için", "gibi", "ama", "ya", "veya", "çok", "en", "var",
    "yok", "ben", "sen", "biz", "siz", "onlar", "benim", "senin", "bana",
    "beni", "nerede", "nasıl", "kaç", "kim", "hangi", "zaman", "notlarımda",
    "notumda", "takvimimde", "bilgi", "hakkında", "dair", "acaba", "mısın",
    "musun", "mısınız", "misin", "nedir", "kimdir", "kimdi", "oldu",
    "bugün", "dün", "yarın", "şimdi", "merhaba", "selam", "lütfen",
    "teşekkürler", "teşekkür", "naber", "nasılsın", "iyi", "kötü", "tamam",
    "evet", "hayır", "olur",
}

_WORD_RE = re.compile(r"\w+")
_FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)
_TAG_LINE_RE = re.compile(r"^\s*(#[\w/-]+\s*)+$", re.MULTILINE)
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")

MIN_MATCH_SCORE = 4.0  # IDF-ağırlıklı skor eşiği (bkz. search())

# Türkçe eklemeli bir dildir: "asker" / "askere" / "askerlik" gibi aynı
# kökten gelen kelimeler saf token eşleşmesinde birbirinden tamamen farklı
# görünür, bu yüzden kullanıcı doğal bir soru sorduğunda (örn. "Ben askere
# ne zaman gittim?") notun içeriğindeki "Askerlik" ile hiç örtüşmez. Tam
# bir morfolojik çözümleyici değil; sadece en sık görülen tek ek kalıbını
# (çoğul, hal, iyelik, "-lik/-lık" vb.) bir kez soyarak kelimeyi basit bir
# köke indirir. En uzun ek önce denenir, kalan köküm en az 3 harf olması
# şart (aksi halde kısa kelimeler anlamsızlaşır).
_SUFFIXES = (
    "leri", "ları",
    "lık", "lik", "luk", "lük",
    "dan", "den", "tan", "ten",
    "lar", "ler",
    "nın", "nin", "nun", "nün",
    "da", "de", "ta", "te",
    "ın", "in", "un", "ün",
    "ım", "im", "um", "üm",
    "ya", "ye",
    "a", "e",
)


def _tokenize(text):
    return [t.lower() for t in _WORD_RE.findall(text)]


def _stem(word):
    for suf in _SUFFIXES:
        if word.endswith(suf) and len(word) - len(suf) >= 3:
            return word[: -len(suf)]
    return word


def _meaningful_terms(text):
    # Her kelime için SADECE kökünü (orijinal halini değil) terime çevirir:
    # orijinal + kök ikisini birden eklemek, aynı tek kelimenin "iki farklı
    # terim" gibi sayılmasına yol açar ve search() içindeki "en az iki
    # farklı terim örtüşmesi" güvenlik kuralını (bkz. orada "hava" örneği)
    # yanlışlıkla atlatır. Kök her zaman tek ve tutarlı bir temsil olduğu
    # için bu riski taşımaz.
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


def _iter_vault_files():
    for root, dirs, files in os.walk(VAULT_DIR):
        dirs[:] = [d for d in dirs if d not in _EXCLUDE_DIR_NAMES]
        for fn in files:
            if not fn.lower().endswith(".md"):
                continue
            if "sync-conflict" in fn.lower():
                continue
            if fn.lower() in _EXCLUDE_FILENAMES:
                continue
            yield os.path.join(root, fn)


def _load_documents():
    """Her çağrıda vault'u yeniden okur (129 küçük dosya için önbellek
    gerektirmeyecek kadar hızlı) — böylece kullanıcı notu düzenler düzenlemez
    bir sonraki soru güncel içeriği görür."""
    docs = []
    for path in _iter_vault_files():
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = f.read()
        except Exception:
            continue
        cleaned = _clean_content(raw)
        if not cleaned:
            continue
        fallback_title = os.path.splitext(os.path.basename(path))[0]
        title = _title_from(cleaned, fallback_title)
        rel_path = os.path.relpath(path, VAULT_DIR)
        title_terms = _meaningful_terms(title)
        docs.append({
            "path": rel_path,
            "title": title,
            "content": cleaned,
            "title_terms": title_terms,
            "terms": title_terms | _meaningful_terms(cleaned),
        })
    return docs


def search(query_text, top_k=2):
    """Sorguyla en çok anlamlı terim örtüşen notları, puana göre azalan
    sırada döner. Her sonuç {title, path, content, score} içerir.

    Skor, IDF (ters belge sıklığı) ağırlıklı: "hava", "bugün" gibi çoğu
    notta rastgele geçen genel kelimeler düşük puan alır; bir kişinin adı,
    soyadı gibi az sayıda notta geçen ayırt edici terimler yüksek puan alır.
    Başlıkta geçen terimler ek olarak 3 katına çıkarılır (ör. not başlığı
    doğrudan kişinin/konunun adıysa güçlü bir sinyaldir)."""
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
            # Başlıkla eşleşmeyen, tek kelimelik bir örtüşme genelde riskli
            # (ör. "hava", "saat" gibi çoğu notta geçen genel bir kelime).
            # Ama bu kasada SADECE bu notta geçen (doc_freq == 1), yani bu
            # notla özdeşleşmiş özgül bir terim (ör. "askerlik") tek başına
            # yeterince güvenilir bir sinyaldir — bu yüzden idf'e değil,
            # doğrudan "kaç notta geçiyor" sayısına bakılır: "hava" birkaç
            # ilgisiz notta da geçtiği için (idf'i yanıltıcı şekilde yüksek
            # çıksa bile) burada güvenilmez, ama "askerlik" tek bir notta
            # geçtiği için güvenilir.
            if not any(doc_freq.get(t, 0) == 1 for t in overlap):
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


def answer_from_vault(llm, user_text, qa_prompt_template, top_k=2):
    """En ilgili `top_k` notu bulup SADECE onların içeriğine dayanarak
    LLM'den kısa bir cevap üretir. Anahtar kelime sıralaması bazen asıl
    cevabı barındıran notu ikinci sıraya koyabildiği için (ör. "araç" gibi
    genel bir kelime başka bir notta başlık eşleşmesi kazanabilir), tek not
    yerine birden fazla aday not birlikte LLM'e verilir. Hiçbir aday yoksa
    ya da en iyi eşleşme çok zayıfsa None döner — çağıran taraf normal
    sohbet akışına devam etmeli."""
    results = search(user_text, top_k=top_k)
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
    if not cevap:
        return None
    return cevap
