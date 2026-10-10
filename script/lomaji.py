"""KPL (Kàu-io̍k Pō͘ Lô-má-jī, Unicode) → POJ (Pe̍h-ōe-jī, Unicode) for Taigi Roman Orthography.

A Python port of the KPL_UNICODE → POJ_UNICODE "direct" route of KonvertToPOJ
(https://github.com/PehoejiKesi/KonvertToPOJ, GPL-3.0): per syllable, read the
tone off the diacritic, convert the bare letters between systems, then re-place
the tone mark by the POJ rules (狗公會曉學台語 §21). Only tokens shaped like a
KPL syllable are converted; anything else (English words, abbreviations, digits,
Hanji, punctuation) passes through unchanged.

    ts/tsh → ch/chh   ua/ue → oa/oe   ik/ing → ek/eng   oo → o͘   nn → ⁿ
    ir/er → ur/or (海口腔)   tone 9  a̋ (U+030B) → ă (U+0306)
"""

import re
import unicodedata

_NFC = lambda s: unicodedata.normalize("NFC", s)
_NFD = lambda s: unicodedata.normalize("NFD", s)

# Combining tone marks → tone number. Breve (POJ) and double acute (KPL) are both tone 9.
_TONE_MARKS = {
    "́": 2, "̀": 3, "̂": 5, "̄": 7,
    "̍": 8, "̆": 9, "̋": 9,
}
_POJ_MARK = {2: "́", 3: "̀", 5: "̂", 7: "̄", 8: "̍", 9: "̆"}
_NASAL = "ⁿ"       # ⁿ
_OO_DOT = "͘"      # o͘
_OR_DOT = "̤"      # o̤
_OTHER_MARKS = {_OO_DOT, _OR_DOT}

_CONFUSABLES = {"ı": "i", "İ": "I"}


# --- POJ tone map (number form → Unicode), mirrors KonvertToPOJ's PojToneMap ------------

def _build_poj_n2u():
    n2u = {}

    def put(key, value):
        n2u.setdefault(key, _NFC(value))

    for t, m in _POJ_MARK.items():
        for v in "AIUEO":
            put(f"{v}{t}", v + m)
            put(f"{v.lower()}{t}", v.lower() + m)
        put(f"Oo{t}", "O" + m + _OO_DOT)
        put(f"oo{t}", "o" + m + _OO_DOT)
        put(f"Ur{t}", "Ṳ" + m)
        put(f"ur{t}", "ṳ" + m)
        mark8 = m + m if t == 8 else m   # or8 is written with a doubled U+030D
        put(f"Or{t}", "O" + _OR_DOT + mark8)
        put(f"or{t}", "o" + _OR_DOT + mark8)
        for n in "MN":
            put(f"{n}{t}", n + m)
            put(f"{n.lower()}{t}", n.lower() + m)
        put(f"Ng{t}", "N" + m + "g")
        put(f"NG{t}", "N" + m + "G")
        put(f"ng{t}", "n" + m + "g")
    return n2u


_POJ_N2U = _build_poj_n2u()


# --- Tokenizer -----------------------------------------------------------------------------

def _is_lomaji_char(c):
    if c.isascii():
        return c.isalpha()
    if c == _NASAL or c in _TONE_MARKS or c in _OTHER_MARKS:
        return True
    base = _NFD(c)
    return base[0].isascii() and base[0].isalpha() and all(
        x in _TONE_MARKS or x in _OTHER_MARKS for x in base[1:]
    )


def split_syllables(text):
    """Yield (token, is_lomaji) pairs; every non-lomaji character is its own token."""
    current = []
    for c in text:
        if _is_lomaji_char(c) or c.isdigit():
            current.append(c)
        else:
            if current:
                yield "".join(current), True
                current = []
            yield c, False
    if current:
        yield "".join(current), True


# --- Tone stripping -------------------------------------------------------------------------

def strip_tone_mark(syllable):
    """Return (bare_syllable, tone or None), or None if two different tone marks are present."""
    tone = None
    bare = []
    for c in _NFD(syllable):
        t = _TONE_MARKS.get(c)
        if t is None:
            bare.append(c)
            continue
        if tone is not None and tone != t:
            return None
        tone = t
    return _NFC("".join(bare)), tone


# --- Syllable shape (KPL) ------------------------------------------------------------------

_CODA = "ng|m|n|p|t|k|h"
_KPL_SHAPE = re.compile(
    r"^(?:tsh|ts|ph|th|kh|ng|p|m|b|t|l|k|n|g|h|s|j)?"
    r"(?:(?:ir|er|[aiueo]){1,3}(?:(?:nn)h?|h(?:nn)|" + _CODA + r")?|(?:m|ng)h?)$"
)


def _tone_fits(lower, tone, nasal):
    if tone not in (4, 8):
        return True
    if lower.endswith(nasal):
        lower = lower[: -len(nasal)]
    return bool(lower) and lower[-1] in "ptkh"


def _nasal_fits(lower, nasals):
    if lower.startswith("ng"):
        rest = lower[2:]
    elif lower[:1] in ("m", "n"):
        rest = lower[1:]
    else:
        return True
    return not any(n in rest for n in nasals)


def is_kpl_shape(bare, tone):
    lower = bare.lower()
    return bool(_KPL_SHAPE.match(lower)) and _tone_fits(lower, tone, "nn") and _nasal_fits(lower, ["nn"])


def is_kpl_syllable(syllable):
    """True when the Unicode token is shaped like a KPL syllable (at most one tone mark, no digits)."""
    stripped = strip_tone_mark(syllable)
    if stripped is None:
        return False
    return is_kpl_shape(*stripped)


