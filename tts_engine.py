# Türkçe TTS (metin okuma) mantığı. Bu modül kasıtlı olarak faster-whisper ve
# PyQt5 bağımlılıklarını İÇERMEZ: her okuma çağrısı (seçili ses ne olursa
# olsun) ayrı bir alt süreçte çalıştırılıyor (bkz. _speak_via_subprocess) ve
# bu yüzden bu dosyanın `python tts_engine.py --speak-once ...` olarak
# hızlıca, bağımsız şekilde başlatılabilmesi gerekiyor.
import os
import sys
import json
import shutil
import subprocess
import time

import pyttsx3
import comtypes.client

# Kullanıcının Dashboard > Ayarlar sayfasından seçtiği TTS sesi gibi kalıcı
# ayarları tutan dosya. Proje genelinde tek bir ayar dosyası kullanılıyor.
SETTINGS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")

# Lej77'nin Piper SAPI motoru (bkz. _set_turkish_voice), kaç model dosyası
# bulunursa bulunsun Windows'a HER ZAMAN tek bir ses ("Lej77 - Piper -
# Multilingual") olarak görünür ve aynı dilde birden fazla .onnx modeli
# varsa aralarından birini kullanıcının kontrolü dışında, dosya sistemi
# sırasına göre seçer (motorun kaynak kodunda doğrulanmıştır). Bu yüzden
# Dashboard > Ayarlar'da Piper modelleri arasında gerçek bir seçim sunmak
# için, o an aktif olmayan modelleri bu "kütüphane" klasöründe bekletip,
# kullanıcı birini seçtiğinde sadece o modeli motorun okuduğu asıl
# `piper_models` klasörüne taşıyoruz. Hiçbir model dosyası silinmez.
PIPER_ENGINE_DIR = r"C:\Program Files\Lej77TextToSpeech"
PIPER_MODELS_DIR = os.path.join(PIPER_ENGINE_DIR, "piper_models")
PIPER_MODELS_LIBRARY_DIR = os.path.join(PIPER_ENGINE_DIR, "piper_models_library")
PIPER_VOICE_ID_PREFIX = "piper_model::"
PIPER_MODEL_FILE_SUFFIXES = (".onnx", ".onnx.json", ".voice.txt")

# EMA Lightning (bkz. ema_tts_engine.py): pyttsx3/SAPI'den bağımsız, yerel bir
# ONNX modeli olduğu için gerçek bir SAPI token'ı değil, diğer seslerle aynı
# {"id", "description"} biçiminde sabit bir giriş olarak listeye ekleniyor.
EMA_VOICE_ID = "ema_lightning"
EMA_VOICE_DESCRIPTION = "EMA Lightning - Türkçe (çevrimdışı, nöral)"

# Ahenk Cep (bkz. ahenk_tts_engine.py): EMA Lightning gibi SAPI'den bağımsız
# yerel bir model, aynı şekilde sabit {"id", "description"} girişi olarak
# listeleniyor.
AHENK_VOICE_ID = "ahenk_cep"
AHENK_VOICE_DESCRIPTION = "Ahenk Cep - Türkçe (çevrimdışı, nöral, f022 sesi)"


def _piper_model_label(stem):
    """'tr_TR-fahrettin-medium' -> 'Fahrettin'. Piper'ın dosya adı kuralı
    '<dil>-<konuşmacı>-<kalite>' şeklindedir."""
    parts = stem.split("-")
    speaker = parts[1] if len(parts) >= 2 else stem
    return speaker.capitalize()


def _list_piper_model_stems():
    """`piper_models` (aktif) ve `piper_models_library` (bekleyen)
    klasörlerindeki tüm Piper modellerinin dosya adı köklerini (uzantısız)
    döner, böylece hangisi o an aktif olursa olsun hepsi listelenebilir."""
    stems = set()
    for folder in (PIPER_MODELS_DIR, PIPER_MODELS_LIBRARY_DIR):
        try:
            for name in os.listdir(folder):
                if name.endswith(".onnx"):
                    stems.add(name[: -len(".onnx")])
        except Exception:
            continue
    return sorted(stems)


