# db_query_resolver.py
#
# Yerel SQLite veritabanındaki (notes.db — note_database.py) yapılandırılmış
# kayıtlar (alışveriş listesi, yapılacak/bekleyen işler, son alınan notlar,
# veritabanı özeti) için deterministik sorgu çözücü ve kelime örtüşmesi
# bulunamadığında devreye giren hafif notes.db özet (digest) RAG katmanı.

import note_database
import vault_cache
from vault_knowledge import (
    _DB_CATEGORY_LABELS,
    _format_db_note_document,
    _meaningful_terms,
    _soften_to_second_person,
    _stem,
    is_not_found_answer,
    tr_lower,
)

_SHOPPING_PHRASES = (
    "alışveriş listem",
    "alışveriş listesi",
    "alışverişte ne",
    "alışveriş not",
    "alınacaklar",
    "alınacak ürün",
    "market listem",
    "market listesi",
    "neler alacaktım",
    "ne alacaktım",
    "neler satın al",
    "ne satın al",
    "satın alacaklarım",
    "satın alınacak",
)

_SHOPPING_GENERIC_WORDS = {
    "alışveriş", "liste", "listem", "listemde", "listesi", "listesinde",
    "alınacak", "alınacaklar", "ürün", "ürünler", "market", "satın",
    "alacaktım", "alacağım", "almak", "al", "eklediğim", "kayıtlı",
    "bekleyen", "aktif", "var", "yok", "neler", "ne", "şey", "not",
    "notum", "notlar", "notlarım",
}
_SHOPPING_GENERIC_STEMS = {_stem(w) for w in _SHOPPING_GENERIC_WORDS} | _SHOPPING_GENERIC_WORDS

_TODO_PHRASES = (
    "yapılacaklar",
    "yapılacak iş",
    "bekleyen iş",
    "bekleyen görev",
    "bekleyen not",
    "bekleyen hatırlatma",
    "tamamlanmamış not",
    "tamamlanmamış iş",
    "tamamlanmamış görev",
    "hatırlatma notlarım",
    "hatırlatma listem",
    "aktif görevlerim",
)

_TODO_GENERIC_WORDS = {
    "yapılacak", "yapılacaklar", "bekleyen", "tamamlanmamış", "aktif",
    "iş", "işler", "işlerim", "görev", "görevler", "görevlerim",
    "hatırlatma", "hatırlatmalar", "hatırlatmalarım", "liste", "listem",
    "listemde", "listesi", "not", "notlar", "notlarım", "notlarımda",
    "kayıtlı", "var", "neler", "ne", "şey",
}
_TODO_GENERIC_STEMS = {_stem(w) for w in _TODO_GENERIC_WORDS} | _TODO_GENERIC_WORDS

_DB_OVERVIEW_PHRASES = (
    "veritabanında",
    "veritabanındaki",
    "veri tabanında",
    "veri tabanındaki",
    "veritabanımda",
    "kaç tane not",
    "kaç notum var",
    "kaç not var",
    "toplam kaç not",
    "son aldığım not",
    "son eklediğim not",
    "son kaydettiğim not",
    "en son ne not",
    "son notlarım",
    "kayıtlı notlarım",
    "notlarımda neler var",
    "notlarımda ne var",
)

_OVERVIEW_GENERIC_WORDS = {
    "veritabanı", "veritabanında", "veritabanındaki", "veritabanımda",
    "veri", "tabanı", "tabanında", "tabanındaki", "veriler", "verilerim",
    "not", "notum", "notlar", "notlarım", "notlarımda", "notumda",
    "kayıt", "kayıtlı", "kayıtlar", "kayıtlarım", "kasa", "kasada", "kasamda",
    "sistem", "sistemde", "toplam", "kaç", "tane", "adet", "son", "en",
    "yeni", "eklediğim", "aldığım", "yazdığım", "kaydettiğim", "mevcut",
    "aktif", "tamamı", "hepsi", "neler", "ne", "var", "listele", "özetle",
    "göster", "söyle", "oku", "bana",
}
_OVERVIEW_GENERIC_STEMS = {_stem(w) for w in _OVERVIEW_GENERIC_WORDS} | _OVERVIEW_GENERIC_WORDS

