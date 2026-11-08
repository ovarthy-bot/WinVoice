# telegram_briefing.py
#
# WinVoice'un Dashboard'daki Günlük Brifing kartıyla AYNI metni üretip
# (bkz. briefing_data.py / briefing_text.py / prompts.DAILY_BRIEFING_PROMPT)
# Telegram'a gönderen, arayüzsüz (PyQt'siz) komut satırı betiği. Windows
# Görev Zamanlayıcı ile her gün saat 12:00'de otomatik çalıştırılmak üzere
# tasarlandı (bkz. README.md "Telegram Günlük Brifing" bölümü).
#
# main.py'deki dashboard akışından kasıtlı olarak bağımsızdır: worker_threads
# (faster-whisper), PyQt5, win32* gibi sesli asistan/arayüz bağımlılıklarının
# HİÇBİRİNİ içe aktarmaz — sadece brifing metnini üretip Telegram'a yazmak
# için gereken en hafif modülleri kullanır.

import logging
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from langchain_core.prompts import PromptTemplate
from langchain_ollama.llms import OllamaLLM

import briefing_data
import briefing_text
import events_data
import telegram_notify
import telegram_settings
from llm_settings import get_llm_model
from persona_settings import current_persona_instructions
from prompts import DAILY_BRIEFING_PROMPT
from tr_dates import format_tr_date

LOG_PATH = Path(__file__).resolve().parent / "telegram_briefing.log"
LOCATION = "İstanbul / Çatalca"
OLLAMA_URL = "http://localhost:11434"

_handlers = [logging.FileHandler(LOG_PATH, encoding="utf-8")]
if sys.stdout is not None:
    # Görev Zamanlayıcı pythonw.exe ile sessizce çalıştırdığında sys.stdout
    # None olur (konsol penceresi yok); bu durumda sadece log dosyasına yazılır.
    _handlers.append(logging.StreamHandler(sys.stdout))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=_handlers,
)
log = logging.getLogger("telegram_briefing")


def _ensure_ollama_running():
    """Ollama'ya hızlı bir bağlantı denemesi yapar; yanıt vermiyorsa (ör.
    bilgisayar yeniden başladıktan sonra arka plan servisi henüz açılmadıysa)
    `ollama serve`'i arka planda başlatmayı dener. Başlatma denemesi
    başarısız olsa bile akış devam eder — asıl bekleme/yeniden deneme işi
    generate_daily_briefing() içindedir (bkz. main.py'deki orijinal mantık)."""
    import urllib.request

    try:
        urllib.request.urlopen(OLLAMA_URL, timeout=3)
        return
    except Exception:
        pass

    log.warning("Ollama %s üzerinde yanıt vermiyor, 'ollama serve' başlatılmaya çalışılıyor...", OLLAMA_URL)
    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except Exception as e:
        log.warning("'ollama serve' başlatılamadı (muhtemelen zaten çalışıyor veya kurulu değil): %s", e)


def generate_daily_briefing(llm, prompt_template, location, time_str, news_items_text, now_dt=None):
    """main.py'deki generate_daily_briefing ile aynı mantık; Telegram yazılı
    okuma için rakamların doğal kalmasına izin verir."""
    import briefing_coordinator
    from persona_settings import (
        briefing_length_instruction,
        briefing_time_context,
        get_shift_override,
        hitap_talimati,
    )

    now_dt = now_dt or datetime.now()
    espri_talimati, arkadaslik_talimati = current_persona_instructions()
    t_ctx = briefing_time_context(now_dt.hour)
    coord = briefing_coordinator.collect_personal_coordination_data(today=now_dt.date())
    shift = briefing_coordinator.resolve_shift_for_date(now_dt.date(), get_shift_override())
    focus_hint = coord.get("primary_focus") or shift["label"]

    prompt = prompt_template.format(
        location=location,
        time=time_str,
        news_items_text=news_items_text,
        espri_talimati=espri_talimati,
        arkadaslik_talimati=arkadaslik_talimati,
        hitap_talimati=hitap_talimati(),
        uzunluk_talimati=briefing_length_instruction(),
        zaman_rol_tanimi=t_ctx["role_desc"],
        selamlama_ifadesi=t_ctx["greeting"],
        kapanis_ipucu=t_ctx["closing_hint"],
        odak_ipucu=focus_hint,
        rakam_kurali="Sayı ve yüzdeleri okunaklı ve doğal biçimde yazabilirsin.",
    )
    last_error = None
    for wait_seconds in (0, 3, 5, 8, 15, 20):
        if wait_seconds:
            time.sleep(wait_seconds)
        try:
            return llm.invoke(prompt).strip()
        except Exception as e:
            last_error = e
    raise last_error


