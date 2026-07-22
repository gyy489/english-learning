#!/bin/zsh

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_URL="http://127.0.0.1:8787"

# Finder 启动脚本不会继承终端环境；只读取本机 shell 配置里的 OpenAI 变量，
# 不执行整份 .zshrc，避免 Conda 等交互式初始化阻塞启动。
if [[ -f "$HOME/.zshrc" ]]; then
  while IFS= read -r env_line; do
    case "$env_line" in
      "export OPENAI_API_KEY="*|"export OPENAI_BASE_URL="*|"export OPENAI_TEXT_MODEL="*|"export OPENAI_TTS_MODEL="*)
        env_name="${env_line#export }"
        env_name="${env_name%%=*}"
        env_value="${env_line#*=}"
        env_value="${env_value#\"}"
        env_value="${env_value%\"}"
        env_value="${env_value#\'}"
        env_value="${env_value%\'}"
        export "$env_name=$env_value"
        ;;
    esac
  done < "$HOME/.zshrc"
fi

# 如果服务已经在运行，就直接打开网页，避免重复启动多个服务。
if curl -fsS "$APP_URL/api/days" >/dev/null 2>&1; then
  open "$APP_URL"
  exit 0
fi

cd "$PROJECT_DIR" || exit 1
export ENGLISH_LEARNING_PROJECT_ROOT="$PROJECT_DIR"

# 在后台等待服务就绪并打开浏览器；当前终端保持运行服务。
(
  for _ in {1..30}; do
    if curl -fsS "$APP_URL/api/days" >/dev/null 2>&1; then
      open "$APP_URL"
      exit 0
    fi
    sleep 0.2
  done
  echo "英语学习项目启动失败，请检查 Python 环境。"
) &

if [[ -x /opt/homebrew/bin/uv ]]; then
  uv run --with openai python english-learning-web/server.py
else
  python3 english-learning-web/server.py
fi
