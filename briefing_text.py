# briefing_text.py
#
# Akıllı Günlük Brifing metnini birleştiren saf Python fonksiyonları:
# - Saatlik (çıkış / gün içi / dönüş) hava durumu ve vardiya uyumlu kıyafet/şemsiye rehberi
# - Koşullu piyasa filtresi (<%1,5 döviz/altın/BIST ve <%3,5 BTC ise tamamen atlanır)
# - Kişisel görev/takvim/alışveriş koordinasyonu + R1D vardiya hazırlığı + İngilizce kartı
# - Masaüstü sesli okuma (for_tts=True) ve Telegram yazılı özet (for_tts=False) çift kip desteği.

import re
from datetime import datetime

import briefing_coordinator
import learning_cards
import note_database
import persona_settings
from tr_numbers import currency_to_words, percent_to_words, plain_number_to_words

_KNOWN_SECTION_HEADER_RE = re.compile(
    r"^\s*[\*_#]{0,3}\s*(giriş|hava\s*&\s*piyasa|hava\s+ve\s+piyasa|seçilmiş\s+gündem|"
    r"havacılık|yapay\s+zeka|türkiye\s+gündemi|dünya\s+turu|teknoloji|kapanış)\s*[:：]\s*[\*_#]{0,3}\s*",
    re.IGNORECASE,
)

# Sakin günlerde piyasa bölümünü tamamen atlamak için eşik değerler
FX_GOLD_BIST_THRESHOLD_PCT = 1.5
BTC_THRESHOLD_PCT = 3.5

_RAIN_CODES = {51, 53, 55, 61, 63, 65, 80, 81, 82, 95, 96, 99}
_SNOW_CODES = {71, 73, 75}
_FOG_CODES = {45, 48}


# --------------------------------------------------------------------------- #
# Saatlik Hava Dilimi Analizi + Kıyafet / Şemsiye / Rüzgâr Rehberi
# --------------------------------------------------------------------------- #

def _shift_weather_windows(shift_code):
    """Aktif vardiyaya göre (çıkış, gün ortası, dönüş) saat aralıklarını döner."""
    if shift_code == "07-15":
        return [
            ("out", "sabah evden çıkarken", "Sabah çıkış (05-07)", range(5, 8)),
            ("mid", "öğle saatlerinde", "Gün içi (11-14)", range(11, 15)),
            ("ret", "akşamüstü dönerken", "Dönüş (16-18)", range(16, 19)),
        ]
    if shift_code == "15-23":
        return [
            ("out", "öğlen evden çıkarken", "Öğlen çıkış (12-14)", range(12, 15)),
            ("mid", "akşam saatlerinde", "Akşam (17-20)", range(17, 21)),
            ("ret", "gece dönerken", "Gece dönüş (23-00)", range(23, 26)),
        ]
    return [
        ("out", "sabah saatlerinde", "Sabah (07-10)", range(7, 11)),
        ("mid", "gün ortasında", "Öğle (12-16)", range(12, 17)),
        ("ret", "akşam saatlerinde", "Akşam (18-21)", range(18, 22)),
    ]


def _summarize_window(hourly_points, idx_range):
    pts = [p for p in (hourly_points or []) if p.get("hour_index") in idx_range and p.get("temp") is not None]
    if not pts:
        return None
    avg_temp = round(sum(p["temp"] for p in pts) / len(pts))
    apparent_vals = [p["apparent"] if p.get("apparent") is not None else p["temp"] for p in pts]
    avg_apparent = round(sum(apparent_vals) / len(apparent_vals))
    max_precip = max(int(p.get("precip_prob") or 0) for p in pts)
    max_gust = round(max(float(p.get("wind_gust") or 0) for p in pts))
    codes = [int(p.get("code") or 0) for p in pts]
    has_rain = any(c in _RAIN_CODES for c in codes) or max_precip >= 45
    has_snow = any(c in _SNOW_CODES for c in codes)
    has_fog = any(c in _FOG_CODES for c in codes)
    return {
        "temp": avg_temp,
        "apparent": avg_apparent,
        "max_precip": max_precip,
        "max_gust": max_gust,
        "has_rain": has_rain,
        "has_snow": has_snow,
        "has_fog": has_fog,
    }


