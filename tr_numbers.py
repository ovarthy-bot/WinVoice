# Türkçe sayı -> yazı dönüştürücü.
#
# Yerel LLM (gemma3:4b) fiyat/yüzde gibi rakamları Türkçe yazıya çevirmede
# güvenilir değil (test sırasında "49.7892 TL" gibi değerleri yanlış veya
# hiç çevirmeden bıraktığı görüldü). Bu yüzden TTS'e gidecek hava/piyasa
# rakamları LLM'e hiç ham sayı olarak verilmiyor; burada deterministik
# olarak kelimeye çevrilip LLM'e hazır Türkçe ifade olarak veriliyor.

_ONES = ["", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz"]
_TENS = ["", "on", "yirmi", "otuz", "kırk", "elli", "altmış", "yetmiş", "seksen", "doksan"]
_SCALES = ["", "bin", "milyon", "milyar", "trilyon"]


def _three_digits_to_words(n: int) -> str:
    hundreds, remainder = divmod(n, 100)
    tens, ones = divmod(remainder, 10)
    parts = []
    if hundreds:
        parts.append("yüz" if hundreds == 1 else f"{_ONES[hundreds]} yüz")
    if tens:
        parts.append(_TENS[tens])
    if ones:
        parts.append(_ONES[ones])
    return " ".join(parts)


def number_to_words(n) -> str:
    n = int(round(n))
    if n == 0:
        return "sıfır"
    negative = n < 0
    n = abs(n)

    groups = []
    while n > 0:
        groups.append(n % 1000)
        n //= 1000

    parts = []
    for i in reversed(range(len(groups))):
        group = groups[i]
        if group == 0:
            continue
        if i == 1 and group == 1:
            # "bir bin" değil, sadece "bin"
            parts.append(_SCALES[i])
        elif i > 0:
            parts.append(f"{_three_digits_to_words(group)} {_SCALES[i]}")
        else:
            parts.append(_three_digits_to_words(group))

    result = " ".join(parts)
    return f"eksi {result}" if negative else result


def currency_to_words(amount: float, unit: str = "lira", subunit: str = "kuruş") -> str:
    """Örn: 49.7892 -> 'kırk dokuz lira seksen kuruş'."""
    negative = amount < 0
    amount = abs(amount)
    lira = int(amount)
    kurus = round((amount - lira) * 100)
    if kurus >= 100:
        lira += 1
        kurus -= 100
    text = f"{number_to_words(lira)} {unit}"
    if kurus > 0:
        text += f" {number_to_words(kurus)} {subunit}"
    return f"eksi {text}" if negative else text


def percent_to_words(value: float) -> str:
    """Örn: 0.13 -> 'yüzde sıfır virgül on üç', 1.5 -> 'yüzde bir virgül beş'."""
    negative = value < 0
    value = abs(value)
    integer_part = int(value)
    decimal_part = round((value - integer_part) * 100)
    if decimal_part >= 100:
        integer_part += 1
        decimal_part -= 100
    text = f"yüzde {number_to_words(integer_part)}"
    if decimal_part > 0:
        # Tek ondalık basamaklı değerler (1.5 gibi) "virgül elli" değil,
        # daha doğal olan "virgül beş" şeklinde okunur.
        spoken_decimal = decimal_part // 10 if decimal_part % 10 == 0 else decimal_part
        text += f" virgül {number_to_words(spoken_decimal)}"
    return f"eksi {text}" if negative else text


def plain_number_to_words(value) -> str:
    """Ondalıklı bir değeri (ör. puan, derece) en yakın tam sayıya
    yuvarlayıp birimsiz olarak yazıya çevirir."""
    return number_to_words(value)
