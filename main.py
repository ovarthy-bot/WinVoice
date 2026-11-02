import ctypes
from ctypes import wintypes
import sys

_SINGLE_INSTANCE_MUTEX_NAME = "Local\\WinVoice_SingleInstance_Mutex"
_SHOW_DASHBOARD_EVENT_NAME = "Local\\WinVoice_ShowDashboard_Event"
_ERROR_ALREADY_EXISTS = 183
_EVENT_MODIFY_STATE = 0x0002
_WAIT_OBJECT_0 = 0x00000000

_INSTANCE_MUTEX_HANDLE = None
_SHOW_EVENT_HANDLE = None


def _acquire_single_instance_lock() -> bool:
    """Windows adlandırılmış mutex ile aynı anda yalnızca TEK bir WinVoice
    sürecinin mikrofonu ve Telegram bağlantısını açmasını garanti eder.
    İkinci bir kopya başlatılırsa mevcut sürecin Dashboard penceresini öne
    getirmesi için olay (event) sinyali gönderir ve False döner."""
    global _INSTANCE_MUTEX_HANDLE, _SHOW_EVENT_HANDLE
    if sys.platform != "win32":
        return True

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CreateEventW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateEventW.restype = wintypes.HANDLE
    kernel32.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.OpenEventW.restype = wintypes.HANDLE
    kernel32.SetEvent.argtypes = [wintypes.HANDLE]
    kernel32.SetEvent.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    mutex = kernel32.CreateMutexW(None, False, _SINGLE_INSTANCE_MUTEX_NAME)
    last_err = ctypes.get_last_error()
    if not mutex:
        return True

    if last_err == _ERROR_ALREADY_EXISTS:
        ev = kernel32.OpenEventW(_EVENT_MODIFY_STATE, False, _SHOW_DASHBOARD_EVENT_NAME)
        if ev:
            kernel32.SetEvent(ev)
            kernel32.CloseHandle(ev)
        kernel32.CloseHandle(mutex)
        return False

    _INSTANCE_MUTEX_HANDLE = mutex
    _SHOW_EVENT_HANDLE = kernel32.CreateEventW(None, False, False, _SHOW_DASHBOARD_EVENT_NAME)
    return True


if __name__ == "__main__":
    if not _acquire_single_instance_lock():
        if sys.stdout is not None:
            print("WinVoice zaten çalışıyor; mevcut pencere öne getirildi.")
        sys.exit(0)


class _StdoutRelay:
    """baslat.bat artık pythonw.exe ile, konsol penceresi açmadan çalışıyor —
    bu durumda gerçek bir stdout/stderr yoktur (ikisi de None olur) ve herhangi
    bir print() çağrısı uygulamayı anında çökertir. Bu yüzden worker_threads
    (ve PyQt5) İÇE AKTARILMADAN ÖNCE sys.stdout/stderr'i bu sahte akışla
    değiştiriyoruz. Dashboard penceresi henüz yokken yazılan satırları
    arabelleğe alır; pencere açılınca attach() ile GUI log paneline (bkz.
    dashboard_ui.LogRelay / DailyDashboardWindow.append_log_line) bağlanır ve
    o andan sonraki tüm satırları oraya akıtır."""

    def __init__(self, mirror_stream=None):
        self._buffer = ""
        self._pending_lines = []
        self._listener = None
        self._mirror = mirror_stream

    def write(self, text):
        if not text:
            return
        if self._mirror is not None:
            try:
                self._mirror.write(text)
                self._mirror.flush()
            except Exception:
                pass
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._handle_line(line)

    def _handle_line(self, line):
        if self._listener is not None:
            self._listener(line)
        else:
            self._pending_lines.append(line)

    def flush(self):
        if self._mirror is not None:
            try:
                self._mirror.flush()
            except Exception:
                pass

    def isatty(self):
        return False

    def attach(self, listener):
        self._listener = listener
        pending, self._pending_lines = self._pending_lines, []
        for line in pending:
            listener(line)


_stdout_relay = _StdoutRelay(mirror_stream=sys.__stdout__)
if __name__ == "__main__" or sys.stdout is None:
    sys.stdout = _stdout_relay
if __name__ == "__main__" or sys.stderr is None:
    sys.stderr = _stdout_relay

import re
import subprocess
# worker_threads, PyQt5'ten ÖNCE import edilmeli: faster-whisper'ın native
# kütüphaneleri (ctranslate2/onnxruntime) PyQt5 yüklendikten sonra Whisper
# modeli oluşturulursa Windows'ta DLL çakışmasından çöküyor (access violation).
from worker_threads import HotwordListener, AssistantWorker
from langchain_ollama.llms import OllamaLLM
from langchain_core.prompts import PromptTemplate
import speech_recognition as sr
import time
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer, QCoreApplication, Qt, QThread
from ui_manager import AssistantUI
from dashboard_ui import DailyDashboardWindow, LogRelay
from prompts import POWERSHELL_AND_CHAT_PROMPT, DAILY_BRIEFING_PROMPT, VAULT_QA_PROMPT, VAULT_ELAPSED_DAYS_PROMPT
from personal_context import answer_calendar_query, resolve_date_hint
from vault_knowledge import answer_from_vault, answer_elapsed_days_from_vault, tr_lower
from db_query_resolver import (
    answer_db_query,
    answer_from_db_digest,
    is_explicit_db_or_notes_query,
)
from persona_settings import current_persona_instructions
from llm_settings import get_llm_model, set_llm_model
import urllib.parse

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
vault_elapsed_days_prompt_template = PromptTemplate.from_template(VAULT_ELAPSED_DAYS_PROMPT)


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


