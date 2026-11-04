# briefing_text.py
#
# Günlük Brifing metnini birleştiren saf Python fonksiyonları: hava/piyasa
# rakamlarını deterministik Türkçe ifadelere çevirir, kişisel hatırlatma
# paragrafını kurar ve LLM çıktısıyla bunları tek bir metinde birleştirir.
# PyQt bağımlılığı YOKTUR — hem dashboard_ui.py (DailyDashboardWindow) hem de
# arayüzsüz telegram_briefing.py aynı birleştirme mantığını kullanır.

import re

from tr_numbers import currency_to_words, percent_to_words, plain_number_to_words
from personal_context import build_reminder_block

_KNOWN_SECTION_HEADER_RE = re.compile(
    r"^\s*[\*_#]{0,3}\s*(giriş|hava\s*&\s*piyasa|hava\s+ve\s+piyasa|türkiye\s+gündemi|"
    r"dünya\s+turu|teknoloji|kapanış)\s*[:：]\s*[\*_#]{0,3}\s*",
    re.IGNORECASE,
)


def weather_phrases(weather_data):
    """Hava verisindeki rakamları LLM'e göndermeden önce, burada
    deterministik olarak hazır Türkçe ifadelere çevirir (bkz. tr_numbers.py)."""
    w = weather_data or {}
    phrases = {}
    if w.get("sicaklik_c") is not None:
        phrases["sicaklik"] = f"{plain_number_to_words(w['sicaklik_c'])} derece"
    if w.get("aciklama"):
        phrases["hava_durumu_aciklamasi"] = w["aciklama"]
    if w.get("nem_yuzde") is not None:
        phrases["nem_orani"] = percent_to_words(w["nem_yuzde"])
    if w.get("ruzgar_kmh") is not None:
        phrases["ruzgar_hizi"] = f"saatte {plain_number_to_words(w['ruzgar_kmh'])} kilometre"
    if w.get("bugun_max_c") is not None:
        phrases["bugun_en_yuksek_sicaklik"] = f"{plain_number_to_words(w['bugun_max_c'])} derece"
    if w.get("bugun_min_c") is not None:
        phrases["bugun_en_dusuk_sicaklik"] = f"{plain_number_to_words(w['bugun_min_c'])} derece"
    return phrases


def finance_phrases(finance_data):
    """Piyasa verisindeki rakamları LLM'e göndermeden önce, burada
    deterministik olarak hazır Türkçe ifadelere çevirir (bkz. tr_numbers.py)."""
    f = finance_data or {}
    phrases = {}
    if f.get("usd_try_satis") is not None:
        phrases["dolar_tl_satis_kuru"] = currency_to_words(f["usd_try_satis"])
    if f.get("bist100") is not None:
        phrases["bist100_endeksi"] = f"{plain_number_to_words(f['bist100'])} puan"
    if f.get("bist100_gunluk_yuzde_degisim") is not None:
        phrases["bist100_gunluk_degisim"] = percent_to_words(f["bist100_gunluk_yuzde_degisim"])
    if f.get("gram_altin_try") is not None:
        phrases["gram_altin_fiyati"] = currency_to_words(f["gram_altin_try"])
    if f.get("btc_try") is not None:
        phrases["bitcoin_tl_karsiligi"] = f"{plain_number_to_words(f['btc_try'])} lira"
    if f.get("btc_usd") is not None:
        phrases["bitcoin_dolar_karsiligi"] = f"{plain_number_to_words(f['btc_usd'])} dolar"
    return phrases


def _top_clothing(low, high):
    if low < 5:
        return "üstüne kalın bir mont ya da kaban, altına kazak"
    if high < 15:
        return "üstüne mont ya da kalın bir ceket, altına sweatshirt"
    if high < 22:
        return "üstüne ince bir ceket ya da uzun kollu gömlek"
    return "tişört ya da hafif bir gömlek"


def _bottom_clothing(high):
    if high >= 27:
        return "kısa pantolon ya da ince chino"
    return "uzun pantolon, chino ya da kot"


def build_outfit_sentence(weather_data):
    """Hava verisine göre erkek kullanıcı için 'bugün ne giysem' önerisini
    deterministik olarak kurar (kadın kıyafeti önerilmez). Sıcaklık yoksa
    boş string döner."""
    w = weather_data or {}
    high = w.get("bugun_max_c") if w.get("bugun_max_c") is not None else w.get("sicaklik_c")
    low = w.get("bugun_min_c") if w.get("bugun_min_c") is not None else w.get("sicaklik_c")
    if high is None or low is None:
        return ""

    description = (w.get("aciklama") or "").lower()
    wind = w.get("ruzgar_kmh") or 0

    items = [_top_clothing(low, high), _bottom_clothing(high)]
    if high - low >= 10:
        items.append("gün içinde hava çok değişecek, katmanlı giyin")
    if any(word in description for word in ("yağmur", "çisenti", "sağanak", "fırtına", "dolu")):
        items.append("yanına yağmurluk ya da su geçirmez bir mont al")
    elif "kar" in description:
        items.append("su geçirmez bot ve eldiven tercih et")
    if wind >= 30:
        items.append("rüzgar sert, rüzgarlık da işine yarar")
    if high >= 22 and ("açık" in description or "az bulutlu" in description):
        items.append("güneş gözlüğü de al")
    return "Bugün ne giysen; " + "; ".join(items) + "."


