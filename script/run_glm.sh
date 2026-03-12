#!/usr/bin/env bash
# GLM-4.5 专用运行脚本
# 官方限制并发数为 3，因此：
#   - 每个脚本内部不使用 async（USE_ASYNC=0）
#   - 同时最多运行 MAX_PARALLEL=3 个脚本

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GLM_DIR="$REPO_ROOT/script/glm-4.5"

# ===== Python 解释器 =====
PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  else
    echo "[run_glm][error] No python found in PATH." >&2
    exit 1
  fi
fi

# ===== 从 config.py 读取配置（但覆盖并发参数） =====
eval "$("$PYTHON_BIN" -c "
import os, sys
repo_root = os.path.abspath(os.path.join(os.path.dirname(r'${BASH_SOURCE[0]}'), '..'))
sys.path.insert(0, repo_root)
from config import DATASET_NAME, DATA_BASE_PATH, BATCH, SEED, CONDA_SH_PATH, CONDA_ENV_NAME
print(f'export DATASET_NAME=\"{DATASET_NAME}\"')
print(f'export DATA_BASE_PATH=\"{DATA_BASE_PATH}\"')
print(f'export BATCH=\"{BATCH}\"')
print(f'export SEED={SEED}')
print(f'export CONDA_SH_PATH=\"{CONDA_SH_PATH}\"')
print(f'export CONDA_ENV_NAME=\"{CONDA_ENV_NAME}\"')
")"

# 强制覆盖：每个脚本内部不用 async，并发为 1
export USE_ASYNC=0
export CONCURRENCY=3

MAX_PARALLEL=1

echo "[run_glm] DATA_BASE_PATH=$DATA_BASE_PATH"
echo "[run_glm] BATCH=$BATCH"
echo "[run_glm] USE_ASYNC=$USE_ASYNC, CONCURRENCY=$CONCURRENCY, MAX_PARALLEL=$MAX_PARALLEL"

# ===== 收集所有脚本 =====
shopt -s nullglob
all_scripts=()
while IFS= read -r script; do
  all_scripts+=("$script")
done < <(find "$GLM_DIR" -type f -name "*.sh" | sort)

echo "[run_glm] Total scripts: ${#all_scripts[@]}"

if ((${#all_scripts[@]} == 0)); then
  echo "[run_glm] No scripts found in $GLM_DIR"
  exit 1
fi

# ===== 并行执行，最多同时 MAX_PARALLEL 个 =====
running=0
for script in "${all_scripts[@]}"; do
  echo "[run_glm] Starting: $(basename "$(dirname "$script")")/$(basename "$script")"
  (cd "$REPO_ROOT"; bash "$script") &
  running=$((running + 1))
  if ((running >= MAX_PARALLEL)); then
  
    wait -n
    running=$((running - 1))
  fi
done

wait
echo "[run_glm] All ${#all_scripts[@]} scripts completed."
