"""Applying the word filter to a message."""

from dataclasses import dataclass

from apps.moderation.models import Severity, compiled_words


@dataclass
class FilterResult:
    text: str
    masked: bool
    blocked: bool

    @property
    def clean(self) -> bool:
        return not (self.masked or self.blocked)


def screen(text: str) -> FilterResult:
    """Run a message past the word filter.

    Two outcomes rather than one: most terms are masked so the conversation
    continues without the insult, while the worst are refused outright. A
    filter that only ever rejects teaches people to test it; a filter that only
    ever masks lets the genuinely abusive keep talking.
    """
    if not text:
        return FilterResult(text=text, masked=False, blocked=False)

    result = text
    masked = False

    for severity, pattern in compiled_words():
        if not pattern.search(result):
            continue
        if severity == Severity.BLOCK:
            return FilterResult(text=text, masked=False, blocked=True)
        result = pattern.sub("***", result)
        masked = True

    return FilterResult(text=result, masked=masked, blocked=False)
