from pathlib import Path
import sys
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "english-learning-web"))

from server import (  # noqa: E402
    choose_listening_source,
    generation_mode,
    listening_source_units,
    persistent_server_enabled,
    review_dashboard_payload,
    validate_generated_article,
)


class GenerationModeTests(unittest.TestCase):
    def test_clean_load_uses_a_listening_source(self) -> None:
        mode = generation_mode(5, 3, 0, 2, 4, 8)
        self.assertTrue(mode["usesSource"])
        self.assertEqual(mode["newWords"], "最多 2")
        self.assertEqual(mode["minimumSentences"], 50)
        self.assertEqual(mode["maximumSentences"], 70)

    def test_eight_target_words_keep_listening_story_but_add_no_new_words(self) -> None:
        mode = generation_mode(8, 4, 0, 1, 4, 8)
        self.assertTrue(mode["usesSource"])
        self.assertEqual(mode["sentenceCount"], "约 55-65")
        self.assertEqual(mode["minimumSentences"], 50)
        self.assertEqual(mode["newWords"], "0")

    def test_too_many_current_unknown_words_keep_listening_story(self) -> None:
        mode = generation_mode(5, 5, 0, 1, 6, 8)
        self.assertTrue(mode["usesSource"])
        self.assertEqual(mode["newWords"], "0")

    def test_due_backlog_keeps_listening_story_without_new_words(self) -> None:
        mode = generation_mode(5, 3, 1, 0, 3, 8)
        self.assertTrue(mode["usesSource"])
        self.assertEqual(mode["newWords"], "0")

    def test_large_inbox_keeps_listening_story_without_new_words(self) -> None:
        mode = generation_mode(4, 2, 0, 0, 2, 16)
        self.assertTrue(mode["usesSource"])
        self.assertEqual(mode["newWords"], "0")

    def test_dashboard_exposes_the_source_decision(self) -> None:
        history = {
            "summary": {"currentMarkedWords": 12},
            "nextPlan": {
                "targetWords": [f"word{index}" for index in range(12)],
                "recentWords": ["word0"],
                "deferredDueCount": 4,
                "newWordAllowance": 0,
                "inboxWaitingCount": 20,
            },
        }
        payload = review_dashboard_payload(history)
        self.assertTrue(payload["generationMode"]["usesSource"])
        self.assertEqual(payload["generationMode"]["newWords"], "0")

    def test_listening_transcripts_split_into_sixteen_sections(self) -> None:
        sections = listening_source_units()
        self.assertEqual(len(sections), 16)
        self.assertTrue(all(section["text"] for section in sections))
        self.assertEqual(choose_listening_source(41)["id"], choose_listening_source(41)["id"])

    def test_article_requires_listening_metadata_and_accepts_approximate_length(self) -> None:
        mode = generation_mode(2, 1)
        sentences = "\n\n".join(
            f"{number}. This is a common sentence.\n\n   > 这是一句常见的话。\n   >"
            for number in range(1, 51)
        )
        markdown = f"""# A Clear Story

- 天数：第 41 天
- 来源真题：Cambridge IELTS 1 Listening Test 1 / Section 1
- 来源文件：雅思真题/用于雅思学习skills数据/超给的资料/listening/cambridge-ielts-1/test1.md
- 听力片段：cambridge-ielts-1-test1-section1
- 复习内容：D40 当前生词 + 到期旧词 + 听力情节扩展

## 复习生词

- word - 词

## 正文

{sentences}

生单词:
"""
        validate_generated_article(markdown, 41, mode)

    def test_persistent_remote_mode_is_controlled_by_environment(self) -> None:
        with patch.dict("os.environ", {"ENGLISH_LEARNING_PERSISTENT": "1"}):
            self.assertTrue(persistent_server_enabled())
        with patch.dict("os.environ", {"ENGLISH_LEARNING_PERSISTENT": "0"}):
            self.assertFalse(persistent_server_enabled())


if __name__ == "__main__":
    unittest.main()
