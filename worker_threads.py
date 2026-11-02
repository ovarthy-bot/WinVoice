# faster-whisper (ctranslate2/onnxruntime) PyQt5'ten ÖNCE import edilip
# model burada oluşturulmalı: PyQt5 önce yüklenirse native DLL çakışması
# yüzünden Windows'ta uygulama çöküyor (access violation). Bu yüzden bu
# dosyadaki PyQt5 importu kasıtlı olarak faster-whisper'dan SONRA geliyor.
from faster_whisper import WhisperModel

# Sesi metne çevirme tamamen yerelde çalışır (internet/Google'a veri gitmez).
# Model ilk kullanımda bir kez indirilir (Hugging Face), sonrasında yerel
# önbellekten yüklenir. "small" modeli hız/Türkçe doğruluk dengesi için seçildi.
print("🧠 Yerel konuşma tanıma modeli (faster-whisper/small) yükleniyor...")
_whisper_model = WhisperModel("small", device="cpu", compute_type="int8")
print("✅ Yerel konuşma tanıma modeli hazır.")

from PyQt5.QtCore import QThread, pyqtSignal
import speech_recognition as sr
import re
import threading
import time
import os
import tempfile
import pythoncom

from tts_engine import (
    speak_text, speak_text_interruptible, list_turkish_voices,
    get_selected_voice_id, set_selected_voice_id, get_setting, set_setting,
)
from vault_knowledge import tr_lower

MIN_ENERGY_THRESHOLD = 150
MAX_ENERGY_THRESHOLD = 1000


def _clamp_recognizer_threshold(recognizer: sr.Recognizer) -> None:
    if recognizer.energy_threshold < MIN_ENERGY_THRESHOLD:
        recognizer.energy_threshold = MIN_ENERGY_THRESHOLD
    elif recognizer.energy_threshold > MAX_ENERGY_THRESHOLD:
        recognizer.energy_threshold = MAX_ENERGY_THRESHOLD


class LocalSpeechUnderstoodError(Exception):
    """Ses yakalandı ama yerel modelden anlamlı bir metin çıkmadı."""


def transcribe_audio(audio: sr.AudioData, language: str = "tr") -> str:
    """Mikrofonla yakalanan sesi, Google'a göndermeden, yerel faster-whisper
    modeliyle metne çevirir. Ses verisi geçici bir .wav dosyasına yazılır,
    işlem bitince dosya silinir."""
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
            tmp_file.write(audio.get_wav_data())
            tmp_path = tmp_file.name

        # vad_filter: sessizlik/gürültü klipleri Whisper'a hiç gitmeden elenir.
        # Bu olmadan Whisper, ses içermeyen kliplerde bile YouTube altyazısı
        # tarzı rastgele cümleler ("abone olmayı unutmayın" vb.) halüsinasyon
        # olarak üretebiliyor. threshold=0.35 ile alçak sesli tek kelimelik
        # "bilgisayar" / "evet" komutlarının yutulması engellenir.
        segments, _info = _whisper_model.transcribe(
            tmp_path,
            language=language,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=400, threshold=0.35),
        )
        text = "".join(segment.text for segment in segments).strip()

        if not text:
            raise LocalSpeechUnderstoodError("Ses anlaşılamadı.")
        return text
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