def build_briefing_text():
    log.info("Hava, piyasa ve haber verisi toplanıyor...")
    try:
        weather_raw = briefing_data.fetch_weather()
        weather_data = briefing_data.extract_weather_for_briefing(weather_raw)
    except Exception as e:
        log.warning("Hava durumu alınamadı, brifing havasız devam edecek: %s", e)
        weather_data = {}

    try:
        finance_data = briefing_data.fetch_finance()
    except Exception as e:
        log.warning("Piyasa verisi alınamadı, brifing piyasasız devam edecek: %s", e)
        finance_data = {}

    try:
        news_items_text = briefing_data.fetch_news_items_text()
    except Exception as e:
        log.warning("Haber akışı alınamadı: %s", e)
        news_items_text = "(Haber akışı alınamadı.)"

    try:
        events = events_data.get_prioritized_events(
            min_priority=telegram_settings.get_briefing_events_min_priority(),
            tmdb_api_key=telegram_settings.get_tmdb_api_key(),
            football_api_key=telegram_settings.get_football_api_key(),
        )
    except Exception as e:
        log.warning("Önemli etkinlikler alınamadı, brifing bu bölümsüz devam edecek: %s", e)
        events = []

    _ensure_ollama_running()
    llm = OllamaLLM(model=get_llm_model())
    prompt_template = PromptTemplate.from_template(DAILY_BRIEFING_PROMPT)

    now = datetime.now()
    time_str = f"{format_tr_date(now)} {now.strftime('%H:%M')}"

    log.info("LLM (%s) ile brifing metni üretiliyor...", get_llm_model())
    llm_text = generate_daily_briefing(llm, prompt_template, LOCATION, time_str, news_items_text, now_dt=now)

    return briefing_text.assemble_final_briefing(
        llm_text, weather_data, finance_data, events, for_tts=False, today=now.date(), current_hour=now.hour,
    )


def main():
    if not telegram_settings.is_telegram_configured():
        log.error(
            "Telegram ayarlanmamış (telegram_bot_token / telegram_chat_id "
            "settings.json'da yok). Önce 'python telegram_briefing.py --setup' "
            "ile kurulumu tamamlayın."
        )
        sys.exit(1)

    try:
        final_text = build_briefing_text()
    except Exception as e:
        log.exception("Brifing üretilemedi: %s", e)
        try:
            telegram_notify.send_message(
                telegram_settings.get_telegram_bot_token(),
                telegram_settings.get_telegram_chat_id(),
                f"⚠️ Günlük brifing oluşturulamadı: {e}",
            )
        except Exception:
            log.exception("Hata bildirimi de Telegram'a gönderilemedi.")
        sys.exit(1)

    log.info("Brifing üretildi (%d karakter), Telegram'a gönderiliyor...", len(final_text))
    try:
        telegram_notify.send_message(
            telegram_settings.get_telegram_bot_token(),
            telegram_settings.get_telegram_chat_id(),
            final_text,
        )
    except telegram_notify.TelegramError as e:
        log.exception("Telegram'a gönderilemedi: %s", e)
        sys.exit(1)

    log.info("Brifing Telegram'a başarıyla gönderildi.")


def setup_wizard():
    """İlk kurulum: kullanıcıdan BotFather'dan aldığı bot token'ı ister,
    ardından getUpdates ile chat_id'yi otomatik bulup settings.json'a kaydeder."""
    print("--- WinVoice Telegram Brifing Kurulumu ---")
    print("1) Telegram'da @BotFather'a '/newbot' yazıp bir bot oluşturun ve verdiği TOKEN'ı kopyalayın.")
    print("2) Oluşturduğunuz bota Telegram'dan en az bir mesaj gönderin (ör. 'merhaba').")
    token = input("Bot token'ını buraya yapıştırın: ").strip()
    if not token:
        print("Token boş olamaz, kurulum durduruldu.")
        return

    print("getUpdates ile chat_id aranıyor...")
    try:
        updates = telegram_notify.get_updates(token)
    except telegram_notify.TelegramError as e:
        print(f"Telegram'a bağlanılamadı: {e}")
        return

    if not updates:
        print(
            "Hiç güncelleme bulunamadı. Bota en az bir mesaj gönderdiğinizden emin olup "
            "tekrar deneyin (ör. tekrar 'python telegram_briefing.py --setup')."
        )
        return

    chat_id = updates[-1]["message"]["chat"]["id"]
    telegram_settings.set_telegram_bot_token(token)
    telegram_settings.set_telegram_chat_id(chat_id)
    print(f"chat_id bulundu ve kaydedildi: {chat_id}")

    print("Test mesajı gönderiliyor...")
    telegram_notify.send_message(token, chat_id, "✅ WinVoice Telegram brifingi başarıyla kuruldu!")
    print("Kurulum tamamlandı. Artık 'python telegram_briefing.py' ile brifing gönderilebilir.")


if __name__ == "__main__":
    if "--setup" in sys.argv:
        setup_wizard()
    else:
        main()