def _activate_piper_model(stem):
    """Seçilen Piper modelinin dosyalarını `piper_models_library`'den asıl
    `piper_models` klasörüne taşır; o klasörde o an duran başka bir Piper
    modeli varsa önce onu library'ye geri taşır. Böylece motor her zaman
    tam olarak istenen modeli bulur, ama hiçbir dosya silinmez."""
    try:
        os.makedirs(PIPER_MODELS_LIBRARY_DIR, exist_ok=True)

        active_onnx = os.path.join(PIPER_MODELS_DIR, stem + ".onnx")
        if os.path.exists(active_onnx):
            return  # İstenen model zaten aktif klasörde.

        for name in list(os.listdir(PIPER_MODELS_DIR)):
            if name.endswith(PIPER_MODEL_FILE_SUFFIXES):
                shutil.move(
                    os.path.join(PIPER_MODELS_DIR, name),
                    os.path.join(PIPER_MODELS_LIBRARY_DIR, name),
                )

        for suffix in PIPER_MODEL_FILE_SUFFIXES:
            src = os.path.join(PIPER_MODELS_LIBRARY_DIR, stem + suffix)
            if os.path.exists(src):
                shutil.move(src, os.path.join(PIPER_MODELS_DIR, stem + suffix))
    except Exception as e:
        print(f"⚠️ Piper modeli etkinleştirilemedi ({stem}): {e}")


def _read_settings():
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_settings(data):
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Ayarlar kaydedilemedi: {e}")


def list_turkish_voices():
    """Sistemde kurulu, Türkçe için kullanılabilecek OneCore seslerini
    (ör. Microsoft Tolga, Lej77 Piper) listeler. Dashboard > Ayarlar
    sayfasındaki ses seçimi listesini doldurmak için kullanılır.

    Piper motoru Windows'a tek bir ses olarak göründüğü için (bkz.
    PIPER_MODELS_DIR'in üstündeki not), o motor bulunduğunda onu tek bir
    satır olarak değil, kütüphanedeki her Piper modeli için ayrı, seçilebilir
    bir satır olarak listeliyoruz (id: "piper_model::<dosya kökü>")."""
    voices = []
    try:
        category = comtypes.client.CreateObject("SAPI.SpObjectTokenCategory")
        category.SetId(r'HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech_OneCore\Voices', False)
        tokens = category.EnumerateTokens()
        for i in range(tokens.Count):
            token = tokens.Item(i)
            description = token.GetDescription()
            if "piper" in description.lower():
                for stem in _list_piper_model_stems():
                    voices.append({
                        "id": PIPER_VOICE_ID_PREFIX + stem,
                        "description": f"Lej77 - Piper - {_piper_model_label(stem)}",
                    })
            elif "tr" in token.Id.lower() or "turk" in description.lower():
                voices.append({"id": token.Id, "description": description})
    except Exception as e:
        print(f"⚠️ Sesler listelenemedi: {e}")

    try:
        from ema_tts_engine import ema_tts
        if ema_tts.available():
            voices.append({"id": EMA_VOICE_ID, "description": EMA_VOICE_DESCRIPTION})
    except Exception as e:
        print(f"⚠️ EMA Lightning sesi listelenemedi: {e}")

    try:
        from ahenk_tts_engine import ahenk_tts
        if ahenk_tts.available():
            voices.append({"id": AHENK_VOICE_ID, "description": AHENK_VOICE_DESCRIPTION})
    except Exception as e:
        print(f"⚠️ Ahenk Cep sesi listelenemedi: {e}")

    return voices


def get_setting(key, default=None):
    return _read_settings().get(key, default)


def set_setting(key, value):
    data = _read_settings()
    data[key] = value
    _write_settings(data)


