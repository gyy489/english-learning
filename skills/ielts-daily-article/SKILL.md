---
name: ielts-daily-article
description: Generate daily English learning articles from this project, reusing the user's unresolved vocabulary and grounding new topics in converted IELTS reading Markdown sources. Use when the user says 更新, generate today's article, continue the vocabulary loop, create an IELTS-based practice article, or maintain this English-learning project.
---

# IELTS Daily Article

Use this skill inside `/path/to/user` to continue the user's daily English-learning loop.

## Core Goal

Generate one readable English article per day for IELTS 6.0-oriented practice. Each new article must:

- reuse the unresolved words from the previous article's `生单词:` section;
- use a converted IELTS reading source only when the previous unresolved vocabulary count is 15 or fewer;
- paraphrase and simplify source ideas instead of copying long passages;
- keep the user's stable format: vocabulary review, numbered English sentences, Chinese explanation under each sentence, and an empty `生单词:` section at the end;
- adjust article length and new vocabulary load according to the previous article's unresolved word count;
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
2. Read the previous file's bottom `生单词:` section.
3. Count the previous unresolved words/phrases, then choose the vocabulary-load mode. Count each non-empty entry under `生单词:`; if one line contains multiple comma- or semicolon-separated words/phrases, count each item separately.
   - **Vocabulary-only review mode**: if the previous `生单词:` count is greater than 15, do not read or use an IELTS source. Build a simple, coherent article only around the previous words, introduce no new target vocabulary, and keep the language easier than normal.
   - **Light-load source mode**: if the previous `生单词:` count is 0-5, combine the previous words with a new IELTS source, make the article longer with about 40 numbered English sentences, and allow a modest amount of new IELTS-style vocabulary from the source.
   - **Normal source mode**: if the previous `生单词:` count is 6-15, combine the previous words with a new IELTS source, write at least 30 numbered English sentences, and introduce a small set of useful IELTS-style words or phrases.
4. Normalize the previous words to dictionary forms where appropriate, then add concise Chinese meanings in the new article's `## 复习生词`.
5. If the previous word count is 15 or fewer, select one IELTS source from `readingpractice-index.json`. If it is greater than 15, skip source selection completely and write `无（纯生词复习）` in both source metadata fields.
   - Prefer `P1` or accessible `P2` for IELTS 6.0 practice.
   - Use `P3` only when the user asks for harder reading, or when simplifying a difficult topic.
   - Avoid using the same source repeatedly if recent articles already used it.
6. In a source mode, read the selected source Markdown. In vocabulary-only review mode, use only the previous words and their meanings as content input.
7. Generate a new article using the selected load mode. In a source mode, use the source topic and facts while keeping the text original and easier. In vocabulary-only review mode, create a simple everyday narrative or explanation that naturally reuses all previous words without introducing a new subject vocabulary set.
8. Save the next article in a day folder under `作文素材/按时间排序/` using the next two-digit number and an English slug, e.g. `17_food_traditions/17_food_traditions.md`.
9. Generate listening audio from the Markdown article and save it in the same day folder as `17_food_traditions.mp3`.

## Article Format

Use this exact structure:

```markdown
# English Title

- 天数：第 N 天
- 来源真题：<IELTS source title>
- 来源文件：<relative markdown path>
- 复习内容：D(N-1) 生词复用 + IELTS 阅读主题改写

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

- Use the selected vocabulary-load mode to set length, source usage, and new vocabulary pressure:
  - Previous `生单词:` count greater than 15: do not use an IELTS source, write about 25-30 simple English sentences, and introduce no new target vocabulary.
  - Previous `生单词:` count 0-5: combine the words with a new IELTS source and write about 40 English sentences.
  - Previous `生单词:` count 6-15: combine the words with a new IELTS source and write at least 30 English sentences.
- Target IELTS 5.5-6.0 readability even when the source is harder.
- Keep sentences natural, concrete, and suitable for reading aloud.
- Reuse every previous unresolved word at least once in the English body, with correct inflection if needed.
- Introduce new IELTS-style words or phrases according to the selected load mode:
  - Vocabulary-only review mode: 0 new target words and no IELTS source; keep vocabulary familiar and reuse-focused.
  - Light-load source mode: 6-10 useful IELTS-style words or phrases from the source topic.
  - Normal source mode: 4-8 useful IELTS-style words or phrases from the source topic.
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
