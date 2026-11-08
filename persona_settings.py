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
HITAP_KEY = "persona_hitap_sekli"
BRIEFING_LENGTH_KEY = "briefing_length_mode"
FINANCE_MODE_KEY = "briefing_finance_mode"
LEARNING_CARD_KEY = "briefing_learning_card_enabled"
SHIFT_OVERRIDE_KEY = "shift_manual_override"

DEFAULT_PCT = 50
VALID_HITAP_MODES = ("onur", "patron", "hitapsiz")
VALID_BRIEFING_LENGTHS = ("short", "balanced", "detailed")
VALID_FINANCE_MODES = ("significant", "always", "off")


def get_espri_pct():
    return get_setting(ESPRI_KEY, DEFAULT_PCT)


def set_espri_pct(value):
    set_setting(ESPRI_KEY, int(value))


def get_arkadaslik_pct():
    return get_setting(ARKADASLIK_KEY, DEFAULT_PCT)


def set_arkadaslik_pct(value):
    set_setting(ARKADASLIK_KEY, int(value))


def get_hitap_sekli():
    val = str(get_setting(HITAP_KEY, "onur") or "onur").strip().lower()
    return val if val in VALID_HITAP_MODES else "onur"


def set_hitap_sekli(mode):
    mode = str(mode or "onur").strip().lower()
    if mode not in VALID_HITAP_MODES:
        mode = "onur"
    set_setting(HITAP_KEY, mode)


def get_briefing_length_mode():
    val = str(get_setting(BRIEFING_LENGTH_KEY, "balanced") or "balanced").strip().lower()
    return val if val in VALID_BRIEFING_LENGTHS else "balanced"


def set_briefing_length_mode(mode):
    mode = str(mode or "balanced").strip().lower()
    if mode not in VALID_BRIEFING_LENGTHS:
        mode = "balanced"
    set_setting(BRIEFING_LENGTH_KEY, mode)


def get_briefing_finance_mode():
    val = str(get_setting(FINANCE_MODE_KEY, "significant") or "significant").strip().lower()
    return val if val in VALID_FINANCE_MODES else "significant"


def set_briefing_finance_mode(mode):
    mode = str(mode or "significant").strip().lower()
    if mode not in VALID_FINANCE_MODES:
        mode = "significant"
    set_setting(FINANCE_MODE_KEY, mode)


def get_learning_card_enabled():
    return bool(get_setting(LEARNING_CARD_KEY, True))


def set_learning_card_enabled(enabled):
    set_setting(LEARNING_CARD_KEY, bool(enabled))


def get_shift_override():
    return str(get_setting(SHIFT_OVERRIDE_KEY, "") or "").strip()


def set_shift_override(value):
    set_setting(SHIFT_OVERRIDE_KEY, str(value or "").strip())


def hitap_talimati(hitap_mode=None):
    mode = hitap_mode or get_hitap_sekli()
    if mode == "patron":
        return (
            'Kullanıcıya "Patron" diye hitap et; ancak bunu abartmadan metin boyunca '
            "en fazla bir veya iki kez kullan."
        )
    if mode == "hitapsiz":
        return (
            'Kullanıcıya "Patron", "Onur" gibi herhangi bir özel isim veya unvan '
            "kullanmadan doğrudan, sade ve doğal şekilde hitap et."
        )
    return (
        'Kullanıcıya ismiyle ("Onur") doğal şekilde hitap et (yalnızca selamlamada ve '
        'uygunsa kapanışta bir kez kullan; her cümlede tekrarlama ve asla "Patron" deme).'
    )


def briefing_length_instruction(length_mode=None):
    mode = length_mode or get_briefing_length_mode()
    if mode == "short":
        return (
            "KISA MOD: Haber özetlerini çok öz tut; toplamda yalnızca en kritik 2 haberi "
            "birer kısa cümleyle aktar."
        )
    if mode == "detailed":
        return (
            "DETAYLI MOD: Seçilmiş haberlerin her birini bir veya iki doyurucu cümleyle, "
            "bağlamını da vererek aktar (toplam 5-6 haber)."
        )
    return (
        "DENGELİ MOD: Seçilmiş haberlerden en önemli 3-4 gelişmeyi sıkmadan, net ve akıcı "
        "birer cümleyle özetle."
    )


def briefing_time_context(hour):
    """Saate göre brifing zaman kipini (selamlama + rol açıklaması + kapanış tonu) döner."""
    if 4 <= hour < 12:
        return {
            "slot": "morning",
            "greeting": "Günaydın",
            "role_desc": "Kullanıcıya güne başlarken kişisel sabah yaşam koordinasyonu brifingi hazırlıyorsun.",
            "closing_hint": "Sabah enerjisine uygun, bugünkü ana odağı destekleyen net ve sıcak tek bir kapanış cümlesi kur.",
        }
    if 12 <= hour < 18:
        return {
            "slot": "afternoon",
            "greeting": "Tünaydın",
            "role_desc": "Kullanıcıya gün ortası kişisel durum ve gündem koordinasyonu brifingi hazırlıyorsun.",
            "closing_hint": "Günün kalan yarısı için odaklayıcı ve kısa tek bir kapanış cümlesi kur.",
        }
    if 18 <= hour < 22:
        return {
            "slot": "evening",
            "greeting": "İyi akşamlar",
            "role_desc": "Kullanıcıya akşam değerlendirmesi ve yarına hazırlık brifingi hazırlıyorsun.",
            "closing_hint": "Günü toparlayan ve yarına sakin bir geçiş sağlayan tek bir kapanış cümlesi kur.",
        }
    return {
        "slot": "night",
        "greeting": "İyi geceler",
        "role_desc": "Kullanıcıya gece sonu kısa özet ve yarına hazırlık brifingi hazırlıyorsun.",
        "closing_hint": "Dinlenmeyi hatırlatan ve yarınki güne huzurlu bir başlangıç dileyen kısa tek bir kapanış cümlesi kur.",
    }


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
