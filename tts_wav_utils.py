# TTS motorları (ema_tts_engine.py, kokoro_tts_engine.py) arasında paylaşılan
# WAV yazımı ve bellekten ses çalma yardımcıları.
import io
import wave

import numpy as np


def to_wav(samples: np.ndarray, rate: int) -> bytes:
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def play_wav_bytes(wav_bytes: bytes) -> None:
    """WAV verisini disk dosyası oluşturmadan, bellekten çalar. Ses bitene
    kadar bloklar."""
    import winsound
    winsound.PlaySound(wav_bytes, winsound.SND_MEMORY)