def get_selected_voice_id():
    return get_setting("tts_voice_id")


def set_selected_voice_id(voice_id):
    set_setting("tts_voice_id", voice_id)


def _set_turkish_voice(engine):
    """pyttsx3'ün 'voice' özelliği, Windows'un modern (OneCore) seslerini
    (ör. Tolga, Lej77 Piper) doğru şekilde seçemiyor ve sessizce varsayılan
    sese (genelde İngilizce) geri düşüyor çünkü pyttsx3 yalnızca klasik
    SAPI5 ses kategorisini tarıyor. Bu yüzden pyttsx3'ün kendi COM
    altyapısı olan comtypes ile doğrudan OneCore ses kategorisinden sesi
    arayıp pyttsx3'ün SAPI nesnesine kendimiz atıyoruz.

    Öncelik sırası: (1) Dashboard > Ayarlar sayfasından kullanıcının
    açıkça seçtiği ses (settings.json), (2) "Lej77 - Piper - Multilingual"
    (yerel, nöral Piper TTS motorunu Windows SAPI5 sesi olarak sunan bir
    motor; https://github.com/Lej77/windows-text-to-speech), (3) Windows'un
    yerleşik Türkçe OneCore sesi (Microsoft Tolga)."""
    try:
        tts_com = engine.proxy._driver._tts
        category = comtypes.client.CreateObject("SAPI.SpObjectTokenCategory")
        category.SetId(r'HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech_OneCore\Voices', False)
        tokens = category.EnumerateTokens()

        selected_id = get_selected_voice_id()

        # Kullanıcı Dashboard > Ayarlar'dan belirli bir Piper modeli
        # seçtiyse (ör. "piper_model::tr_TR-fahrettin-medium"), gerçek bir
        # SAPI token'ı değil, hangi .onnx dosyasının motorun okuduğu
        # piper_models klasöründe duracağını seçiyoruz (bkz. _activate_piper_model).
        selected_piper_stem = None
        if selected_id and selected_id.startswith(PIPER_VOICE_ID_PREFIX):
            selected_piper_stem = selected_id[len(PIPER_VOICE_ID_PREFIX):]
            selected_id = None

        selected_token = None
        piper_token = None
        turkish_token = None
        for i in range(tokens.Count):
            token = tokens.Item(i)
            description = token.GetDescription()
            if selected_id and token.Id == selected_id:
                selected_token = token
            if "piper" in description.lower():
                piper_token = token
            elif "tr" in token.Id.lower() or "turk" in description.lower():
                turkish_token = token

        if selected_piper_stem is not None and piper_token is not None:
            _activate_piper_model(selected_piper_stem)
            tts_com.Voice = piper_token
            print(f"✅ Ses seçildi (kullanıcı tercihi): Piper - {_piper_model_label(selected_piper_stem)}")
            return
        if selected_token is not None:
            tts_com.Voice = selected_token
            print(f"✅ Ses seçildi (kullanıcı tercihi): {selected_token.GetDescription()}")
            return
        if piper_token is not None:
            tts_com.Voice = piper_token
            print(f"✅ Ses seçildi (varsayılan): {piper_token.GetDescription()}")
            return
        if turkish_token is not None:
            tts_com.Voice = turkish_token
            print(f"✅ Ses seçildi (yedek): {turkish_token.GetDescription()}")
            return
        print("⚠️ Ne Piper ne de Türkçe OneCore sesi bulundu, varsayılan ses kullanılacak.")
    except Exception as e:
        print(f"⚠️ Ses ayarlanamadı, varsayılan ses kullanılacak: {e}")