def _contains_word(text, words):
    """Kelime listesindeki herhangi birinin TAM KELİME olarak `text` içinde
    geçip geçmediğini kontrol eder — basit `in` alt string kontrolünün
    AKSİNE. Örn. "aç" kelimesi "kaç" içinde alt string olarak geçtiği için
    (bkz. aşağıdaki comut_belirtisi kontrolü), "...üzerinden kaç gün
    geçti?" gibi SIRADAN bir soru yanlışlıkla bir komut (uygulama/dosya
    açma) belirtisi taşıyormuş gibi algılanıp not/takvim sorgularının
    (vault_knowledge/personal_context RAG) hiç denenmeden adım 5'teki genel
    LLM'e düşmesine yol açıyordu."""
    return any(re.search(r"\b" + re.escape(w) + r"\b", text) for w in words)


def processar_entrada(user_input: str) -> tuple[str, str]:
    """
    Kullanıcının girdisini değerlendirir:
    Dönüş: ("KOMUT", <powershell_komutu>) veya ("SOHBET", <sesli_cevap>)
    """
    user_input_lower = tr_lower(user_input).strip()

    # 0. Takvim / Kişisel Hatırlatma Sorguları (doğum günü, randevu, ödeme
    # tarihi vb.). LLM'e hiç gidilmez: tarih hesaplaması personal_context.py
    # içinde Python ile deterministik yapılır (hava & piyasa brifinginde
    # kullanılan aynı prensip — küçük yerel model tarih/sayı hesabına
    # güvenilmiyor).
    takvim_cevabi = answer_calendar_query(user_input_lower)
    if takvim_cevabi:
        return ("SOHBET", takvim_cevabi)

    comut_belirtisi = ["aç", "başlat", "çalıştır", "kapat", "sil", "oluştur", "kaydet"]
    has_command_intent = _contains_word(user_input_lower, comut_belirtisi)

    # 0.5. Yapılandırılmış Veritabanı (notes.db) Liste ve Özet Sorguları
    # ("Alışveriş listemde ne var?", "Bekleyen işlerim neler?", "Veritabanında
    # ne var?" vb.) — doğrudan SQLite üzerinden deterministik yanıtlanır.
    if not has_command_intent:
        db_liste_cevabi = answer_db_query(user_input)
        if db_liste_cevabi:
            return ("SOHBET", db_liste_cevabi)

    # 1. Doğrudan Tanımlı Uygulamalar
    for nome_app, caminho_app in APPS.items():
        if nome_app in user_input_lower and _contains_word(user_input_lower, ["aç", "başlat", "çalıştır"]):
            return ("KOMUT", f'Start-Process "{caminho_app}"')

    # 2. Doğrudan Tanımlı Web Siteleri
    for nome_site, url_site in WEBSITES.items():
        if nome_site in user_input_lower and _contains_word(user_input_lower, ["aç", "git", "sitesi"]):
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
    if _contains_word(user_input_lower, ["aç", "git", "sitesini"]):
        parts = user_input_lower.split()
        for part in parts:
            if "." in part and ("http" in part or "www" in part or part.endswith(".com") or part.endswith(".com.tr") or part.endswith(".org") or part.endswith(".net")):
                if not part.startswith("http"):
                    part = "https://" + part
                return ("KOMUT", f'Start-Process "{part}"')

    # 4.5. Birleşik Bilgi Tabanı (HAKKIMDA + notes.db) Sorguları — RAG: en
    # ilgili kaydı bulup SADECE o kaydın içeriğine dayanarak cevap üretir
    # (vault_knowledge.py & db_query_resolver.py).
    if not has_command_intent:
        # 4.4. "... üzerinden kaç gün geçti?" türü sorgular: ilgili notta
        # geçen tarih ile bugün arasındaki gün sayısı Python'da deterministik
        # hesaplanır (bkz. vault_knowledge.answer_elapsed_days_from_vault).
        elapsed_cevabi = answer_elapsed_days_from_vault(
            llm, user_input, vault_elapsed_days_prompt_template,
        )
        if elapsed_cevabi:
            return ("SOHBET", elapsed_cevabi)

        tarih_ipuclari = resolve_date_hint(user_input_lower)
        extra_search_terms = " ".join(tarih_ipuclari) if tarih_ipuclari else None
        vault_cevabi = answer_from_vault(
            llm, user_input, vault_qa_prompt_template, extra_search_terms=extra_search_terms,
        )
        if vault_cevabi:
            return ("SOHBET", vault_cevabi)

        # Anahtar kelime araması eşleşmediyse ama soru kişisel hafıza / görev /
        # veritabanı sorusuysa ("Hangi araçları deneyecektim?" gibi), aktif
        # notes.db özetinden (digest) yanıt ara.
        digest_cevabi = answer_from_db_digest(
            llm, user_input, vault_qa_prompt_template,
        )
        if digest_cevabi:
            return ("SOHBET", digest_cevabi)

        if is_explicit_db_or_notes_query(user_input):
            return ("SOHBET", "Bu konuda notlarında veya veritabanında bir bilgi bulamadım.")

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


