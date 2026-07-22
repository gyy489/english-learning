#!/usr/bin/env python3
"""Local web app for the daily English-learning Markdown workflow."""

from __future__ import annotations

import argparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
from urllib.parse import parse_qs, unquote, urlparse


APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(
    os.getenv("ENGLISH_LEARNING_PROJECT_ROOT") or APP_DIR.parent
).expanduser().resolve()
STATIC_DIR = APP_DIR / "static"
ARTICLES_DIR = PROJECT_ROOT / "作文素材" / "按时间排序"
SOURCE_INDEX = (
    PROJECT_ROOT
    / "雅思真题"
    / "Markdown资料"
    / "7月阅读"
    / "ReadingPractice"
    / "readingpractice-index.json"
)
TTS_SCRIPT = PROJECT_ROOT / "scripts" / "article_to_speech.py"
DICTIONARY_BUNDLE = (
    PROJECT_ROOT
    / "雅思真题"
    / "用于雅思学习skills数据"
    / "7月阅读"
    / "assets"
    / "wordlists"
    / "ecdict_reading.bundle.js"
)
ENV_FILE = PROJECT_ROOT / ".env"
TEXT_MODEL = os.getenv("OPENAI_TEXT_MODEL", "gpt-4o-mini")
WRITE_LOCK = threading.Lock()
DICTIONARY_LOCK = threading.Lock()
DICTIONARY_INDEX: dict[str, dict[str, object]] | None = None


IRREGULAR_FORMS = {
    "am": "be",
    "are": "be",
    "is": "be",
    "was": "be",
    "were": "be",
    "been": "be",
    "began": "begin",
    "begun": "begin",
    "bought": "buy",
    "brought": "bring",
    "came": "come",
    "children": "child",
    "did": "do",
    "done": "do",
    "fell": "fall",
    "felt": "feel",
    "found": "find",
    "gave": "give",
    "given": "give",
    "gone": "go",
    "got": "get",
    "had": "have",
    "has": "have",
    "kept": "keep",
    "knew": "know",
    "known": "know",
    "leaves": "leaf",
    "made": "make",
    "men": "man",
    "mice": "mouse",
    "people": "person",
    "ran": "run",
    "read": "read",
    "reached": "reach",
    "said": "say",
    "saw": "see",
    "seen": "see",
    "spoke": "speak",
    "spoken": "speak",
    "taught": "teach",
    "thought": "think",
    "took": "take",
    "taken": "take",
    "teeth": "tooth",
    "went": "go",
    "women": "woman",
    "wrote": "write",
    "written": "write",
    "argued": "argue",
}

S_ENDING_BASE_FORMS = {
    "analysis",
    "business",
    "class",
    "fish",
    "gas",
    "glass",
    "his",
    "news",
    "process",
    "series",
    "species",
    "this",
}

INVARIANT_BASE_FORMS = {
    "always",
    "anything",
    "during",
    "evening",
    "morning",
    "nothing",
    "perhaps",
    "something",
    "spring",
    "thus",
}

def load_project_env() -> None:
    if not ENV_FILE.exists():
        return
    for raw_line in ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value


def article_number(path: Path) -> int | None:
    match = re.match(r"^(\d+)_", path.name)
    return int(match.group(1)) if match else None


def article_files() -> list[tuple[int, Path]]:
    found: list[tuple[int, Path]] = []
    if not ARTICLES_DIR.exists():
        return found
    for directory in ARTICLES_DIR.iterdir():
        if not directory.is_dir():
            continue
        number = article_number(directory)
        if number is None:
            continue
        preferred = directory / f"{directory.name}.md"
        candidates = [preferred] if preferred.exists() else sorted(directory.glob("*.md"))
        if candidates:
            found.append((number, candidates[0]))
    return sorted(found, key=lambda item: item[0])


def latest_article() -> tuple[int, Path]:
    found = article_files()
    if not found:
        raise FileNotFoundError(f"没有在 {ARTICLES_DIR} 找到每日文章")
    return found[-1]