def _speak_once(texto):
    """Metni önce lang_segmenter ile Türkçe/İngilizce parçalara ayırır (sözlük
    kurulu değilse tamamı Türkçe sayılır, davranış değişmez), sonra her
    parçayı sırayla uygun sesle okur: Türkçe parçalar mevcut EMA/pyttsx3
    sesiyle, İngilizce parçalar Kokoro ile."""
    import lang_segmenter
    for seg in lang_segmenter.segments(texto):
        text = seg["text"].strip()
        if not text:
            continue
        if seg["lang"] == "en":
            try:
                _speak_once_kokoro(text)
                continue
            except Exception as e:
                print(f"⚠️ Kokoro (İngilizce) sesi başarısız oldu, Türkçe sese dönülüyor: {e}")
        _speak_once_turkish(text)


def _speak_once_turkish(texto):
    """Seçili ses EMA Lightning veya Ahenk Cep ise onunla, değilse pyttsx3
    motoruyla, aynı süreç içinde metni okur. Seçili nöral ses başarısız
    olursa (model dosyaları eksik, onnxruntime/torch hatası vb.) mevcut
    pyttsx3 sesine geri döner, böylece asistan sessiz kalmaz."""
    selected = get_selected_voice_id()
    if selected == EMA_VOICE_ID:
        try:
            _speak_once_ema(texto)
            return
        except Exception as e:
            print(f"⚠️ EMA Lightning sesi başarısız oldu, mevcut sese dönülüyor: {e}")
    elif selected == AHENK_VOICE_ID:
        try:
            _speak_once_ahenk(texto)
            return
        except Exception as e:
            print(f"⚠️ Ahenk Cep sesi başarısız oldu, mevcut sese dönülüyor: {e}")

    engine = pyttsx3.init()
    _set_turkish_voice(engine)
    engine.say(texto)
    engine.runAndWait()
    engine.stop()


def _speak_once_ema(texto):
    from ema_tts_engine import speak as ema_speak
    ema_speak(texto)


def _speak_once_ahenk(texto):
    from ahenk_tts_engine import speak as ahenk_speak
    ahenk_speak(texto)


def _speak_once_kokoro(texto):
    from kokoro_tts_engine import kokoro_tts, speak as kokoro_speak
    if not kokoro_tts.available():
        raise RuntimeError("Kokoro model dosyaları bulunamadı")
    kokoro_speak(texto)


def _speak_via_subprocess(texto, should_abort=None, poll_interval=0.15):
    """Her ses (Piper dahil) için kullanılır. pyttsx3.init(), sürecin ömrü
    boyunca motoru driver adına göre zayıf referanslı bir sözlükte
    (_activeEngines) önbellekliyor; ama engine.connect() ile eklenen bir
    olay dinleyicisi (bkz. speak_text_interruptible) motoru COM taraflı bir
    referans döngüsüne sokuyor, bu yüzden motor fonksiyon dönünce normal
    refcounting ile HEMEN silinmiyor, yalnızca Python'ın döngüsel çöp
    toplayıcısı çalışınca temizleniyor. Art arda, duraksamasız çağrılarda
    (ör. Günlük Brifing'in paragrafları arasında hiç time.sleep() yok) bu
    toplayıcı araya giremediği için bir sonraki init() çağrısı AYNI,
    durmuş motoru geri döndürüyor ve ona gönderilen metin sessizce
    kayboluyor (Piper'da windows_tts_engine_piper.debug.log'daki boş
    "Speak: " satırıyla görülür). Günlük Brifing'de ilk paragraftan sonra
    sesin kesilmesinin sebebi budur; AssistantWorker'daki (bkz.
    worker_threads.py) sohbet akışında aynı hataya rastlanmaz çünkü orada
    her falar() çağrısı arasında dinleme/time.sleep() nedeniyle çöp
    toplayıcıya araya girecek zaman kalıyor.

    Her çağrıyı tamamen YENİ bir Python süreciyle yaptırarak bu önbellek
    sorununu seçili sesten bağımsız olarak tamamen ortadan kaldırıyoruz
    (bu motor zaten 'started-word' olayını hiç tetiklemiyor, yani kelime
    bazlı kesme hiçbir ses için çalışmıyor; burada should_abort()
    periyodik olarak kontrol edilip gerekirse süreç öldürülerek paragraf
    bazında kesiliyor)."""
    _speak_via_subprocess_once(texto, should_abort, poll_interval, allow_retry=True)