class OllamaWaitThread(QThread):
    """baslat.bat'ta curl ile yapılan eski Ollama bekleme döngüsünün Python
    karşılığı. Artık bir konsol penceresi olmadığı için ilerlemeyi print()
    ile bildirir — bu satırlar _StdoutRelay/LogRelay üzerinden dashboard'un
    sol altındaki sistem günlüğü paneline akar."""

    def run(self):
        import socket
        print("Ollama servisinin hazır olması bekleniyor...")
        for _ in range(60):
            try:
                with socket.create_connection(("localhost", 11434), timeout=1):
                    print("Ollama hazır.")
                    return
            except OSError:
                time.sleep(1)
        print("[UYARI] Ollama 60 saniye içinde yanıt vermedi, WinVoice yine de çalışmaya devam ediyor.")
        print("        Ollama uygulamasının açık olduğundan emin olun.")


if __name__ == "__main__":
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
    hotword_listener_thread = HotwordListener(hotword="bilgisayar")

    daily_dashboard = DailyDashboardWindow(
        process_input_func=processar_entrada,
        execute_powershell_func=executar_comando_powershell_subprocess,
        pause_hotword_func=hotword_listener_thread.pause_and_wait,
        resume_hotword_func=hotword_listener_thread.resume,
        generate_briefing_func=generate_daily_briefing,
        set_listening_muted_func=hotword_listener_thread.set_muted,
        set_llm_model_func=set_active_llm_model,
        get_llm_func=lambda: llm,
    )

    # Artık bir konsol penceresi olmadığından (bkz. baslat.bat), uygulamanın
    # şimdiye kadar print() ile konsola yazdığı her şeyi (bu Ollama bekleme
    # mesajları dahil) dashboard'un sol alt köşesindeki sistem günlüğü paneline
    # yönlendiriyoruz. Önce slot bağlanır, SONRA relay'e attach edilir — aksi
    # halde attach ile ilk satırların akmaya başlaması arasındaki anda gelecek
    # satırlar kaybolabilir.
    _log_relay = LogRelay()
    _log_relay.line_received.connect(daily_dashboard.append_log_line)
    _stdout_relay.attach(_log_relay.emit_line)

    _ollama_wait_thread = OllamaWaitThread()
    _ollama_wait_thread.start()

    assistant_worker_thread = AssistantWorker(
        llm=llm,
        processar_entrada_func=processar_entrada,
        executar_powershell_func=executar_comando_powershell_subprocess
    )

    def on_hotword_detected():
        if assistant_worker_thread.isRunning():
            return
        hotword_listener_thread.pause_and_wait(timeout=2)
        assistant_worker_thread.start()

    def on_assistant_finished():
        assistant_ui.hide_window()
        hotword_listener_thread.statusUpdate.emit(f"Etkinleştirmek için '{hotword_listener_thread.hotword}' deyin.")
        hotword_listener_thread.resume()

    hotword_listener_thread.statusUpdate.connect(assistant_ui.update_status_message)
    hotword_listener_thread.hotwordDetected.connect(on_hotword_detected)

    assistant_worker_thread.assistantResponse.connect(assistant_ui.show_command_and_status)
    assistant_worker_thread.assistantResult.connect(assistant_ui.show_final_result)
    assistant_worker_thread.chatResponse.connect(assistant_ui.show_chat_message)
    assistant_worker_thread.errorOccurred.connect(assistant_ui.update_status_message)
    assistant_worker_thread.finished.connect(on_assistant_finished)

    # İkinci bir WinVoice kopyası açılmaya çalışıldığında gönderilen olayı dinle
    # ve mevcut Dashboard penceresini görünür kılıp öne getir.
    if _SHOW_EVENT_HANDLE:
        _k32_poll = ctypes.WinDLL("kernel32", use_last_error=True)
        _k32_poll.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        _k32_poll.WaitForSingleObject.restype = wintypes.DWORD

        def _check_show_dashboard_signal():
            if _k32_poll.WaitForSingleObject(_SHOW_EVENT_HANDLE, 0) == _WAIT_OBJECT_0:
                if daily_dashboard.isMinimized() or not daily_dashboard.isVisible():
                    daily_dashboard._apply_maximized_geometry()
                daily_dashboard.show()
                daily_dashboard.raise_()
                daily_dashboard.activateWindow()

        _single_instance_timer = QTimer()
        _single_instance_timer.timeout.connect(_check_show_dashboard_signal)
        _single_instance_timer.start(400)

    hotword_listener_thread.start()
    sys.exit(app_qt.exec_())
