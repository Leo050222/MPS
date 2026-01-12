#!/bin/bash
source ~/miniconda3/bin/activate
conda activate MPS

model="qwen-plus"
enable_thinking=True
level="T3"
class="MP2"
task="MP2_Synthesised"
base_path="data/SMP_100_Verified"
data_path="$base_path/$level/$class"
output_path="output/$model/thinking/$level/$class/Synthesised"
type="${level}_${task}_Evaluation_Summary"
# special_list="[24]"

echo "Start inference"
python expriment/inference.py  \
    $model \
    $enable_thinking \
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

