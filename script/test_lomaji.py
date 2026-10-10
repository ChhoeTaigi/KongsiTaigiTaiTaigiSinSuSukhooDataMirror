"""Tests for lomaji.kpl_to_poj, taken from KonvertToPOJ's KPL_UNICODE → POJ_UNICODE cases."""

import unicodedata
import unittest

from lomaji import kpl_to_poj

N = lambda s: unicodedata.normalize("NFC", s)

CASES = [
    # KonvertToPojTest: cross-system KPL Unicode → POJ Unicode
    ("tsi̍t", "chi̍t"),
    ("uân", "oân"),
    ("gōo", "gō͘"),
    ("huē", "hōe"),
    ("kuànn", "kòaⁿ"),
    ("hiu̍hnn", "hiu̍hⁿ"),
    ("a̋", "ă"),
    ("Tsi̍t-ê tsa-bóo", "Chi̍t-ê cha-bó͘"),
    ("COVID19", "COVID19"),
    ("ÎR ÊR", N("Ṳ̂ Ô̤")),
    ("streaming tsi̍t", "streaming chi̍t"),
    ("chi̍t", "chi̍t"),
    ("khia̍ih ua̍ih iâunn", "khia̍ih oa̍ih iâuⁿ"),
    ("niûnn mânn", "niûnn mânn"),
    ("nn̄g mn̂g", "nn̄g mn̂g"),
    ("sing", "seng"),
    ("tik", "tek"),
    ("kíng", "kéng"),
    ("kua", "koa"),
    ("tshiú", "chhiú"),
    # Round-trips of the POJ → KPL cases
    ("tsui̍t", "chu̍it"),
    ("hnĝ m̄ n̍gh", "hn̂g m̄ n̍gh"),
    ("Siōng-tè", "Siōng-tè"),
    # Entries from 台語新詞辭庫
    ("tō-pún-luí", "tō-pún-lúi"),
    ("nn̄g hó-kiû sa̋n-sín-lu̍t", "nn̄g hó-kiû săn-sín-lu̍t"),
    ("muí kio̍k pī tsiūnn-luí-lu̍t", "múi kio̍k pī chiūⁿ-lúi-lu̍t"),
    ("hí-tooh", "hí-to͘h"),
    ("kuainn-mn̂g--ê", "koaiⁿ-mn̂g--ê"),
    ("BB-káu-ti̍t", "BB-káu-ti̍t"),
    ("ECMO", "ECMO"),
    ("Tsio̍h-thâu", "Chio̍h-thâu"),
    ("tshài-kué/ké", "chhài-kóe/ké"),
    ("ī-pī tshâi-phuànn", "ī-pī chhâi-phòaⁿ"),
    ("thuí-jī-thâu-ki", "thúi-jī-thâu-ki"),
    ("sàn-jia̍t-khì", "sàn-jia̍t-khì"),
    ("ngē-giâ", "ngē-giâ"),
    ("bô-suànn hīnn-ki", "bô-sòaⁿ hīⁿ-ki"),
    ("tsuā-kū", "chōa-kū"),
    ("ue̍h-tsuā", "oe̍h-chōa"),
    ("khue-sióng", "khoe-sióng"),
    ("tsa̍p-gōo", "cha̍p-gō͘"),
    ("Oo-mi-tôo", "O͘-mi-tô͘"),
]


class KplToPojTest(unittest.TestCase):
    def test_cases(self):
        for kpl, poj in CASES:
            with self.subTest(kpl=kpl):
                self.assertEqual(N(poj), kpl_to_poj(kpl))


if __name__ == "__main__":
    unittest.main()
