#!/bin/zsh

set -u

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# launchd only calls the ASCII-path copy of this script. The project itself can
# remain in its existing Chinese path.
if [[ -f "$HOME/.config/api-keys.env" ]]; then
  source "$HOME/.config/api-keys.env"
fi

cd "$PROJECT_DIR" || exit 1
export ENGLISH_LEARNING_PROJECT_ROOT="$PROJECT_DIR"
export ENGLISH_LEARNING_SOCKET_ACTIVATED=1
unset ENGLISH_LEARNING_PERSISTENT

# The OpenAI-API fallback path (used when Codex CLI is unavailable) needs the
# `openai` package. System/Homebrew Python is externally managed and can't
# have it installed directly, so prefer a dedicated venv if one has been set
# up at this path; otherwise fall back to bare python3 (Codex-only mode).
VENV_PYTHON="$HOME/Library/Application Support/EnglishLearning/venv/bin/python3"
if [[ -x "$VENV_PYTHON" ]]; then
  exec "$VENV_PYTHON" english-learning-web/server.py
fi

if [[ -x /opt/homebrew/bin/python3 ]]; then
  exec /opt/homebrew/bin/python3 english-learning-web/server.py
fi

exec /usr/bin/python3 english-learning-web/server.py