class HotwordListener(QThread):
    hotwordDetected = pyqtSignal(str)
    statusUpdate = pyqtSignal(str)

    def __init__(self, hotword="bilgisayar"):
        super().__init__()
        self.hotword = tr_lower(hotword).strip()
        self._hotword_compact = re.sub(r"\W+", "", self.hotword)
        self.recognizer = sr.Recognizer()
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.energy_threshold = 300
        self.recognizer.pause_threshold = 0.7
        try:
            default_mic_name = sr.Microphone.list_microphone_names()[sr.Microphone().device_index or 0]
        except Exception:
            default_mic_name = "bilinmiyor"
        print(f"🎙️ Kullanılan mikrofon: {default_mic_name}")
        print(f"🎙️ Tüm mikrofonlar: {sr.Microphone.list_microphone_names()}")
        self.mic = sr.Microphone()
        self._calibrated = False
        self._running = True
        self.paused = False
        # Dashboard'daki "Dinlemeyi Duraklat" düğmesiyle verilen KALICI
        # tercih. pause()/resume() Brifing ve ses testi gibi akışlar
        # tarafından da geçici olarak çağrılıyor; manually_muted True
        # olduğunda resume()'un bu geçici çağrıları kullanıcının kararını
        # ezmesini engelliyoruz (bkz. resume() ve set_muted()).
        self.manually_muted = False
        # Mikrofon o an KAPALIYKEN set, açıkken clear durumda. Bluetooth
        # kulaklığın mikrofonu dinlerken cihaz "Hands-Free" (HFP) moduna
        # geçip ses çıkışını bozabiliyor; pause_and_wait() bu event ile
        # gerçekten mikrofonun bırakıldığından emin oluyor (bkz. o metod).
        self._mic_idle_event = threading.Event()
        self._mic_idle_event.set()

    def pause(self):
        self.paused = True

    def set_muted(self, muted):
        """Dashboard'daki "Dinlemeyi Duraklat/Başlat" düğmesi bunu çağırır.
        pause()/resume()'dan farklı olarak kalıcıdır: Brifing okunurken
        veya Ayarlar'da ses testi yapılırken tetiklenen otomatik resume()
        çağrıları, kullanıcı burada susturmayı seçtiyse mikrofonu tekrar
        açmaz (bkz. resume())."""
        self.manually_muted = muted
        if muted:
            self.paused = True

    def resume(self):
        if not self.manually_muted:
            self.paused = False

    def pause_and_wait(self, timeout=10):
        """pause()'un senkron hâli: Bluetooth kulaklığın mikrofonu asıl
        olarak bırakmasını (HFP modundan çıkmasını) bekler. pause() sadece
        bir bayrak set ettiği için, o anda sürmekte olan
        recognizer.listen() çağrısı (4-10 saniyeye kadar) hemen kesilmiyor;
        bu yüzden hemen ardından başlayan TTS, mikrofon hâlâ açıkken aynı
        Bluetooth cihazda sese başlamaya çalışıp sessizce başarısız
        olabiliyor. Günlük Brifing ve Ayarlar'daki ses testi bu metodu
        kullanır (bkz. main.py)."""
        self.paused = True
        self._mic_idle_event.wait(timeout)

    def run(self):
        self.statusUpdate.emit(f"Etkinleştirmek için '{self.hotword}' deyin.")
        while self._running:
            if self.paused:
                self._mic_idle_event.set()
                time.sleep(0.25)
                continue
            self._mic_idle_event.clear()
            try:
                try:
                    with self.mic as source:
                        if not self._calibrated:
                            self.recognizer.adjust_for_ambient_noise(source, duration=0.8)
                            self._calibrated = True
                        _clamp_recognizer_threshold(self.recognizer)
                        if self.paused:
                            continue
                        print(f"👂 Dinleniyor... (enerji eşiği: {self.recognizer.energy_threshold:.0f})")
                        audio = self.recognizer.listen(source, timeout=4, phrase_time_limit=6)
                finally:
                    self._mic_idle_event.set()
                if self.paused:
                    continue
                print("🧠 Sözleriniz yerel olarak işleniyor (faster-whisper)...")
                frase = tr_lower(transcribe_audio(audio)).strip()
                frase_compact = re.sub(r"\W+", "", frase)
                print(f"🗣️ Hotword Kontrol: {frase}")
                if self.hotword in frase or (self._hotword_compact and self._hotword_compact in frase_compact):
                    self.hotwordDetected.emit(self.hotword)
                    self.statusUpdate.emit("Dinleniyor...")
                    time.sleep(0.3)
            except sr.WaitTimeoutError:
                _clamp_recognizer_threshold(self.recognizer)
                continue
            except LocalSpeechUnderstoodError:
                print("🤷 Ses yakalandı ama çözümlenemedi (anlaşılmadı).")
                continue
            except Exception as e:
                print(f"❌ Mikrofon hatası (yeniden başlatılıyor): {e}")
                self.statusUpdate.emit(f"Mikrofon yeniden bağlanıyor...")
                try:
                    self.mic = sr.Microphone()
                    self._calibrated = False
                except Exception:
                    pass
                time.sleep(1.5)

    def stop(self):
        self._running = False
        self.wait()