def _top_clothing_advice(min_app, max_app):
    if min_app <= 4:
        return "kalın mont veya kabanla çık"
    if min_app <= 11:
        if max_app >= 18:
            return "sabah serinliği için ceket veya mont giy, öğlen ısınacağı için içine ince katman seç"
        return "mont veya kalın bir ceket tercih et"
    if max_app < 21:
        return "ince bir ceket veya uzun kollu katman yeterli olur"
    return "hafif gömlek veya tişörtle rahat edersin"


def build_smart_weather_paragraph(weather_data, shift_code="tatil", for_tts=True):
    """Saatlik tahmin verisiyle çıkış/gün içi/dönüş dilimlerini analiz edip
    eyleme dönük hazırlık ve giyim önerisi üretir."""
    w = weather_data or {}
    hourly = w.get("hourly") or []
    windows = _shift_weather_windows(shift_code)

    win_stats = []
    for key, spoken_lbl, tg_lbl, idx_range in windows:
        st = _summarize_window(hourly, idx_range)
        if st:
            win_stats.append({"key": key, "spoken_lbl": spoken_lbl, "tg_lbl": tg_lbl, **st})

    # Saatlik veri yoksa mevcut günlük/anlık veriye zarifçe düş
    if not win_stats:
        cur_t = w.get("sicaklik_c")
        desc = (w.get("aciklama") or "").strip()
        if cur_t is None:
            return ""
        high = round(w.get("bugun_max_c") if w.get("bugun_max_c") is not None else cur_t)
        low = round(w.get("bugun_min_c") if w.get("bugun_min_c") is not None else cur_t)
        advice = _top_clothing_advice(low, high)
        if for_tts:
            return (
                f"Hava durumuna gelirsek; Çatalca'da hava {desc.lower()}, "
                f"sıcaklık {plain_number_to_words(round(cur_t))} derece; {advice}."
            )
        return f"🌤️ Hava & Hazırlık:\n• Çatalca: {desc}, {round(cur_t)}°C (En düşük {low}°C / En yüksek {high}°C)\n• Öneri: {advice.capitalize()}."

    out_w = win_stats[0]
    mid_w = win_stats[1] if len(win_stats) > 1 else out_w
    ret_w = win_stats[-1]

    min_app = min(x["apparent"] for x in win_stats)
    max_app = max(x["apparent"] for x in win_stats)
    max_gust = max(x["max_gust"] for x in win_stats)
    rain_windows = [x for x in win_stats if x["has_rain"]]
    snow_windows = [x for x in win_stats if x["has_snow"]]
    fog_out = out_w["has_fog"]

    tips = [_top_clothing_advice(min_app, max_app)]
    if max_app - min_app >= 7 and "katman" not in tips[0]:
        tips.append("hissedilen sıcaklık gün içinde belirgin değişeceği için katmanlı giyin")

    if snow_windows:
        tips.append("kar beklentisi nedeniyle su geçirmez bot ve eldiven al")
    elif rain_windows:
        when_lbl = " ve ".join(x["spoken_lbl"] for x in rain_windows[:2])
        peak_p = max(x["max_precip"] for x in rain_windows)
        if for_tts:
            tips.append(
                f"{when_lbl} yağış ihtimali {percent_to_words(peak_p)} seviyesinde, yanına şemsiye veya yağmurluk al"
            )
        else:
            tips.append(f"{when_lbl} yağış ihtimali %{peak_p}, yanına şemsiye veya yağmurluk al")

    if max_gust >= 38:
        if for_tts:
            tips.append(
                f"rüzgar hamlesi saatte {plain_number_to_words(max_gust)} kilometreye çıkıyor, rüzgar kesici dış katman iyi olur"
            )
        else:
            tips.append(f"rüzgar hamlesi {max_gust} km/s, rüzgar kesici dış katman iyi olur")

    if fog_out:
        tips.append("çıkış saatinde sis beklendiği için yola birkaç dakika erken çıkmakta fayda var")

    desc = (w.get("aciklama") or "").lower()
    if for_tts:
        desc_part = f"{desc}, " if desc and desc != "bilinmiyor" else ""
        temp_flow = (
            f"Hava ve günlük hazırlığa gelirsek; Çatalca'da genel görünüm {desc_part}"
            f"{out_w['spoken_lbl']} hissedilen sıcaklık {plain_number_to_words(out_w['apparent'])} derece, "
            f"{mid_w['spoken_lbl']} {plain_number_to_words(mid_w['apparent'])} derece, "
            f"{ret_w['spoken_lbl']} ise {plain_number_to_words(ret_w['apparent'])} derece olacak."
        )
        advice_sentence = "Hazırlık olarak " + "; ".join(tips) + "."
        return f"{temp_flow} {advice_sentence}"

    win_summary = " | ".join(
        f"{x['tg_lbl']}: {x['apparent']}°C" + (f" (🌧️%{x['max_precip']})" if x["max_precip"] >= 30 else "")
        for x in win_stats
    )
    return (
        f"🌤️ Saatlik Hava & Kıyafet Rehberi:\n"
        f"• {win_summary}\n"
        f"• Hazırlık: {'; '.join(tips)}."
    )