_PERSONAL_MEMORY_CUES = (
    "notum", "notlarım", "notlarımda", "notumda", "not almış",
    "veritabanı", "veritabanında", "veritabanındaki", "veri tabanı",
    "kayıtlarımda", "kayıtlı", "listemde",
    "acaktım", "ecektim", "yapacaktım", "edecektim", "deneyecektim",
    "araştıracaktım", "kuracaktım", "alacaktım", "gidecektim",
    "yazmıştım", "kaydetmiştim", "eklemiştim", "başvurmuştum", "başvurum",
)

_EXPLICIT_DB_OR_NOTES_CUES = (
    "veritabanında", "veritabanındaki", "veri tabanında", "veri tabanındaki",
    "notlarımda", "notumda", "kayıtlarımda",
)


def _is_stale_meta_note(n) -> bool:
    title = (n.get("title") or "").strip()
    desc = (n.get("description") or "").strip()
    return (
        title == "Önceki mesajın açıklaması"
        and desc.startswith("Bu, şu önceki belirsiz mesajın açıklaması:")
    )


def _active_clean_notes(category="all"):
    try:
        rows = note_database.get_notes(category=category, include_completed=False)
    except Exception:
        return []
    return [r for r in rows if not _is_stale_meta_note(r)]


def _format_shopping_item(n) -> str:
    product = (n.get("product_name") or "").strip()
    qty = (n.get("quantity") or "").strip()
    title = (n.get("title") or "").strip()
    desc = (n.get("description") or "").strip()

    label = product or title or "Ürün"
    if qty:
        label = f"{label} ({qty})"
    if desc and tr_lower(desc) != tr_lower(label):
        return f"{label} — {desc}"
    return label


def _format_short_note(n) -> str:
    title = (n.get("title") or "").strip()
    desc = (n.get("description") or "").strip()
    return title or desc or "İsimsiz not"


