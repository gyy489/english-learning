import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "english-learning-web"))

from server import (  # noqa: E402
    diagnose_previous_writing,
    complete_reading,
    create_writing_practice,
    save_writing_draft,
    submit_writing_attempt,
    write_json,
    writing_practice_path,
    writing_workspace_path,
)


class WritingPracticeTests(unittest.TestCase):
    def test_previous_draft_diagnosis_keeps_many_findings_but_selects_one_focus(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            article_path = Path(temporary) / "41_story.md"
            article_path.write_text("# Temporary\n", encoding="utf-8")
            self.make_practice(article_path)
            practice_path = writing_practice_path(article_path)
            practice = json.loads(practice_path.read_text(encoding="utf-8"))
            practice["draftText"] = "She go there yesterday. The students goes there too."
            write_json(practice_path, practice)
            diagnosis_json = json.dumps(
                {
                    "majorIssues": ["一般过去时错误", "主谓一致错误"],
                    "focusTitle": "一般过去时",
                    "focusExplanation": "过去事件仍使用了动词原形。",
                    "practiceInstruction": "用多个过去事件反复练习规则与不规则过去式。",
                },
                ensure_ascii=False,
            )
            with patch(
                "server.request_generated_text",
                return_value=(diagnosis_json, "test model", False),
            ):
                diagnosis = diagnose_previous_writing(41, article_path)
            self.assertEqual(len(diagnosis["majorIssues"]), 2)
            self.assertEqual(diagnosis["focusTitle"], "一般过去时")

    def test_writing_workspace_puts_single_focus_above_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            article_path = Path(temporary) / "41_story.md"
            article_path.write_text("# Temporary\n", encoding="utf-8")
            self.make_practice(article_path)
            practice_path = writing_practice_path(article_path)
            practice = json.loads(practice_path.read_text(encoding="utf-8"))
            practice["writingFocus"] = {
                "sourceDay": 40,
                "majorIssues": ["一般过去时", "主谓一致"],
                "focusTitle": "一般过去时",
                "focusExplanation": "过去事件的动词形式不稳定。",
                "practiceInstruction": "统一使用一般过去时。",
            }
            write_json(practice_path, practice)
            from server import write_writing_workspace

            write_writing_workspace(article_path, practice)
            workspace = writing_workspace_path(article_path).read_text(encoding="utf-8")
            focus_position = workspace.index("## 本次只解决一个问题")
            prompt_position = workspace.index("## 中文题目")
            self.assertLess(focus_position, prompt_position)
            self.assertIn("**一般过去时**", workspace)

    def make_practice(self, article_path: Path) -> None:
        write_json(
            writing_practice_path(article_path),
            {
                "version": 1,
                "day": 41,
                "articlePath": "temporary/41_story.md",
                "readingCompletedAt": None,
                "title": "A Clear Plan",
                "instructions": "用常见英语完成表达。",
                "paragraphs": ["一名学生先发现问题。", "后来他做了一个计划并解决问题。"],
                "suggestedWords": ["plan"],
                "attempts": [],
            },
        )

    def test_completion_unlocks_practice_and_repeated_submission_is_saved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            article_path = Path(temporary) / "41_story.md"
            article_path.write_text("# Temporary\n", encoding="utf-8")
            self.make_practice(article_path)
            with patch("server.article_for_day", return_value=(41, article_path)):
                completed = complete_reading(41)
                self.assertTrue(completed["available"])
                self.assertTrue(completed["readingCompleted"])
                saved_draft = save_writing_draft(
                    41,
                    "The student made a plan.\n\nThen the problem was solved.",
                    ["The student made a plan.", "Then the problem was solved."],
                )
                self.assertTrue(saved_draft["saved"])
                workspace = writing_workspace_path(article_path)
                self.assertTrue(workspace.exists())
                self.assertIn("当前英文草稿", workspace.read_text(encoding="utf-8"))
                self.assertIn("第 1 段", workspace.read_text(encoding="utf-8"))
                self.assertIn("The student made a plan", workspace.read_text(encoding="utf-8"))

                model_result = json.dumps(
                    {
                        "correctedText": "The student made a plan and solved the problem.",
                        "feedback": ["注意过去式。"],
                        "usedTargetWords": ["plan"],
                        "suggestions": [],
                        "coverage": ["主要因果关系完整。"],
                    }
                )
                with patch("server.load_project_env"), patch(
                    "server.refresh_review_documents", return_value=({"words": {}}, {})
                ), patch(
                    "server.request_generated_text",
                    return_value=(model_result, "test model", False),
                ):
                    result = submit_writing_attempt(
                        41,
                        "The student make a plan and solve the problem.",
                        "natural",
                    )
            self.assertEqual(result["attempt"]["id"], 1)
            self.assertEqual(result["attempt"]["usedTargetWords"], ["plan"])
            self.assertEqual(len(result["practice"]["attempts"]), 1)
            workspace_text = writing_workspace_path(article_path).read_text(encoding="utf-8")
            self.assertIn("网页订正", workspace_text)
            self.assertIn("注意过去式。", workspace_text)

    def test_submission_shows_correction_next_to_each_paragraph(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            article_path = Path(temporary) / "41_story.md"
            article_path.write_text("# Temporary\n", encoding="utf-8")
            self.make_practice(article_path)
            with patch("server.article_for_day", return_value=(41, article_path)):
                save_writing_draft(
                    41,
                    "The student made a plan.\n\nThen the problem was solved.",
                    ["The student made a plan.", "Then the problem was solved."],
                )
                model_result = json.dumps(
                    {
                        "correctedText": (
                            "The student noticed a problem.\n\n"
                            "Then she made a plan and solved it."
                        ),
                        "feedback": [],
                        "usedTargetWords": ["plan"],
                        "suggestions": [],
                        "coverage": [],
                    }
                )
                with patch("server.load_project_env"), patch(
                    "server.refresh_review_documents", return_value=({"words": {}}, {})
                ), patch(
                    "server.request_generated_text",
                    return_value=(model_result, "test model", False),
                ):
                    submit_writing_attempt(
                        41,
                        "The student made a plan.\n\nThen the problem was solved.",
                        "natural",
                    )
            workspace_text = writing_workspace_path(article_path).read_text(encoding="utf-8")
            # Each paragraph's correction should sit right after its own draft,
            # not only in the submission history at the bottom of the file.
            first_paragraph = workspace_text.split("### 第 2 段")[0]
            self.assertIn("#### 订正", first_paragraph)
            self.assertIn("The student noticed a problem.", first_paragraph)
            self.assertNotIn("Then she made a plan and solved it.", first_paragraph)

    def test_historical_article_can_create_a_practice_on_demand(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=project_root) as temporary:
            temporary_root = Path(temporary)
            article_path = temporary_root / "40_story.md"
            article_path.write_text(
                """# A Story

## 复习生词

- plan - 计划

## 正文

1. The student made a plan.

   > 学生制定了一个计划。
   >

生单词:
""",
                encoding="utf-8",
            )
            generated = json.dumps(
                {
                    "title": "一个清晰的计划",
                    "instructions": "用常见英语表达。",
                    "paragraphs": ["学生先发现一个问题。", "后来他想出了一个计划。"],
                    "suggestedWords": ["plan"],
                }
            )
            with patch("server.load_project_env"), patch(
                "server.PROJECT_ROOT", temporary_root
            ), patch("server.article_for_day", return_value=(40, article_path)), patch(
                "server.request_generated_text", return_value=(generated, "test model", False)
            ):
                practice = create_writing_practice(40)
            self.assertTrue(practice["available"])
            self.assertTrue(practice["readingCompleted"])
            self.assertEqual(practice["suggestedWords"], ["plan"])

    def test_generated_practice_accepts_a_draft_before_completion_is_marked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            article_path = Path(temporary) / "41_story.md"
            article_path.write_text("# Temporary\n", encoding="utf-8")
            self.make_practice(article_path)
            with patch("server.article_for_day", return_value=(41, article_path)):
                saved = save_writing_draft(41, "The student made a plan.")
            self.assertTrue(saved["saved"])
            self.assertIn(
                "The student made a plan.",
                writing_workspace_path(article_path).read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
