from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "english-learning-web"))

from review_scheduler import (  # noqa: E402
    build_review_state,
    empty_history,
    make_word,
    select_next_targets,
)


class ReviewSchedulerTests(unittest.TestCase):
    def test_success_moves_word_to_three_day_interval(self) -> None:
        snapshots = [
            {"day": 1, "reviewWords": [], "markedWords": ["portrait"], "meanings": {}},
            {"day": 2, "reviewWords": ["portrait"], "markedWords": [], "meanings": {}},
        ]
        history, plan = build_review_state(snapshots)
        entry = history["words"]["portrait"]
        self.assertEqual(entry["nextReviewDay"], 5)
        self.assertEqual(entry["successCount"], 1)
        self.assertEqual(plan["targetWords"], [])

    def test_failure_resets_word_to_next_day(self) -> None:
        snapshots = [
            {"day": 1, "reviewWords": [], "markedWords": ["stir"], "meanings": {}},
            {"day": 2, "reviewWords": ["stir"], "markedWords": ["stir"], "meanings": {}},
        ]
        history, plan = build_review_state(snapshots)
        entry = history["words"]["stir"]
        self.assertEqual(entry["nextReviewDay"], 3)
        self.assertEqual(entry["lapseCount"], 1)
        self.assertEqual(plan["targetWords"], ["stir"])

    def test_recent_words_are_capped_at_fifteen(self) -> None:
        history = empty_history()
        marked = [f"word{index}" for index in range(20)]
        plan = select_next_targets(history, 20, marked)
        self.assertEqual(len(plan["targetWords"]), 15)
        self.assertEqual(plan["deferredRecentCount"], 5)
        self.assertEqual(plan["dueWords"], [])
        self.assertEqual(plan["totalDueCount"], 0)

    def test_six_recent_words_allow_four_due_words(self) -> None:
        history = empty_history()
        history["words"] = {
            f"due{index}": make_word(f"due{index}", 1)
            for index in range(8)
        }
        marked = [f"recent{index}" for index in range(6)]
        plan = select_next_targets(history, 10, marked)
        self.assertEqual(len(plan["recentWords"]), 6)
        self.assertEqual(len(plan["dueWords"]), 4)
        self.assertEqual(len(plan["targetWords"]), 10)
        self.assertEqual(plan["deferredDueCount"], 4)

    def test_review_habits_are_derived_from_completed_sessions(self) -> None:
        snapshots = [
            {"day": 1, "reviewWords": [], "markedWords": ["stir"], "meanings": {}},
            {
                "day": 2,
                "reviewWords": ["stir", "portrait"],
                "markedWords": ["portrait"],
                "meanings": {},
            },
            {"day": 3, "reviewWords": ["portrait"], "markedWords": [], "meanings": {}},
        ]
        history, _ = build_review_state(snapshots)
        habits = history["habits"]
        self.assertEqual(habits["completedSessions"], 2)
        self.assertEqual(habits["totalReviewAttempts"], 2)
        self.assertEqual(habits["overallRecallRate"], 50)
        self.assertEqual(habits["averageMarkedWords"], 1.0)


if __name__ == "__main__":
    unittest.main()
