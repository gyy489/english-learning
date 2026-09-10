#!/usr/bin/env python3
"""Validate an article against the project's local top-5000 word list."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "english-learning-web"))

from common_vocabulary import report_words, vocabulary_report  # noqa: E402


def article_body(text: str) -> str:
    if "## 正文" not in text:
        return text
    body = text.split("## 正文", 1)[1]
    return body.split("生单词:", 1)[0]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="检查 Markdown 是否只使用项目高频词表")
    parser.add_argument("markdown", type=Path, help="待检查的 Markdown 文件")
    parser.add_argument("--max-rank", type=int, default=5000)
    parser.add_argument("--allow", action="append", default=[], help="额外允许的复习词，可重复传入")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    text = args.markdown.read_text(encoding="utf-8")
    report = vocabulary_report(
        article_body(text),
        allowed_words=args.allow,
        max_rank=args.max_rank,
    )
    words = report_words(report)
    if not words:
        print(f"PASS: {args.markdown} 未发现超出前 {args.max_rank} 高频词范围的候选词。")
        return 0
    print(
        f"CHECK: {args.markdown} 发现 {len(words)} 个候选偏词："
        + ", ".join(words)
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
