PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def fa_digits(value: object) -> str:
    """Render numbers with Persian digits.

    API validation messages are shown to the user verbatim, and Latin digits
    inside a Persian sentence read as a bug to a Persian speaker.
    """
    return str(value).translate(PERSIAN_DIGITS)
