#!/usr/bin/env bash

BASE_DIR="script"

# ===== 从 config.py 读取所有运行配置 =====
eval "$(python3 -c "
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath('$(dirname \"${BASH_SOURCE[0]}\")')))
from config import (DATASET_NAME, DATA_BASE_PATH, BATCH, SEED,
                     USE_ASYNC, CONCURRENCY, SELECTED_MODELS)
print(f'export DATASET_NAME=\"{DATASET_NAME}\"')
print(f'export DATA_BASE_PATH=\"{DATA_BASE_PATH}\"')
print(f'export BATCH=\"{BATCH}\"')
print(f'export SEED={SEED}')
print(f'export USE_ASYNC={1 if USE_ASYNC else 0}')
print(f'export CONCURRENCY={CONCURRENCY}')
# 输出 bash 数组格式
models_str = ' '.join(f'\"{m}\"' for m in SELECTED_MODELS)
print(f'SELECTED_MODELS=({models_str})')
")"

# 用下划线连接模型名作为 session 名，去掉点号
session_suffix=$(IFS=_; echo "${SELECTED_MODELS[*]}")
session_suffix="${session_suffix//./-}"
SESSION="run_${session_suffix}"

echo "[run.sh] DATA_BASE_PATH=$DATA_BASE_PATH"
echo "[run.sh] BATCH=$BATCH"

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

# 创建 session，第一个脚本用初始窗口
first_name=$(get_window_name 0 "${all_scripts[0]}")
tmux new-session -d -s "$SESSION" -n "$first_name"
tmux send-keys -t "$SESSION" "echo '[run] ${all_scripts[0]}'; bash '${all_scripts[0]}'" C-m

# 剩余脚本每个创建一个新窗口
for ((i=1; i<${#all_scripts[@]}; i++)); do
  script="${all_scripts[$i]}"
  win_name=$(get_window_name "$i" "$script")
  tmux new-window -t "$SESSION" -n "$win_name"
  tmux send-keys -t "$SESSION" "echo '[run] $script'; bash '$script'" C-m
done

echo "[run.sh] Started ${#all_scripts[@]} scripts in tmux session '$SESSION'"
echo "[run.sh] Use 'Ctrl+B n' to switch windows, 'Ctrl+B d' to detach"

# 进入 session
tmux attach -t "$SESSION"
