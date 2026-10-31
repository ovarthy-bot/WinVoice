import subprocess
# worker_threads, PyQt5'ten ÖNCE import edilmeli: faster-whisper'ın native
# kütüphaneleri (ctranslate2/onnxruntime) PyQt5 yüklendikten sonra Whisper
# modeli oluşturulursa Windows'ta DLL çakışmasından çöküyor (access violation).
from worker_threads import HotwordListener, AssistantWorker
from langchain_ollama.llms import OllamaLLM
from langchain_core.prompts import PromptTemplate
import speech_recognition as sr
import sys
import time
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer, QCoreApplication, Qt
from ui_manager import AssistantUI
from dashboard_ui import DailyDashboardWindow
from prompts import POWERSHELL_AND_CHAT_PROMPT, DAILY_BRIEFING_PROMPT, VAULT_QA_PROMPT
from personal_context import answer_calendar_query
from vault_knowledge import answer_from_vault
from persona_settings import current_persona_instructions
from llm_settings import get_llm_model, set_llm_model
import urllib.parse

# Windows'un ekran ölçekleme ayarını (ör. %150/%200) Qt'ye tanıtır.
# Bu olmadan Qt ekranı "ham" piksel çözünürlüğüyle görür ve arayüz
# elemanları diğer pencerelere göre çok küçük/orantısız görünür.
QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

app_qt = QApplication(sys.argv)
# Dashboard penceresi kapatılınca (ör. "Sesli Asistan" sayfasına geçmek
# yerine X'e basılırsa) tüm uygulamanın kapanmasını engeller; hotword
# dinleyici arka planda çalışmaya devam etmeli.
app_qt.setQuitOnLastWindowClosed(False)

assistant_ui = AssistantUI()

llm = OllamaLLM(model=get_llm_model())


def set_active_llm_model(model_id):
    """Dashboard > Ayarlar'da model seçimi değiştirildiğinde çağrılır: global
    `llm`'i yeni modelle yeniden kurar ve seçimi settings.json'a kaydeder.
    main.py'deki fonksiyonlar `llm`'e her çağrıda modül seviyesindeki global
    üzerinden eriştiği için (bkz. processar_entrada, generate_daily_briefing),
    bu yeniden atama anında tüm asistanın kullandığı modeli değiştirir."""
    global llm
    llm = OllamaLLM(model=model_id)
    set_llm_model(model_id)

APPS = {
    "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "tarayıcı": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "not defteri": "notepad.exe",
    "hesap makinesi": "calc.exe",
    "görev yöneticisi": "taskmgr.exe",
    "dosya gezgini": "explorer.exe",
    "ayarlar": "start ms-settings:"
}

WEBSITES = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "haberler": "https://www.haberler.com",
    "twitter": "https://x.com",
    "x": "https://x.com",
    "instagram": "https://www.instagram.com",
    "facebook": "https://www.facebook.com",
    "whatsapp": "https://web.whatsapp.com",
    "github": "https://github.com"
}

prompt_template = PromptTemplate.from_template(POWERSHELL_AND_CHAT_PROMPT)
briefing_prompt_template = PromptTemplate.from_template(DAILY_BRIEFING_PROMPT)
vault_qa_prompt_template = PromptTemplate.from_template(VAULT_QA_PROMPT)