# --------------------------------------------------------------------------- #
# Koşullu Piyasa Özeti (<%1,5 döviz/altın/BIST ve <%3,5 BTC ise tamamen atlanır)
# --------------------------------------------------------------------------- #

def build_conditional_finance_paragraph(finance_data, finance_mode=None, for_tts=True):
    """Piyasa verilerini kullanıcının seçtiği filtre kipine göre üretir.
    Varsayılan 'significant' modunda eşik altı sakin günlerde boş string döner."""
    mode = finance_mode or persona_settings.get_briefing_finance_mode()
    if mode == "off" or not finance_data:
        return ""

    f = finance_data
    usd_val = f.get("usd_try_satis")
    usd_pct = f.get("usd_try_gunluk_yuzde_degisim") or 0.0
    gold_val = f.get("gram_altin_try")
    gold_pct = f.get("gram_altin_gunluk_yuzde_degisim") or 0.0
    bist_val = f.get("bist100")
    bist_pct = f.get("bist100_gunluk_yuzde_degisim") or 0.0
    btc_usd = f.get("btc_usd")
    btc_pct = f.get("btc_gunluk_yuzde_degisim") or 0.0

    movers_tts = []
    movers_tg = []

    def _dir_word(pct):
        return "yükselişle" if pct > 0 else "düşüşle"

    def _sign_pct(pct):
        return f"+%{pct:.2f}" if pct > 0 else f"%{pct:.2f}"

    include_all = mode == "always"

    if usd_val is not None and (include_all or abs(usd_pct) >= FX_GOLD_BIST_THRESHOLD_PCT):
        if abs(usd_pct) >= 0.05:
            movers_tts.append(
                f"dolar {percent_to_words(abs(usd_pct))} {_dir_word(usd_pct)} {currency_to_words(usd_val)} seviyesinde"
            )
            movers_tg.append(f"USD/TRY: {usd_val:.2f} ₺ ({_sign_pct(usd_pct)})")
        else:
            movers_tts.append(f"dolar {currency_to_words(usd_val)} seviyesinde")
            movers_tg.append(f"USD/TRY: {usd_val:.2f} ₺")

    if gold_val is not None and (include_all or abs(gold_pct) >= FX_GOLD_BIST_THRESHOLD_PCT):
        if abs(gold_pct) >= 0.05:
            movers_tts.append(
                f"gram altın {percent_to_words(abs(gold_pct))} {_dir_word(gold_pct)} {currency_to_words(gold_val)}"
            )
            movers_tg.append(f"Gram Altın: {gold_val:.0f} ₺ ({_sign_pct(gold_pct)})")
        else:
            movers_tts.append(f"gram altın {currency_to_words(gold_val)}")
            movers_tg.append(f"Gram Altın: {gold_val:.0f} ₺")

    if bist_val is not None and (include_all or abs(bist_pct) >= FX_GOLD_BIST_THRESHOLD_PCT):
        movers_tts.append(
            f"BIST yüz endeksi {percent_to_words(abs(bist_pct))} {_dir_word(bist_pct)} {plain_number_to_words(round(bist_val))} puanda"
        )
        movers_tg.append(f"BIST 100: {bist_val:.0f} ({_sign_pct(bist_pct)})")

    if btc_usd is not None and (include_all or abs(btc_pct) >= BTC_THRESHOLD_PCT):
        movers_tts.append(
            f"Bitcoin {percent_to_words(abs(btc_pct))} {_dir_word(btc_pct)} {plain_number_to_words(round(btc_usd))} dolarda"
        )
        movers_tg.append(f"BTC: {round(btc_usd):,} USD ({_sign_pct(btc_pct)})".replace(",", "."))

    if not movers_tts:
        # Eşik altında hiçbir sert hareket yoksa bölümü tamamen atla
        return ""

    if for_tts:
        prefix = "Piyasalarda bugün dikkat çeken hareket var; " if mode == "significant" else "Piyasalara kısaca bakarsak; "
        return prefix + ", ".join(movers_tts) + "."

    header = "📈 Piyasa Hareketi:" if mode == "significant" else "📈 Piyasa Özeti:"
    return header + "\n• " + " | ".join(movers_tg)


