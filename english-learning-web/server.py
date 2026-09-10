#!/usr/bin/env python3
"""Local web app for the daily English-learning Markdown workflow."""

from __future__ import annotations

import argparse
import ctypes
from datetime import UTC, datetime
import gzip
import hashlib
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from urllib.parse import parse_qs, unquote, urlparse

from common_vocabulary import report_words, vocabulary_report
from review_scheduler import (
    build_review_state,
    dashboard_payload,
    render_markdown_report,
)


APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(
    os.getenv("ENGLISH_LEARNING_PROJECT_ROOT") or APP_DIR.parent
).expanduser().resolve()
STATIC_DIR = APP_DIR / "static"
ARTICLES_DIR = PROJECT_ROOT / "作文素材" / "按时间排序"
LISTENING_SOURCE_DIR = (
    PROJECT_ROOT
    / "雅思真题"
    / "用于雅思学习skills数据"
    / "超给的资料"
    / "listening"
    / "cambridge-ielts-1"
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
GLOBAL_ENV_FILE = Path.home() / ".config" / "api-keys.env"
REVIEW_DIR = PROJECT_ROOT / "作文素材" / "单词复习"
REVIEW_JSON = REVIEW_DIR / "vocabulary.json"
REVIEW_REPORT = REVIEW_DIR / "review-history.md"
TEXT_MODEL = os.getenv("OPENAI_TEXT_MODEL", "gpt-5.5")
MAX_GENERATION_ATTEMPTS = 5
MAX_EXTRA_INSTRUCTION_LENGTH = 300
LISTENING_SOURCE_HISTORY_WINDOW = 12
MIN_ARTICLE_SENTENCES = 50
MAX_ARTICLE_SENTENCES = 70
MAX_WRITING_INPUT_LENGTH = 12_000
WRITING_LEVELS = {
    "basic": "基础纠错",
    "natural": "自然表达",
    "advanced": "结构提升",
}

WRITE_LOCK = threading.RLock()
DICTIONARY_LOCK = threading.Lock()
REVIEW_LOCK = threading.Lock()
WRITING_LOCK = threading.Lock()
AUDIO_CACHE_LOCK = threading.Lock()
DICTIONARY_INDEX: dict[str, dict[str, object]] | None = None
SESSION_LOCK = threading.Lock()
ACTIVE_SESSIONS: dict[str, float] = {}
ACTIVE_OPERATIONS = 0
SHUTDOWN_TIMER: threading.Timer | None = None
SESSION_AUDIT_TIMER: threading.Timer | None = None
SESSION_HAS_CONNECTED = False
SESSION_GRACE_SECONDS = 4.0
SESSION_STARTUP_SECONDS = 45.0
SESSION_AUDIT_SECONDS = 30.0
SESSION_STALE_SECONDS = 180.0
AUDIO_CACHE_DIR = PROJECT_ROOT / ".cache" / "english-learning-audio"
AUDIO_CACHE_BITRATE = "48k"

# ECDICT does not contain every short function word. These direct glosses keep
# the word-order view useful without asking an API for each sentence.
BASIC_WORDS_TO_SKIP = {
    "a": "一个", "an": "一个", "the": "这/该", "i": "我", "you": "你/你们",
    "he": "他", "she": "她", "it": "它", "we": "我们", "they": "他们",
    "me": "我", "him": "他", "her": "她", "us": "我们", "them": "他们",
    "my": "我的", "your": "你的", "his": "他的", "its": "它的", "our": "我们的",
    "their": "他们的", "this": "这", "that": "那", "these": "这些", "those": "那些",
    "am": "是", "is": "是", "are": "是", "was": "是/在", "were": "是/在",
    "be": "是", "been": "是过", "being": "正在是", "do": "做", "does": "做",
    "did": "做了", "done": "做完", "have": "有", "has": "有", "had": "有过",
    "will": "将", "would": "会", "can": "能", "could": "能够", "may": "可能",
    "might": "可能", "must": "必须", "should": "应该", "to": "去/向",
    "of": "的", "in": "在...里", "on": "在...上", "at": "在", "by": "被/通过",
    "for": "为了/给", "with": "和/用", "from": "从", "into": "进入", "about": "关于",
    "over": "在...上方", "under": "在...下方", "between": "在...之间", "before": "在...之前",
    "after": "在...之后", "and": "和", "or": "或", "but": "但是", "if": "如果",
    "because": "因为", "so": "所以", "as": "作为/当", "than": "比", "not": "不",
    "no": "不/没有", "very": "非常", "also": "也", "just": "只是", "there": "那里/有",
    "here": "这里", "when": "当...时", "where": "哪里", "why": "为什么", "how": "如何",
    "who": "谁", "what": "什么", "which": "哪个", "all": "全部", "some": "一些",
    "any": "任何", "more": "更多", "most": "大多数", "less": "更少", "many": "许多",
    "few": "少数", "each": "每个", "every": "每一个", "both": "两者都",
    "art": "艺术", "world": "世界", "common": "通常的", "daily": "每天的",
    "simple": "简单的", "quiet": "安静的", "small": "小的", "great": "伟大的",
}
HARD_GLOSS_TAGS = {"cet6", "toefl", "gre"}


def persistent_server_enabled() -> bool:
    return os.getenv("ENGLISH_LEARNING_PERSISTENT", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def optimized_audio_path(source_path: Path) -> Path:
    """Return a compact speech MP3 while preserving the generated original."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return source_path
    source_stat = source_path.stat()
    relative_name = str(source_path.relative_to(PROJECT_ROOT)).encode("utf-8")
    cache_key = hashlib.sha256(relative_name).hexdigest()[:12]
    cached_path = AUDIO_CACHE_DIR / (
        f"{cache_key}-{source_stat.st_mtime_ns}-{AUDIO_CACHE_BITRATE}.mp3"
    )
    if cached_path.exists():
        return cached_path
    with AUDIO_CACHE_LOCK:
        if cached_path.exists():
            return cached_path
        AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        temp_path = cached_path.with_suffix(".tmp.mp3")
        result = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source_path),
                "-vn",
                "-map_metadata",
                "-1",
                "-codec:a",
                "libmp3lame",
                "-b:a",
                AUDIO_CACHE_BITRATE,
                "-ar",
                "24000",
                "-ac",
                "1",
                str(temp_path),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if result.returncode != 0 or not temp_path.exists():
            temp_path.unlink(missing_ok=True)
            print(f"Audio compression skipped: {result.stderr.strip()[-300:]}", flush=True)
            return source_path
        temp_path.replace(cached_path)
    return cached_path


def register_session(token: str, server: ThreadingHTTPServer) -> None:
    """Register or refresh a browser tab using the local app."""
    global SHUTDOWN_TIMER, SESSION_AUDIT_TIMER, SESSION_HAS_CONNECTED
    token = token.strip()
    if not token:
        raise ValueError("session token 不能为空")
    with SESSION_LOCK:
        ACTIVE_SESSIONS[token] = time.monotonic()
        SESSION_HAS_CONNECTED = True
        if SHUTDOWN_TIMER is not None:
            SHUTDOWN_TIMER.cancel()
            SHUTDOWN_TIMER = None
        if SESSION_AUDIT_TIMER is None:
            SESSION_AUDIT_TIMER = threading.Timer(
                SESSION_AUDIT_SECONDS,
                audit_sessions,
                args=(server,),
            )
            SESSION_AUDIT_TIMER.daemon = True
            SESSION_AUDIT_TIMER.start()


def audit_sessions(server: ThreadingHTTPServer) -> None:
    """Expire tabs that vanished without delivering a close event."""
    global SESSION_AUDIT_TIMER
    now = time.monotonic()
    should_stop = False
    with SESSION_LOCK:
        SESSION_AUDIT_TIMER = None
        stale_tokens = [
            token
            for token, last_seen in ACTIVE_SESSIONS.items()
            if now - last_seen > SESSION_STALE_SECONDS
        ]
        for token in stale_tokens:
            ACTIVE_SESSIONS.pop(token, None)
        if ACTIVE_SESSIONS:
            SESSION_AUDIT_TIMER = threading.Timer(
                SESSION_AUDIT_SECONDS,
                audit_sessions,
                args=(server,),
            )
            SESSION_AUDIT_TIMER.daemon = True
            SESSION_AUDIT_TIMER.start()
        elif SESSION_HAS_CONNECTED:
            should_stop = True
    if should_stop:
        schedule_shutdown_if_idle(server)


def schedule_shutdown_if_idle(server: ThreadingHTTPServer) -> None:
    """Stop the local server after the last browser tab has closed."""
    global SHUTDOWN_TIMER
    if persistent_server_enabled():
        return
    with SESSION_LOCK:
        if (
            not SESSION_HAS_CONNECTED
            or ACTIVE_SESSIONS
            or ACTIVE_OPERATIONS
            or SHUTDOWN_TIMER is not None
        ):
            return
        SHUTDOWN_TIMER = threading.Timer(
            SESSION_GRACE_SECONDS,
            shutdown_if_idle,
            args=(server,),
        )
        SHUTDOWN_TIMER.daemon = True
        SHUTDOWN_TIMER.start()


def close_session(token: str, server: ThreadingHTTPServer) -> None:
    with SESSION_LOCK:
        ACTIVE_SESSIONS.pop(token.strip(), None)
    schedule_shutdown_if_idle(server)


def begin_operation() -> None:
    global ACTIVE_OPERATIONS
    with SESSION_LOCK:
        ACTIVE_OPERATIONS += 1


def end_operation(server: ThreadingHTTPServer) -> None:
    global ACTIVE_OPERATIONS
    with SESSION_LOCK:
        ACTIVE_OPERATIONS = max(0, ACTIVE_OPERATIONS - 1)
    schedule_shutdown_if_idle(server)


def shutdown_if_idle(server: ThreadingHTTPServer) -> None:
    global SHUTDOWN_TIMER
    with SESSION_LOCK:
        SHUTDOWN_TIMER = None
        if not SESSION_HAS_CONNECTED or ACTIVE_SESSIONS or ACTIVE_OPERATIONS:
            return
    print("No browser sessions remain; stopping the English learning app.", flush=True)
    # shutdown() must run outside the request handler thread.
    threading.Thread(target=server.shutdown, daemon=True).start()


def schedule_startup_claim_timeout(server: ThreadingHTTPServer) -> None:
    """Stop a socket-triggered backend when no browser registers."""
    global SHUTDOWN_TIMER
    if persistent_server_enabled():
        return
    with SESSION_LOCK:
        if SHUTDOWN_TIMER is not None:
            return
        SHUTDOWN_TIMER = threading.Timer(
            SESSION_STARTUP_SECONDS,
            shutdown_if_unclaimed,
            args=(server,),
        )
        SHUTDOWN_TIMER.daemon = True
        SHUTDOWN_TIMER.start()


def shutdown_if_unclaimed(server: ThreadingHTTPServer) -> None:
    global SHUTDOWN_TIMER
    with SESSION_LOCK:
        SHUTDOWN_TIMER = None
        if SESSION_HAS_CONNECTED or ACTIVE_SESSIONS or ACTIVE_OPERATIONS:
            return
    print("No browser claimed the socket-activated app; stopping.", flush=True)
    threading.Thread(target=server.shutdown, daemon=True).start()


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
    "held": "hold",
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
    "rode": "ride",
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
    "described": "describe",
    "drawn": "draw",
    "frustrating": "frustrate",
    "smoother": "smooth",
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
    "unexpected",
}

def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value


def load_project_env() -> None:
    load_env_file(GLOBAL_ENV_FILE)
    load_env_file(ENV_FILE)


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


SECTION_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4}
SECTION_MARKER = re.compile(r"\bSection\s+(?P<number>[1-4]|one|two|three|four)\b", re.IGNORECASE)


def _section_number(raw_number: str) -> int:
    value = raw_number.strip().lower()
    return int(value) if value.isdigit() else SECTION_WORDS[value]


def listening_sections_from_file(path: Path) -> list[dict[str, object]]:
    """Split a Cambridge test transcript into its four usable listening units."""
    raw_markdown = path.read_text(encoding="utf-8", errors="replace")
    transcript = raw_markdown.split("## 转录文本", 1)[1] if "## 转录文本" in raw_markdown else ""
    if not transcript:
        return []
    starts: dict[int, int] = {}
    for match in SECTION_MARKER.finditer(transcript):
        number = _section_number(match.group("number"))
        following = transcript[match.end() : match.end() + 260].lower()
        is_content_start = any(
            phrase in following
            for phrase in (
                "you will hear",
                "in this section",
                "you are going to hear",
                "two students",
                "a talk given",
                "a conversation between",
            )
        )
        if is_content_start and number not in starts:
            starts[number] = match.start()
    ordered = sorted(starts.items())
    sections: list[dict[str, object]] = []
    test_match = re.search(r"Listening Test\s+(\d+)", raw_markdown, re.IGNORECASE)
    test_number = int(test_match.group(1)) if test_match else 0
    for index, (number, start) in enumerate(ordered):
        end = ordered[index + 1][1] if index + 1 < len(ordered) else len(transcript)
        text = transcript[start:end].strip()
        if len(text) < 180:
            continue
        identifier = f"cambridge-ielts-1-test{test_number}-section{number}"
        sections.append(
            {
                "id": identifier,
                "title": f"Cambridge IELTS 1 Listening Test {test_number} / Section {number}",
                "test": test_number,
                "section": number,
                "markdownPath": str(path.relative_to(PROJECT_ROOT)),
                "text": text,
            }
        )
    return sections


def listening_source_units() -> list[dict[str, object]]:
    if not LISTENING_SOURCE_DIR.exists():
        raise FileNotFoundError(f"听力转写目录不存在：{LISTENING_SOURCE_DIR}")
    units: list[dict[str, object]] = []
    for path in sorted(LISTENING_SOURCE_DIR.glob("test*.md")):
        units.extend(listening_sections_from_file(path))
    if not units:
        raise RuntimeError("没有从超给的听力转写中识别出可用的 Section")
    return units


def recent_listening_source_ids(limit: int = LISTENING_SOURCE_HISTORY_WINDOW) -> list[str]:
    identifiers: list[str] = []
    for _, article_path in article_files()[-limit:]:
        text = article_path.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"^- 听力片段：(.+)$", text, re.MULTILINE)
        if not match:
            continue
        identifiers.extend(
            identifier.strip()
            for identifier in match.group(1).split(";")
            if identifier.strip()
        )
    return identifiers


def choose_listening_source(next_day: int) -> dict[str, object]:
    """Pick a stable random listening unit while avoiding recent repetition."""
    units = listening_source_units()
    recent = set(recent_listening_source_ids())
    candidates = [unit for unit in units if str(unit["id"]) not in recent]
    if not candidates:
        # The initial pool contains only 16 sections. Once it is exhausted,
        # reset the cycle while still avoiding the last few days when possible.
        recent_tail = set(recent_listening_source_ids(4))
        candidates = [unit for unit in units if str(unit["id"]) not in recent_tail] or units
    candidates.sort(key=lambda unit: str(unit["id"]))
    digest = hashlib.sha256(f"listening-source:{next_day}".encode("utf-8")).hexdigest()
    return candidates[int(digest, 16) % len(candidates)]


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
            {
                "number": number,
                "english": english,
                "chinese": chinese,
                "glosses": build_hard_glosses(english),
            }
        )

    today_words = dedupe_words(clean_today_entries(text))
    audio_path = path.with_suffix(".mp3")
    return {
        "day": article_number(path.parent) or metadata.get("天数", ""),
        "title": title,
        "metadata": metadata,
        "reviewWords": review_words,
        "sentences": sentences,
        "todayWords": today_words,
        "todayWordMeanings": {
            word: concise_dictionary_meaning(word) for word in today_words
        },
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
    single_word = re.fullmatch(r"[^a-z]*([a-z]+(?:'[a-z]+)?)[^a-z]*", entry)
    if single_word:
        return normalize_word(single_word.group(1))
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


def hard_gloss_for_word(raw_word: str) -> str:
    requested = raw_word.lower().replace("’", "'")
    if requested in BASIC_WORDS_TO_SKIP:
        return ""
    try:
        index = dictionary_index()
        lemma = normalize_word(requested)
        entry = index.get(lemma) or index.get(requested)
    except (FileNotFoundError, RuntimeError):
        return ""
    if not entry:
        return ""

    translation = str(entry.get("t", "")).strip()
    if not translation:
        return ""
    tags = {str(tag).lower() for tag in entry.get("tags", [])}
    first_sense = re.split(r"[；;，,]", translation, maxsplit=1)[0].strip()
    is_content_word = bool(
        re.match(r"^(?:n|v|vt|vi|a|ad|adv)\.\s*", first_sense, re.IGNORECASE)
    )
    if not is_content_word:
        return ""
    # Keep simple everyday words visually clean; retain longer or IELTS-level
    # content words that are more useful for deliberate vocabulary study.
    if len(lemma) < 6 and not tags.intersection(HARD_GLOSS_TAGS):
        return ""
    # ECDICT prefixes senses with labels such as n., v. and prep.
    first_sense = re.sub(r"^[A-Za-z]+\.\s*", "", first_sense)
    return first_sense


def build_hard_glosses(english: str) -> list[dict[str, object]]:
    """Split an English sentence into words and punctuation with direct glosses."""
    segments: list[dict[str, object]] = []
    cursor = 0
    for match in re.finditer(r"[A-Za-z]+(?:['’][A-Za-z]+)?", english):
        if match.start() > cursor:
            segments.append({"text": english[cursor : match.start()], "isWord": False})
        word = match.group(0)
        segments.append(
            {
                "text": word,
                "gloss": hard_gloss_for_word(word),
                "isWord": True,
            }
        )
        cursor = match.end()
    if cursor < len(english):
        segments.append({"text": english[cursor:], "isWord": False})
    return segments


def concise_dictionary_meaning(word: str) -> str:
    try:
        result = lookup_dictionary(word)
    except (FileNotFoundError, ValueError, RuntimeError):
        return ""
    translation = str(result.get("translation", "")).strip()
    first_sense = re.split(r"[；;]", translation, maxsplit=1)[0].strip()
    first_sense = re.sub(r"^[A-Za-z]+\.\s*", "", first_sense)
    return first_sense


def article_review_snapshot(day: int, path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    review_text = section_between(text, "## 复习生词", "## 正文")
    review_words: list[str] = []
    meanings: dict[str, str] = {}
    for line in review_text.splitlines():
        match = re.match(r"^\s*-\s+(.+?)(?:\s+-\s+(.+))?$", line)
        if not match:
            continue
        word = normalize_entry(match.group(1))
        if not word or word == "无":
            continue
        review_words.append(word)
        meaning = (match.group(2) or "").strip()
        if meaning and meaning != "无":
            meanings[word] = meaning

    marked_words = dedupe_words(clean_today_entries(text))
    for word in marked_words:
        if word not in meanings:
            meanings[word] = concise_dictionary_meaning(word)
    return {
        "day": day,
        "reviewWords": dedupe_words(review_words),
        "markedWords": marked_words,
        "meanings": meanings,
    }


def write_text_if_changed(path: Path, content: str) -> None:
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def refresh_review_documents() -> tuple[dict[str, object], dict[str, object]]:
    with WRITE_LOCK, REVIEW_LOCK:
        snapshots = [article_review_snapshot(day, path) for day, path in article_files()]
        history, plan = build_review_state(snapshots)
        json_content = json.dumps(history, ensure_ascii=False, indent=2) + "\n"
        report_content = render_markdown_report(history)
        write_text_if_changed(REVIEW_JSON, json_content)
        write_text_if_changed(REVIEW_REPORT, report_content)
        return history, plan


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


def generation_mode(
    target_count: int,
    recent_count: int,
    deferred_due_count: int = 0,
    new_word_allowance: int = 0,
    current_marked_count: int = 0,
    inbox_waiting_count: int = 0,
) -> dict[str, object]:
    high_load = (
        target_count >= 8
        or recent_count >= 6
        or current_marked_count >= 6
        or deferred_due_count > 0
        or inbox_waiting_count > 15
    )
    if high_load:
        if deferred_due_count > 0:
            name = "积压清理（听力情节复习）"
        elif target_count >= 8 or current_marked_count >= 6:
            name = "高负荷听力情节复习"
        else:
            name = "收件箱减压（听力情节复习）"
        return {
            "name": name,
            "sentenceCount": "约 55-65",
            "minimumSentences": MIN_ARTICLE_SENTENCES,
            "maximumSentences": MAX_ARTICLE_SENTENCES,
            "newWords": "0",
            "usesSource": True,
        }
    return {
        "name": "听力情节扩展",
        "sentenceCount": "约 55-65",
        "minimumSentences": MIN_ARTICLE_SENTENCES,
        "maximumSentences": MAX_ARTICLE_SENTENCES,
        "newWords": f"最多 {max(0, new_word_allowance)}",
        "usesSource": True,
    }


def review_dashboard_payload(history: dict[str, object]) -> dict[str, object]:
    payload = dashboard_payload(history)
    summary = dict(history.get("summary", {}))
    plan = dict(history.get("nextPlan", {}))
    targets = list(plan.get("targetWords", []))
    recent = list(plan.get("recentWords", []))
    payload["generationMode"] = generation_mode(
        len(targets),
        len(recent),
        int(plan.get("deferredDueCount", 0)),
        int(plan.get("newWordAllowance", 0)),
        int(summary.get("currentMarkedWords", 0)),
        int(plan.get("inboxWaitingCount", 0)),
    )
    return payload


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
    required = [
        "# ",
        f"- 天数：第 {expected_day} 天",
        "- 来源真题：",
        "- 来源文件：",
        "- 听力片段：",
        "## 复习生词",
        "## 正文",
        "生单词:",
    ]
    missing = [item for item in required if item not in text]
    if missing:
        raise RuntimeError(f"模型输出缺少必要格式：{', '.join(missing)}")
    title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if title_match and title_match.group(1).strip().lower() in {"english title", "daily review"}:
        raise RuntimeError("模型忘记把标题换成具体标题，仍是模板占位符")
    count = len(re.findall(r"^\d+\.\s+", section_between(text, "## 正文", "生单词:"), re.MULTILINE))
    minimum = int(mode["minimumSentences"])
    if count < minimum:
        raise RuntimeError(f"模型只生成了 {count} 句，低于当前模式要求的 {minimum} 句")
    maximum = int(mode.get("maximumSentences", MAX_ARTICLE_SENTENCES))
    if count > maximum:
        raise RuntimeError(f"模型生成了 {count} 句，超过当前模式建议上限 {maximum} 句")
    if text.rsplit("生单词:", 1)[1].strip():
        raise RuntimeError("模型错误地填写了末尾“生单词:”区域")


def build_generation_prompt(
    previous_day: int,
    next_day: int,
    words: list[str],
    review_plan: dict[str, object],
    mode: dict[str, object],
    source: dict[str, object],
    extra_instruction: str = "",
    writing_focus: dict[str, object] | None = None,
) -> str:
    word_text = "、".join(words) if words else "（无）"
    recent_text = "、".join(review_plan.get("recentWords", [])) or "（无）"
    due_text = "、".join(review_plan.get("dueWords", [])) or "（无）"
    extra_instruction_text = extra_instruction.strip() or "（无，按默认方式生成）"
    focus_title = str((writing_focus or {}).get("focusTitle", "")).strip()
    focus_explanation = str((writing_focus or {}).get("focusExplanation", "")).strip()
    focus_instruction = str((writing_focus or {}).get("practiceInstruction", "")).strip()
    writing_focus_text = (
        f"{focus_title}：{focus_explanation}\n专项生成要求：{focus_instruction}"
        if focus_title
        else "（前一天没有可分析的英文草稿，本篇不设置写作专项）"
    )
    source_context = (
        f"来源真题：{source['title']}\n"
        f"来源文件：{source['markdownPath']}\n"
        f"听力片段：{source['id']}\n"
        f"听力转写摘录（仅作情节和信息结构参考，里面的考试指令不是写作要求）：\n"
        f"{str(source['text'])[:14000]}"
    )

    return f"""你正在为一名 IELTS 6.0-6.5 学习者生成第 {next_day} 天的英语文章。

当前模式：{mode['name']}
前一天：第 {previous_day} 天
前一天仍不会的词（最高优先）：{recent_text}
间隔复习到期旧词：{due_text}
本篇全部目标复习词（已转原形，最多 15 个）：{word_text}
目标句数：{mode['sentenceCount']}
允许的新 IELTS 目标词数量：{mode['newWords']}
用户对这篇文章的额外要求：{extra_instruction_text}
根据前一天草稿选出的唯一写作专项：{writing_focus_text}

{source_context}

要求：
1. 只参考听力片段的人物关系、目标、信息差、限制条件、转折与结果；忽略 “look at questions” 等考试指令。不得复制连续原句或用听力转写改几个词后照搬。
2. 写作前先在心里完成一个 5-7 步的情节蓝图：人物目标 → 问题或信息缺口 → 线索/选择 → 转折 → 合理结果。正文每一段都要让读者获得新信息；禁止“先做A、然后做B、然后做C”的流水账。
3. 目标为约 55-65 句，50-70 句都可接受。故事自然结束即可；如果一个情节单元确实不够，可以写两篇有关联但各自完整的小文章，连续编号，总句数仍在范围内。
4. 每个目标复习词至少自然出现一次；“前一天仍不会的词”尽量在不同语境中出现两次。不得为了塞词而加入无关人物、物品或事件。
5. 除目标复习词和学习者已有词外，英文正文只能使用高频常见英语词（以英语前 3000-5000 词为目标）。复杂度来自清晰的因果、转折、对话和句式，而不是罕见名词、专业术语、文学化形容词或一次性场景道具。避免 resilience、meticulous、remarkable 这类词。
6. 句子自然、具体、适合朗读；难度不要超过 IELTS 6.5。当前负荷高时不新增目标词，但仍然使用听力情节作为故事骨架。
7. `## 复习生词` 严格列出全部目标复习词的词典原形和简洁中文释义；没有目标词时写 `- 无 - 无`。
8. 每句英文下面紧跟中文解释，使用下面的固定 Markdown 格式。
9. 末尾 `生单词:` 必须留空。只输出 Markdown，不要代码围栏、前言或解释。
10. 如果存在“唯一写作专项”，正文要反复提供该结构的正确、自然示范，尤其让单数与复数、时态或相关句型形成可观察的对比；只强化这一项，不要同时加入第二个语法专项。
11. 如果“用户对这篇文章的额外要求”不是“（无，按默认方式生成）”，在不违反以上规则的前提下尽量满足；冲突时以本提示中的复习、词汇和格式规则为准。

固定格式：
# English Title

- 天数：第 {next_day} 天
- 来源真题：{source['title']}
- 来源文件：{source['markdownPath']}
- 听力片段：{source['id']}
- 复习内容：D{previous_day} 当前生词 + 到期旧词 + <当前模式>

## 复习生词

- word - 中文释义

## 正文

1. English sentence.

   > 中文解释。
   >

生单词:
"""


def find_codex() -> str | None:
    """Find Codex even when the app is launched outside VS Code or a shell."""
    configured = os.getenv("CODEX_BIN", "").strip()
    if configured:
        configured_path = Path(configured).expanduser()
        if configured_path.is_file() and os.access(configured_path, os.X_OK):
            return str(configured_path)

    available = shutil.which("codex")
    if available:
        return available

    # macOS GUI apps do not inherit VS Code's extension directory in PATH.
    # Search installed OpenAI VS Code extensions and use the newest one.
    extension_candidates = sorted(
        Path.home().glob(".vscode/extensions/openai.chatgpt-*/bin/*/codex"),
        reverse=True,
    )
    for candidate in extension_candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def find_uv() -> str | None:
    """Find uv when launchd starts the app with a minimal PATH."""
    configured = os.getenv("UV_BIN", "").strip()
    candidates = [
        Path(configured).expanduser() if configured else None,
        Path(shutil.which("uv")) if shutil.which("uv") else None,
        Path("/opt/homebrew/bin/uv"),
        Path("/usr/local/bin/uv"),
    ]
    for candidate in candidates:
        if candidate and candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def run_codex(prompt: str) -> str:
    codex = find_codex()
    if not codex:
        raise RuntimeError("未找到可用的 Codex CLI")
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
            raise RuntimeError(message)
        return output_path.read_text(encoding="utf-8")


def run_openai_api(prompt: str, max_output_tokens: int = 8_000) -> tuple[str, str]:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("未配置 OPENAI_API_KEY，无法调用 API 生成文章")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("未安装 openai 库，无法调用 API 生成文章") from exc
    model = os.getenv("OPENAI_TEXT_MODEL", TEXT_MODEL)
    response = OpenAI().responses.create(
        model=model,
        input=prompt,
        max_output_tokens=max_output_tokens,
    )
    return response.output_text, model


def request_generated_text(
    prompt: str, *, max_output_tokens: int = 8_000
) -> tuple[str, str, bool]:
    """Generate text with independent writer/reviewer prompts.

    Codex CLI is the primary generator. If Codex is missing, not logged in,
    or out of quota, automatically fall back to the OpenAI API (when
    OPENAI_API_KEY is configured). Returns (text, generator_label, used_codex).
    """
    if find_codex():
        try:
            return run_codex(prompt), "Codex CLI", True
        except RuntimeError as codex_error:
            if not os.getenv("OPENAI_API_KEY"):
                raise RuntimeError(f"Codex CLI 生成失败：{codex_error}") from codex_error
            text, model = run_openai_api(prompt, max_output_tokens)
            return text, f"{model}（Codex 不可用，已自动改用 API：{codex_error}）", False

    if os.getenv("OPENAI_API_KEY"):
        text, model = run_openai_api(prompt, max_output_tokens)
        return text, f"{model}（未检测到 Codex CLI，已自动改用 API）", False

    raise RuntimeError(
        "没有可用的文章生成方式：请配置 OPENAI_API_KEY，或安装并登录 Codex CLI。"
    )


def request_generated_markdown(prompt: str) -> tuple[str, str, bool]:
    return request_generated_text(prompt, max_output_tokens=8_000)


def article_vocabulary_report(
    markdown: str, target_words: list[str], known_words: list[str]
) -> dict[str, object]:
    return vocabulary_report(
        section_between(markdown, "## 正文", "生单词:"),
        allowed_words=target_words,
        known_words=known_words,
    )


def build_article_critic_prompt(
    markdown: str,
    target_words: list[str],
    known_words: list[str],
    vocabulary_check: dict[str, object],
) -> str:
    target_text = "、".join(target_words) if target_words else "（无）"
    known_text = "、".join(known_words) or "（无）"
    flagged_text = "、".join(report_words(vocabulary_check)) or "（无）"
    return f"""你是第二位独立审稿人。第一位写作者已经完成一篇 IELTS 学习文章；你要怀疑地检查它并输出修订后的完整 Markdown。

目标复习词（必须保留）：{target_text}
学习者已学过、允许保留的词：{known_text}
程序按英语前5000高频词检查出的候选偏词：{flagged_text}

请完成以下审稿工作：
1. 把候选偏词改成更常见的表达；目标词和已学词除外。不得加入新的偏词、专业词、罕见姓名或为了装饰场景而出现一次的道具词。
2. 检查故事是否有清晰因果和信息推进。删改流水账、重复动作、无结果的旁支和前后矛盾。
3. 保持文章自然、适合朗读，不能把正常英语改成幼稚的逐词替换。
4. 保持全部 Markdown 结构、每个英文句子后的中文解释、听力来源元数据、目标词覆盖、句子编号和总句数。末尾 `生单词:` 必须为空。
5. 只输出修订后的完整 Markdown，不要审稿说明、代码围栏或前言。

待审文章：
{markdown}
"""


def extract_article_english(markdown: str) -> str:
    body = section_between(markdown, "## 正文", "生单词:")
    return "\n".join(
        match.group(1).strip()
        for match in re.finditer(r"^\s*\d+\.\s+(.+?)\s*$", body, re.MULTILINE)
    )


def parse_model_json(text: str) -> dict[str, object]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end < start:
        raise RuntimeError("模型没有返回 JSON 对象")
    try:
        payload = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise RuntimeError("模型返回的 JSON 格式错误") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("模型返回的 JSON 不是对象")
    return payload


def diagnose_previous_writing(
    previous_day: int, article_path: Path
) -> dict[str, object] | None:
    """Choose exactly one learning focus from the previous day's draft."""
    practice = read_writing_practice(article_path)
    if practice is None:
        return None
    attempts = practice.get("attempts", [])
    latest_attempt = (
        attempts[-1]
        if isinstance(attempts, list) and attempts and isinstance(attempts[-1], dict)
        else None
    )
    draft = str((latest_attempt or {}).get("originalText", "")).strip()
    if not draft:
        draft = str(practice.get("draftText", "")).strip()
    if not draft:
        draft = "\n\n".join(
            part.strip() for part in draft_paragraphs_for_practice(practice) if part.strip()
        )
    if not draft:
        return None

    previous_feedback = "\n".join(
        f"- {item}" for item in _clean_feedback_list((latest_attempt or {}).get("feedback"), 4)
    ) or "（没有已有反馈，请直接分析草稿）"
    prompt = f"""你是英语写作诊断教练。分析第 {previous_day} 天的学习者英文草稿，找出 2-4 个最严重、最反复、最影响理解或 IELTS 分数的问题，但下一天只能训练其中一个。

选择规则：
1. 只选择一个范围清楚、可通过一篇中译英反复练习的问题，例如“一般过去时”“主谓一致”“although 后不再接 but”。
2. 优先选择反复出现的基础问题；不要选择“整体语法较差”“表达不自然”这种过宽标签。
3. focusExplanation 用简短中文说明草稿中出现了什么错误。
4. practiceInstruction 明确告诉下一篇阅读和中译英应怎样反复呈现正确结构。
5. majorIssues 可以列出多个诊断结果，但 focusTitle 必须只有一个问题，不能用“和、以及、/”合并两个问题。

只返回合法 JSON：
{{
  "majorIssues": ["问题一", "问题二"],
  "focusTitle": "下一天只训练的一个问题",
  "focusExplanation": "为什么优先解决它",
  "practiceInstruction": "下一篇内容如何训练它"
}}

已有反馈：
{previous_feedback}

学习者草稿：
{draft}
"""
    generated, _generator, _used_codex = request_generated_text(
        prompt, max_output_tokens=1_200
    )
    diagnosis = parse_model_json(generated)
    major_issues = _clean_feedback_list(diagnosis.get("majorIssues"), 4)
    focus_title = str(diagnosis.get("focusTitle", "")).strip()
    focus_explanation = str(diagnosis.get("focusExplanation", "")).strip()
    practice_instruction = str(diagnosis.get("practiceInstruction", "")).strip()
    if not major_issues or not focus_title or not focus_explanation or not practice_instruction:
        raise RuntimeError("前一天写作诊断缺少主要问题或唯一训练重点")
    return {
        "sourceDay": previous_day,
        "majorIssues": major_issues,
        "focusTitle": focus_title,
        "focusExplanation": focus_explanation,
        "practiceInstruction": practice_instruction,
    }


def writing_practice_path(article_path: Path) -> Path:
    return article_path.with_name(f"{article_path.stem}.writing.json")


def writing_workspace_path(article_path: Path) -> Path:
    """Human-readable counterpart of the writing JSON, kept in the article folder."""
    return article_path.with_name(f"{article_path.stem}.translation.md")


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def markdown_code_block(value: object, empty_message: str = "") -> str:
    text = str(value or "").strip()
    if not text:
        return empty_message
    longest_backticks = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest_backticks + 1)
    return f"{fence}text\n{text}\n{fence}"


def draft_paragraphs_for_practice(practice: dict[str, object]) -> list[str]:
    """Return one editable English draft per Chinese paragraph, including legacy drafts."""
    prompt_paragraphs = practice.get("paragraphs", [])
    paragraph_count = len(prompt_paragraphs) if isinstance(prompt_paragraphs, list) else 0
    stored = practice.get("draftParagraphs")
    if isinstance(stored, list):
        drafts = [str(item) for item in stored]
    else:
        legacy_text = str(practice.get("draftText", "")).strip()
        drafts = re.split(r"\n\s*\n", legacy_text) if legacy_text else []
    if paragraph_count:
        return (drafts[:paragraph_count] + [""] * paragraph_count)[:paragraph_count]
    return drafts


def corrected_paragraphs_for_attempt(
    attempt: dict[str, object] | None, paragraph_count: int
) -> list[str] | None:
    """Split the latest attempt's correctedText back into per-paragraph pieces.

    Returns None when there is no attempt yet, or the correction did not
    preserve the same paragraph count, so callers can fall back instead of
    misaligning a paragraph's correction with the wrong Chinese prompt.
    """
    if not attempt or not paragraph_count:
        return None
    corrected = str(attempt.get("correctedText", "")).strip()
    if not corrected:
        return None
    pieces = [part.strip() for part in re.split(r"\n\s*\n", corrected) if part.strip()]
    if len(pieces) != paragraph_count:
        return None
    return pieces


def writing_workspace_markdown(practice: dict[str, object]) -> str:
    """Render the learner's current work in a Markdown file for VS Code assistants."""
    day = practice.get("day", "")
    title = str(practice.get("title", "中译英练习")).strip() or "中译英练习"
    paragraphs = [str(item).strip() for item in practice.get("paragraphs", []) if str(item).strip()]
    suggested_words = [str(item).strip() for item in practice.get("suggestedWords", []) if str(item).strip()]
    attempts = practice.get("attempts", [])
    if not isinstance(attempts, list):
        attempts = []
    latest_attempt = attempts[-1] if attempts and isinstance(attempts[-1], dict) else None
    corrected_paragraphs = corrected_paragraphs_for_attempt(latest_attempt, len(paragraphs))
    lines = [
        f"# 第 {day} 天中译英：{title}",
        "",
    ]
    writing_focus = practice.get("writingFocus")
    if isinstance(writing_focus, dict) and str(writing_focus.get("focusTitle", "")).strip():
        lines.extend(
            [
                "## 本次只解决一个问题",
                "",
                f"**{str(writing_focus.get('focusTitle', '')).strip()}**",
                "",
                str(writing_focus.get("focusExplanation", "")).strip(),
                "",
                f"练习方法：{str(writing_focus.get('practiceInstruction', '')).strip()}",
                "",
            ]
        )
    lines.extend([
        "## 中文题目",
        "",
        str(practice.get("instructions", "")).strip(),
        "",
    ])
    for paragraph in paragraphs:
        lines.extend([paragraph, ""])
    lines.extend(["## 建议使用词", ""])
    lines.append("、".join(f"`{word}`" for word in suggested_words) or "（无）")
    lines.extend(["", "## 当前英文草稿", ""])
    drafts = draft_paragraphs_for_practice(practice)
    if paragraphs:
        for index, (paragraph, draft) in enumerate(zip(paragraphs, drafts), start=1):
            lines.extend([f"### 第 {index} 段", "", "#### 中文", "", paragraph, ""])
            lines.extend(["#### 英文草稿", "", markdown_code_block(draft, "（尚未输入；网页输入后会自动同步。）"), ""])
            if corrected_paragraphs:
                lines.extend(["#### 订正", "", markdown_code_block(corrected_paragraphs[index - 1]), ""])
    else:
        lines.append(markdown_code_block(practice.get("draftText"), "（尚未输入；网页输入后会自动同步。）"))
    lines.extend(["", "## 提交与订正记录", ""])

    if not attempts:
        lines.append("（尚未提交。）")
    else:
        for record in attempts:
            if not isinstance(record, dict):
                continue
            attempt_id = record.get("id", "")
            level = str(record.get("levelLabel", "")).strip()
            submitted_at = str(record.get("submittedAt", "")).strip()
            metadata = " | ".join(part for part in (level, submitted_at) if part)
            lines.extend([f"### 第 {attempt_id} 次{f'：{metadata}' if metadata else ''}", ""])
            lines.extend(["#### 学习者提交", "", markdown_code_block(record.get("originalText")), ""])
            lines.extend(["#### 网页订正", "", markdown_code_block(record.get("correctedText")), ""])
            feedback = _clean_feedback_list(record.get("feedback"), 4)
            coverage = _clean_feedback_list(record.get("coverage"), 3)
            suggestions = [str(item).strip() for item in record.get("suggestions", []) if str(item).strip()]
            if feedback or coverage or suggestions:
                lines.extend(["#### 反馈", ""])
                lines.extend(f"- {item}" for item in [*feedback, *coverage])
                if suggestions:
                    lines.append(f"- 可尝试使用：{'、'.join(suggestions)}")
                lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_writing_workspace(article_path: Path, practice: dict[str, object]) -> None:
    path = writing_workspace_path(article_path)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(writing_workspace_markdown(practice), encoding="utf-8")
    temporary.replace(path)


def build_writing_practice_prompt(
    day: int,
    article_path: Path,
    markdown: str,
    target_words: list[str],
    writing_focus: dict[str, object] | None = None,
) -> str:
    target_text = "、".join(target_words) if target_words else "（无）"
    focus_text = (
        f"{writing_focus.get('focusTitle')}：{writing_focus.get('practiceInstruction')}"
        if writing_focus
        else "（无专项）"
    )
    return f"""根据下面第 {day} 天的英文阅读，制作一题给英语学习者的中译英练习。

目标复习词：{target_text}
本次唯一写作专项：{focus_text}

规则：
1. 中文题必须保留相似的因果骨架和主要信息，但绝对不能逐句翻译原阅读。
2. 改变叙述顺序、人物视角或部分具体细节；用 2-4 个中文段落组织为一个小故事或说明。
3. 中文题应自然引导学习者使用目标复习词的原有含义，但不要直接在正文中给英文答案。
4. 不要给参考英文答案、评分或任何英文句子。
5. 如果有写作专项，中文题必须安排多处自然语境，让学习者反复使用该专项；不要额外设计第二个语法难点。
6. 只返回下列 JSON，不要代码围栏：
{{
  "title": "中文练习标题",
  "instructions": "一句简短中文说明",
  "paragraphs": ["中文段落一", "中文段落二"],
  "suggestedWords": ["目标词"]
}}

阅读英文正文：
{extract_article_english(markdown)}

文章路径：{article_path.relative_to(PROJECT_ROOT)}
"""


def generate_writing_practice(
    day: int,
    article_path: Path,
    markdown: str,
    target_words: list[str],
    writing_focus: dict[str, object] | None = None,
) -> tuple[dict[str, object], str, bool]:
    prompt = build_writing_practice_prompt(
        day, article_path, markdown, target_words, writing_focus
    )
    last_error: RuntimeError | None = None
    for _ in range(MAX_GENERATION_ATTEMPTS):
        generated, generator, used_codex = request_generated_text(
            prompt, max_output_tokens=2_500
        )
        try:
            practice = parse_model_json(generated)
            title = str(practice.get("title", "")).strip()
            instructions = str(practice.get("instructions", "")).strip()
            paragraphs = practice.get("paragraphs", [])
            if not title or not instructions or not isinstance(paragraphs, list):
                raise RuntimeError("中译英题目缺少标题、说明或段落")
            cleaned_paragraphs = [str(item).strip() for item in paragraphs if str(item).strip()]
            if not 2 <= len(cleaned_paragraphs) <= 4:
                raise RuntimeError("中译英题目必须包含 2-4 个中文段落")
            return (
                {
                    "version": 1,
                    "day": day,
                    "articlePath": str(article_path.relative_to(PROJECT_ROOT)),
                    "createdAt": datetime.now(UTC).isoformat(),
                    "readingCompletedAt": None,
                    "title": title,
                    "instructions": instructions,
                    "paragraphs": cleaned_paragraphs,
                    "suggestedWords": dedupe_words(
                        list(practice.get("suggestedWords", [])) or target_words
                    ),
                    "writingFocus": writing_focus,
                    "attempts": [],
                },
                generator,
                used_codex,
            )
        except RuntimeError as exc:
            last_error = exc
            prompt += f"\n\n上次返回无效，原因：{exc}。请严格只返回要求的 JSON。"
    assert last_error is not None
    raise last_error


def read_writing_practice(article_path: Path) -> dict[str, object] | None:
    path = writing_practice_path(article_path)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("中译英练习数据格式错误")
    return payload


def public_writing_practice(practice: dict[str, object] | None, day: int) -> dict[str, object]:
    if practice is None:
        return {
            "day": day,
            "available": False,
            "canCreate": True,
            "message": "中译英练习会从新生成的每日文章开始提供。",
        }
    article_reference = Path(str(practice.get("articlePath", "")))
    workspace_reference = article_reference.with_name(
        f"{article_reference.stem}.translation.md"
    )
    paragraphs = list(practice.get("paragraphs", []))
    attempts = practice.get("attempts", [])
    latest_attempt = (
        attempts[-1] if isinstance(attempts, list) and attempts and isinstance(attempts[-1], dict) else None
    )
    return {
        "day": day,
        "available": True,
        "readingCompleted": bool(practice.get("readingCompletedAt")),
        "title": str(practice.get("title", "")),
        "instructions": str(practice.get("instructions", "")),
        "writingFocus": practice.get("writingFocus"),
        "paragraphs": paragraphs,
        "suggestedWords": list(practice.get("suggestedWords", [])),
        "draftText": str(practice.get("draftText", "")),
        "draftParagraphs": draft_paragraphs_for_practice(practice),
        "draftUpdatedAt": str(practice.get("draftUpdatedAt", "")),
        "workspacePath": str(workspace_reference),
        "attempts": list(practice.get("attempts", [])),
        # Latest correction split back into one entry per Chinese paragraph, so
        # the reading page can show it right next to that paragraph's draft
        # instead of only inside the submission history at the bottom.
        "latestCorrectionParagraphs": corrected_paragraphs_for_attempt(latest_attempt, len(paragraphs)) or [],
    }


def get_writing_practice(day: object | None = None) -> dict[str, object]:
    article_day, article_path = article_for_day(day)
    with WRITING_LOCK:
        practice = read_writing_practice(article_path)
        if practice is not None and not writing_workspace_path(article_path).exists():
            write_writing_workspace(article_path, practice)
        return public_writing_practice(practice, article_day)


def article_target_words(article_path: Path) -> list[str]:
    text = article_path.read_text(encoding="utf-8", errors="replace")
    review_words: list[str] = []
    for line in section_between(text, "## 复习生词", "## 正文").splitlines():
        match = re.match(r"^\s*-\s+(.+?)(?:\s+-\s+.+)?$", line)
        if match:
            review_words.append(match.group(1))
    return dedupe_words(review_words + clean_today_entries(text))


def create_writing_practice(day: object | None = None) -> dict[str, object]:
    """Backfill one exercise for a historical article on explicit user action."""
    load_project_env()
    article_day, article_path = article_for_day(day)
    with WRITING_LOCK:
        existing = read_writing_practice(article_path)
        if existing is not None:
            return public_writing_practice(existing, article_day)
        markdown = article_path.read_text(encoding="utf-8", errors="replace")
        practice, _generator, _used_codex = generate_writing_practice(
            article_day, article_path, markdown, article_target_words(article_path)
        )
        # This action is available only from the writing tab, which is the
        # learner's explicit confirmation that this historical reading is done.
        practice["readingCompletedAt"] = datetime.now(UTC).isoformat()
        write_json(writing_practice_path(article_path), practice)
        write_writing_workspace(article_path, practice)
        return public_writing_practice(practice, article_day)


def complete_reading(day: object | None = None) -> dict[str, object]:
    article_day, article_path = article_for_day(day)
    with WRITING_LOCK:
        practice = read_writing_practice(article_path)
        if practice is None:
            return public_writing_practice(None, article_day)
        if not practice.get("readingCompletedAt"):
            practice["readingCompletedAt"] = datetime.now(UTC).isoformat()
            write_json(writing_practice_path(article_path), practice)
            write_writing_workspace(article_path, practice)
        return public_writing_practice(practice, article_day)


def save_writing_draft(
    day: object, draft_text: str, draft_paragraphs: list[object] | None = None
) -> dict[str, object]:
    if len(draft_text) > MAX_WRITING_INPUT_LENGTH:
        raise ValueError(f"英文内容最多 {MAX_WRITING_INPUT_LENGTH} 个字符")
    article_day, article_path = article_for_day(day)
    with WRITING_LOCK:
        practice = read_writing_practice(article_path)
        if practice is None:
            raise FileNotFoundError("当前日期没有中译英练习")
        if draft_paragraphs is not None:
            expected_count = len(practice.get("paragraphs", []))
            if len(draft_paragraphs) != expected_count:
                raise ValueError("英文草稿段落数量与题目不一致")
            drafts = [str(item) for item in draft_paragraphs]
        else:
            drafts = draft_paragraphs_for_practice({**practice, "draftText": draft_text})
        combined_text = "\n\n".join(part.strip() for part in drafts if part.strip())
        if len(combined_text) > MAX_WRITING_INPUT_LENGTH:
            raise ValueError(f"英文内容最多 {MAX_WRITING_INPUT_LENGTH} 个字符")
        practice["draftText"] = combined_text
        practice["draftParagraphs"] = drafts
        practice["draftUpdatedAt"] = datetime.now(UTC).isoformat()
        write_json(writing_practice_path(article_path), practice)
        write_writing_workspace(article_path, practice)
        workspace_path = writing_workspace_path(article_path)
        try:
            workspace_reference = str(workspace_path.relative_to(PROJECT_ROOT))
        except ValueError:
            workspace_reference = str(workspace_path)
        return {
            "day": article_day,
            "saved": True,
            "draftUpdatedAt": practice["draftUpdatedAt"],
            "workspacePath": workspace_reference,
        }


def _clean_feedback_list(value: object, limit: int = 6) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()][:limit]