# --- System conversion on bare letters (KPL input → POJ input) -----------------------------

def kpl_input_to_poj_input(kpl):
    s = kpl
    for a, b in (("tsh", "chh"), ("Tsh", "Chh"), ("TSH", "CHH"),
                 ("ts", "ch"), ("Ts", "Ch"), ("TS", "CH")):
        s = s.replace(a, b)
    s = re.sub(r"u([aAeE])", r"o\1", s)
    s = re.sub(r"U([aAeE])", r"O\1", s)
    for a, b in (("ik", "ek"), ("Ik", "Ek"), ("IK", "EK"),
                 ("ing", "eng"), ("Ing", "Eng"), ("ING", "ENG"),
                 ("IR", "UR"), ("Ir", "Ur"), ("ir", "ur"),
                 ("ER", "OR"), ("Er", "Or"), ("er", "or")):
        s = s.replace(a, b)
    return s


# --- POJ tone placement (input form → Unicode) ---------------------------------------------

def _poj_fix_nn(s):
    if "nng" in s.lower():
        return s
    return s.replace("nn", _NASAL).replace("NN", _NASAL).replace("Nn", _NASAL)


def _poj_fix_oo(s):
    if s.upper() == s:
        return s.replace("OO", "O" + _OO_DOT).replace("UR", "Ṳ").replace("OR", "O" + _OR_DOT)
    return (s.replace("Oo", "O" + _OO_DOT).replace("oo", "o" + _OO_DOT)
             .replace("Ur", "Ṳ").replace("ur", "ṳ")
             .replace("Or", "O" + _OR_DOT).replace("or", "o" + _OR_DOT))


def _last_index_of_any(s, needles):
    return max(s.rfind(n) for n in needles)


def _find_letter_from_right(s, n):
    """Position of the n-th letter from the right, skipping ⁿ and o͘'s dot, with "ng" as one letter."""
    pos = len(s) - 1
    count = 0
    while pos >= 0:
        c = s[pos]
        if c == _NASAL or c == _OO_DOT:
            pass
        elif c.lower() == "g" and pos > 0 and s[pos - 1].lower() == "n":
            count += 1
            if count == n:
                pos -= 1
                break
            pos -= 2
            continue
        else:
            count += 1
            if count == n:
                break
        pos -= 1
    return max(pos, 0)


def _strip_nasal(s):
    return s.replace(_NASAL, "")


def _is_checked(lower):
    cleaned = _strip_nasal(lower)
    return bool(cleaned) and cleaned[-1] in "ptkh"


def find_poj_tone_position(lower_base):
    """Return (offset, length) of the letters that carry the tone mark, or None."""
    vowels = ["a", "i", "u", "o", "e"]
    last_vowel = _last_index_of_any(lower_base, vowels)

    if last_vowel == -1:
        last_semi = _last_index_of_any(lower_base, ["m", "ng", "n"])
        if last_semi == -1:
            return None
        return last_semi, (2 if "ng" in lower_base else 1)

    if "ur" in lower_base or "or" in lower_base:
        return _last_index_of_any(lower_base, ["ur", "or"]), 2

    adjacent = 1
    if last_vowel > 0 and lower_base[last_vowel - 1] in "aiueo":
        adjacent = 2

    if adjacent == 1:
        return last_vowel, 1
    if adjacent == 2 and "oo" in lower_base:
        return last_vowel - 1, 2

    pos2 = _find_letter_from_right(lower_base, 2)
    char2 = lower_base[pos2]
    if _is_checked(lower_base):
        if "iuh" in _strip_nasal(lower_base):
            return _find_letter_from_right(lower_base, 2), 1
        if char2 in "iu":
            return _find_letter_from_right(lower_base, 3), 1
        return pos2, 1
    if char2 == "i":
        return _find_letter_from_right(lower_base, 1), 1
    return _find_letter_from_right(lower_base, 2), 1


def poj_input_to_unicode(syllable):
    s = _poj_fix_nn(syllable)
    if len(s) <= 1:
        return s
    last = s[-1]
    if not last.isdigit():
        return _poj_fix_oo(s)
    base = s[:-1]
    pos = find_poj_tone_position(base.lower())
    if pos is None:
        return _poj_fix_oo(s)
    if last in "14":
        return _poj_fix_oo(base)
    off, length = pos
    target = base[off: off + length]
    repl = _POJ_N2U.get(target + last) or _POJ_N2U.get(target[:1] + target[1:].lower() + last)
    if repl is None:
        return base
    return _NFC(base[:off] + repl + base[off + length:])


# --- Public API ------------------------------------------------------------------------------

def kpl_syllable_to_poj(syllable):
    """Convert one KPL Unicode syllable to POJ Unicode; unchanged if it is not KPL-shaped."""
    stripped = strip_tone_mark(syllable)
    if stripped is None or not is_kpl_shape(*stripped):
        return syllable
    bare, tone = stripped
    poj = kpl_input_to_poj_input(bare)
    if tone is None:
        return poj_input_to_unicode(poj)
    result = poj_input_to_unicode(poj + str(tone))
    return syllable if result[-1:].isdigit() else result


def kpl_to_poj(text):
    """Convert KPL Unicode text (syllables separated by hyphens, spaces or punctuation) to POJ."""
    normalized = "".join(_CONFUSABLES.get(c, c) for c in _NFC(text))
    return "".join(kpl_syllable_to_poj(tok) if is_lomaji else tok
                   for tok, is_lomaji in split_syllables(normalized))


if __name__ == "__main__":
    import sys
    for line in sys.stdin:
        print(kpl_to_poj(line.rstrip("\n")))