def build_weather_finance_paragraph(weather_data, finance_data):
    """Hava & Piyasa paragrafını LLM'e hiç yazdırmadan, tamamen deterministik
    olarak kurar. Testlerde küçük yerel modelin (gemma3:4b) hazır Türkçe
    rakam ifadelerini bile ara sıra yanlış kopyaladığı (ör. "yetmiş dokuz"
    yerine "seksen dokuz" yazması) görüldü; bu yüzden rakam içeren tek bölüm
    LLM'in eline hiç bırakılmıyor."""
    w = weather_phrases(weather_data)
    f = finance_phrases(finance_data)

    sentences = []
    if w.get("hava_durumu_aciklamasi") and w.get("sicaklik"):
        weather_sentence = (
            f"Hava durumuna gelirsek; İstanbul Çatalca'da hava "
            f"{w['hava_durumu_aciklamasi'].lower()}, sıcaklık {w['sicaklik']}"
        )
        if w.get("nem_orani"):
            weather_sentence += f", nem oranı {w['nem_orani']}"
        if w.get("ruzgar_hizi"):
            weather_sentence += f", rüzgar hızı {w['ruzgar_hizi']}"
        sentences.append(weather_sentence + ".")

    outfit_sentence = build_outfit_sentence(weather_data)
    if outfit_sentence:
        sentences.append(outfit_sentence)

    finance_bits = []
    if f.get("dolar_tl_satis_kuru"):
        finance_bits.append(f"dolar {f['dolar_tl_satis_kuru']} seviyesinde")
    if f.get("bist100_endeksi"):
        bist_bit = f"BIST 100 endeksi {f['bist100_endeksi']}"
        if f.get("bist100_gunluk_degisim"):
            bist_bit += f" ile günü {f['bist100_gunluk_degisim']} değişimle tamamlıyor"
        finance_bits.append(bist_bit)
    if f.get("gram_altin_fiyati"):
        finance_bits.append(f"gram altın {f['gram_altin_fiyati']}")
    if f.get("bitcoin_tl_karsiligi"):
        btc_bit = f"Bitcoin {f['bitcoin_tl_karsiligi']}"
        if f.get("bitcoin_dolar_karsiligi"):
            btc_bit += f" ({f['bitcoin_dolar_karsiligi']})"
        finance_bits.append(btc_bit)
    if finance_bits:
        sentences.append("Piyasalara bakacak olursak; " + ", ".join(finance_bits) + ".")

    return " ".join(sentences)


def build_personal_reminders_paragraph():
    """Doğum Günleri ve Randevular.md'deki yaklaşan (14 gün içindeki)
    kayıtları, hava & piyasa paragrafıyla aynı mantıkla tamamen deterministik
    olarak hazırlar; LLM'in eline hiç bırakılmaz."""
    block = build_reminder_block(within_days=14)
    if not block:
        return ""
    return "Kişisel hatırlatmalara gelirsek; " + block


def build_events_paragraph(events):
    """events_data.get_prioritized_events()'in döndürdüğü, zaten eşiğe göre
    filtrelenmiş ve tarihe göre sıralı listeyi hava/piyasa paragrafıyla aynı
    mantıkla tamamen deterministik bir cümleye çevirir — LLM'e hiç gitmez."""
    if not events:
        return ""
    bits = [e["title"] for e in events]
    return "Öne çıkan etkinliklere gelirsek; " + ", ".join(bits) + "."


def strip_known_section_headers(text):
    """LLM, talimata uymayıp ara sıra 'Türkiye Gündemi: ...' gibi bölüm
    başlıklarını (tek başına bir satır olarak ya da bir paragrafın başına
    yapıştırarak) çıktıya yazabiliyor; bunlar TTS'te garip durduğu için hem
    tek başına hem de bir paragrafın önüne eklenmiş hallerinde eleniyor."""
    cleaned_lines = []
    for line in text.split("\n"):
        line = _KNOWN_SECTION_HEADER_RE.sub("", line, count=1)
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


def assemble_final_briefing(llm_text, weather_data, finance_data, events=None):
    """LLM'in ürettiği Giriş/Türkiye/Dünya/Teknoloji/Kapanış metnine, LLM'e
    hiç gösterilmeyen Hava & Piyasa, Kişisel Hatırlatmalar ve Önemli
    Etkinlikler paragraflarını doğru sırada (Giriş'ten hemen sonra) ekleyip
    son brifing metnini döner."""
    text = strip_known_section_headers(llm_text)
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    weather_finance_paragraph = build_weather_finance_paragraph(weather_data, finance_data)
    personal_reminders_paragraph = build_personal_reminders_paragraph()
    events_paragraph = build_events_paragraph(events or [])

    insert_at = 1
    if paragraphs and weather_finance_paragraph:
        paragraphs.insert(insert_at, weather_finance_paragraph)
        insert_at += 1
    elif weather_finance_paragraph:
        paragraphs.append(weather_finance_paragraph)

    if paragraphs and personal_reminders_paragraph:
        paragraphs.insert(insert_at, personal_reminders_paragraph)
        insert_at += 1
    elif personal_reminders_paragraph:
        paragraphs.append(personal_reminders_paragraph)

    if paragraphs and events_paragraph:
        paragraphs.insert(insert_at, events_paragraph)
    elif events_paragraph:
        paragraphs.append(events_paragraph)

    return "\n\n".join(paragraphs)
