from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "english-learning-web"))

from review_scheduler import (  # noqa: E402
    apply_session,
    build_review_state,
    empty_history,
    make_word,
    record_success,
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

    def test_only_two_new_discoveries_enter_the_active_pipeline(self) -> None:
        history = empty_history()
        marked = [f"word{index}" for index in range(20)]
        plan = select_next_targets(history, 20, marked)
        self.assertEqual(len(plan["targetWords"]), 2)
        self.assertEqual(len(plan["admittedWords"]), 2)
        self.assertEqual(plan["deferredRecentCount"], 18)
        self.assertEqual(plan["inboxWaitingCount"], 18)
        self.assertEqual(plan["dueWords"], [])
        self.assertEqual(plan["totalDueCount"], 0)

    def test_active_pool_and_daily_article_are_both_bounded(self) -> None:
        history = empty_history()
        entries = {}
        for index in range(500):
            entry = make_word(f"due{index}", 1)
            entry["activationDay"] = 2
            entries[entry["word"]] = entry
        history["words"] = entries
        plan = select_next_targets(history, 10, [])
        self.assertEqual(plan["poolCounts"]["active"], 60)
        self.assertEqual(plan["poolCounts"]["inbox"], 120)
        self.assertEqual(plan["poolCounts"]["archive"], 320)
        self.assertEqual(len(plan["targetWords"]), 15)
        self.assertEqual(plan["totalDueCount"], 60)
        self.assertEqual(plan["deferredDueCount"], 45)
        self.assertEqual(plan["admittedWords"], [])

    def test_maintenance_is_limited_to_two_words_per_article(self) -> None:
        history = empty_history()
        entries = {}
        for index in range(20):
            entry = make_word(f"active{index}", 1)
            entry["activationDay"] = 2
            entries[entry["word"]] = entry
        for index in range(8):
            entry = make_word(f"maintenance{index}", 1)
            entry["activationDay"] = 2
            entry["status"] = "familiar"
            entries[entry["word"]] = entry
        history["words"] = entries
        plan = select_next_targets(history, 10, [])
        self.assertEqual(len(plan["maintenanceWords"]), 2)
        self.assertEqual(len(plan["activeDueWords"]), 13)
        self.assertEqual(len(plan["targetWords"]), 15)

    def test_word_is_archived_only_after_a_sixty_day_recall(self) -> None:
        entry = make_word("portrait", 1)
        entry["activationDay"] = 2
        entry["intervalIndex"] = 5
        entry["status"] = "familiar"
        record_success(entry, 62)
        self.assertEqual(entry["longIntervalSuccessCount"], 1)
        self.assertEqual(entry["status"], "mastered")

    def test_resurfaced_archived_word_is_reactivated(self) -> None:
        history = empty_history()
        entry = make_word("portrait", 1)
        entry["pool"] = "archive"
        history["words"] = {"portrait": entry}
        apply_session(
            history,
            {"day": 20, "reviewWords": [], "markedWords": ["portrait"]},
        )
        self.assertEqual(entry["activationDay"], 20)
        self.assertEqual(entry["nextReviewDay"], 21)

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