def generate_daily_briefing(location: str, time_str: str, news_items_text: str) -> str:
    """Günlük Dashboard'daki "Günlük Brifing" kartı için Giriş/Türkiye/Dünya/
    Teknoloji/Kapanış bölümlerini üretir. Hava & Piyasa bölümü LLM'e hiç
    verilmez — dashboard_ui.py tarafında tamamen deterministik olarak
    kurulup bu metnin içine eklenir (küçük yerel modelin rakamları
    güvenilir şekilde seslendiremediği görüldüğü için)."""
    espri_talimati, arkadaslik_talimati = current_persona_instructions()
    prompt = briefing_prompt_template.format(
        location=location,
        time=time_str,
        news_items_text=news_items_text,
        espri_talimati=espri_talimati,
        arkadaslik_talimati=arkadaslik_talimati,
    )
    # Ollama uygulaması WinVoice ile (örn. baslat.bat ile) hemen hemen aynı
    # anda başlatılmış olabilir ve modeli yüklemesi birkaç saniye sürebilir.
    # Bu yüzden "bağlantı reddedildi" (WinError 10061) gibi geçici hatalarda
    # birkaç kez yeniden denenir; toplamda ~50 saniye Ollama'nın hazır
    # olmasına şans verilir.
    last_error = None
    for wait_seconds in (0, 3, 5, 8, 15, 20):
        if wait_seconds:
            time.sleep(wait_seconds)
        try:
            return llm.invoke(prompt).strip()
        except Exception as e:
            last_error = e
    raise last_error


def processar_entrada(user_input: str) -> tuple[str, str]:
    """
    Kullanıcının girdisini değerlendirir:
    Dönüş: ("KOMUT", <powershell_komutu>) veya ("SOHBET", <sesli_cevap>)
    """
    user_input_lower = user_input.lower().strip()

    # 0. Takvim / Kişisel Hatırlatma Sorguları (doğum günü, randevu, ödeme
    # tarihi vb.). LLM'e hiç gidilmez: tarih hesaplaması personal_context.py
    # içinde Python ile deterministik yapılır (hava & piyasa brifinginde
    # kullanılan aynı prensip — küçük yerel model tarih/sayı hesabına
    # güvenilmiyor).
    takvim_cevabi = answer_calendar_query(user_input_lower)
    if takvim_cevabi:
        return ("SOHBET", takvim_cevabi)

    # 1. Doğrudan Tanımlı Uygulamalar
    for nome_app, caminho_app in APPS.items():
        if nome_app in user_input_lower and any(w in user_input_lower for w in ["aç", "başlat", "çalıştır"]):
            return ("KOMUT", f'Start-Process "{caminho_app}"')

    # 2. Doğrudan Tanımlı Web Siteleri
    for nome_site, url_site in WEBSITES.items():
        if nome_site in user_input_lower and any(w in user_input_lower for w in ["aç", "git", "sitesi"]):
            return ("KOMUT", f'Start-Process "{url_site}"')

    # 3. Google'da Arama İstekleri
    search_keywords = ["google'da ara", "internette ara", "hakkında ara"]
    for keyword in search_keywords:
        if keyword in user_input_lower:
            search_query_raw = user_input_lower.split(keyword, 1)[1].strip()
            if not search_query_raw:
                search_query_raw = user_input_lower.split(keyword, 1)[0].strip()
            if search_query_raw:
                search_query_encoded = urllib.parse.quote_plus(search_query_raw)
                google_search_url = f"https://www.google.com/search?q={search_query_encoded}"
                return ("KOMUT", f'Start-Process "{google_search_url}"')

    # 4. Doğrudan URL Tespiti
    if any(w in user_input_lower for w in ["aç", "git", "sitesini"]):
        parts = user_input_lower.split()
        for part in parts:
            if "." in part and ("http" in part or "www" in part or part.endswith(".com") or part.endswith(".com.tr") or part.endswith(".org") or part.endswith(".net")):
                if not part.startswith("http"):
                    part = "https://" + part
                return ("KOMUT", f'Start-Process "{part}"')

    # 4.5. Kişisel Not Kasası (HAKKIMDA) Sorguları — RAG: en ilgili notu
    # bulup SADECE o notun içeriğine dayanarak cevap üretir (vault_knowledge.py).
    # "aç/başlat/çalıştır/kapat" gibi bir komut belirtisi taşıyan ifadeler
    # BURADA denenmez — APPS/WEBSITES sözlüğünde olmayan bir uygulama/dosya
    # komutu (ör. "notepad aç") yanlışlıkla ilgisiz bir nota eşleşip komut
    # üretiminin önüne geçmesin diye bu tür ifadeler doğrudan adım 5'teki
    # LLM KOMUT/SOHBET sınıflandırmasına bırakılır.
    comut_belirtisi = ["aç", "başlat", "çalıştır", "kapat", "sil", "oluştur", "kaydet"]
    if not any(v in user_input_lower for v in comut_belirtisi):
        vault_cevabi = answer_from_vault(llm, user_input, vault_qa_prompt_template)
        if vault_cevabi:
            return ("SOHBET", vault_cevabi)

    # 5. LLM ile Analiz ve Üretim (KOMUT veya SOHBET)
    espri_talimati, arkadaslik_talimati = current_persona_instructions()
    prompt = prompt_template.format(
        user_input=user_input,
        espri_talimati=espri_talimati,
        arkadaslik_talimati=arkadaslik_talimati,
    )
    raw_response = llm.invoke(prompt).strip()

    # Çıktı Ayrıştırma
    if "SOHBET:" in raw_response:
        msg = raw_response.split("SOHBET:", 1)[1].strip()
        msg = msg.split("###")[0].strip().strip('`"\'')
        return ("SOHBET", msg)
    elif "KOMUT:" in raw_response:
        cmd = raw_response.split("KOMUT:", 1)[1].strip()
        cmd = cmd.split("###")[0].strip()
        if cmd.startswith("```"):
            lines = cmd.splitlines()
            cmd = "\n".join([line for line in lines if not line.startswith("```")])
        return ("KOMUT", cmd.strip().strip('`'))
    else:
        ps_indicators = ["start-process", "new-item", "get-childitem", "invoke-item", "remove-item", "stop-process", "stop-computer", "restart-computer", "$env:"]
        if any(ind in raw_response.lower() for ind in ps_indicators):
            return ("KOMUT", raw_response)
        return ("SOHBET", raw_response)


