#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="script"           # <- 你的目录（例如 "script" 或 "s"）
SESSION="run_models"

# 数据集基础路径
export DATA_BASE_PATH="data/A_equivalence_strategy_100_full"

# 输出批次名称（用于区分不同实验）
export BATCH="default"

SELECTED_MODELS=(
  # "gpt-4o"
  # "gpt-4o-2024-08-06"
  "gpt-5.1"
  "gpt-5.1-medium"
  # "meta-llama"
  "qwen-plus"
)


echo "[run.sh] DATA_BASE_PATH=$DATA_BASE_PATH"
echo "[run.sh] BATCH=$BATCH"

# 如果 session 已存在就直接 attach（避免重复开）
if tmux has-session -t "$SESSION" 2>/dev/null; then
  tmux attach -t "$SESSION"
  exit 0
fi

# 建 session（后台），先有一个占位 window
tmux new-session -d -s "$SESSION" -n "main"

# 获取要运行的模型列表
shopt -s nullglob
if ((${#SELECTED_MODELS[@]} > 0)); then
  # 使用配置的模型列表
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
  # 未指定，运行所有模型
  models=( "$BASE_DIR"/*/ )
  echo "[run.sh] MODELS=all"
fi

if ((${#models[@]} == 0)); then
  echo "No model directories found!"
  tmux kill-session -t "$SESSION" 2>/dev/null || true
  exit 1
fi

# 在某个 pane 里运行目录下所有 sh（递归）
# target 可以是：
# - "session:window.pane" 例如 "run_models:gpt-5.1.0"
# - 或者更稳的 "#{pane_id}" 例如 "%12"
send_run_recursive() {
  local target="$1"
  local dir="$2"

  # 在 pane 内执行：find -> sort -> 逐个 bash
  # 用 while read -r 处理空格路径
  tmux send-keys -t "$target" \
"echo \"[run] dir: $dir\"; \
files=\$(find \"$dir\" -type f -name \"*.sh\" | sort); \
if [ -z \"\$files\" ]; then \
  echo \"(skip) no .sh\"; \
else \
  echo \"\$files\" | while IFS= read -r f; do \
    echo \"-> bash \$f\"; \
    bash \"\$f\"; \
  done; \
fi" C-m
}

# 给每个 model 开一个 window
for model_path in "${models[@]}"; do
  model_path="${model_path%/}"
  model_name="$(basename "$model_path")"

  # 新建 window（名字=模型名）
  # 注意：window 建好后默认只有一个 pane：.0
  tmux new-window -t "$SESSION" -n "$model_name"

  # 该 window 的初始 pane id（最稳的定位方式）
  base_pane_id="$(tmux display-message -p -t "$SESSION:$model_name.0" "#{pane_id}")"

  # 找子目录（只看一层）
  mapfile -t subdirs < <(find "$model_path" -mindepth 1 -maxdepth 1 -type d -print | sort)

  if ((${#subdirs[@]} == 0)); then
    # 没子目录：直接在该 window 的 0 号 pane 跑 model_path
    send_run_recursive "$base_pane_id" "$model_path"
  else
    # 有子目录：第一个子目录用 base pane，其余子目录 split 出新 pane
    first=1
    for sub in "${subdirs[@]}"; do
      sub_name="$(basename "$sub")"

      if [ "$first" -eq 1 ]; then
        # 第一个子目录用 base pane
        tmux select-pane -t "$base_pane_id" -T "$sub_name" 2>/dev/null || true
        send_run_recursive "$base_pane_id" "$sub"
        first=0
      else
        # split 后拿到新 pane_id（关键修复点）
        new_pane_id="$(tmux split-window -t "$SESSION:$model_name" -h -P -F "#{pane_id}")"
        tmux select-layout -t "$SESSION:$model_name" tiled

        tmux select-pane -t "$new_pane_id" -T "$sub_name" 2>/dev/null || true
        send_run_recursive "$new_pane_id" "$sub"
      fi
    done
  fi
done

# 删掉最开始的 main window（可选）
tmux kill-window -t "$SESSION:main" 2>/dev/null || true

# 进入 session
tmux attach -t "$SESSION"