def article_for_day(day: object | None = None) -> tuple[int, Path]:
    if day is None or day == "":
        return latest_article()
    try:
        requested_day = int(str(day))
    except ValueError as exc:
        raise ValueError("天数必须是数字") from exc
    for number, path in article_files():
        if number == requested_day:
            return number, path
    raise FileNotFoundError(f"没有找到第 {requested_day} 天的文章")


def article_summaries() -> dict[str, object]:
    summaries = []
    for day, path in article_files():
        text = path.read_text(encoding="utf-8")
        title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        summaries.append(
            {
                "day": day,
                "title": title_match.group(1).strip() if title_match else path.stem,
                "audioAvailable": path.with_suffix(".mp3").exists(),
            }
        )
    if not summaries:
        raise FileNotFoundError(f"没有在 {ARTICLES_DIR} 找到每日文章")
    return {"days": summaries, "latestDay": summaries[-1]["day"]}


def section_between(text: str, start: str, end: str) -> str:
    if start not in text:
        return ""
    section = text.split(start, 1)[1]
    if end in section:
        section = section.split(end, 1)[0]
    return section


def clean_today_entries(text: str) -> list[str]:
    marker = "生单词:"
    if marker not in text:
        return []
    section = text.rsplit(marker, 1)[1]
    entries: list[str] = []
    for line in section.splitlines():
        for item in re.split(r"[,;，；]", line):
            item = re.sub(r"^[-*]\s*", "", item.strip())
            if item:
                entries.append(item)
    return entries


