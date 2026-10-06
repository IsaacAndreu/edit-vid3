"""Numbers written in words, for the narration only (GenAIPro gets «cuatrocientos trece millones», the on-screen
graphics keep «413 M»).

ElevenLabs sometimes reads «413.240.000» digit by digit, or «206,6» as «doscientos seis mil seiscientos». Spanish
rules: a dot groups thousands, a comma marks decimals; «%» is «por ciento», «€» «euros», «$» «dólares»; a number
ending in 1 before a noun loses its «o» («veintiún años», «un millón»). Numbers glued to letters (COVID-19, 4K, A4)
and times (13:57) are left as they are.
"""

from __future__ import annotations

import re

_UNITS = ["cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez", "once", "doce",
          "trece", "catorce", "quince", "dieciséis", "diecisiete", "dieciocho", "diecinueve", "veinte", "veintiuno",
          "veintidós", "veintitrés", "veinticuatro", "veinticinco", "veintiséis", "veintisiete", "veintiocho",
          "veintinueve"]
_TENS = {30: "treinta", 40: "cuarenta", 50: "cincuenta", 60: "sesenta", 70: "setenta", 80: "ochenta", 90: "noventa"}
_HUNDREDS = {1: "ciento", 2: "doscientos", 3: "trescientos", 4: "cuatrocientos", 5: "quinientos", 6: "seiscientos",
             7: "setecientos", 8: "ochocientos", 9: "novecientos"}
# words after which «uno» stays «uno» (a date, «el 1 de enero», a list): before a noun it is «un»
_KEEP_UNO = {"de", "del", "y", "o", "a", "al", "en", "por", "coma", "entre", "e", "u", "que", "con", "para", "sobre"}


def _below_thousand(n: int) -> str:
    if n < 30:
        return _UNITS[n]
    if n < 100:
        tens, unit = divmod(n, 10)
        return _TENS[tens * 10] + (f" y {_UNITS[unit]}" if unit else "")
    if n == 100:
        return "cien"
    hundreds, rest = divmod(n, 100)
    return _HUNDREDS[hundreds] + (f" {_below_thousand(rest)}" if rest else "")


def _apocope(words: str) -> str:
    """«uno» → «un», «veintiuno» → «veintiún» (before «mil», «millones» or a noun)."""

    if words.endswith("veintiuno"):
        return words[:-len("veintiuno")] + "veintiún"
    if words.endswith("uno"):
        return words[:-3] + "un"
    return words


_MASCULINE_A = {"día", "días", "problema", "problemas", "idioma", "idiomas", "programa", "programas", "sistema",
                "sistemas", "mapa", "mapas", "tema", "temas", "planeta", "planetas", "clima", "dilema", "dilemas",
                "esquema", "esquemas", "millonaria", "pijama", "sofá", "sofás", "euros", "dólares"}


_FEMININE_OTHER = {"noche", "noches", "vez", "veces", "parte", "partes", "ley", "leyes", "red", "redes", "clase", "clases",
                   "mujer", "mujeres", "calle", "calles", "fuente", "fuentes", "torre", "torres", "imagen", "imágenes",
                   "fase", "fases", "base", "bases", "frase", "frases", "serie", "series", "especie", "especies",
                   "tarde", "tardes", "llave", "llaves", "nave", "naves", "flor", "flores", "piel", "cárcel",
                   "sede", "sedes", "muerte", "muertes", "gente", "suerte", "mente", "mentes", "nieve", "sal"}


def _feminine(words: str) -> str:
    """«cuarenta y una páginas», «doscientas personas» (not across «millones»: «dos millones de personas»)."""

    if "millón" in words or "millones" in words or "billón" in words or "billones" in words:
        return words
    words = re.sub(r"ientos\b", "ientas", words)
    if words.endswith("veintiuno") or words.endswith("veintiún"):
        return re.sub(r"veinti(uno|ún)$", "veintiuna", words)
    return re.sub(r"\b(uno|un)$", "una", words)


def _feminine_noun(word: str) -> bool:
    word = word.casefold()
    if word in _FEMININE_OTHER:
        return True
    return word not in _MASCULINE_A and (word.endswith("as") or word.endswith("a") or word.endswith("ión")
                                         or word.endswith("iones") or word.endswith("dad") or word.endswith("dades"))


def to_words(n: int) -> str:
    """A whole number (up to billions, «billón» = 10¹²) in Spanish words, masculine."""

    if n < 0:
        return "menos " + to_words(-n)
    if n < 1000:
        return _below_thousand(n)
    for size, one, many in ((10**12, "un billón", "billones"), (10**6, "un millón", "millones")):
        if n >= size:
            high, rest = divmod(n, size)
            head = one if high == 1 else f"{_apocope(to_words(high))} {many}"
            return head + (f" {to_words(rest)}" if rest else "")
    high, rest = divmod(n, 1000)
    head = "mil" if high == 1 else f"{_apocope(_below_thousand(high))} mil"
    return head + (f" {to_words(rest)}" if rest else "")


_NUMBER = re.compile(
    r"(?<![\w.,:/])(?<![^\W\d_]-)"                         # not glued to letters (COVID-19), a time, a code
    r"(?P<sign>(?<![\w-])[-−])?"
    r"(?P<int>\d{1,3}(?:\.\d{3})+|\d+)"                  # 413.240.000 or 2023
    r"(?:,(?P<dec>\d+))?"                                # 206,6
    r"(?![\w:/]|[.,]\d)"
    r"(?P<tail>\s?(?:%|€|\$))?"
)


def _decimals(digits: str) -> str:
    if len(digits) <= 2 and not digits.startswith("0"):
        return to_words(int(digits))
    return " ".join(_UNITS[int(d)] for d in digits)     # 3,05 → tres coma cero cinco


def spoken_numbers(text: str) -> str:
    """Every number of the text in words (Spanish)."""

    def replace(match: re.Match) -> str:
        whole = int(match.group("int").replace(".", ""))
        words = to_words(whole)
        decimals = match.group("dec")
        tail = (match.group("tail") or "").strip()
        after = text[match.end():].lstrip()
        next_word = re.match(r"[^\W\d_]+", after)
        if decimals:
            words += " coma " + _decimals(decimals)
        elif not tail and next_word and _feminine_noun(next_word.group(0)):
            words = _feminine(words)                    # «una noche», «doscientas personas»
        elif tail in ("€", "$") or (next_word and next_word.group(0).casefold() not in _KEEP_UNO):
            words = _apocope(words)                     # «un millón», «veintiún años», «un euro»
        if match.group("sign"):
            words = "menos " + words
        if tail == "%":
            words += " por ciento"
        elif tail == "€":
            words += " euro" if whole == 1 and not decimals else " euros"
        elif tail == "$":
            words += " dólar" if whole == 1 and not decimals else " dólares"
        return words

    return _NUMBER.sub(replace, text)
