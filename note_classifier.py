# note_classifier.py
#
# Telegram'dan gelen ham bir mesajı Ollama ile yapılandırılmış not(lar)a
# ayrıştırır (bkz. prompts.NOTE_CLASSIFICATION_PROMPT). PyQt5 ve Telegram'dan
# bağımsızdır; `llm` dışarıdan parametre olarak alınır (main.py'deki vault_
# knowledge.answer_from_vault(llm, ...) çağrısıyla aynı yaklaşım) ki hem
# dashboard'dan hem de ileride bağımsız bir script'ten çağrılabilsin.

import json
import re
from datetime import datetime, timedelta, timezone

from langchain_core.prompts import PromptTemplate

from prompts import NOTE_CLASSIFICATION_PROMPT

_prompt_template = PromptTemplate.from_template(NOTE_CLASSIFICATION_PROMPT)

# note_database.now_istanbul_iso() ile aynı saat dilimi (UTC+03:00); hatırlatma
# zamanları karşılaştırma için bu ofsetle saklanmalı.
_ISTANBUL_TZ = timezone(timedelta(hours=3))

VALID_CATEGORIES = ("appointment", "shopping", "reminder", "task", "general", "query")
VALID_CONFIDENCE = ("high", "medium", "low")
VALID_PRIORITIES = ("high", "normal", "low")

# Kategoriye özgü alanlar (bkz. prompts.NOTE_CLASSIFICATION_PROMPT KURAL 3) —
# note_database.py'deki alt tablo sütun adlarına eşlenir.
_CATEGORY_FIELD_MAP = {
    "appointment": {"tarih": "appt_date", "saat": "appt_time", "konum": "location",
                    "ilgili_kisi": "related_person"},
    "shopping": {"urun_adi": "product_name", "urun_miktari": "quantity"},
    "reminder": {"hatirlatma_zamani": "remind_at", "tekrar_sikligi": "repeat_frequency"},
    "task": {"son_tarih": "due_date", "baglam": "context"},
    "general": {},
    "query": {},
}

_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)
# "03.11.2026", "03.11.2026 12:00", "03.11.2026 tarihinde saat 12:00'ye" gibi
# Türkçe tarih biçimleri (gün.ay.yıl, isteğe bağlı saat).
_TR_DATETIME_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})(?:\D+?(\d{1,2})[:.](\d{2}))?")
# LLM'in istenen "YYYY-MM-DD" ya da "YYYY-MM-DDTHH:MM" biçimi.
_ISO_DATETIME_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?")


def _parse_date_parts(value):
    """Tarih metnini (year, month, day, hour, minute) olarak çözer; tanınmazsa
    None döner. Saat yoksa hour/minute None olur."""
    match = _TR_DATETIME_RE.search(value)
    if match:
        day, month, year, hour, minute = match.groups()
        return int(year), int(month), int(day), _to_int(hour), _to_int(minute)
    match = _ISO_DATETIME_RE.search(value)
    if match:
        year, month, day, hour, minute = match.groups()
        return int(year), int(month), int(day), _to_int(hour), _to_int(minute)
    return None


def _to_int(text):
    return int(text) if text is not None else None


def _normalize_date(value):
    """'03.11.2026' → '2026-11-03'. Çözülemeyen (ör. 'cuma') değerler olduğu
    gibi bırakılır."""
    parts = _parse_date_parts(value)
    if not parts:
        return value
    year, month, day, _, _ = parts
    try:
        return datetime(year, month, day).strftime("%Y-%m-%d")
    except ValueError:
        return value


def _normalize_remind_at(value):
    """Hatırlatma zamanını, note_database.get_due_reminders()'ın string
    karşılaştırmasıyla çalışması için 'YYYY-MM-DDTHH:MM:SS+03:00' biçimine
    çevirir. Saat yoksa 09:00 kabul edilir. Çözülemezse olduğu gibi döner —
    ham metin ("03.11.2026") karşılaştırmada hep 'geçmiş' sayılıp hatırlatmayı
    hemen tetikliyordu."""
    parts = _parse_date_parts(value)
    if not parts:
        return value
    year, month, day, hour, minute = parts
    try:
        moment = datetime(year, month, day, hour if hour is not None else 9,
                          minute or 0, tzinfo=_ISTANBUL_TZ)
    except ValueError:
        return value
    return moment.isoformat()


