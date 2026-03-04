#!/bin/bash
# 删除 deepseek-v3.2 所有输出目录下的题目 JSON 文件（保留 summary.json / eval.json）
# 用法: bash script/clear_deepseek_outputs.sh [--dry-run]

DEEPSEEK_DIR="output/SMP_MP2_300_Modified_V2/deepseek-v3.2"
DRY_RUN=0

if [[ "$1" == "--dry-run" ]]; then
    DRY_RUN=1
    echo "[dry-run] 仅预览，不实际删除"
fi

if [[ ! -d "$DEEPSEEK_DIR" ]]; then
    echo "目录不存在: $DEEPSEEK_DIR"
    exit 1
fi

count=0
while IFS= read -r -d '' f; do
    fname="$(basename "$f")"
    # 跳过 summary.json 和 eval.json
    if [[ "$fname" == "summary.json" || "$fname" == "eval.json" ]]; then
        continue
    fi
    # 只删除纯数字命名的 json（题目文件）
    stem="${fname%.json}"
    if [[ "$stem" =~ ^[0-9]+$ ]]; then
        if [[ $DRY_RUN -eq 1 ]]; then
            echo "[dry-run] 将删除: $f"
        else
            rm "$f"
        fi
        ((count++))
    fi
done < <(find "$DEEPSEEK_DIR" -name "*.json" -print0)

if [[ $DRY_RUN -eq 1 ]]; then
    echo "[dry-run] 共找到 $count 个题目文件"
else
    echo "已删除 $count 个题目文件"
fi