# Geriye dönük uyumluluk için eski yardımcı imzaları koru
def build_weather_finance_paragraph(weather_data, finance_data, shift_code="tatil", for_tts=True):
    parts = []
    wx = build_smart_weather_paragraph(weather_data, shift_code=shift_code, for_tts=for_tts)
    if wx:
        parts.append(wx)
    fin = build_conditional_finance_paragraph(finance_data, for_tts=for_tts)
    if fin:
        parts.append(fin)
    return ("\n\n" if not for_tts else " ").join(parts)


def build_personal_reminders_paragraph(today=None, length_mode="balanced", for_tts=True):
    return briefing_coordinator.build_personal_coordination_paragraph(
        today=today, length_mode=length_mode, for_tts=for_tts,
    )


def build_events_paragraph(events, length_mode="balanced", for_tts=True):
    if not events:
        return ""
    cap = 1 if length_mode == "short" else (3 if length_mode == "detailed" else 2)
    seen = set()
    unique_titles = []
    for e in events:
        t = (e.get("title") or "").strip()
        if not t or t.lower() in seen:
            continue
        seen.add(t.lower())
        unique_titles.append(t)
        if len(unique_titles) >= cap:
            break
    if not unique_titles:
        return ""
    if for_tts:
        spoken_bits = [briefing_coordinator._digits_to_tr_words_in_text(t) for t in unique_titles]
        return "Yaklaşan önemli etkinliklerde " + ", ".join(spoken_bits) + " yer alıyor."
    return "🎟️ Öne Çıkan Etkinlikler:\n" + "\n".join(f"• {t}" for t in unique_titles)


def strip_known_section_headers(text):
    cleaned_lines = []
    for line in (text or "").split("\n"):
        line = _KNOWN_SECTION_HEADER_RE.sub("", line, count=1)
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