def answer_db_query(user_text: str) -> str | None:
    """Alışveriş listesi, bekleyen işler veya genel veritabanı özeti gibi
    doğrudan yapılandırılmış liste sorgularını deterministik olarak yanıtlar.
    Sorgu özel bir konuya odaklanıyorsa (örn. 'veritabanında lisans belgesiyle
    ilgili ne var?') None döner ki birleşik RAG katmanı ilgili kaydı bulsun."""
    q = tr_lower(user_text).strip()
    if not q:
        return None

    # 1. Alışveriş listesi sorguları
    if any(p in q for p in _SHOPPING_PHRASES):
        items = _active_clean_notes(category="shopping")
        subject_terms = _meaningful_terms(q) - _SHOPPING_GENERIC_STEMS
        if subject_terms:
            matched = [
                it for it in items
                if subject_terms & _meaningful_terms(
                    f"{it.get('title', '')} {it.get('description', '')} {it.get('product_name', '')}"
                )
            ]
            if matched:
                detay = "; ".join(_format_shopping_item(it) for it in matched)
                return f"Alışveriş listenizde bu konuyla ilgili şu kayıt var: {detay}"
            # Alışveriş tablosunda bu özel konu yoksa serbest metin notlarında
            # (RAG) aranabilmesi için None dön.
            return None

        if not items:
            return "Alışveriş listenizde şu an alınacak bir ürün görünmüyor."
        if len(items) == 1:
            return f"Alışveriş listenizde 1 ürün var: {_format_shopping_item(items[0])}"
        sayim = "; ".join(_format_shopping_item(it) for it in items[:8])
        return f"Alışveriş listenizde {len(items)} ürün var: {sayim}"

    # 2. Yapılacaklar / bekleyen işler / hatırlatma notları listesi
    if any(p in q for p in _TODO_PHRASES):
        subject_terms = _meaningful_terms(q) - _TODO_GENERIC_STEMS
        if subject_terms:
            return None

        reminders = _active_clean_notes(category="reminder")
        # Doğum günlerini ve periyodik ödeme takvim kayıtlarını "yapılacak iş"
        # listesinden ayır; onlar zaten takvim/ödeme sorgularında yer alıyor.
        gorevler = [
            r for r in reminders
            if not any(
                etiket in tr_lower(r.get("title") or "")
                for etiket in ("doğum günü", "ödeme hatırlatması")
            )
        ]
        if not gorevler:
            return "Şu an bekleyen bir yapılacak iş veya hatırlatma notunuz görünmüyor."
        ozetler = ", ".join(_format_short_note(r) for r in gorevler[:8])
        ek = f" (ve {len(gorevler) - 8} kayıt daha)" if len(gorevler) > 8 else ""
        return f"Bekleyen {len(gorevler)} yapılacak iş ve hatırlatma notunuz var: {ozetler}.{ek}"

    # 3. Veritabanı özeti / kaç not var / son alınan notlar
    if any(p in q for p in _DB_OVERVIEW_PHRASES):
        subject_terms = _meaningful_terms(q) - _OVERVIEW_GENERIC_STEMS
        if subject_terms:
            # Örn. "Veritabanında lisans başvurusuyla ilgili ne var?" -> RAG'a bırak
            return None

        all_active = _active_clean_notes(category="all")
        try:
            vault_count = len(vault_cache.get_all_notes())
        except Exception:
            vault_count = 0

        if not all_active and vault_count == 0:
            return "Veritabanınızda ve kasanızda henüz kayıtlı bir not bulunmuyor."

        if any(k in q for k in ("son aldığım", "son eklediğim", "son kaydettiğim", "en son ne not", "son notlarım")):
            if not all_active:
                return "Yerel not veritabanınızda henüz aktif bir not bulunmuyor."
            son_bes = "; ".join(
                f"{_DB_CATEGORY_LABELS.get(n.get('category'), 'Not')}: {n.get('title') or n.get('description')}"
                for n in all_active[:5]
            )
            return f"Son eklediğiniz notlar şunlar: {son_bes}."

        counts = {}
        for n in all_active:
            cat = n.get("category") or "general"
            counts[cat] = counts.get(cat, 0) + 1

        parcalar = []
        for cat_key, label in (
            ("appointment", "randevu"),
            ("shopping", "alışveriş ürünü"),
            ("reminder", "hatırlatma"),
            ("general", "genel not"),
        ):
            if counts.get(cat_key):
                parcalar.append(f"{counts[cat_key]} {label}")

        dagilim = ", ".join(parcalar) if parcalar else "0 aktif kayıt"
        son_uc = "; ".join(
            f"{n.get('title') or n.get('description')}" for n in all_active[:3]
        )
        son_ek = f" Son eklenen kayıtlar: {son_uc}." if son_uc else ""
        return (
            f"Veritabanınızda {len(all_active)} aktif kayıt ({dagilim}) ve "
            f"kişisel bilgi kasanızda {vault_count} not bulunuyor.{son_ek}"
        )

    return None


def is_personal_memory_query(user_text: str) -> bool:
    q = tr_lower(user_text)
    return any(cue in q for cue in _PERSONAL_MEMORY_CUES)


def is_explicit_db_or_notes_query(user_text: str) -> bool:
    q = tr_lower(user_text)
    return any(cue in q for cue in _EXPLICIT_DB_OR_NOTES_CUES)


def answer_from_db_digest(
    llm,
    user_text: str,
    qa_prompt_template,
    max_notes: int = 35,
    force: bool = False,
) -> str | None:
    """Anahtar kelime araması (answer_from_vault) eşleşme bulamadığında, soru
    kişisel hafıza/görev/veritabanı sorusuysa ('Hangi araçları deneyecektim?'
    gibi) notes.db'deki aktif kayıtların kompakt özetini LLM'e vererek yanıt
    arar. İlgili kayıt yoksa None döner."""
    if not force and not is_personal_memory_query(user_text):
        return None

    active = _active_clean_notes(category="all")
    if not active:
        return None

    blocks = []
    for n in active[:max_notes]:
        doc = _format_db_note_document(n)
        if doc is not None:
            blocks.append(f"### {doc['title']}\n{doc['content']}")

    if not blocks:
        return None

    notlar = "\n\n".join(blocks)
    prompt = qa_prompt_template.format(notlar=notlar, soru=user_text)
    cevap = llm.invoke(prompt).strip()
    if not cevap or is_not_found_answer(cevap):
        return None
    return _soften_to_second_person(cevap)
