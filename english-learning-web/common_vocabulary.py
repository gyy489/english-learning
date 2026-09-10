"""Frequency-based vocabulary checks shared by the web app and CLI tools."""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Iterable


WORDLIST_PATH = Path(__file__).resolve().parent / "data" / "common-english-5000.json"
WORD_PATTERN = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)?")

# Common irregular verbs whose past tense / past participle is not reachable
# by the regular suffix rules in word_forms() (e.g. "hang" -> "hung", not
# "hangs"/"hanging"/"hanged"). Without this, a model that correctly inflects
# an allowed or already-common verb irregularly (e.g. writing "hung" for the
# target word "hang", or "eaten" for the common word "eat") gets that form
# flagged as an unrelated rare word.
IRREGULAR_VERB_FORMS: dict[str, tuple[str, ...]] = {
    "be": ("am", "is", "are", "was", "were", "been", "being"),
    "become": ("became", "become"),
    "begin": ("began", "begun"),
    "break": ("broke", "broken"),
    "bring": ("brought",),
    "build": ("built",),
    "buy": ("bought",),
    "catch": ("caught",),
    "choose": ("chose", "chosen"),
    "come": ("came",),
    "do": ("does", "did", "done"),
    "draw": ("drew", "drawn"),
    "drink": ("drank", "drunk"),
    "drive": ("drove", "driven"),
    "eat": ("ate", "eaten"),
    "fall": ("fell", "fallen"),
    "feel": ("felt",),
    "find": ("found",),
    "fly": ("flew", "flown"),
    "forget": ("forgot", "forgotten"),
    "get": ("got", "gotten"),
    "give": ("gave", "given"),
    "go": ("went", "gone"),
    "grow": ("grew", "grown"),
    "hang": ("hung",),
    "have": ("has", "had"),
    "hear": ("heard",),
    "hide": ("hid", "hidden"),
    "hold": ("held",),
    "keep": ("kept",),
    "know": ("knew", "known"),
    "leave": ("left",),
    "lend": ("lent",),
    "lose": ("lost",),
    "make": ("made",),
    "mean": ("meant",),
    "meet": ("met",),
    "pay": ("paid",),
    "ride": ("rode", "ridden"),
    "ring": ("rang", "rung"),
    "rise": ("rose", "risen"),
    "run": ("ran",),
    "say": ("said",),
    "see": ("saw", "seen"),
    "sell": ("sold",),
    "send": ("sent",),
    "shine": ("shone",),
    "shoot": ("shot",),
    "show": ("showed", "shown"),
    "sing": ("sang", "sung"),
    "sit": ("sat",),
    "sleep": ("slept",),
    "speak": ("spoke", "spoken"),
    "spend": ("spent",),
    "stand": ("stood",),
    "steal": ("stole", "stolen"),
    "swim": ("swam", "swum"),
    "take": ("took", "taken"),
    "teach": ("taught",),
    "tear": ("tore", "torn"),
    "tell": ("told",),
    "think": ("thought",),
    "throw": ("threw", "thrown"),
    "understand": ("understood",),
    "wake": ("woke", "woken"),
    "wear": ("wore", "worn"),
    "win": ("won",),
    "write": ("wrote", "written"),
}
_IRREGULAR_FORM_TO_BASE: dict[str, str] = {
    form: base for base, forms in IRREGULAR_VERB_FORMS.items() for form in forms
}

# A few common compact expressions whose pieces do not reduce to a known
# base word through the suffix rules or the "'s" stripping above.
EXTRA_WORD_ALIASES: dict[str, str] = {
    "o'clock": "clock",
}