def assemble_final_briefing(
    llm_text,
    weather_data,
    finance_data,
    events=None,
    for_tts=True,
    today=None,
    current_hour=None,
):
    """LLM'in ürettiği Giriş + Seçilmiş Gündem + Kapanış iskeletine deterministik
    koordinasyon bloklarını doğru akış sırasıyla yerleştirir:
      1. Giriş (LLM)
      2. Kişisel Görev, Takvim ve Alışveriş Koordinatörü
      3. Vardiya & İş Günü Hazırlığı
      4. Saatlik Hava & Kıyafet Rehberi
      5. Koşullu Piyasa Hareketi (yalnızca eşik aşımında)
      6. Öne Çıkan Etkinlikler (varsa, max 1-2)
      7. Seçilmiş Kişisel Gündem (LLM)
      8. Günün İngilizce Öğrenme Kartı (açıksa)
      9. Haftalık Aktif Proje Odağı (yalnızca Pazartesi)
     10. Odaklı Kapanış (LLM)
    """
    now_dt = datetime.now(note_database.ISTANBUL_TZ)
    today_d = today or now_dt.date()
    hour = current_hour if current_hour is not None else now_dt.hour

    length_mode = persona_settings.get_briefing_length_mode()
    shift_override = persona_settings.get_shift_override()
    shift_info = briefing_coordinator.resolve_shift_for_date(today_d, shift_override)

    text = strip_known_section_headers(llm_text or "")
    llm_paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    greeting_p = llm_paragraphs[0] if llm_paragraphs else ""
    closing_p = llm_paragraphs[-1] if len(llm_paragraphs) >= 2 else ""
    news_paragraphs = llm_paragraphs[1:-1] if len(llm_paragraphs) >= 3 else (
        llm_paragraphs[1:] if len(llm_paragraphs) == 2 else []
    )
    # Eğer LLM iki paragraf döndürdüyse ikinci paragraf haber mi kapanış mı ayırt et
    if len(llm_paragraphs) == 2 and len(llm_paragraphs[1]) <= 180:
        news_paragraphs = []
    elif len(llm_paragraphs) == 2 and len(llm_paragraphs[1]) > 180:
        news_paragraphs = [llm_paragraphs[1]]
        closing_p = ""

    personal_p = briefing_coordinator.build_personal_coordination_paragraph(
        today=today_d, length_mode=length_mode, for_tts=for_tts,
    )
    workday_p = briefing_coordinator.build_workday_prep_paragraph(
        today=today_d,
        current_hour=hour,
        override_str=shift_override,
        length_mode=length_mode,
        for_tts=for_tts,
    )
    weather_p = build_smart_weather_paragraph(
        weather_data, shift_code=shift_info["code"], for_tts=for_tts,
    )
    finance_p = build_conditional_finance_paragraph(
        finance_data, for_tts=for_tts,
    )
    events_p = build_events_paragraph(
        events or [], length_mode=length_mode, for_tts=for_tts,
    )

    learning_p = ""
    if persona_settings.get_learning_card_enabled():
        card = learning_cards.select_daily_learning_card(today=today_d)
        if card:
            learning_p = learning_cards.format_learning_card_paragraph(card, for_tts=for_tts)

    weekly_proj_p = briefing_coordinator.build_weekly_project_paragraph(
        today=today_d, length_mode=length_mode, for_tts=for_tts,
    )

    final_blocks = []
    if greeting_p:
        final_blocks.append(greeting_p)
    for block in (personal_p, workday_p, weather_p, finance_p, events_p):
        if block:
            final_blocks.append(block)
    if news_paragraphs:
        if not for_tts:
            final_blocks.append("🗞️ Seçilmiş Gündem:\n" + "\n\n".join(news_paragraphs))
        else:
            final_blocks.extend(news_paragraphs)
    if learning_p:
        final_blocks.append(learning_p)
    if weekly_proj_p:
        final_blocks.append(weekly_proj_p)
    if closing_p:
        final_blocks.append(closing_p)

    return "\n\n".join(final_blocks)