class AssistantWorker(QThread):
    commandRecognized = pyqtSignal(str)
    assistantResponse = pyqtSignal(str, str)
    assistantResult = pyqtSignal(str, str)
    chatResponse = pyqtSignal(str, str)  # (user_text, assistant_text)
    errorOccurred = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, llm, processar_entrada_func, executar_powershell_func):
        super().__init__()
        self.llm = llm
        self.processar_entrada = processar_entrada_func
        self.executar_comando_powershell = executar_powershell_func
        self.recognizer = sr.Recognizer()
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.energy_threshold = 300
        self.recognizer.pause_threshold = 0.8
        self.mic = sr.Microphone()

    def run(self):
        # COM motorunu bu iş parçacığında (QThread) başlat
        pythoncom.CoInitialize()
        try:
            falar = speak_text

            # Selamlama
            self.chatResponse.emit("", "Sizi dinliyorum...")
            falar("Sizi dinliyorum.")
            time.sleep(0.2)

            consecutive_silence = 0
            stream_errors = 0

            while True:
                try:
                    with self.mic as source:
                        _clamp_recognizer_threshold(self.recognizer)
                        self.chatResponse.emit("", "Dinleniyor...")
                        audio = self.recognizer.listen(source, timeout=7, phrase_time_limit=14)

                    self.chatResponse.emit("", "Sözleriniz yerel olarak işleniyor (faster-whisper)...")
                    raw_transcript = transcribe_audio(audio).strip()
                    user_text = tr_lower(raw_transcript).strip()
                    print(f"🗣️ Kullanıcı: {raw_transcript}")
                    consecutive_silence = 0
                    stream_errors = 0

                except sr.WaitTimeoutError:
                    consecutive_silence += 1
                    if consecutive_silence >= 1:
                        print("Zaman aşımı: Beklemeye dönülüyor.")
                        break
                    continue
                except LocalSpeechUnderstoodError:
                    self.chatResponse.emit("", "Sizi tam anlayamadım, tekrar eder misiniz?")
                    falar("Tam anlayamadım.")
                    time.sleep(0.2)
                    continue
                except Exception as e:
                    print(f"Ses tanıma / mikrofon hatası: {e}")
                    stream_errors += 1
                    if stream_errors <= 1:
                        try:
                            self.mic = sr.Microphone()
                            time.sleep(0.4)
                            continue
                        except Exception:
                            pass
                    break

                # Çıkış ifadeleri (noktalama temizlenmiş metin üzerinden)
                cleaned_exit = re.sub(r"[^\w\s]", "", user_text).strip()
                exit_phrases = ["çık", "çıkış", "kapat", "iptal", "vazgeç", "görüşürüz", "bay bay", "hoşça kal", "sus"]
                if any(cleaned_exit == ep or cleaned_exit.startswith(ep + " ") for ep in exit_phrases):
                    self.chatResponse.emit(raw_transcript, "Görüşmek üzere, iyi günler!")
                    falar("Görüşmek üzere.")
                    time.sleep(0.6)
                    break

                # Girdiyi Analiz Et (KOMUT mu SOHBET mi?)
                try:
                    tipo, resposta = self.processar_entrada(raw_transcript)
                except Exception as err:
                    print(f"Yanıt üretim hatası: {err}")
                    self.chatResponse.emit(raw_transcript, "Yanıt üretilirken bir hata oluştu, lütfen tekrar deneyin.")
                    falar("Bir hata oluştu, lütfen tekrar deneyin.")
                    continue

                # --- SİSTEM KOMUTU ---
                if tipo == "KOMUT":
                    comando_powershell = resposta
                    print(f"[+] Üretilen Komut: {comando_powershell}")
                    self.assistantResponse.emit("Bu komutu onaylıyor musunuz?", comando_powershell)
                    falar("Bu komutu çalıştırayım mı?")
                    time.sleep(0.2)

                    conf_text = ""
                    try:
                        with self.mic as source:
                            _clamp_recognizer_threshold(self.recognizer)
                            audio_conf = self.recognizer.listen(source, timeout=5, phrase_time_limit=4)
                        conf_text = tr_lower(transcribe_audio(audio_conf)).strip()
                        print(f"🗣️ Onay: {conf_text}")
                    except Exception:
                        conf_text = ""

                    if any(k in conf_text for k in ["evet", "tamam", "olur", "çalıştır", "yap", "onayla", "ok", "yes", "başlat"]):
                        self.assistantResponse.emit("Komut çalıştırılıyor...", comando_powershell)
                        resultado = self.executar_comando_powershell(comando_powershell)
                        falar("Komut çalıştırıldı.")
                        self.assistantResult.emit("Komut çalıştırıldı!", resultado)
                        time.sleep(2)
                    else:
                        self.assistantResult.emit("İşlem iptal edildi.", "")
                        falar("İşlem iptal edildi.")
                        time.sleep(1)
                    break

                # --- SOHBET / SORU ---
                elif tipo == "SOHBET":
                    print(f"[+] Sohbet Cevabı: {resposta}")
                    self.chatResponse.emit(raw_transcript, resposta)
                    falar(resposta)
                    time.sleep(0.3)
        finally:
            self.finished.emit()
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass
