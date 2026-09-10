from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "english-learning-web"))

from common_vocabulary import load_word_ranks, report_words, vocabulary_report  # noqa: E402


class CommonVocabularyTests(unittest.TestCase):
    def test_local_wordlist_contains_top_five_thousand_words(self) -> None:
        ranks = load_word_ranks()
        self.assertEqual(len(ranks), 5000)
        self.assertEqual(ranks["the"], 1)
        self.assertLessEqual(ranks["ability"], 5000)

    def test_report_allows_target_words_but_flags_rare_candidates(self) -> None:
        report = vocabulary_report(
            "The student made a meticulous plan for the garden.",
            allowed_words=["garden"],
        )
        self.assertIn("meticulous", report_words(report))
        self.assertNotIn("garden", report_words(report))

    def test_report_accepts_common_inflections(self) -> None:
        report = vocabulary_report("The students were walking home after dinner.")
        self.assertEqual(report_words(report), [])

    def test_report_accepts_irregular_forms_of_target_words(self) -> None:
        # "hang" is a target word; the model correcting to its irregular past
        # tense "hung" should not be treated as introducing a new rare word.
        report = vocabulary_report(
            "An old map was hung on the fence near the gate.",
            allowed_words=["hang"],
        )
        self.assertNotIn("hung", report_words(report))

    def test_report_accepts_irregular_forms_of_common_words(self) -> None:
        # "eat" is already inside the top-5000 list; its irregular participle
        # "eaten" should inherit that rank instead of being flagged as rare.
        report = vocabulary_report("She had already eaten before the queue moved.")
        self.assertNotIn("eaten", report_words(report))

    def test_report_accepts_oclock(self) -> None:
        # "clock" is common, but "o'clock" does not reduce to it through the
        # regular suffix rules, so it needs an explicit alias.
        report = vocabulary_report("They arrived at one o'clock sharp.")
        self.assertNotIn("o'clock", report_words(report))


if __name__ == "__main__":
    unittest.main()