def build_writing_feedback_prompt(
    practice: dict[str, object], submitted_text: str, level: str
) -> str:
    level_instructions = {
        "basic": "只修正拼写、语法、冠词、时态、单复数和明显的介词错误，最大程度保留学习者原句和语序。",
        "natural": "在保留学习者原意的前提下，修正搭配、语序和衔接，使其成为自然常用的英文。",
        "advanced": "允许重组句子和段落，使因果与衔接清晰，但保持在 IELTS 6.0-6.5 的常见英语范围，不展示偏词。",
    }
    target_text = "、".join(map(str, practice.get("suggestedWords", []))) or "（无）"
    writing_focus = practice.get("writingFocus")
    focus_title = (
        str(writing_focus.get("focusTitle", "")).strip()
        if isinstance(writing_focus, dict)
        else ""
    )
    focus_feedback_rule = (
        f"今天只教学和解释“{focus_title}”。修正版仍可保证全文正确，但 feedback 只反馈这一项，"
        "不要再列出其他语法或表达问题。"
        if focus_title
        else "今天没有预设专项，可按通常方式给出不超过4条反馈。"
    )
    chinese_prompt = "\n\n".join(map(str, practice.get("paragraphs", [])))
    return f"""你是中译英教练，不存在唯一标准答案。请根据中文题目审阅学习者的英文，并给出“{WRITING_LEVELS[level]}”级别的修正版。

修正强度：{level_instructions[level]}
今日建议使用词：{target_text}
专项反馈规则：{focus_feedback_rule}

所有英文都应以英语前3000-5000常见词为主。不能为了显得高级而引入罕见、专业或文学化词。如果学习者原句里某个概念已经用了一个常见词表达（例如用 "food hall" 表示食堂），请直接保留那个词，不要替换成更少见的同义词（例如 "cafeteria"）。不要因为学习者没有使用建议词就判错；可在 suggestions 中给出可选提示。

只返回合法 JSON：
{{
  "correctedText": "完整修正版英文",
  "feedback": ["不超过4条中文反馈"],
  "usedTargetWords": ["正确使用的建议词"],
  "suggestions": ["可以考虑使用但未强制的建议词"],
  "coverage": ["内容覆盖或遗漏提示，最多3条"]
}}

中文题目：
{chinese_prompt}

学习者提交：
{submitted_text}
"""


