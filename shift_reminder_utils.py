# shift_reminder_utils.py
#
# "<vardiya kodu> vardiyasında olduğum günlerde saat <HH:MM>'de ..." biçimindeki
# vardiya bağımlı, TEKRARLI hatırlatmalar için ortak mantık. note_classifier.py
# (mesaj geldiğinde ilk hedef zamanı hesaplamak için) ve reminder_scheduler.py
# (bildirildikten sonra bir sonraki hedef zamanı hesaplamak için) tarafından
# paylaşılır — vardiya takvimi mantığını (briefing_coordinator.resolve_shift_for_date)
# iki yerde ayrı ayrı, birbirinden sapabilecek şekilde kopyalamamak için.
#
# note_database.py'deki genel repeat_frequency alanı bu durumda "vardiya:07-15"
# ya da "vardiya:15-23" değerini taşır; remind_at her ateşlemeden sonra BİR
# SONRAKİ uygun güne taşınır (bkz. reminder_scheduler._check_due_reminders),
# notified_at sıfırlanır — yani klasik tek seferlik hatırlatmaların tersine
# bu not asla "bitmiş" sayılmaz.
import re
from datetime import datetime, timedelta

import briefing_coordinator
import note_database

REPEAT_PREFIX = "vardiya:"

# briefing_coordinator._SHIFT_META'daki kodlarla AYNI olmalı ("07-15", "15-23");
# "tatil" burada kasıtlı yok — "tatil günlerinde hatırlat" nadir ve kafa
# karıştırıcı bir istek, şimdilik yalnızca gerçek vardiya kodları destekleniyor.
_SHIFT_CODE_RE = re.compile(r"\b(07[-_]15|15[-_]23)\b")
_TIME_RE = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b")

# 27 günlük R1D döngüsünden (bkz. briefing_coordinator._R1D_27DAY_CYCLE) uzun,
# sonsuz döngüye girmeyi önleyen güvenli bir arama üst sınırı.
_SEARCH_LIMIT_DAYS = 60


def detect_shift_code(text):
    """Mesaj metninde '07-15'/'07_15' veya '15-23'/'15_23' geçiyorsa normalize
    edilmiş vardiya kodunu döner; yoksa None."""
    match = _SHIFT_CODE_RE.search(text or "")
    return match.group(1).replace("_", "-") if match else None


def detect_time(text):
    """Mesaj metninde 'HH:MM' ya da 'HH.MM' biçiminde bir saat varsa
    'HH:MM' olarak döner; yoksa None."""
    match = _TIME_RE.search(text or "")
    if not match:
        return None
    return f"{int(match.group(1)):02d}:{match.group(2)}"


def repeat_value(shift_code):
    return f"{REPEAT_PREFIX}{shift_code}"


def is_shift_repeat(repeat_frequency):
    return bool(repeat_frequency) and str(repeat_frequency).startswith(REPEAT_PREFIX)


def shift_code_from_repeat(repeat_frequency):
    return str(repeat_frequency)[len(REPEAT_PREFIX):]


def _next_matching_date(shift_code, after_date):
    d = after_date + timedelta(days=1)
    for _ in range(_SEARCH_LIMIT_DAYS):
        if briefing_coordinator.resolve_shift_for_date(d)["code"] == shift_code:
            return d
        d += timedelta(days=1)
    return None


def _combine(target_date, time_str):
    hour, minute = (int(p) for p in time_str.split(":"))
    return datetime(target_date.year, target_date.month, target_date.day, hour, minute,
                     tzinfo=note_database.ISTANBUL_TZ)


def first_occurrence_iso(shift_code, time_str, now=None):
    """Hatırlatma ŞİMDİ oluşturulduğunda ilk ateşleneceği zamanı döner: bugün
    o vardiyadaysak ve saat henüz gelmediyse bugün, aksi halde o vardiyaya
    denk gelen ilk gelecek gün."""
    now = now or datetime.now(note_database.ISTANBUL_TZ)
    today = now.date()
    if briefing_coordinator.resolve_shift_for_date(today)["code"] == shift_code:
        candidate = _combine(today, time_str)
        if candidate > now:
            return candidate.isoformat()
    next_date = _next_matching_date(shift_code, today)
    return _combine(next_date, time_str).isoformat() if next_date else None


def next_occurrence_iso(shift_code, time_str, after_date):
    """Bir hatırlatma `after_date` gününde ateşlendikten SONRAKİ ilk uygun
    günün zamanını döner; bulunamazsa None."""
    next_date = _next_matching_date(shift_code, after_date)
    return _combine(next_date, time_str).isoformat() if next_date else None
