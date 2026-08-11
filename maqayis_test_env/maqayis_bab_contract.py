"""
maqayis_bab_contract.py — Production BAB letter mapping contract
MAQAYIS-CONSTITUTIONAL-SOURCE-LEXICON-PRODUCTION-01

BAB_CANONICAL_WORDS : frozenset of the 28 canonical Arabic bāb heading words
                      as they appear in the Maqayis corpus.
BAB_LETTER_MAP      : dict mapping every Arabic Unicode letter (including all
                      hamza forms) to its canonical bāb heading word.

These constants are the single authoritative source for both production
pipelines and test suites.  Do NOT define them locally in test files.
"""
from __future__ import annotations

BAB_CANONICAL_WORDS: frozenset[str] = frozenset({
    "الألف",
    "الباء",
    "التاء",
    "الثاء",
    "الجيم",
    "الحاء",
    "الخاء",
    "الدال",
    "الذال",
    "الراء",
    "الزاي",
    "السين",
    "الشين",
    "الصاد",
    "الضاد",
    "الطاء",
    "الظاء",
    "العين",
    "الغين",
    "الفاء",
    "القاف",
    "الكاف",
    "اللام",
    "الميم",
    "النون",
    "الهاء",
    "الواو",
    "الياء",
})

# Maps every Arabic letter codepoint (including hamza variants) to its
# canonical bāb heading word.  Hamza variants (أ إ آ ء) all map to "الألف".
BAB_LETTER_MAP: dict[str, str] = {
    "ا": "الألف",
    "أ": "الألف",
    "إ": "الألف",
    "آ": "الألف",
    "ء": "الألف",
    "ب": "الباء",
    "ت": "التاء",
    "ث": "الثاء",
    "ج": "الجيم",
    "ح": "الحاء",
    "خ": "الخاء",
    "د": "الدال",
    "ذ": "الذال",
    "ر": "الراء",
    "ز": "الزاي",
    "س": "السين",
    "ش": "الشين",
    "ص": "الصاد",
    "ض": "الضاد",
    "ط": "الطاء",
    "ظ": "الظاء",
    "ع": "العين",
    "غ": "الغين",
    "ف": "الفاء",
    "ق": "القاف",
    "ك": "الكاف",
    "ل": "اللام",
    "م": "الميم",
    "ن": "النون",
    "ه": "الهاء",
    "و": "الواو",
    "ي": "الياء",
}
