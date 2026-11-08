# Ahenk Cep (torch) Türkçe TTS motoru.
#
# Model: Ahenk Cep, Özgür Güler (ağırlıklar CC BY 4.0, çıkarım kodu
# Apache-2.0) - https://huggingface.co/ozgurguler/ahenk-cep-tr , kaynak proje
# https://github.com/ozguradmin/ahenk-turkish-tts . EMA Lightning (Canberk
# Aslan, Apache-2.0, bkz. ema_tts_engine.py) taban ağırlıklarından, büyük
# Ahenk modelinin (VoxCPM2 LoRA ince ayarı, 2B) f022 sesiyle damıtılmış
# küçük (8.6M parametre, CPU'da gerçek zamana yakın) bir öğrenci model.
#
# ema_tts_engine.py'nin tersine (saf onnxruntime) bu motor torch + resmi
# `ema-lightning` paketini ve modelle birlikte gelen resmi çıkarım kodunu
# (models/ahenk_cep/ahenk_cep.py, HF model deposundan olduğu gibi
# vendor'landı) kullanıyor; modelin kendi chunk/pause/decoder-pencere
# mantığını (EMA Lightning'in engine'i) yeniden yazmak yerine doğrudan
# çağırıyoruz.
#
# f022 sesi yapay/tasarlanmıştır, gerçek bir kişiye ait değildir (bkz.
# models/ahenk_cep/README.md ve LICENSE). Üretilen sesi yapay olarak
# etiketleyin (AB Yapay Zekâ Yasası md. 50).
import logging
import os
import sys
import threading

import tts_wav_utils

log = logging.getLogger(__name__)

MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "ahenk_cep")
STUDENT_PATH = os.path.join(MODEL_DIR, "student.pt")
DECODER_PATH = os.path.join(MODEL_DIR, "decoder.pt")
INFER_MODULE_PATH = os.path.join(MODEL_DIR, "ahenk_cep.py")

DEFAULT_STYLE = "neutral"


class AhenkCepTTS:
    def __init__(self):
        self.lock = threading.Lock()
        self.tts = None

    def available(self) -> bool:
        return all(os.path.exists(p) for p in (STUDENT_PATH, DECODER_PATH, INFER_MODULE_PATH))

    def _load(self):
        if self.tts is not None:
            return
        import torch
        # Alt süreç başına yeniden yükleniyor (bkz. tts_engine._speak_via_subprocess);
        # ema_tts_engine'deki onnxruntime intra_op_num_threads sınırlamasının
        # torch karşılığı. CPU'daki tüm çekirdekleri kullanmak ısınma
        # sonrası en iyi gerçek-zaman oranını veriyor (ölçüldü).
        torch.set_num_threads(max(1, os.cpu_count() or 4))

        if MODEL_DIR not in sys.path:
            sys.path.insert(0, MODEL_DIR)
        from ahenk_cep import AhenkCep

        self.tts = AhenkCep(STUDENT_PATH, DECODER_PATH)
        log.info("Türkçe ses (Ahenk Cep) yüklendi")

    def synthesize(self, text: str, speed: float = 1.0, style: str = DEFAULT_STYLE, seed: int = 0) -> bytes:
        """Verilen Türkçe metnin WAV sesini döner; metin modelin kendi trnorm
        ön ucuyla okunuş formuna çevrilir."""
        with self.lock:
            self._load()
            audio, rate = self.tts.say(text, style=style, speed=speed, seed=seed)
        return tts_wav_utils.to_wav(audio, rate)


ahenk_tts = AhenkCepTTS()


def speak(text: str, speed: float = 1.0) -> None:
    """Metni Ahenk Cep ile üretir ve bellekten çalar. Çağrı, ses bitene
    kadar bloklar."""
    wav_bytes = ahenk_tts.synthesize(text, speed=speed)
    tts_wav_utils.play_wav_bytes(wav_bytes)