def _current_date_hint():
    return datetime.now(_ISTANBUL_TZ).strftime("%Y-%m-%d (%A)")


def _fallback_note(message_text):
    """Ayrıştırma başarısız olduğunda bile mesaj kaybolmasın diye (bkz.
    requirement: "hiçbir mesaj sessizce kaybolmamalı") düşük güvenli, genel
    kategorili tek bir not üretir."""
    title = message_text.strip().splitlines()[0][:60] if message_text.strip() else "Telegram Notu"
    return [{
        "kategori": "general",
        "güven": "low",
        "başlık": title or "Telegram Notu",
        "açıklama": message_text,
    }]


def _extract_json_array(raw_response):
    text = raw_response.strip()
    # Model bazen ```json ... ``` kod bloğuna sarabiliyor; önce onu soy.
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    match = _JSON_ARRAY_RE.search(text)
    return match.group(0) if match else text


def _normalize_item(item):
    """Modelin döndürdüğü ham JSON nesnesini note_database.insert_note()'un
    beklediği şekle getirir: kategori/güven doğrulanır (tanınmayan değerler
    güvenli varsayılana düşer), kategoriye özgü alanlar `extra` sözlüğüne
    toplanır."""
    if not isinstance(item, dict):
        return None

    category = str(item.get("kategori", "general")).strip().lower()
    if category not in VALID_CATEGORIES:
        category = "general"

    confidence = str(item.get("güven", item.get("guven", "low"))).strip().lower()
    if confidence not in VALID_CONFIDENCE:
        confidence = "low"

    priority = str(item.get("öncelik", item.get("oncelik", "normal"))).strip().lower()
    if priority not in VALID_PRIORITIES:
        priority = "normal"

    title = (item.get("başlık") or item.get("baslik") or "").strip() or "Telegram Notu"
    description = (item.get("açıklama") or item.get("aciklama") or "").strip() or None

    extra = {}
    for source_key, db_column in _CATEGORY_FIELD_MAP.get(category, {}).items():
        value = item.get(source_key)
        if value is not None and str(value).strip().lower() not in ("", "null", "none"):
            extra[db_column] = str(value).strip()

    if "appt_date" in extra:
        extra["appt_date"] = _normalize_date(extra["appt_date"])
    if "due_date" in extra:
        extra["due_date"] = _normalize_date(extra["due_date"])
    if "remind_at" in extra:
        extra["remind_at"] = _normalize_remind_at(extra["remind_at"])

    return {
        "category": category,
        "confidence": confidence,
        "priority": priority,
        "title": title,
        "description": description,
        "extra": extra,
    }


def classify_message(llm, message_text):
    """Ham Telegram mesajını sınıflandırıp, note_database.insert_note()'a
    doğrudan verilebilecek sözlüklerden oluşan bir liste döner. Ollama'dan
    beklenmeyen/bozuk bir yanıt gelirse ASLA exception fırlatmaz — mesajı tek,
    düşük-güvenli "general" bir nota düşürür (bkz. _fallback_note)."""
    if not message_text or not message_text.strip():
        return []

    prompt = _prompt_template.format(message_text=message_text, bugun=_current_date_hint())
    try:
        raw_response = llm.invoke(prompt)
    except Exception as e:
        print(f"⚠️ Not sınıflandırma (Ollama) hatası: {e}")
        return [n for n in (_normalize_item(i) for i in _fallback_note(message_text)) if n]

    try:
        json_text = _extract_json_array(raw_response)
        items = json.loads(json_text)
        if not isinstance(items, list) or not items:
            raise ValueError("Beklenen JSON dizisi dönmedi.")
    except Exception as e:
        print(f"⚠️ Not sınıflandırma JSON ayrıştırma hatası: {e} — ham yanıt genel nota düşürülüyor.")
        items = _fallback_note(message_text)

    normalized = [_normalize_item(item) for item in items]
    normalized = [n for n in normalized if n]
    return normalized or [n for n in (_normalize_item(i) for i in _fallback_note(message_text)) if n]
