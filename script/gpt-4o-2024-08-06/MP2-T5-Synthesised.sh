#!/bin/bash
# 加载公共配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../common.sh" 2>/dev/null || source "$SCRIPT_DIR/../../common.sh" 2>/dev/null || source "script/common.sh"

# 脚本特定参数
model="gpt-4o-2024-08-06"
reasoning_effort="minimal"
level="T5"
class="MP2"
task="MP2_Synthesised"

# 构建路径并运行
build_paths "$model" "$reasoning_effort" "$level" "$class" "$task" "Synthesised"
run_inference "$model" "$reasoning_effort" "$level" "$class" "$task"
run_postprocess "$model" "$task"