@lru_cache(maxsize=1)
def load_word_ranks(path: str | None = None) -> dict[str, int]:
    """Load the checked-in top-5000 list as a word-to-rank mapping."""
    selected = Path(path) if path else WORDLIST_PATH
    if not selected.exists():
        raise FileNotFoundError(
            f"高频词表不存在：{selected}。请运行 scripts/build_common_words.py。"
        )
    payload = json.loads(selected.read_text(encoding="utf-8"))
    ranks = payload.get("ranks")
    if not isinstance(ranks, dict):
        raise RuntimeError("高频词表格式错误：缺少 ranks")
    return {
        str(word).lower(): int(rank)
        for word, rank in ranks.items()
        if isinstance(word, str) and isinstance(rank, int)
    }


def word_forms(raw_word: str) -> set[str]:
    """Return practical inflection candidates without pretending to be a full lemmatizer."""
    word = raw_word.strip().lower().replace("’", "'")
    if not word:
        return set()
    forms = {word}
    if word.endswith("'s"):
        forms.add(word[:-2])
    if len(word) > 4 and word.endswith("ies"):
        forms.add(word[:-3] + "y")
    if len(word) > 5 and word.endswith("ing"):
        stem = word[:-3]
        forms.add(stem)
        if len(stem) > 2 and stem[-1:] == stem[-2:-1]:
            forms.add(stem[:-1])
        forms.add(stem + "e")
    if len(word) > 4 and word.endswith("ed"):
        stem = word[:-2]
        forms.add(stem)
        if stem.endswith("i"):
            forms.add(stem[:-1] + "y")
        if len(stem) > 2 and stem[-1:] == stem[-2:-1]:
            forms.add(stem[:-1])
        forms.add(stem + "e")
    if len(word) > 3 and word.endswith("es"):
        forms.add(word[:-2])
        forms.add(word[:-1])
    if len(word) > 3 and word.endswith("s"):
        forms.add(word[:-1])
    if word in IRREGULAR_VERB_FORMS:
        forms.update(IRREGULAR_VERB_FORMS[word])
    base = _IRREGULAR_FORM_TO_BASE.get(word)
    if base:
        forms.add(base)
    alias = EXTRA_WORD_ALIASES.get(word)
    if alias:
        forms.add(alias)
    return {form for form in forms if form}


def _normalise_allowed(words: Iterable[object]) -> set[str]:
    allowed: set[str] = set()
    for raw in words:
        match = WORD_PATTERN.search(str(raw))
        if match:
            allowed.update(word_forms(match.group(0)))
    return allowed


def vocabulary_report(
    text: str,
    *,
    allowed_words: Iterable[object] = (),
    known_words: Iterable[object] = (),
    max_rank: int = 5000,
) -> dict[str, object]:
    """Find content words outside the project high-frequency vocabulary list.

    This is intentionally conservative: it marks words for an editor to replace
    rather than attempting to decide that a rare word is always wrong.
    """
    ranks = load_word_ranks()
    allowed = _normalise_allowed(allowed_words)
    allowed.update(_normalise_allowed(known_words))
    flagged: dict[str, dict[str, object]] = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        for match in WORD_PATTERN.finditer(line):
            raw = match.group(0).lower().replace("’", "'")
            forms = word_forms(raw)
            rank = min((ranks[form] for form in forms if form in ranks), default=None)
            if raw in allowed or forms.intersection(allowed) or (rank is not None and rank <= max_rank):
                continue
            entry = flagged.setdefault(
                raw,
                {"word": raw, "count": 0, "lines": []},
            )
            entry["count"] = int(entry["count"]) + 1
            lines = entry["lines"]
            if isinstance(lines, list) and line_number not in lines:
                lines.append(line_number)
    words = sorted(
        flagged.values(),
        key=lambda entry: (-int(entry["count"]), str(entry["word"])),
    )
    return {
        "maxRank": max_rank,
        "flaggedWords": words,
        "flaggedCount": len(words),
        "tokenCount": len(WORD_PATTERN.findall(text)),
    }


def report_words(report: dict[str, object], limit: int = 80) -> list[str]:
    entries = report.get("flaggedWords", [])
    if not isinstance(entries, list):
        return []
    return [
        str(entry.get("word", ""))
        for entry in entries[:limit]
        if isinstance(entry, dict) and entry.get("word")
    ]