def parse_article(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else path.stem

    metadata: dict[str, str] = {}
    for match in re.finditer(r"^-\s+([^：\n]+)：(.+)$", text, re.MULTILINE):
        metadata[match.group(1).strip()] = match.group(2).strip()

    review_text = section_between(text, "## 复习生词", "## 正文")
    review_words: list[dict[str, str]] = []
    for line in review_text.splitlines():
        match = re.match(r"^\s*-\s+(.+?)(?:\s+-\s+(.+))?$", line)
        if match:
            review_words.append(
                {"word": match.group(1).strip(), "meaning": (match.group(2) or "").strip()}
            )

    body_text = section_between(text, "## 正文", "生单词:")
    if not body_text:
        body_text = text.rsplit("生单词:", 1)[0]
    body_lines = body_text.splitlines()
    sentences: list[dict[str, object]] = []
    has_numbered_sentences = any(re.match(r"^\s*\d+\.\s+", line) for line in body_lines)
    for index, line in enumerate(body_lines):
        match = re.match(r"^\s*(\d+)\.\s+(.+?)\s*$", line)
        if match:
            number = int(match.group(1))
            english = match.group(2).strip()
        elif not has_numbered_sentences:
            english = line.strip()
            if (
                not english
                or english.startswith(("#", "-", ">", "⸻"))
                or not re.search(r"[A-Za-z]", english)
            ):
                continue
            number = len(sentences) + 1
        else:
            continue

        chinese = ""
        for candidate in body_lines[index + 1 : index + 7]:
            stripped = candidate.strip()
            if re.match(r"^\d+\.\s+", stripped):
                break
            if stripped.startswith(">") and stripped != ">":
                chinese = stripped[1:].strip()
                break
        if not chinese and not match:
            continue
        sentences.append(
            {"number": number, "english": english, "chinese": chinese}
        )

    audio_path = path.with_suffix(".mp3")
    return {
        "day": article_number(path.parent) or metadata.get("天数", ""),
        "title": title,
        "metadata": metadata,
        "reviewWords": review_words,
        "sentences": sentences,
        "todayWords": dedupe_words(clean_today_entries(text)),
        "audioAvailable": audio_path.exists(),
        "audioUrl": "/api/audio" if audio_path.exists() else None,
        "markdownPath": str(path.relative_to(PROJECT_ROOT)),
        "updatedAt": path.stat().st_mtime_ns,
    }


def normalize_word(raw_word: str) -> str:
    word = raw_word.strip().lower().replace("’", "'")
    match = re.search(r"[a-z]+(?:'[a-z]+)?", word)
    if not match:
        return ""
    word = match.group(0)
    if word.endswith("'s"):
        word = word[:-2]
    if word in IRREGULAR_FORMS:
        return IRREGULAR_FORMS[word]
    if word in INVARIANT_BASE_FORMS:
        return word
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith("ves"):
        return word[:-3] + "f"
    if len(word) > 5 and word.endswith("ing"):
        stem = word[:-3]
        if len(stem) > 2 and stem[-1] == stem[-2] and stem[-1] not in "lsz":
            stem = stem[:-1]
        if stem.endswith(("mak", "tak", "writ", "mov", "us", "giv", "shap")):
            stem += "e"
        return stem
    if len(word) > 4 and word.endswith("ed"):
        stem = word[:-2]
        if stem.endswith("i"):
            return stem[:-1] + "y"
        if len(stem) > 2 and stem[-1] == stem[-2]:
            return stem[:-1]
        if stem.endswith(("argu", "creat", "mov", "us", "prepar", "shap")):
            return stem + "e"
        return stem
    if len(word) > 4 and word.endswith("es") and word.endswith(("ches", "shes", "sses", "xes", "zes")):
        return word[:-2]
    if (
        len(word) > 3
        and word.endswith("s")
        and word not in S_ENDING_BASE_FORMS
        and not word.endswith(("ss", "us", "is"))
    ):
        return word[:-1]
    return word


def normalize_entry(raw_entry: str) -> str:
    entry = re.sub(r"\s+", " ", raw_entry.strip().lower().replace("’", "'"))
    if re.fullmatch(r"[a-z]+(?:'[a-z]+)?", entry):
        return normalize_word(entry)
    return entry


def dictionary_index() -> dict[str, dict[str, object]]:
    global DICTIONARY_INDEX
    if DICTIONARY_INDEX is not None:
        return DICTIONARY_INDEX
    with DICTIONARY_LOCK:
        if DICTIONARY_INDEX is not None:
            return DICTIONARY_INDEX
        if not DICTIONARY_BUNDLE.exists():
            raise FileNotFoundError("本地 ECDICT 词库不存在")
        bundle = DICTIONARY_BUNDLE.read_text(encoding="utf-8")
        start_marker = "entries: "
        start = bundle.find(start_marker)
        end = bundle.rfind("] };")
        if start < 0 or end < 0:
            raise RuntimeError("无法读取本地 ECDICT 词库")
        entries = json.loads(bundle[start + len(start_marker) : end + 1])
        DICTIONARY_INDEX = {
            str(entry.get("w", "")).lower(): entry
            for entry in entries
            if isinstance(entry, dict) and entry.get("w")
        }
        return DICTIONARY_INDEX


def lookup_dictionary(raw_word: str) -> dict[str, object]:
    match = re.search(r"[A-Za-z]+(?:['’][A-Za-z]+)?", raw_word)
    if not match:
        raise ValueError("请选择一个英文单词")
    requested = match.group(0).lower().replace("’", "'")
    index = dictionary_index()
    lemma = normalize_word(requested)
    entry = index.get(requested) or index.get(lemma)
    if not entry:
        raise FileNotFoundError(f"词典中没有找到 {requested}")
    return {
        "query": requested,
        "word": entry.get("w", lemma),
        "phonetic": entry.get("p", ""),
        "translation": entry.get("t", ""),
        "definition": entry.get("d", ""),
        "source": "ECDICT",
    }


def dedupe_words(words: list[object]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in words:
        word = normalize_entry(str(item))
        if word and word not in seen:
            seen.add(word)
            cleaned.append(word)
    return cleaned


def save_today_words(path: Path, words: list[object]) -> list[str]:
    cleaned = dedupe_words(words)
    text = path.read_text(encoding="utf-8")
    marker = "生单词:"
    if marker not in text:
        text = f"{text.rstrip()}\n\n{marker}\n"
    prefix = text.rsplit(marker, 1)[0].rstrip()
    suffix = "\n\n" + "\n\n".join(cleaned) + "\n" if cleaned else "\n"
    path.write_text(f"{prefix}\n\n{marker}{suffix}", encoding="utf-8")
    return cleaned


def choose_source() -> dict[str, object]:
    entries = json.loads(SOURCE_INDEX.read_text(encoding="utf-8"))
    used_sources: set[str] = set()
    for _, path in article_files():
        match = re.search(r"^- 来源文件：(.+)$", path.read_text(encoding="utf-8"), re.MULTILINE)
        if match:
            used_sources.add(match.group(1).strip())

    candidates = [
        item
        for item in entries
        if item.get("status") == "ok"
        and item.get("part") in {"P1", "P2"}
        and item.get("markdown_path") not in used_sources
        and (PROJECT_ROOT / str(item.get("markdown_path", ""))).exists()
    ]
    candidates.sort(key=lambda item: (item.get("part") != "P1", int(str(item.get("number", 9999)))))
    if not candidates:
        raise RuntimeError("没有找到未使用的 P1/P2 阅读材料")
    return candidates[0]


def generation_mode(word_count: int) -> dict[str, object]:
    if word_count > 15:
        return {
            "name": "纯生词复习",
            "sentenceCount": "约 25-30",
            "newWords": "0",
            "usesSource": False,
        }
    if word_count <= 5:
        return {
            "name": "轻负荷题库扩展",
            "sentenceCount": "约 40",
            "newWords": "6-10",
            "usesSource": True,
        }
    return {
        "name": "正常题库学习",
        "sentenceCount": "至少 30",
        "newWords": "4-8",
        "usesSource": True,
    }


def strip_model_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:markdown)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip() + "\n"


def slugify_title(title: str, day: int) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    if not slug:
        slug = "daily_review"
    return f"{day:02d}_{slug[:72].rstrip('_')}"


def validate_generated_article(text: str, expected_day: int, mode: dict[str, object]) -> None:
    required = ["# ", f"- 天数：第 {expected_day} 天", "## 复习生词", "## 正文", "生单词:"]
    missing = [item for item in required if item not in text]
    if missing:
        raise RuntimeError(f"模型输出缺少必要格式：{', '.join(missing)}")
    count = len(re.findall(r"^\d+\.\s+", section_between(text, "## 正文", "生单词:"), re.MULTILINE))
    minimum = 25 if not mode["usesSource"] else (36 if mode["sentenceCount"] == "约 40" else 30)
    if count < minimum:
        raise RuntimeError(f"模型只生成了 {count} 句，低于当前模式要求的 {minimum} 句")
    if text.rsplit("生单词:", 1)[1].strip():
        raise RuntimeError("模型错误地填写了末尾“生单词:”区域")
    if not mode["usesSource"]:
        for field in ("来源真题", "来源文件"):
            if f"- {field}：无（纯生词复习）" not in text:
                raise RuntimeError(f"纯复习模式的“{field}”必须标记为无")


def build_generation_prompt(
    previous_day: int,
    next_day: int,
    words: list[str],
    mode: dict[str, object],
    source: dict[str, object] | None,
) -> str:
    word_text = "、".join(words) if words else "（无）"
    if source:
        source_path = PROJECT_ROOT / str(source["markdown_path"])
        source_text = source_path.read_text(encoding="utf-8", errors="replace")[:12000]
        source_context = (
            f"来源真题：{source['title']}\n"
            f"来源文件：{source['markdown_path']}\n"
            f"来源摘录：\n{source_text}"
        )
        source_rule = "根据来源的主题和事实原创改写，不复制长句。"
        if mode["newWords"] == "0":
            source_rule += "来源只提供主题与事实，不把来源词汇作为新的目标生词。"
    else:
        source_context = "来源真题：无（纯生词复习）\n来源文件：无（纯生词复习）"
        source_rule = (
            "不要使用题库、外部材料或专业新主题。只根据旧生词构造一个简单、连贯的日常故事或说明，"
            "除必要基础词外不引入新的目标词。"
        )

    return f"""你正在为一名 IELTS 5.5-6.0 学习者生成第 {next_day} 天的英语文章。

当前模式：{mode['name']}
前一天：第 {previous_day} 天
前一天生词（已转原形）：{word_text}
目标句数：{mode['sentenceCount']}
允许的新 IELTS 目标词数量：{mode['newWords']}

{source_context}

要求：
1. 每个旧生词至少在英文正文中自然出现一次，可以按语境变形。
2. {source_rule}
3. 句子自然、具体、适合朗读；难度不要超过 IELTS 6.0。纯复习模式要明显更简单。
4. `## 复习生词` 列出全部旧生词的词典原形和简洁中文释义；没有旧生词时写 `- 无 - 无`。
5. 每句英文下面紧跟中文解释，使用下面的固定 Markdown 格式。
6. 末尾 `生单词:` 必须留空。
7. 只输出 Markdown，不要代码围栏、前言或解释。

固定格式：
# English Title

- 天数：第 {next_day} 天
- 来源真题：<题目；纯复习模式写“无（纯生词复习）”>
- 来源文件：<相对路径；纯复习模式写“无（纯生词复习）”>
- 复习内容：D{previous_day} 生词复用 + <当前模式>

## 复习生词

- word - 中文释义

## 正文

1. English sentence.

   > 中文解释。
   >

生单词:
"""


def request_generated_markdown(prompt: str) -> tuple[str, str]:
    if os.getenv("OPENAI_API_KEY"):
        try:
            from openai import OpenAI
        except ImportError:
            pass
        else:
            model = os.getenv("OPENAI_TEXT_MODEL", TEXT_MODEL)
            response = OpenAI().responses.create(
                model=model,
                input=prompt,
                max_output_tokens=8_000,
            )
            return response.output_text, model

    codex = shutil.which("codex")
    if not codex:
        raise RuntimeError(
            "没有可用的文章生成方式：请配置 OPENAI_API_KEY，或安装并登录 Codex CLI。"
        )
    with tempfile.TemporaryDirectory(prefix="english-learning-") as temp_dir:
        output_path = Path(temp_dir) / "article.md"
        codex_env = os.environ.copy()
        # 如果本地同时存在 ChatGPT 登录态和 OPENAI_API_KEY，Codex CLI
        # 可能会误用 API-key 模式。这里让 Codex 使用它自己的已登录状态。
        codex_env.pop("OPENAI_API_KEY", None)
        codex_env.pop("OPENAI_BASE_URL", None)
        result = subprocess.run(
            [
                codex,
                "exec",
                "--ephemeral",
                "--skip-git-repo-check",
                "--sandbox",
                "read-only",
                "--output-last-message",
                str(output_path),
                "-",
            ],
            cwd=PROJECT_ROOT,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
            env=codex_env,
        )
        if result.returncode != 0 or not output_path.exists():
            details = (result.stderr or result.stdout).strip().splitlines()
            message = details[-1] if details else "Codex CLI 没有返回文章"
            raise RuntimeError(f"Codex CLI 生成失败：{message}")
        return output_path.read_text(encoding="utf-8"), "Codex CLI"


def generate_next_article() -> dict[str, object]:
    load_project_env()
    previous_day, previous_path = latest_article()
    previous_text = previous_path.read_text(encoding="utf-8")
    words = dedupe_words(clean_today_entries(previous_text))
    mode = generation_mode(len(words))
    source = choose_source() if mode["usesSource"] else None
    next_day = previous_day + 1
    prompt = build_generation_prompt(previous_day, next_day, words, mode, source)

    generated_text, generator = request_generated_markdown(prompt)
    markdown = strip_model_fences(generated_text)
    validate_generated_article(markdown, next_day, mode)

    title_match = re.search(r"^#\s+(.+)$", markdown, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else "Daily Review"
    folder_name = slugify_title(title, next_day)
    day_dir = ARTICLES_DIR / folder_name
    if day_dir.exists():
        raise RuntimeError(f"目标文件夹已经存在：{day_dir.relative_to(PROJECT_ROOT)}")
    day_dir.mkdir(parents=True)
    article_path = day_dir / f"{folder_name}.md"
    article_path.write_text(markdown, encoding="utf-8")

    audio_warning = None
    uv = shutil.which("uv")
    if not os.getenv("OPENAI_API_KEY"):
        audio_warning = "文章已生成；配置 OPENAI_API_KEY 后才能生成 MP3"
    else:
        command = (
            [uv, "run", "--with", "openai", "python", str(TTS_SCRIPT), str(article_path), "--force"]
            if uv
            else [os.sys.executable, str(TTS_SCRIPT), str(article_path), "--force"]
        )
        audio_result = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        if audio_result.returncode != 0:
            audio_warning = (audio_result.stderr or audio_result.stdout).strip()[-800:]

    return {
        "day": next_day,
        "title": title,
        "mode": mode["name"],
        "markdownPath": str(article_path.relative_to(PROJECT_ROOT)),
        "audioGenerated": article_path.with_suffix(".mp3").exists(),
        "warning": audio_warning,
        "generator": generator,
    }


class AppHandler(BaseHTTPRequestHandler):
    server_version = "EnglishLearningWeb/1.0"

    def log_message(self, format_string: str, *args: object) -> None:
        print(f"[{self.log_date_time_string()}] {format_string % args}")

    def send_json(self, payload: object, status: int = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def read_json(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 1_000_000:
            raise ValueError("请求内容过大")
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8")) if raw else {}

    def send_static(self, relative_path: str) -> None:
        requested = (STATIC_DIR / relative_path).resolve()
        if STATIC_DIR.resolve() not in requested.parents and requested != STATIC_DIR.resolve():
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if not requested.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        data = requested.read_bytes()
        content_type = mimetypes.guess_type(requested.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_audio(self, day: object | None = None) -> None:
        _, article_path = article_for_day(day)
        audio_path = article_path.with_suffix(".mp3")
        if not audio_path.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "当前文章没有 MP3")
            return
        size = audio_path.stat().st_size
        start, end = 0, size - 1
        status = HTTPStatus.OK
        range_header = self.headers.get("Range")
        if range_header:
            match = re.match(r"bytes=(\d*)-(\d*)", range_header)
            if match:
                if match.group(1):
                    start = int(match.group(1))
                if match.group(2):
                    end = min(int(match.group(2)), size - 1)
                status = HTTPStatus.PARTIAL_CONTENT
        if start > end or start >= size:
            self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            return
        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with audio_path.open("rb") as handle:
            handle.seek(start)
            remaining = length
            while remaining:
                chunk = handle.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def do_GET(self) -> None:
        parsed_url = urlparse(self.path)
        path = unquote(parsed_url.path)
        query = parse_qs(parsed_url.query)
        day = query.get("day", [None])[0]
        try:
            if path == "/api/current":
                _, article_path = article_for_day(day)
                self.send_json(parse_article(article_path))
            elif path == "/api/days":
                self.send_json(article_summaries())
            elif path == "/api/article-version":
                day_number, article_path = article_for_day(day)
                self.send_json(
                    {"day": day_number, "updatedAt": article_path.stat().st_mtime_ns}
                )
            elif path == "/api/dictionary":
                self.send_json(lookup_dictionary(query.get("word", [""])[0]))
            elif path == "/api/audio":
                self.send_audio(day)
            elif path in {"/", "/index.html"}:
                self.send_static("index.html")
            elif path.startswith("/static/"):
                self.send_static(path.removeprefix("/static/"))
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            payload = self.read_json()
            if path == "/api/lemma":
                self.send_json({"word": normalize_word(str(payload.get("word", "")))})
                return
            if path == "/api/today-words":
                words = payload.get("words", [])
                if not isinstance(words, list):
                    raise ValueError("words 必须是数组")
                with WRITE_LOCK:
                    day, article_path = article_for_day(payload.get("day"))
                    saved = save_today_words(article_path, words)
                self.send_json(
                    {
                        "day": day,
                        "words": saved,
                        "saved": True,
                        "updatedAt": article_path.stat().st_mtime_ns,
                    }
                )
                return
            if path == "/api/generate-next":
                with WRITE_LOCK:
                    result = generate_next_article()
                self.send_json(result, HTTPStatus.CREATED)
                return
            self.send_error(HTTPStatus.NOT_FOUND)
        except json.JSONDecodeError:
            self.send_json({"error": "JSON 格式错误"}, HTTPStatus.BAD_REQUEST)
        except (FileNotFoundError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:  # Keep the local UI usable while surfacing API errors.
            self.send_json({"error": f"操作失败：{exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start the English learning web app")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_project_env()
    server = ThreadingHTTPServer((args.host, args.port), AppHandler)
    print(f"English learning app: http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