def submit_writing_attempt(day: object, submitted_text: str, level: str) -> dict[str, object]:
    if level not in WRITING_LEVELS:
        raise ValueError("修正等级无效")
    submitted_text = submitted_text.strip()
    if not submitted_text:
        raise ValueError("请先输入英文内容")
    if len(submitted_text) > MAX_WRITING_INPUT_LENGTH:
        raise ValueError(f"英文内容最多 {MAX_WRITING_INPUT_LENGTH} 个字符")
    load_project_env()
    article_day, article_path = article_for_day(day)
    with WRITING_LOCK:
        practice = read_writing_practice(article_path)
        if practice is None:
            raise FileNotFoundError("当前日期没有中译英练习")

        prompt = build_writing_feedback_prompt(practice, submitted_text, level)
        last_error: RuntimeError | None = None
        known_words = sorted(refresh_review_documents()[0].get("words", {}).keys())
        feedback_payload: dict[str, object] | None = None
        vocabulary_check: dict[str, object] | None = None
        generator = ""
        used_codex = False
        for attempt in range(MAX_GENERATION_ATTEMPTS):
            generated, generator, used_codex = request_generated_text(
                prompt, max_output_tokens=3_500
            )
            try:
                candidate = parse_model_json(generated)
                corrected = str(candidate.get("correctedText", "")).strip()
                if not corrected:
                    raise RuntimeError("修正版为空")
                vocabulary_check = vocabulary_report(
                    corrected,
                    allowed_words=list(practice.get("suggestedWords", [])),
                    known_words=known_words,
                )
                flagged = report_words(vocabulary_check)
                if flagged:
                    raise RuntimeError("修正版仍含候选偏词：" + "、".join(flagged))
                feedback_payload = {
                    "correctedText": corrected,
                    "feedback": _clean_feedback_list(candidate.get("feedback"), 4),
                    "usedTargetWords": dedupe_words(candidate.get("usedTargetWords", [])),
                    "suggestions": dedupe_words(candidate.get("suggestions", [])),
                    "coverage": _clean_feedback_list(candidate.get("coverage"), 3),
                    "commonVocabularyCheck": vocabulary_check,
                }
                break
            except RuntimeError as exc:
                last_error = exc
                prompt += (
                    f"\n\n上一次修正未通过高频词验证，原因：{exc}。"
                    "请把列出的每个词都换成前3000-5000常见词范围内的替代表达"
                    "（优先检查学习者原句是否已经用了一个常见词表示同样的意思，直接沿用即可）。"
                    "只返回完整 JSON。"
                )
        if feedback_payload is None:
            assert last_error is not None
            raise last_error

        attempts = practice.setdefault("attempts", [])
        if not isinstance(attempts, list):
            raise RuntimeError("中译英提交历史格式错误")
        record = {
            "id": len(attempts) + 1,
            "submittedAt": datetime.now(UTC).isoformat(),
            "level": level,
            "levelLabel": WRITING_LEVELS[level],
            "originalText": submitted_text,
            **feedback_payload,
        }
        attempts.append(record)
        write_json(writing_practice_path(article_path), practice)
        write_writing_workspace(article_path, practice)
        return {
            "day": article_day,
            "attempt": record,
            "generator": generator,
            "usedCodex": used_codex,
            "practice": public_writing_practice(practice, article_day),
        }