def executar_comando_powershell_subprocess(comando: str) -> str:
    try:
        comandos = comando.strip().splitlines()
        saida_total = ""
        for cmd in comandos:
            resultado = subprocess.run(
                ["powershell", "-Command", cmd],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=30
            )
            saida_total += (resultado.stdout or '') + (resultado.stderr or '')
        return saida_total
    except Exception as e:
        return f"Çalıştırma hatası: {e}"


hotword_listener_thread = HotwordListener(hotword="bilgisayar")

daily_dashboard = DailyDashboardWindow(
    process_input_func=processar_entrada,
    execute_powershell_func=executar_comando_powershell_subprocess,
    pause_hotword_func=hotword_listener_thread.pause_and_wait,
    resume_hotword_func=hotword_listener_thread.resume,
    generate_briefing_func=generate_daily_briefing,
    set_listening_muted_func=hotword_listener_thread.set_muted,
    set_llm_model_func=set_active_llm_model,
)

assistant_worker_thread = AssistantWorker(
    llm=llm,
    processar_entrada_func=processar_entrada,
    executar_powershell_func=executar_comando_powershell_subprocess
)


def on_hotword_detected():
    hotword_listener_thread.pause()
    assistant_worker_thread.start()


def on_assistant_finished():
    assistant_ui.hide_window()
    hotword_listener_thread.statusUpdate.emit(f"Etkinleştirmek için '{hotword_listener_thread.hotword}' deyin.")
    hotword_listener_thread.resume()


if __name__ == "__main__":
    hotword_listener_thread.statusUpdate.connect(assistant_ui.update_status_message)
    hotword_listener_thread.hotwordDetected.connect(on_hotword_detected)

    assistant_worker_thread.assistantResponse.connect(assistant_ui.show_command_and_status)
    assistant_worker_thread.assistantResult.connect(assistant_ui.show_final_result)
    assistant_worker_thread.chatResponse.connect(assistant_ui.show_chat_message)
    assistant_worker_thread.errorOccurred.connect(assistant_ui.update_status_message)
    assistant_worker_thread.finished.connect(on_assistant_finished)

    hotword_listener_thread.start()
    sys.exit(app_qt.exec_())
