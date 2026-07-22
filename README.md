# 英语学习

这个项目用于记录和整理我的英语学习材料。

我的目标是把英语水平提升到雅思 6.0 左右。当前的核心方法是：每天或隔一天生成一篇短文章，把仍不会的生词和到期历史词放进新语境；每篇最多安排 15 个目标复习词，并按 1、3、7、14、30、60 天的间隔持续回顾。

## 学习方法

1. 每天或隔一天，让 AI 根据前一天生词数量生成一篇适合当前水平的英语短文章。
2. 我会把文章熟读，重点练习发音、语感和句子结构。
3. 如果文章里有陌生单词或不熟悉的表达，就记录在文档下面。
4. 新发现的词先进入收件箱；系统根据容量把它们逐步送入活跃学习池，再进入长期维护池和归档。
5. 每篇目标复习词不超过 15 个，每次最多激活 2 个新词；有复习积压时自动关闭新词入口。
6. 通过不断重复，让生词从“认识”变成“会用”。

## “更新”自动流程

以后我只要说“更新”，AI 就按下面的流程继续写新一天的内容：

1. 打开 `作文素材/按时间排序/`，找到编号最大的每日文件夹，并读取其中同名 Markdown 文件作为前一天内容。
2. 读取前一天文档底部 `生单词:`，并根据所有历史文章重建 `作文素材/单词复习/vocabulary.json` 和 `review-history.md`；后者同时记录已完成篇数、回忆成功率和平均生词量等习惯指标。
3. 将词汇分到四层容量池：收件箱最多 120 个、活跃学习池最多 60 个、长期维护池最多 120 个，其余保留历史并归档。
4. 每篇最多安排 15 个目标词：仍不会的词最多占 10 个，长期维护词最多占 2 个，其余位置给活跃池到期词。只有到期词全部排完且活跃池有空位时，才从收件箱激活最多 2 个新词。
5. 复习压力允许时，读取 `雅思真题/Markdown资料/7月阅读/ReadingPractice/readingpractice-index.json`，优先选择 `P1` 和较容易的 `P2`；高负荷纯复习模式不读取题库。
6. 题库模式只读取选中的 `.pdf.md`，借用主题、背景信息、表达领域和少量关键词，不长段照搬原文。
7. 新建下一天的每日文件夹，文件夹名使用 `两位数_英文标题`，并在里面创建同名 Markdown 文件，例如 `17_food_traditions/17_food_traditions.md`。
8. 新文章开头的 `复习生词` 必须使用系统选出的全部目标词（当前生词 + 到期旧词），统一整理成词典原形，并添加中文词典释义。例如我记录了 `rode`，新文章开头应写成 `ride - 骑；乘坐`。
9. 正文继续使用“英文句子 + 中文解释”的格式，让这些生词自然出现在文章里。正文中可以根据语境使用正确的时态、单复数或词形变化，例如开头展示 `ride - 骑；乘坐`，正文可以写 `I rode my bicycle...`。
10. 在文章顶部记录 `来源真题` 和 `来源文件`；纯复习模式两项都写为 `无（纯生词复习）`。
11. 新文章底部只保留空的 `生单词:`，不要替我填写。这个区域由我在阅读和背诵过程中自己记录新的不熟悉单词。
12. 每天新建一个独立文件夹，文件夹名使用 `两位数_英文标题`，例如 `16_food_traditions/`。
13. 当天 Markdown 文章和对应听力音频必须放在同一个文件夹里，例如 `16_food_traditions/16_food_traditions.md` 和 `16_food_traditions/16_food_traditions.mp3`。

这个循环的逻辑是：我阅读文章时，把还没掌握的单词写到文章底部；下一次生成时，复习词如果没有再次被记录，就视为本次记住并延长间隔；如果再次记录，就视为仍不会并回到次日复习。新发现的词先排队，不会全部立刻变成复习任务；复习压力升高时新词入口自动关闭，因此长期负荷保持有界。

## 目录说明

- `作文素材/`：AI 生成的英语短文章、中文解释和生词积累。
- `作文素材/按时间排序/`：每日练习目录，一天一个文件夹；每个文件夹内放当天 Markdown 文章和对应听力音频。
- `作文素材/单词复习/`：间隔复习策略、JSON 词库和自动生成的 Markdown 复习历史。
- `雅思真题/`：雅思真题原始资料和转换后的 AI 可读 Markdown 数据。
- `雅思真题/Markdown资料/`：由 PDF/DOCX 转换得到的 Markdown 数据层，后续生成学习文章时优先使用这里的资料。
- `skills/ielts-daily-article/SKILL.md`：项目内的每日文章生成 skill，后续 agent 可按这个文件执行“更新”流程。
- `录音/`：旧版音频目录，保留作兼容；新音频应放在对应每日文件夹中。
- `默写/`：默写练习和复习内容。
- `scripts/article_to_speech.py`：把作文 Markdown 的英文正文转换成听力音频。

## 雅思真题资料层

当前已将 `雅思真题/用于雅思学习skills数据/7月阅读/ReadingPractice/PDF/` 下的阅读 PDF 批量转换为 Markdown：

```text
雅思真题/Markdown资料/7月阅读/ReadingPractice/
```

这个目录是后续辅助程序的真题语料来源。生成新的英语学习文章、阅读材料、词汇复习或题材模仿时，应优先读取这些 Markdown，而不是临时重新解析 PDF。

关键索引文件：

