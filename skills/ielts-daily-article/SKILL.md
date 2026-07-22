---
name: ielts-daily-article
description: Generate daily English learning articles from this project, reusing the user's unresolved vocabulary and grounding new topics in converted IELTS reading Markdown sources. Use when the user says 更新, generate today's article, continue the vocabulary loop, create an IELTS-based practice article, or maintain this English-learning project.
---

# IELTS Daily Article

Use this skill inside `/path/to/user` to continue the user's daily English-learning loop.

## Core Goal

Generate one readable English article per day for IELTS 6.0-oriented practice. Each new article must:

- reuse unresolved words from the previous article and add a small number of due words from `作文素材/单词复习/vocabulary.json`;
- keep the complete target review list at 15 words or fewer;
- use a converted IELTS reading source only when the review load allows new input;
- paraphrase and simplify source ideas instead of copying long passages;
- keep the user's stable format: vocabulary review, numbered English sentences, Chinese explanation under each sentence, and an empty `生单词:` section at the end;
- adjust article length and new vocabulary load according to the combined current-word and due-word load;
- include a listening audio file in the same day folder as the Markdown article.

## Data Sources

Use these project paths:

- Daily article output: `作文素材/按时间排序/`
- IELTS reading index: `雅思真题/Markdown资料/7月阅读/ReadingPractice/readingpractice-index.json`
- IELTS reading Markdown files: `雅思真题/Markdown资料/7月阅读/ReadingPractice/PDF/`
- Dataset summary: `雅思真题/Markdown资料/7月阅读/ReadingPractice/dataset-summary.json`

Read `references/source-data.md` only when dataset details, selection policy, or quality notes are needed.

## Daily Update Workflow

1. Find the latest numbered day folder or Markdown file in `作文素材/按时间排序/`.
2. Read the previous file's bottom `生单词:` section and rebuild the document-backed review state in `作文素材/单词复习/` from all daily Markdown files.
3. Select no more than 15 target review words, in this order:
   - Keep bounded pools: inbox 120, active learning 60, maintenance 120, then archive.
   - Put still-forgotten or resurfaced words first, up to 10.
   - Reserve at most 2 positions for due maintenance words.
   - Fill remaining positions with due active-pool words.
   - Only when no due word is deferred and the active pool has room, activate at most 2 inbox words.
   - Archive overflow instead of scheduling it; preserve its history and reactivate it if the user marks it again.
4. Normalize all selected words to dictionary forms, then add concise Chinese meanings in the new article's `## 复习生词`.
5. Choose the vocabulary-load mode from the total selected load:
   - **High-load review mode**: 11 or more current words; no IELTS source and 0 new target words.
   - **Due-backlog cleanup mode**: any due historical words remain deferred; use an IELTS source, write at least 30 sentences, and add 0 new target words until the backlog is cleared.
   - **Light-load source mode**: 0-7 total target words; about 36-40 sentences and use only the scheduler's 0-2 new-word allowance.
   - **Normal spaced-review mode**: 8-11 total target words; at least 30 sentences and use only the scheduler's 0-2 new-word allowance.
   - **High review load with source**: 12-15 total target words but fewer than 11 current words; at least 30 sentences and 0 new target words.
6. In a source mode, select one IELTS source from `readingpractice-index.json`. In high-load review mode, skip source selection and write `无（纯生词复习）` in both source metadata fields.
   - Prefer `P1` or accessible `P2` for IELTS 6.0 practice.
   - Use `P3` only when the user asks for harder reading, or when simplifying a difficult topic.
   - Avoid using the same source repeatedly if recent articles already used it.
7. In a source mode, read the selected source Markdown. In high-load review mode, use only the target review words and their meanings as content input.
8. Generate a new article using the selected load mode. Every target review word must appear naturally at least once.
9. Save the next article in a day folder under `作文素材/按时间排序/` using the next two-digit number and an English slug, e.g. `17_food_traditions/17_food_traditions.md`.
10. Generate listening audio from the Markdown article and save it in the same day folder as `17_food_traditions.mp3`.
11. Rebuild `vocabulary.json` and `review-history.md` after the new article is saved.

## Article Format

Use this exact structure:

```markdown
# English Title

- 天数：第 N 天
- 来源真题：<IELTS source title>
- 来源文件：<relative markdown path>
- 复习内容：D(N-1) 当前生词 + 到期旧词 + 当前模式

## 复习生词

- word - 中文释义

## 正文

1. English sentence.

   > 中文解释。
   >

2. English sentence.

   > 中文解释。
   >

生单词:
```

## Writing Rules

- Never put more than 15 target review words into one article.
- Use the selected spaced-review mode to set length, source usage, and new vocabulary pressure.
- Target IELTS 5.5-6.0 readability even when the source is harder.
- Keep sentences natural, concrete, and suitable for reading aloud.
- Reuse every selected target word at least once in the English body, with correct inflection if needed.
- Introduce new IELTS-style words or phrases according to the selected load mode:
  - High-load review mode: 0 new target words and no IELTS source.
  - Due-backlog cleanup mode: 0 new target words while any due historical words remain deferred.
  - Light-load source mode: never exceed the scheduler's 0-2 new-word allowance.
  - Normal spaced-review mode: never exceed the scheduler's 0-2 new-word allowance.
  - 12-15 total target words: 0 new target words.
- Put Chinese explanations directly under each English sentence.
- Do not fill in the final `生单词:` section for the user.
- Do not copy more than one short phrase from the source. Summarize and adapt ideas in original wording.

## Source Tracking

When saving a source-mode article, include the selected source path in the front matter-style bullet list near the top. In vocabulary-only review mode, write `无（纯生词复习）` in both source fields. If a selected source has useful images, mention the source image only when relevant; do not copy images into the daily article unless the user asks.

## Listening Audio

After saving the article, run:

```bash
uv run --with openai python scripts/article_to_speech.py "<day-folder>/<article>.md" --force
```

The script reads only the English sentences in `## 正文` and writes the `.mp3` next to the article by default. It uses `OPENAI_API_KEY` from the environment or project `.env`.

Default speech model is the lower-cost `tts-1`. Use `--model gpt-4o-mini-tts` when instruction-controlled delivery is worth the additional cost, or `--model tts-1-hd` only when higher audio quality is explicitly needed. The web app's default article model is `gpt-4o-mini`.

If `OPENAI_API_KEY` is missing, run the script anyway. It will leave the article complete, create `.env.example` in the project root, create `OPENAI_API_KEY_REQUIRED.md` in the day folder, and stop before calling the OpenAI API.
