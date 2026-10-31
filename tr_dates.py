# tr_dates.py
#
# Türkçe tarih biçimleme yardımcıları. PyQt bağımlılığı YOKTUR — hem
# dashboard_ui.py hem de arayüzsüz telegram_briefing.py aynı biçimi kullanır.

TR_MONTHS = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
             "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
TR_DAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]


def format_tr_date(dt) -> str:
    return f"{dt.day} {TR_MONTHS[dt.month - 1]} {dt.year} {TR_DAYS[dt.weekday()]}"


def format_tr_date_short(dt) -> str:
    return f"{dt.day} {TR_MONTHS[dt.month - 1]}"
