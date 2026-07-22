# Source Data

Use this reference when selecting IELTS reading sources for daily article generation.

## Converted IELTS Reading Dataset

Main dataset:

```text
雅思真题/Markdown资料/7月阅读/ReadingPractice/
```

Key files:

- `readingpractice-index.json`: machine-readable list of all converted readings.
- `readingpractice-index.csv`: human-readable table index.
- `dataset-summary.json`: totals and P1/P2/P3 counts.
- `conversion-report.md`: conversion quality report.

Current summary:

- Total Markdown files: 272
- Total extracted images: 582
- Total characters: 2,282,610
- P1: 79
- P2: 93
- P3: 100
- Conversion method: `pymupdf-layout`
- Conversion status: all `ok`

## Selection Policy

For the user's current IELTS 6.0 goal:

- Prefer P1 for easier daily input and fluency.
- Use P2 for steady growth and useful academic vocabulary.
- Use P3 sparingly, usually as a simplified source.
- Pick topics that can become practical short articles: food, cities, learning, history, science, health, work, technology, environment, culture.

Avoid source reuse by checking the recent files in `作文素材/按时间排序/` for `来源文件：`.

## Quality Notes

These Markdown files are converted from PDF. They are suitable as AI-readable source material, but should not be treated as perfect publication text. When a section looks broken, inspect nearby page markers or choose another source.

Do not copy long source passages into generated daily articles. The expected output is original practice writing based on the source topic and vocabulary.
