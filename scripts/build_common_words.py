#!/usr/bin/env python3
"""Build the project's local top-5000 English frequency list.

Usage:
  uv run --with wordfreq python scripts/build_common_words.py
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import re

from wordfreq import top_n_list


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "english-learning-web" / "data" / "common-english-5000.json"
WORD_PATTERN = re.compile(r"^[a-z]+(?:'[a-z]+)?$")
WORD_LIMIT = 5000


def main() -> None:
    words: list[str] = []
    seen: set[str] = set()
    # Request more than 5000 because the source also contains punctuation and
    # a small number of tokens unsuitable for a word-by-word article checker.
    for raw_word in top_n_list("en", WORD_LIMIT * 2):
        word = raw_word.strip().lower().replace("’", "'")
        if not WORD_PATTERN.fullmatch(word) or word in seen:
            continue
        seen.add(word)
        words.append(word)
        if len(words) == WORD_LIMIT:
            break
    if len(words) != WORD_LIMIT:
        raise RuntimeError(f"词表只生成了 {len(words)} 个词，预期 {WORD_LIMIT} 个")

    payload = {
        "version": 1,
        "source": "wordfreq.top_n_list('en', 10000)",
        "description": "English high-frequency words for IELTS learning validation.",
        "generatedAt": datetime.now(UTC).isoformat(),
        "coreLimit": 3000,
        "maximumRank": WORD_LIMIT,
        "ranks": {word: index for index, word in enumerate(words, start=1)},
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Generated {len(words)} words: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
