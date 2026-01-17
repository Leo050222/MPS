#!/bin/bash
source /mnt/c/Users/Leo/miniconda3/etc/profile.d/conda.sh
conda activate MPS

model="gpt-4o"
reasoning_effort="minimal"
level="T3"
class="MP2"
task="MP2_Synthesised"
base_path="${DATA_BASE_PATH:-data/SMP_100_Verified}"
batch="${BATCH:-default}"
data_path="$base_path/$level/$class"
output_path="output/$batch/$model/$level/$class/Synthesised"
type="${level}_${task}_Evaluation_Summary"
# special_list="[24]"

echo "Start inference"
python expriment/inference.py  \
    $model \
    $reasoning_effort \
    $level \
    $class \
    $task \
    $data_path 
    # $special_list

echo "Inference done"
echo "Start postprocess"
# postprocess
echo "[postprocess] model=$model task=$task type=$type"
echo "[postprocess] output_dir=$output_path"
python expriment/postprocess.py  \
    $model \
    $type \
    $output_path \
    $task

echo "Postprocess done"

