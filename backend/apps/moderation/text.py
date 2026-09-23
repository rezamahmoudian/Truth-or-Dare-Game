"""Persian-aware text matching for the word filter.

A naive `word in text` check catches nothing in Persian. The same word can be
written with Arabic ي or Persian ی, with or without ZWNJ, with diacritics —
and someone who wants past a filter will pad letters ("کثااافت"), separate
them ("ک ث ا ف ت") or break them with punctuation. None of that is clever; it
is what people do within the first hour.

So a banned word becomes a pattern in which every letter matches all of its
visual variants, may repeat, and may be followed by anything that is not a
letter. The pattern then runs against the message exactly as it was typed,
which is what lets masking put the rest of the sentence back unchanged.
"""

import re
import unicodedata

# Letters that are written more than one way. The key is the canonical form.
VARIANTS = {
    "ی": "یيىئ",
    "ک": "کك",
    "ه": "هةۀ",
    "ا": "اأإآٱ",
    "و": "وؤ",
}

# Reverse lookup: any form → the class of every form it could be written as.
_CLASS_FOR = {
    variant: forms for forms in VARIANTS.values() for variant in forms
}

# Fold Arabic forms and Persian/Arabic-Indic digits when comparing whole
# strings (used for equality checks, not for the pattern).
CHAR_MAP = str.maketrans(
    {
        **{variant: canonical for canonical, forms in VARIANTS.items() for variant in forms},
        "ـ": "",  # tatweel, used purely to stretch words
        "‌": "",  # ZWNJ
        "‎": "",
        "‏": "",
    }
)
DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
DIACRITICS = re.compile(r"[ً-ْٰٓ-ٕ]")

# What may sit between two letters of a word without breaking it: spaces,
# punctuation, ZWNJ, tatweel and harakat.
SEPARATOR = r"[\W_ـً-ْٰ‌]*"


def normalize(text: str) -> str:
    """Fold a string to a single canonical spelling."""
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(CHAR_MAP).translate(DIGIT_MAP)
    text = DIACRITICS.sub("", text)
    # Three or more of the same letter is padding, never spelling.
    text = re.sub(r"(.)\1{2,}", r"\1", text)
    return text.casefold()


# A letter on either side means this is part of a longer word, not the word
# itself. Without these, "کس" masks "عکس" and "هرکس", and "خر" masks "دختر" —
# false positives that read as a broken app, and are far worse than a miss.
BOUNDARY_BEFORE = r"(?<![\w؀-ۿ])"
BOUNDARY_AFTER = r"(?![\w؀-ۿ])"

# Persian glues its possessives and plurals straight onto the word, so a strict
# whole-word match catches "احمق" and lets "احمقی" through — which is most of
# how the word is actually used. These are the ordinary enclitics, longest
# first so the regex prefers the fuller match.
SUFFIXES = [
    "هایشان", "هایمان", "هایتان", "هاشون", "هامون", "هاتون",
    "هایش", "هایم", "هایت", "هاش", "هام", "هات",
    "شون", "مون", "تون", "ها", "ای", "ام", "ات", "اش",
    "ی", "ه", "م", "ت", "ش", "ین",
]
OPTIONAL_SUFFIX = r"(?:‌?(?:" + "|".join(SUFFIXES) + r"))?"

# Only words this long get suffix tolerance. Below it the risk flips: "کس" plus
# "ی" is "کسی", and "گه" plus "ها" is inside plenty of ordinary words. Length
# tracks ambiguity closely enough to be the rule.
SUFFIX_MIN_LETTERS = 4


def build_pattern(word: str, *, whole_word: bool = True) -> re.Pattern[str]:
    """A regex matching `word` however it has been stretched or broken up.

    `whole_word` is on by default and is what keeps the filter usable in
    Persian, where short obscenities are spelled inside perfectly ordinary
    words. Turn it off only for stems that are never innocent.

    Evasion still gets caught either way: "ک س" separates the letters but the
    boundaries fall outside the whole phrase, not between its letters.
    """
    letters = [char for char in normalize(word) if char.strip()]
    if not letters:
        return re.compile(r"(?!x)x")  # matches nothing

    parts = []
    for letter in letters:
        forms = _CLASS_FOR.get(letter, letter)
        group = f"[{re.escape(forms)}]" if len(forms) > 1 else re.escape(forms)
        parts.append(f"{group}+")

    body = SEPARATOR.join(parts)
    if whole_word:
        tail = OPTIONAL_SUFFIX if len(letters) >= SUFFIX_MIN_LETTERS else ""
        body = f"{BOUNDARY_BEFORE}{body}{tail}{BOUNDARY_AFTER}"
    return re.compile(body, re.IGNORECASE)


def mask(text: str, pattern: re.Pattern[str], replacement: str = "***") -> str:
    """Replace matches while leaving the rest of the message intact.

    Masking rather than rejecting, for everything short of the worst terms: a
    rejected message makes someone retype and resend it angrier, while a masked
    one simply loses its sting and the conversation carries on.
    """
    return pattern.sub(replacement, text)
