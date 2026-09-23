from functools import lru_cache

from django.core.cache import cache
from django.db import models

from apps.moderation.text import build_pattern

CACHE_KEY = "moderation:banned_words"
CACHE_TTL = 300


class Severity(models.TextChoices):
    MASK = "MASK", "پوشاندن"
    BLOCK = "BLOCK", "رد کردن پیام"


class BannedWord(models.Model):
    """The word filter's vocabulary, editable by moderators.

    In the database rather than in code for the same reason the prompts are:
    the list is never finished. A term that starts appearing on a Tuesday
    should be filterable that Tuesday, without a deploy and without a developer.
    """

    word = models.CharField(max_length=64, unique=True)
    severity = models.CharField(
        max_length=5, choices=Severity.choices, default=Severity.MASK
    )
    # On by default. Persian obscenities are often spelled inside innocent
    # words — "کس" sits in "عکس" and "هرکس" — so matching a bare substring
    # produces false positives that read as a broken app. Turn this off only
    # for stems that are never part of an ordinary word.
    whole_word = models.BooleanField(default=True)
    note = models.CharField(max_length=120, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("word",)

    def __str__(self) -> str:
        return f"{self.word} ({self.severity})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        cache.delete(CACHE_KEY)

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        cache.delete(CACHE_KEY)


def active_words() -> tuple[tuple[str, str, bool], ...]:
    """(severity, word, whole_word) for every active entry, cached in Redis.

    The *words* are cached, not the compiled patterns. Caching patterns looks
    like an optimisation and is a trap: a change to how matching works would
    then keep using the previously-compiled regexes until the cache expired,
    so a deployed fix would appear not to work for five minutes.
    """
    cached = cache.get(CACHE_KEY)
    if cached is not None:
        return cached

    rows = tuple(
        (row.severity, row.word, row.whole_word)
        for row in BannedWord.objects.filter(is_active=True)
    )
    cache.set(CACHE_KEY, rows, CACHE_TTL)
    return rows


@lru_cache(maxsize=8)
def _compile(rows: tuple[tuple[str, str, bool], ...]):
    return [
        (severity, build_pattern(word, whole_word=whole_word))
        for severity, word, whole_word in rows
    ]


def compiled_words():
    """(severity, pattern) for every active word.

    Compilation happens per process and is memoised on the exact word list, so
    an unchanged list costs one dict lookup per message and a changed one
    recompiles immediately.
    """
    return _compile(active_words())
