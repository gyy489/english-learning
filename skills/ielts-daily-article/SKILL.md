---
name: ielts-daily-article
description: Generate daily English learning articles from this project, reusing the user's unresolved vocabulary and grounding story structure in the user's converted Cambridge listening transcripts. Use when the user says 更新, generate today's article, continue the vocabulary loop, create an IELTS-based practice article, or maintain this English-learning project.
---

# IELTS Daily Article

Use this skill from the project root to continue the user's daily English-learning loop.

## Core Goal

Generate one readable English article per day for IELTS 6.5-oriented practice. Each new article must:

- reuse unresolved words from the previous article and add a small number of due words from `作文素材/单词复习/vocabulary.json`;
- keep the complete target review list at 15 words or fewer;
- use one converted Cambridge listening Section as the story and information-structure source in every load mode;
- paraphrase and simplify the listening situation instead of copying long passages;
- keep incidental vocabulary outside the target list to a small, very common set (see Vocabulary Limits), so every unfamiliar word the learner meets is one that will realistically come up again;
- keep the user's stable format: vocabulary review, numbered English sentences, Chinese explanation under each sentence, and an empty `生单词:` section at the end;
- target roughly 55-65 sentences (50-70 is acceptable) and adjust only new-vocabulary pressure according to the combined current-word and due-word load;
- include a listening audio file in the same day folder as the Markdown article.

## Data Sources

Use these project paths:

- Daily article output: `作文素材/按时间排序/`
- Listening transcripts: `雅思真题/用于雅思学习skills数据/超给的资料/listening/cambridge-ielts-1/test*.md`
- Local high-frequency word list: `english-learning-web/data/common-english-5000.json`
- CLI validator: `scripts/verify_common_vocabulary.py`

The old converted-reading dataset is retained for history but is not a generation source.

## Daily Update Workflow

1. Find the latest numbered day folder or Markdown file in `作文素材/按时间排序/`.
2. Read the previous file's bottom `生单词:` section and rebuild the document-backed review state in `作文素材/单词复习/` from all daily Markdown files.
3. Read the previous day's latest English writing draft (prefer the latest submitted `originalText`, then the saved draft). Diagnose 2-4 serious recurring problems, but select exactly one narrow problem as the next day's writing focus. If there is no draft, do not invent a focus.
   - Prefer a repeated foundational error that affects clarity or IELTS scoring.
   - The focus must be one teachable item such as simple past tense, subject-verb agreement, or `although` without `but`; never combine two items with “and”.
   - Save the diagnosis and the single selected focus in the next day's writing-practice JSON.
4. Select no more than 15 target review words, in this order:
   - Keep bounded pools: inbox 120, active learning 60, maintenance 120, then archive.
   - Put still-forgotten or resurfaced words first, up to 10.
   - Reserve at most 2 positions for due maintenance words.
   - Fill remaining positions with due active-pool words.
   - Only when no due word is deferred and the active pool has room, activate at most 2 inbox words.
   - Archive overflow instead of scheduling it; preserve its history and reactivate it if the user marks it again.
5. Normalize all selected words to dictionary forms, then add concise Chinese meanings in the new article's `## 复习生词`.
6. Choose the vocabulary-load mode from the total selected load. Both modes use a listening source; a high load only changes the new-word allowance to 0.
7. Split each `test*.md` into its four Sections. Select one Section with stable daily randomness and avoid the most recent 12 source IDs when possible. Ignore test instructions such as “look at questions”.
8. Build a 5-7 beat story outline from the selected Section: goal, problem or information gap, evidence/choice, turn, and result. Do not turn the outline into a chronological action list.
9. Generate about 55-65 numbered sentences. A natural 50-70 is acceptable; use two related short articles only when one story cannot sustain the length. When a writing focus exists, repeatedly model that one structure correctly; do not introduce a second grammar focus.
10. Run an independent reviewer pass that checks story logic and rewrites all non-target, non-known words outside the local top-5000 frequency list. Do not save until the deterministic validator reports no candidate rare words.
11. Save the next article in a day folder under `作文素材/按时间排序/` using the next two-digit number and an English slug, e.g. `17_food_traditions/17_food_traditions.md`. Also save the generated Chinese-to-English practice JSON next to it. The writing page must show a top card labeled `本次只解决一个问题`, including the single focus, why it was selected, and how to practise it.
12. Generate listening audio from the Markdown article and rebuild `vocabulary.json` and `review-history.md`.

## Article Format

