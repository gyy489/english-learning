#!/usr/bin/env python3
"""Convert an English-learning article Markdown file to speech audio."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


MAX_INPUT_CHARS = 4096
PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / ".env"
GLOBAL_ENV_FILE = Path.home() / ".config" / "api-keys.env"
ENV_EXAMPLE_FILE = PROJECT_ROOT / ".env.example"
API_KEY_NOTICE_NAME = "OPENAI_API_KEY_REQUIRED.md"
DEFAULT_MODEL = "tts-1"
SUPPORTED_MODELS = (
    "gpt-4o-mini-tts",
    "gpt-4o-mini-tts-2025-12-15",
    "tts-1",
    "tts-1-hd",
)
# cedar 属于较新的 TTS 模型声音；默认模型 tts-1 使用 nova 等兼容声音。
DEFAULT_VOICE = "nova"
DEFAULT_FORMAT = "mp3"
DEFAULT_SPEED = 0.92
DEFAULT_INSTRUCTIONS = "\n".join(
    [
        "Voice Affect: Natural, calm, and human-like.",
        "Tone: Clear standard English for listening practice.",
        "Pacing: Steady and slightly slow.",
        "Pronunciation: Enunciate each word clearly, especially ending sounds.",
        "Pauses: Use short natural pauses between sentences.",
    ]
)


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key in {"OPENAI_API_KEY", "OPENAI_TTS_MODEL"} and value and key not in os.environ:
            os.environ[key] = value


def load_project_env() -> None:
    load_env_file(GLOBAL_ENV_FILE)
    load_env_file(ENV_FILE)


def write_env_example() -> None:
    if ENV_EXAMPLE_FILE.exists():
        return
    ENV_EXAMPLE_FILE.write_text(
        "# Copy this file to .env and fill in your OpenAI API key.\n"
        "# Do not paste the key into chat.\n"
        "OPENAI_API_KEY=sk-your-key-here\n",
        encoding="utf-8",
    )


def write_api_key_notice(target_dir: Path, article: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    notice_path = target_dir / API_KEY_NOTICE_NAME
    notice_path.write_text(
        "# 需要填写 OpenAI API Key\n\n"
        "听力音频使用 OpenAI API 生成。当前环境没有检测到 `OPENAI_API_KEY`，所以没有生成 mp3。\n\n"
        "## 推荐做法\n\n"
        "1. 在项目根目录复制 `.env.example` 为 `.env`。\n"
        "2. 打开 `.env`，把下面这一行改成你自己的 key：\n\n"
        "```text\n"
        "OPENAI_API_KEY=sk-your-key-here\n"
        "```\n\n"
        "3. 重新运行音频生成命令：\n\n"
        "```bash\n"
        f"uv run --with openai python scripts/article_to_speech.py \"{article.as_posix()}\" --force\n"
        "```\n\n"
        "不要把 API key 发到聊天中；只在你自己的本地 `.env` 文件里填写。\n",
        encoding="utf-8",
    )
    return notice_path


def ensure_openai_api_key(target_dir: Path, article: Path) -> None:
    load_project_env()
    if os.getenv("OPENAI_API_KEY"):
        return
    write_env_example()
    notice_path = write_api_key_notice(target_dir, article)
    raise SystemExit(f"OPENAI_API_KEY is missing. Wrote instructions to {notice_path}")


def contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", text))


def clean_english_line(line: str) -> str:
    text = line.strip()
    text = re.sub(r"^\d+\.\s+", "", text)
    text = re.sub(r"\s{2,}$", "", text)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    return text.strip()


def extract_article_text(path: Path) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    in_body = False
    body_lines: list[str] = []

    for raw in lines:
        stripped = raw.strip()

        if stripped == "## 正文":
            in_body = True
            continue
        if not in_body:
            continue
        if stripped == "生单词:":
            break
        if stripped.startswith("## ") or stripped.startswith("# "):
            break
        if not stripped or stripped == ">":
            continue
        if stripped.startswith(">"):
            continue
        if contains_cjk(stripped):
            continue

        text = clean_english_line(stripped)
        if text and re.search(r"[A-Za-z]", text):
            body_lines.append(text)

    if not body_lines:
        raise SystemExit(f"No English body text found in {path}")

    return "\n\n".join(body_lines)


def default_output_path(article: Path, out_dir: Path | None, fmt: str) -> Path:
    if out_dir is None:
        return article.with_suffix(f".{fmt}")
    return out_dir / f"{article.stem}.{fmt}"


def speech_cli_path() -> Path:
    if os.getenv("TTS_GEN"):
        return Path(os.environ["TTS_GEN"]).expanduser()
    codex_home = Path(os.getenv("CODEX_HOME", "~/.codex")).expanduser()
    return codex_home / "skills" / "speech" / "scripts" / "text_to_speech.py"


def find_uv() -> str | None:
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


def python_runner(cli_path: Path) -> list[str]:
    if not cli_path.exists():
        raise SystemExit(
            "Speech skill CLI not found. Install it with:\n"
            "python3 /Volumes/工程盘-1T/skills/.system/skill-installer/scripts/"
            "install-skill-from-github.py --repo openai/skills --path skills/.curated/speech"
        )

    try:
        __import__("openai")
        return [sys.executable, str(cli_path)]
    except ImportError:
        uv = find_uv()
        if uv:
            return [uv, "run", "--with", "openai", "python", str(cli_path)]
        return [sys.executable, str(cli_path)]


def build_command(args: argparse.Namespace, text_file: Path, out_path: Path) -> list[str]:
    cmd = python_runner(speech_cli_path())
    cmd.extend(
        [
            "speak",
            "--input-file",
            str(text_file),
            "--model",
            args.model,
            "--voice",
            args.voice,
            "--response-format",
            args.response_format,
            "--speed",
            str(args.speed),
        ]
    )
    if args.model not in {"tts-1", "tts-1-hd"}:
        cmd.extend(["--instructions", args.instructions])
    cmd.extend(["--out", str(out_path)])
    if args.force:
        cmd.append("--force")
    if args.dry_run:
        cmd.append("--dry-run")
    return cmd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate listening-practice audio from an article Markdown file."
    )
    parser.add_argument("article", help="Markdown article path")
    parser.add_argument(
        "--out",
        help="Output audio path. Defaults to <article_dir>/<article_stem>.mp3",
    )
    parser.add_argument("--out-dir", help="Output directory")
    parser.add_argument(
        "--model",
        default=os.getenv("OPENAI_TTS_MODEL", DEFAULT_MODEL),
        choices=SUPPORTED_MODELS,
        help="OpenAI TTS model",
    )
    parser.add_argument("--voice", default=DEFAULT_VOICE, help="Voice name")
    parser.add_argument(
        "--response-format",
        default=DEFAULT_FORMAT,
        choices=["mp3", "opus", "aac", "flac", "wav", "pcm"],
        help="Audio format",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=DEFAULT_SPEED,
        help="Speech speed, 0.25 to 4.0",
    )
    parser.add_argument(
        "--instructions",
        default=DEFAULT_INSTRUCTIONS,
        help="Voice delivery instructions",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite output")
    parser.add_argument("--dry-run", action="store_true", help="Print API payload only")
    parser.add_argument(
        "--print-text",
        action="store_true",
        help="Print extracted English text before generating audio",
    )
    return parser.parse_args()


def main() -> int:
    load_project_env()
    args = parse_args()
    article = Path(args.article)
    if not article.exists():
        raise SystemExit(f"Article not found: {article}")

    text = extract_article_text(article)
    if len(text) > MAX_INPUT_CHARS:
        raise SystemExit(
            f"Extracted text is {len(text)} characters; split it below "
            f"{MAX_INPUT_CHARS} characters before generating speech."
        )
    if args.print_text:
        print(text)
        print()

    out_path = (
        Path(args.out)
        if args.out
        else default_output_path(article, Path(args.out_dir) if args.out_dir else None, args.response_format)
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not args.dry_run:
        ensure_openai_api_key(out_path.parent, article)

    with tempfile.TemporaryDirectory(prefix="article-tts-") as tmp:
        text_file = Path(tmp) / f"{article.stem}.txt"
        text_file.write_text(text, encoding="utf-8")
        cmd = build_command(args, text_file, out_path)
        return subprocess.run(cmd, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