def _speak_via_subprocess_once(texto, should_abort, poll_interval, allow_retry):
    proc = subprocess.Popen(
        [sys.executable, os.path.abspath(__file__), "--speak-once", texto],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        while proc.poll() is None:
            if should_abort is not None and should_abort():
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
                return
            time.sleep(poll_interval)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
        return

    if proc.returncode != 0:
        try:
            stderr_output = proc.stderr.read().strip()
        except Exception:
            stderr_output = ""
        print(f"⚠️ TTS alt süreci başarısız oldu (çıkış kodu {proc.returncode}): {stderr_output}")
        # Bluetooth kulaklık bağlanır bağlanmaz Windows'un varsayılan ses
        # çıkışını yeni cihaza geçirmesi genelde yarım-bir saniye sürüyor;
        # bu geçiş penceresinde yapılan SAPI çağrısı COM hatasıyla sessizce
        # başarısız olur. Kısa bir bekleme sonrası TEK seferlik yeniden
        # deneme bu pencereyi atlamaya yetiyor (sonsuz döngüye girmemek
        # için ikinci denemede allow_retry=False).
        if allow_retry:
            # 1 saniyelik bekleme should_abort() kontrol EDİLMEDEN tek
            # seferde uyunursa, Duraklat/Durdur bu pencerede tıklanırsa
            # hemen etkisini göstermez; bu yüzden küçük parçalara bölüp
            # her parçada tekrar kontrol ediyoruz.
            waited = 0.0
            while waited < 1.0:
                if should_abort is not None and should_abort():
                    return
                time.sleep(poll_interval)
                waited += poll_interval
            if should_abort is None or not should_abort():
                _speak_via_subprocess_once(texto, should_abort, poll_interval, allow_retry=False)


def speak_text(texto):
    """Verilen metni Türkçe TTS ile okur. Dashboard'daki haber okuma gibi
    AssistantWorker dışındaki akışlar da bu fonksiyonu kullanır."""
    try:
        print(f"🔊 Asistan Konuşuyor: {texto}")
        _speak_via_subprocess(texto)
    except Exception as e:
        print(f"❌ TTS Hatası: {e}")


def speak_text_interruptible(texto, should_abort):
    """speak_text ile aynı şekilde okur, ama kesilebilir: seçili ses ne
    olursa olsun paragraf bazında durdurulur (bkz. _speak_via_subprocess).
    pyttsx3'te resmi bir pause() API'si olmadığı için Günlük Brifing'deki
    Duraklat/Durdur düğmeleri bu mekanizmayla çalışır."""
    try:
        print(f"🔊 Asistan Konuşuyor (kesilebilir): {texto}")
        _speak_via_subprocess(texto, should_abort=should_abort)
    except Exception as e:
        print(f"❌ TTS Hatası: {e}")


if __name__ == "__main__":
    # Bu alt süreç her zaman subprocess.PIPE üzerinden ana sürece bağlı
    # çalışır (bkz. _speak_via_subprocess_once), gerçek bir konsola değil;
    # Python bu durumda stdout/stderr kodlamasını konsol değil Windows'un
    # yerel kod sayfasına (Türkçe sistemde cp1254) göre seçiyor ve bu kod
    # sayfası emoji gibi karakterleri kodlayamayınca print() sessizce
    # değil GÜRÜLTÜLÜ şekilde çöküyor, asıl hatayı gizliyor. UTF-8'e
    # zorlayıp kodlanamayan karakterleri değiştirerek bunu önlüyoruz.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if len(sys.argv) >= 3 and sys.argv[1] == "--speak-once":
        try:
            _speak_once(sys.argv[2])
        except Exception as e:
            print(f"❌ TTS alt süreç hatası: {e}", file=sys.stderr)
            sys.exit(1)
