# llm_settings.py
#
# Dashboard > Ayarlar sayfasındaki "Yapay Zeka Modeli" seçimini (settings.json
# üzerinden, bkz. tts_engine.py'deki get_setting/set_setting) okur/yazar.
# main.py açılışta buradan okuyarak OllamaLLM'i kurar; dashboard_ui.py ise
# seçim listesini çizip kullanıcı değiştirdiğinde buraya kaydeder.
#
# get_setting/set_setting doğrudan tts_engine'den alınır (worker_threads
# üzerinden DEĞİL) ki bu modül, faster-whisper/PyQt gerektirmeyen bağlamlarda
# (ör. telegram_briefing.py) de hafifçe içe aktarılabilsin.

from tts_engine import get_setting, set_setting

LLM_MODEL_KEY = "llm_model"
DEFAULT_LLM_MODEL = "gemma3:4b"

AVAILABLE_LLM_MODELS = [
    {"id": "gemma3:4b", "label": "Gemma 3 (4B)", "desc": "Hızlı yanıt — günlük kullanım için önerilir."},
    {"id": "qwen2.5:7b", "label": "Qwen 2.5 (7B)", "desc": "Daha güçlü ve tutarlı, ancak yanıt süresi daha uzun."},
]


def get_llm_model():
    return get_setting(LLM_MODEL_KEY, DEFAULT_LLM_MODEL)


def set_llm_model(model_id):
    set_setting(LLM_MODEL_KEY, model_id)
