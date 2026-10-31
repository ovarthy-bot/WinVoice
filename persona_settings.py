# persona_settings.py
#
# Dashboard > Ayarlar sayfasındaki "Espri" ve "Arkadaş canlısı yaklaşım"
# yüzde kaydırıcılarını (settings.json üzerinden, bkz. tts_engine.py'deki
# get_setting/set_setting) okuyup bunları LLM prompt'larına (prompts.py)
# eklenecek hazır Türkçe talimat cümlelerine çevirir. Tek bir yerden
# yönetilir ki hem dashboard_ui.py (kaydırıcıları çizip kaydeder) hem de
# main.py / telegram_briefing.py (bu değerleri prompt'a enjekte eder) aynı
# ayar anahtarlarını kullansın.
#
# get_setting/set_setting doğrudan tts_engine'den alınır (worker_threads
# üzerinden DEĞİL): worker_threads içe aktarıldığında faster-whisper modelini
# anında yükler, bu da PyQt arayüzü gerekmeyen bağlamlarda (ör.
# telegram_briefing.py) gereksiz ve ağır bir bağımlılık olur.

from tts_engine import get_setting, set_setting

ESPRI_KEY = "persona_espri_pct"
ARKADASLIK_KEY = "persona_arkadas_pct"
DEFAULT_PCT = 50


def get_espri_pct():
    return get_setting(ESPRI_KEY, DEFAULT_PCT)


def set_espri_pct(value):
    set_setting(ESPRI_KEY, int(value))


def get_arkadaslik_pct():
    return get_setting(ARKADASLIK_KEY, DEFAULT_PCT)


def set_arkadaslik_pct(value):
    set_setting(ARKADASLIK_KEY, int(value))


def _espri_talimati(pct):
    if pct <= 20:
        return "Neredeyse hiç espri yapma; ciddi ve sade bir üslup kullan."
    if pct <= 40:
        return "Çok nadiren, sadece uygun olduğunda hafif bir espri yap."
    if pct <= 60:
        return "Ara sıra, ölçülü bir espri/şaka ekleyebilirsin."
    if pct <= 80:
        return "Sık sık hafif espirili, eğlenceli bir ton kullan."
    return "Çok esprili, şakacı ve eğlenceli bir üslup kullan; fırsat buldukça espri yap."


def _arkadaslik_talimati(pct):
    if pct <= 20:
        return "Resmi, mesafeli ve kısa bir üslup kullan."
    if pct <= 40:
        return "Biraz resmi ama kibar bir üslup kullan."
    if pct <= 60:
        return "Sıcak ama ölçülü, dengeli bir üslup kullan."
    if pct <= 80:
        return "Samimi, sıcak ve arkadaş canlısı bir üslup kullan."
    return "Çok samimi, yakın bir arkadaş gibi sıcak ve içten bir üslup kullan."


def current_persona_instructions():
    """Prompt şablonlarındaki {espri_talimati} / {arkadaslik_talimati} yer
    tutucularına geçilecek, güncel ayarlara karşılık gelen hazır Türkçe
    talimat çiftini döner."""
    return _espri_talimati(get_espri_pct()), _arkadaslik_talimati(get_arkadaslik_pct())
