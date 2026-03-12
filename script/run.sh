#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_DIR="$REPO_ROOT/script"

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  else
    echo "[run.sh][error] No python found in PATH. Activate conda env (e.g. 'conda activate MPS') then retry." >&2
    exit 1
  fi
fi

# ===== 从 config.py 读取所有运行配置 =====
eval "$("$PYTHON_BIN" -c "
import os, sys

repo_root = os.path.abspath(os.path.join(os.path.dirname(r'${BASH_SOURCE[0]}'), '..'))
sys.path.insert(0, repo_root)

from config import (DATASET_NAME, DATA_BASE_PATH, BATCH, SEED, USE_ASYNC, CONCURRENCY, SELECTED_MODELS, CONDA_SH_PATH, CONDA_ENV_NAME)

print(f'export DATASET_NAME=\"{DATASET_NAME}\"')
print(f'export DATA_BASE_PATH=\"{DATA_BASE_PATH}\"')
print(f'export BATCH=\"{BATCH}\"')
print(f'export SEED={SEED}')
print(f'export USE_ASYNC={1 if USE_ASYNC else 0}')
print(f'export CONCURRENCY={CONCURRENCY}')
print(f'export CONDA_SH_PATH=\"{CONDA_SH_PATH}\"')
print(f'export CONDA_ENV_NAME=\"{CONDA_ENV_NAME}\"')
models_str = ' '.join(f'\"{m}\"' for m in SELECTED_MODELS)
print(f'SELECTED_MODELS=({models_str})')
")"

# 用下划线连接模型名作为 session 名，去掉点号
session_suffix=$(IFS=_; echo "${SELECTED_MODELS[*]}")
session_suffix="${session_suffix//./-}"
SESSION="run_${session_suffix}"

echo "[run.sh] DATA_BASE_PATH=$DATA_BASE_PATH"
echo "[run.sh] BATCH=$BATCH"

NO_TMUX="${NO_TMUX:-0}"
NO_ATTACH="${NO_ATTACH:-0}"
FIX_CRLF="${FIX_CRLF:-0}"

# 如果 session 已存在就直接 attach
if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "[run.sh] Session exists, attaching..."
  tmux attach -t "$SESSION"
  exit 0
fi

# 获取要运行的模型列表
shopt -s nullglob
if ((${#SELECTED_MODELS[@]} > 0)); then
  models=()
  for model_name in "${SELECTED_MODELS[@]}"; do
    model_path="$BASE_DIR/$model_name"
    if [[ -d "$model_path" ]]; then
      models+=("$model_path/")
    else
      echo "[WARN] Model not found: $model_name (skipped)"
    fi
  done
  echo "[run.sh] MODELS=${SELECTED_MODELS[*]}"
else
  models=( "$BASE_DIR"/*/ )
  echo "[run.sh] MODELS=all"
fi

if ((${#models[@]} == 0)); then
  echo "No model directories found!"
  exit 1
fi

# 收集所有脚本
all_scripts=()
for model_path in "${models[@]}"; do
  model_path="${model_path%/}"
  while IFS= read -r script; do
    all_scripts+=("$script")
  done < <(find "$model_path" -type f -name "*.sh" | sort)
done

echo "[run.sh] Total scripts: ${#all_scripts[@]}"

if ((${#all_scripts[@]} == 0)); then
  echo "No scripts found!"
  exit 1
fi

if [[ "$FIX_CRLF" == "1" ]]; then
  # Strip Windows CRLF so bash doesn't see $'\r'
  for s in "${all_scripts[@]}"; do
    sed -i 's/\r$//' "$s" 2>/dev/null || true
  done
fi

if [[ "$NO_TMUX" == "1" ]]; then
  echo "[run.sh] NO_TMUX=1: running scripts sequentially (no tmux)"
  for script in "${all_scripts[@]}"; do
    echo "[run] $script"
    (cd "$REPO_ROOT"; bash "$script")
  done
  exit 0
fi

if ! command -v tmux >/dev/null 2>&1; then
  echo "[run.sh][warn] tmux not found; falling back to NO_TMUX=1 behavior" >&2
  for script in "${all_scripts[@]}"; do
    echo "[run] $script"
    (cd "$REPO_ROOT"; bash "$script")
  done
  exit 0
fi

# 从脚本路径生成窗口名
# 格式: idx-Sep/Syn-model-reason-T*-MP*
get_window_name() {
  local idx="$1"
  local script="$2"
  local filename=$(basename "$script" .sh)
  
  # 提取 Separated/Synthesised
  if [[ "$filename" == *Separated* ]]; then
    task_type="Sep"
  else
    task_type="Syn"
  fi
  
  # 提取 level (T1-T5) 和 class (MP2)
  local level=$(echo "$filename" | grep -oE 'T[0-9]+')
  local class=$(echo "$filename" | grep -oE 'MP[0-9]+')
  
  # 提取模型名和 reasoning 类型
  local dir=$(dirname "$script")
  local parent=$(basename "$dir")
  local grandparent=$(basename "$(dirname "$dir")")
  
  # 判断目录结构: script/model/reasoning/... 或 script/model/...
  if [[ "$parent" == "reasoning" || "$parent" == "non-reasoning" || "$parent" == "thinking" || "$parent" == "non-thinking" ]]; then
    model_short="${grandparent:0:6}"
    case "$parent" in
      reasoning)    reason="rea" ;;
      non-reasoning) reason="non" ;;
      thinking)     reason="thk" ;;
      non-thinking) reason="nth" ;;
    esac
  else
    model_short="${parent:0:6}"
    reason="def"
  fi
  
  # 去掉点号等特殊字符
  model_short="${model_short//./-}"
  
  echo "${idx}-${task_type}-${model_short}-${reason}-${level}-${class}"
}

# 构建 conda 激活命令
CONDA_ACTIVATE_CMD="conda activate MPS && "

# 创建 session，第一个脚本用初始窗口
first_name=$(get_window_name 0 "${all_scripts[0]}")
tmux new-session -d -s "$SESSION" -n "$first_name"
tmux send-keys -t "$SESSION" "cd '$REPO_ROOT'; ${CONDA_ACTIVATE_CMD}echo '[run] ${all_scripts[0]}'; bash '${all_scripts[0]}'" C-m

# 剩余脚本每个创建一个新窗口
for ((i=1; i<${#all_scripts[@]}; i++)); do
  script="${all_scripts[$i]}"
  win_name=$(get_window_name "$i" "$script")
  tmux new-window -t "$SESSION" -n "$win_name"
  tmux send-keys -t "$SESSION" "cd '$REPO_ROOT'; ${CONDA_ACTIVATE_CMD}echo '[run] $script'; bash '$script'" C-m
done

echo "[run.sh] Started ${#all_scripts[@]} scripts in tmux session '$SESSION'"
echo "[run.sh] Use 'Ctrl+B n' to switch windows, 'Ctrl+B d' to detach"

# 进入 session（可选）
if [[ "$NO_ATTACH" == "1" ]]; then
  echo "[run.sh] NO_ATTACH=1: tmux session created; attach manually with: tmux attach -t '$SESSION'"
  exit 0
fi

tmux attach -t "$SESSION"
