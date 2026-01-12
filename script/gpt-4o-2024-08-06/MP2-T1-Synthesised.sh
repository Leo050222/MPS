#!/bin/bash
source /c/Users/Leo/miniconda3/etc/profile.d/conda.sh
conda activate MPS

model="gpt-4o-2024-08-06"
reasoning_effort="minimal"
level="T1"
class="MP2"
task="MP2_Synthesised"
base_path="data/SMP_100_Verified"
data_path="$base_path/$level/$class"
output_path="output/$model/$level/$class/Synthesised"
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

