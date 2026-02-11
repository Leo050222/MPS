#!/bin/bash
# 公共配置和函数 - 被所有脚本 source

# 从 config.py 读取所有运行配置（一次 python 调用，避免多次启动解释器）
eval "$(python3 -c "
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath('${BASH_SOURCE[0]}')), '..'))
from config import (CONDA_SH_PATH, CONDA_ENV_NAME, DATA_BASE_PATH,
                     BATCH, SEED, USE_ASYNC, CONCURRENCY)
print(f'_CONDA_SH_PATH=\"{CONDA_SH_PATH}\"')
print(f'_CONDA_ENV=\"{CONDA_ENV_NAME}\"')
print(f'base_path=\"{DATA_BASE_PATH}\"')
print(f'batch=\"{BATCH}\"')
print(f'seed={SEED}')
print(f'use_async={1 if USE_ASYNC else 0}')
print(f'concurrency={CONCURRENCY}')
")"

# Conda 环境（可被 run.sh 的环境变量覆盖）
_CONDA_SH_PATH="${CONDA_SH_PATH_OVERRIDE:-$_CONDA_SH_PATH}"
_CONDA_ENV="${CONDA_ENV_OVERRIDE:-$_CONDA_ENV}"
source "$_CONDA_SH_PATH"
conda activate "$_CONDA_ENV"

# 允许 run.sh 通过环境变量覆盖 config.py 的值
base_path="${DATA_BASE_PATH:-$base_path}"
batch="${BATCH:-$batch}"
seed="${SEED:-$seed}"
use_async="${USE_ASYNC:-$use_async}"
concurrency="${CONCURRENCY:-$concurrency}"

# 构建路径的函数
# 用法: build_paths <model> <reasoning_param> <level> <class> <task> <task_type>
# task_type: "Separated" 或 "Synthesised"
build_paths() {
    local model="$1"
    local reasoning_param="$2"
    local level="$3"
    local class="$4"
    local task="$5"
    local task_type="$6"
    
    # 模型目录名（保持原始名称，斜杠替换为下划线）
    model_dir="${model//\//_}"
    
    # 判断 reasoning 子目录
    # 支持 reasoning_effort (minimal/medium/high) 和 enable_thinking (True/False)
    if [[ "$reasoning_param" == "minimal" || "$reasoning_param" == "False" || "$reasoning_param" == "false" ]]; then
        reasoning_subdir="non-reasoning"
    elif [[ "$reasoning_param" == "True" || "$reasoning_param" == "true" ]]; then
        reasoning_subdir="thinking"
    elif [[ "$reasoning_param" == "False" || "$reasoning_param" == "false" ]]; then
        reasoning_subdir="non-thinking"
    else
        reasoning_subdir="reasoning"
    fi
    
    # 特殊处理 qwen-plus 的目录名（数据目录使用 reasoning/non-reasoning）
    if [[ "$model" == "qwen-plus" ]]; then
        model_dir="qwen-plus"
        if [[ "$reasoning_param" == "True" || "$reasoning_param" == "true" ]]; then
            reasoning_subdir="reasoning"
        else
            reasoning_subdir="non-reasoning"
        fi
    fi
    
    # 构建路径
    data_path="$base_path/$model_dir/$reasoning_subdir/$level/$class"
    output_path="output/$batch/$model/$reasoning_subdir/$level/$class/$task_type"
    type="${level}_${task}_Evaluation_Summary"
}

# 运行推理
run_inference() {
    local model="$1"
    local reasoning_param="$2"
    local level="$3"
    local class="$4"
    local task="$5"
    
    # 构建基础命令
    local cmd="python expriment/inference.py \
        \"$model\" \
        \"$reasoning_param\" \
        \"$level\" \
        \"$class\" \
        \"$task\" \
        \"$data_path\" \
        \"$output_path\" \
        --seed $seed"
    
    # 如果启用并发模式，追加 --use_async 和 --concurrency
    if [[ "$use_async" == "1" ]]; then
        cmd="$cmd --use_async --concurrency $concurrency"
        echo "Start inference (async, concurrency=$concurrency)"
    else
        echo "Start inference (sync)"
    fi
    
    eval $cmd
    echo "Inference done"
}

# 运行后处理
run_postprocess() {
    local model="$1"
    local task="$2"
    
    echo "Start postprocess"
    echo "[postprocess] model=$model task=$task type=$type"
    echo "[postprocess] output_dir=$output_path"
    python expriment/postprocess.py \
        "$model" \
        "$type" \
        "$output_path" \
        "$task"
    echo "Postprocess done"
}