- `雅思真题/Markdown资料/7月阅读/ReadingPractice/readingpractice-index.csv`
- `雅思真题/Markdown资料/7月阅读/ReadingPractice/readingpractice-index.json`
- `雅思真题/Markdown资料/7月阅读/ReadingPractice/dataset-summary.json`
- `雅思真题/Markdown资料/7月阅读/ReadingPractice/conversion-report.md`

## 项目 Skill

这个项目内已经创建一个本地 skill：

```text
skills/ielts-daily-article/SKILL.md
```

这个文件就是后续 agent 应该读取的“使用说明”。当我说“更新”“生成今天的文章”“根据雅思真题继续写一篇”时，agent 应按这个 skill 和单词复习策略工作：先读取当前生词和到期旧词，再按负荷决定是否选择 IELTS 阅读材料，最后生成新的每日练习文章。

## 开源仓库说明

本仓库公开 Web App、脚本、项目 Skill 和个人生成的英语学习文章/音频。原始雅思题库、视频、PDF、临时转换产物和本地密钥不在仓库中；这些内容应仅保留在本机，并按 `.gitignore` 排除。

## 听力音频生成

已经安装 OpenAI 官方 curated `speech` skill。重启 Codex 后，这个 skill 会自动加载；当前项目也可以直接用下面的脚本生成音频。

默认只读取文章 `## 正文` 里的英文句子，不读取中文解释、复习生词和底部 `生单词:`。音频默认输出到文章所在文件夹。

```bash
uv run --with openai python scripts/article_to_speech.py "作文素材/按时间排序/16_a_quiet_cup_of_tea/16_a_quiet_cup_of_tea.md"
```

默认输出到：

```text
作文素材/按时间排序/16_a_quiet_cup_of_tea/16_a_quiet_cup_of_tea.mp3
```

常用选项：

```bash
# 覆盖已经存在的音频
uv run --with openai python scripts/article_to_speech.py "作文素材/按时间排序/16_a_quiet_cup_of_tea/16_a_quiet_cup_of_tea.md" --force

# 换成 marin 声音
uv run --with openai python scripts/article_to_speech.py "作文素材/按时间排序/16_a_quiet_cup_of_tea/16_a_quiet_cup_of_tea.md" --voice marin

# 临时切换到支持语气指令的声音模型
uv run --with openai python scripts/article_to_speech.py "作文素材/按时间排序/16_a_quiet_cup_of_tea/16_a_quiet_cup_of_tea.md" --model gpt-4o-mini-tts

# 先检查会读取哪些英文
uv run --with openai python scripts/article_to_speech.py "作文素材/按时间排序/16_a_quiet_cup_of_tea/16_a_quiet_cup_of_tea.md" --dry-run --print-text
```

模型选择：

- `tts-1`：默认值，价格较低、生成速度快，适合日常英语学习；不支持 `--instructions`，但仍支持 `--speed`。
- `gpt-4o-mini-tts`：声音更自然并支持 `--instructions`，需要时可临时切换；官方模型目录已将它标记为 deprecated。
- `gpt-4o-mini-tts-2025-12-15`：固定版本，适合需要保持声音效果一致的情况。
- `tts-1-hd`：旧款高质量模型；不支持 `--instructions`。

生成音频需要本机设置 `OPENAI_API_KEY`。脚本会优先读取环境变量；如果没有，也会读取项目根目录的 `.env`。从“应用程序”启动“每日英语”时，启动脚本会读取 `~/.zshrc` 中的 OpenAI 配置，但不会把 key 写入项目或 GitHub。

Web 应用生成文章默认使用 `gpt-4o-mini`，生成音频默认使用 `tts-1`。可以在 `.env` 中分别设置 `OPENAI_TEXT_MODEL` 和 `OPENAI_TTS_MODEL` 覆盖。

如果没有检测到 API key，脚本不会生成音频，而会：

- 在项目根目录生成 `.env.example`
- 在文章所在文件夹生成 `OPENAI_API_KEY_REQUIRED.md`

把 `.env.example` 复制成 `.env`，然后在 `.env` 里填写：

```text
OPENAI_API_KEY=sk-your-key-here
```

不要把 API key 发到聊天中。`.env` 已加入 `.gitignore`。

默认声音是 `nova`，与默认的 `tts-1` 模型兼容；语速略慢，适合清楚跟读。

## 文章格式建议

每篇文章可以按下面的结构保存：

```markdown
# 文章标题

- 天数：第 N 天
- 来源真题：
- 来源文件：
- 复习内容：D(N-1) 当前生词 + 到期旧词 + 当前模式

## 复习生词

- word - 中文词典释义
- ride - 骑；乘坐
- bring - 带来；拿来

## 正文

1. English sentence.

   > 中文解释。
   >

2. I rode my bicycle to the station yesterday.

   > 昨天我骑自行车去了车站。（开头展示原形 `ride`，正文按语境使用过去式 `rode`。）
   >

生单词:
```

## 学习原则

- 每篇文章最多安排 15 个目标复习词；活跃池最多 60 个，每次最多激活 2 个新词，超出容量的词进入收件箱或归档。
- 生词不要只背意思，要尽量放进新的文章和句子里。
- `复习生词` 区域统一使用词典原形和中文释义；正文里按语境使用合适词形；底部 `生单词:` 可以记录我实际遇到的词形。
- 保持稳定频率，比一次性学习很多内容更重要。
- 定期回看旧文章，检查以前的生词是否已经熟悉。