Use this exact structure:

```markdown
# English Title

- 天数：第 N 天
- 来源真题：<Cambridge listening test and section>
- 来源文件：<relative markdown path>
- 听力片段：<stable listening section id>
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
- Use the selected spaced-review mode to set new-vocabulary pressure, not whether a listening source is used.
- Target IELTS 6.0-6.5 readability even when the source is harder. Complexity should come from coherent information flow, not rare vocabulary.
- Keep sentences natural, concrete, and suitable for reading aloud.
- Reuse every selected target word at least once in the English body, with correct inflection if needed.
- Introduce new IELTS-style words or phrases only within the scheduler's 0-2 allowance; high load allows 0.
- Follow Vocabulary Limits below for every word that is not a target review word.
- Put Chinese explanations directly under each English sentence.
- Do not fill in the final `生单词:` section for the user.
- Do not copy more than one short phrase from the source. Summarize and adapt ideas in original wording.
- If the previous day has a writing draft, make the new reading and Chinese-to-English prompt practise exactly one selected error pattern. Other errors may be diagnosed internally but must wait for later days.

## Vocabulary Limits

Do not enforce a fixed word list or a hard numeric cap on incidental words — that produces stilted, repetitive writing. Instead, use a draft-then-audit process:

1. Draft from the listening Section's information structure, writing natural IELTS 6.0-6.5 sentences without importing source wording.
2. Audit every non-target word against `english-learning-web/data/common-english-5000.json`; a word already in `作文素材/单词复习/vocabulary.json` is also allowed. Replace candidate rare words with a common alternative and update the Chinese line.
3. Use `python3 scripts/verify_common_vocabulary.py <article.md> --allow <target-word>` before saving. Only save once the report is clean.

## Retired Daily Scenarios

Do not use the following scenario rotation for new articles. It is retained only as historical context for old articles; new articles always derive their story structure from a listening Section.

Rotate through everyday settings instead of reusing the same one — rereading "walking somewhere" or "a market day" for the tenth time is exactly what this section prevents. Pick the scenario at position `(day number) mod 30` from this list as the default backdrop, then check the last 5-6 real folder names/titles under `作文素材/按时间排序/` and pick a different nearby entry if that one was just used:

起床后在家吃早饭、上班或上学的路上、中午和同事或同学一起吃饭、下班或放学后在家休息、周末在家做家务、和家人打电话或视频聊天、去附近超市或商店买东西、天气突然变化的一天（比如晴转雨）、在公园散步或坐着休息、在家做一顿简单的饭、照顾宠物或给植物浇水、整理房间或打扫卫生、在家看一部电影或一集节目、和朋友一起玩一个简单的游戏或运动、睡前的安静时光、修理或整理家里的东西、骑自行车去附近的地方、和家人一起做作业或学习、简单的运动或锻炼、收拾行李准备一次短途旅行、计划周末要做的事情、翻看老照片或拍几张照片、懒散的周日下午、听音乐或练习一种乐器、整理书桌或书架、和邻居简单聊几句、在车站或诊所排队等候、学一个新的小技能或爱好、在家写日记或读书、一次简单的家庭聚餐或小庆祝

Stay within the chosen scenario's natural backdrop — don't invent a new one-off event (festival, ceremony, exhibition, competition, party, tour) purely to host the target words, since elaborate scenes are what drag in the throwaway props this section is trying to avoid.

## Source Tracking

Include the selected listening test title, transcript path, and stable Section ID in the front matter-style bullet list near the top. Do not copy source images or source wording into the daily article.

## Listening Audio

After saving the article, run:

```bash
uv run --with openai python scripts/article_to_speech.py "<day-folder>/<article>.md" --force
```

The script reads only the English sentences in `## 正文` and writes the `.mp3` next to the article by default. It uses `OPENAI_API_KEY` from the environment or project `.env`.

Default speech model is `gpt-4o-mini-tts-2025-12-15` with British-English IELTS listening instructions. The project wrapper uses speed `0.84` with clear, slightly longer pauses so the learner can follow each sentence. Use `--model tts-1` only when lower cost matters more than accent/delivery control, or `--model tts-1-hd` only when higher audio quality is explicitly needed. The web app's default article model is `gpt-4o-mini`.

If `OPENAI_API_KEY` is missing, run the script anyway. It will leave the article complete, create `.env.example` in the project root, create `OPENAI_API_KEY_REQUIRED.md` in the day folder, and stop before calling the OpenAI API.
