# Kokoro-82M (ONNX) İngilizce TTS motoru.
#
# Model: Kokoro-82M v1.0, hexgrad (Apache License 2.0) -
# https://huggingface.co/hexgrad/Kokoro-82M, ONNX dosyaları
# https://github.com/thewh1teagle/kokoro-onnx üzerinden (kokoro-onnx paketi,
# MIT). G2P (metin -> fonem) için kokoro-onnx, espeakng-loader (eSpeak NG,
# GPL-3.0-or-later) ve phonemizer (GPL-3.0) kullanıyor; bkz. requirements.txt.
#
# EMA Lightning (ema_tts_engine.py) ile aynı amaçla, ama cümle içindeki
# İngilizce parçalar için: tts_engine.py'nin _speak_once'ı, lang_segmenter ile
# ayrıştırdığı her İngilizce segment için bu motoru çağırır. Sabit tek ses
# (af_heart, en-us) kullanılır; EMA'daki gibi kullanıcıya görünen bir ses
# seçim ekranı yok.
import logging
import os
import threading

import tts_wav_utils

log = logging.getLogger(__name__)

MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "kokoro")
MODEL_PATH = os.path.join(MODEL_DIR, "kokoro-v1.0.int8.onnx")
VOICES_PATH = os.path.join(MODEL_DIR, "voices-v1.0.bin")
VOICE_ID = "af_heart"
LANG = "en-us"


class KokoroTTS:
    def __init__(self):
        self.lock = threading.Lock()
        self.kokoro = None

    def available(self) -> bool:
        return os.path.exists(MODEL_PATH) and os.path.exists(VOICES_PATH)

    def _load(self):
        if self.kokoro is not None:
            return
        from kokoro_onnx import Kokoro
        self.kokoro = Kokoro(MODEL_PATH, VOICES_PATH)
        log.info("İngilizce ses (Kokoro-82M, ONNX) yüklendi")

    def synthesize(self, text: str, speed: float = 1.0) -> bytes:
        """Verilen İngilizce metnin WAV sesini döner."""
        with self.lock:
            self._load()
            samples, rate = self.kokoro.create(text, voice=VOICE_ID, speed=speed, lang=LANG)
        return tts_wav_utils.to_wav(samples, rate)


kokoro_tts = KokoroTTS()


def speak(text: str, speed: float = 1.0) -> None:
    """Metni Kokoro ile üretir ve bellekten çalar. Çağrı, ses bitene kadar
    bloklar."""
    wav_bytes = kokoro_tts.synthesize(text, speed=speed)
    tts_wav_utils.play_wav_bytes(wav_bytes)
