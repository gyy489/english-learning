from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "english-learning-web"))

from server import generation_mode, review_dashboard_payload  # noqa: E402


class GenerationModeTests(unittest.TestCase):
    def test_clean_light_load_can_use_ielts_source(self) -> None:
        mode = generation_mode(5, 3, 0, 2, 4, 8)
        self.assertTrue(mode["usesSource"])
        self.assertEqual(mode["newWords"], "最多 2")

    def test_eight_target_words_disable_ielts_source(self) -> None:
        mode = generation_mode(8, 4, 0, 1, 4, 8)
        self.assertFalse(mode["usesSource"])

    def test_too_many_current_unknown_words_disable_source(self) -> None:
        mode = generation_mode(5, 5, 0, 1, 6, 8)
        self.assertFalse(mode["usesSource"])

    def test_due_backlog_disables_source(self) -> None:
        mode = generation_mode(5, 3, 1, 0, 3, 8)
        self.assertFalse(mode["usesSource"])
        self.assertEqual(mode["newWords"], "0")

    def test_large_inbox_disables_source(self) -> None:
        mode = generation_mode(4, 2, 0, 0, 2, 16)
        self.assertFalse(mode["usesSource"])

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
        self.assertFalse(payload["generationMode"]["usesSource"])


if __name__ == "__main__":
    unittest.main()