def generate_next_article(extra_instruction: str = "") -> dict[str, object]:
    load_project_env()
    previous_day, previous_article_path = latest_article()
    writing_focus = diagnose_previous_writing(previous_day, previous_article_path)
    review_history, review_plan = refresh_review_documents()
    words = dedupe_words(list(review_plan.get("targetWords", [])))
    recent_words = list(review_plan.get("recentWords", []))
    mode = generation_mode(
        len(words),
        len(recent_words),
        int(review_plan.get("deferredDueCount", 0)),
        int(review_plan.get("newWordAllowance", 0)),
        int(dict(review_history.get("summary", {})).get("currentMarkedWords", 0)),
        int(review_plan.get("inboxWaitingCount", 0)),
    )
    next_day = previous_day + 1
    source = choose_listening_source(next_day)
    prompt = build_generation_prompt(
        previous_day,
        next_day,
        words,
        review_plan,
        mode,
        source,
        extra_instruction,
        writing_focus,
    )
    known_words = sorted(review_history.get("words", {}).keys())

    markdown = None
    writer_generator = ""
    critic_generator = ""
    used_codex = False
    last_error: RuntimeError | None = None
    attempt_prompt = prompt
    for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
        generated_text, writer_generator, writer_used_codex = request_generated_markdown(
            attempt_prompt
        )
        candidate = strip_model_fences(generated_text)
        try:
            validate_generated_article(candidate, next_day, mode)
            vocabulary_check = article_vocabulary_report(candidate, words, known_words)
            critic_prompt = build_article_critic_prompt(
                candidate, words, known_words, vocabulary_check
            )
            critic_text, critic_generator, critic_used_codex = request_generated_markdown(
                critic_prompt
            )
            revised = strip_model_fences(critic_text)
            validate_generated_article(revised, next_day, mode)
            final_check = article_vocabulary_report(revised, words, known_words)
            flagged = report_words(final_check)
            if flagged:
                raise RuntimeError("审稿后仍有候选偏词：" + "、".join(flagged))
        except RuntimeError as exc:
            last_error = exc
            attempt_prompt = (
                f"{prompt}\n\n"
                f"第 {attempt} 次草稿或审稿未通过，原因：{exc}。"
                "请重写完整文章，优先保证情节完整和高频词验证，不要只补几句。"
            )
            continue
        markdown = revised
        used_codex = writer_used_codex and critic_used_codex
        last_error = None
        break

    if markdown is None:
        assert last_error is not None
        raise RuntimeError(
            f"连续 {MAX_GENERATION_ATTEMPTS} 次生成与审稿都未通过，最后一次原因：{last_error}"
        )

    title_match = re.search(r"^#\s+(.+)$", markdown, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else "Daily Review"
    folder_name = slugify_title(title, next_day)
    day_dir = ARTICLES_DIR / folder_name
    if day_dir.exists():
        raise RuntimeError(f"目标文件夹已经存在：{day_dir.relative_to(PROJECT_ROOT)}")
    day_dir.mkdir(parents=True)
    article_path = day_dir / f"{folder_name}.md"
    article_path.write_text(markdown, encoding="utf-8")

    writing_warning = None
    try:
        practice, _practice_generator, _practice_used_codex = generate_writing_practice(
            next_day, article_path, markdown, words, writing_focus
        )
        write_json(writing_practice_path(article_path), practice)
    except RuntimeError as exc:
        writing_warning = f"中译英题目未生成：{exc}"

    audio_warning = None
    uv = find_uv()
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

    updated_history, _ = refresh_review_documents()
    warnings = [warning for warning in (audio_warning, writing_warning) if warning]
    generator = f"写作：{writer_generator}；审稿：{critic_generator}"
    return {
        "day": next_day,
        "title": title,
        "mode": mode["name"],
        "markdownPath": str(article_path.relative_to(PROJECT_ROOT)),
        "audioGenerated": article_path.with_suffix(".mp3").exists(),
        "warning": "\n".join(warnings) if warnings else None,
        "generator": generator,
        "usedCodex": used_codex,
        "generatorNotice": None if used_codex else f"本篇含 API 生成步骤：{generator}",
        "reviewPlan": review_dashboard_payload(updated_history),
    }


class AppHandler(BaseHTTPRequestHandler):
    server_version = "EnglishLearningWeb/1.0"

    def log_message(self, format_string: str, *args: object) -> None:
        print(f"[{self.log_date_time_string()}] {format_string % args}")

    def send_json(self, payload: object, status: int = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        compressed = len(data) >= 1024 and "gzip" in self.headers.get("Accept-Encoding", "")
        if compressed:
            data = gzip.compress(data, compresslevel=6)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if compressed:
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
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
        file_stat = requested.stat()
        etag = f'"{file_stat.st_mtime_ns:x}-{file_stat.st_size:x}"'
        # This is a local learning app under active development. Revalidate all
        # static assets so a normal refresh immediately picks up CSS/JS edits.
        cache_control = "no-cache"
        if self.headers.get("If-None-Match") == etag:
            self.send_response(HTTPStatus.NOT_MODIFIED)
            self.send_header("Cache-Control", cache_control)
            self.send_header("ETag", etag)
            self.end_headers()
            return
        data = requested.read_bytes()
        content_type = mimetypes.guess_type(requested.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", cache_control)
        self.send_header("ETag", etag)
        self.end_headers()
        self.wfile.write(data)

    def send_audio(self, day: object | None = None) -> None:
        _, article_path = article_for_day(day)
        audio_path = article_path.with_suffix(".mp3")
        if not audio_path.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "当前文章没有 MP3")
            return
        audio_path = optimized_audio_path(audio_path)
        audio_stat = audio_path.stat()
        size = audio_stat.st_size
        etag = f'"{audio_stat.st_mtime_ns:x}-{size:x}"'
        start, end = 0, size - 1
        status = HTTPStatus.OK
        range_header = self.headers.get("Range")
        if not range_header and self.headers.get("If-None-Match") == etag:
            self.send_response(HTTPStatus.NOT_MODIFIED)
            self.send_header("Cache-Control", "private, max-age=3600")
            self.send_header("ETag", etag)
            self.end_headers()
            return
        if range_header:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
            if not match or not any(match.groups()):
                self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                return
            if match.group(1):
                start = int(match.group(1))
                if match.group(2):
                    end = min(int(match.group(2)), size - 1)
            else:
                suffix_length = int(match.group(2))
                start = max(size - suffix_length, 0)
            status = HTTPStatus.PARTIAL_CONTENT
        if start > end or start >= size:
            self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            return
        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "private, max-age=3600")
        self.send_header("ETag", etag)
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
            elif path == "/api/review-plan":
                history, _ = refresh_review_documents()
                self.send_json(review_dashboard_payload(history))
            elif path == "/api/writing-practice":
                self.send_json(get_writing_practice(day))
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
            if path == "/api/session":
                register_session(str(payload.get("token", "")), self.server)
                self.send_json({"active": True})
                return
            if path == "/api/session-close":
                close_session(str(payload.get("token", "")), self.server)
                self.send_json({"closed": True})
                return
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
                history, _ = refresh_review_documents()
                self.send_json(
                    {
                        "day": day,
                        "words": saved,
                        "saved": True,
                        "updatedAt": article_path.stat().st_mtime_ns,
                        "reviewPlan": review_dashboard_payload(history),
                    }
                )
                return
            if path == "/api/complete-reading":
                self.send_json(complete_reading(payload.get("day")))
                return
            if path == "/api/create-writing-practice":
                begin_operation()
                try:
                    practice = create_writing_practice(payload.get("day"))
                finally:
                    end_operation(self.server)
                self.send_json(practice, HTTPStatus.CREATED)
                return
            if path == "/api/writing-draft":
                self.send_json(
                    save_writing_draft(
                        payload.get("day"),
                        str(payload.get("text", "") or ""),
                        payload.get("paragraphs") if isinstance(payload.get("paragraphs"), list) else None,
                    )
                )
                return
            if path == "/api/writing-submit":
                begin_operation()
                try:
                    result = submit_writing_attempt(
                        payload.get("day"),
                        str(payload.get("text", "") or ""),
                        str(payload.get("level", "natural") or "natural"),
                    )
                finally:
                    end_operation(self.server)
                self.send_json(result, HTTPStatus.CREATED)
                return
            if path == "/api/generate-next":
                extra_instruction = str(payload.get("extraInstruction", "") or "").strip()
                if len(extra_instruction) > MAX_EXTRA_INSTRUCTION_LENGTH:
                    raise ValueError(f"额外要求最多 {MAX_EXTRA_INSTRUCTION_LENGTH} 个字符")
                begin_operation()
                try:
                    with WRITE_LOCK:
                        result = generate_next_article(extra_instruction)
                finally:
                    end_operation(self.server)
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


def launchd_socket_server(host: str, port: int) -> ThreadingHTTPServer:
    """Adopt the listening socket supplied by a macOS launchd Sockets job."""
    library = ctypes.CDLL(None)
    activate = library.launch_activate_socket
    activate.argtypes = [
        ctypes.c_char_p,
        ctypes.POINTER(ctypes.POINTER(ctypes.c_int)),
        ctypes.POINTER(ctypes.c_size_t),
    ]
    activate.restype = ctypes.c_int
    descriptors = ctypes.POINTER(ctypes.c_int)()
    count = ctypes.c_size_t()
    result = activate(b"Listeners", ctypes.byref(descriptors), ctypes.byref(count))
    if result != 0 or count.value != 1:
        raise RuntimeError(
            f"launchd socket activation failed: result={result}, sockets={count.value}"
        )
    descriptor = descriptors[0]
    library.free.argtypes = [ctypes.c_void_p]
    library.free.restype = None
    library.free(descriptors)

    listener = socket.socket(fileno=descriptor)
    listener.setblocking(True)
    server = ThreadingHTTPServer((host, port), AppHandler, bind_and_activate=False)
    server.socket.close()
    server.socket = listener
    server.server_address = listener.getsockname()
    server.server_name = host
    server.server_port = port
    return server


def main() -> None:
    args = parse_args()
    load_project_env()
    try:
        refresh_review_documents()
    except (FileNotFoundError, ValueError, RuntimeError, OSError) as exc:
        print(f"Review history initialization skipped: {exc}", flush=True)
    socket_activated = os.getenv("ENGLISH_LEARNING_SOCKET_ACTIVATED") == "1"
    server = (
        launchd_socket_server(args.host, args.port)
        if socket_activated
        else ThreadingHTTPServer((args.host, args.port), AppHandler)
    )
    server.daemon_threads = True
    if socket_activated:
        schedule_startup_claim_timeout(server)
    print(f"English learning app: http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
