#!/bin/bash
source /c/Users/Leo/miniconda3/etc/profile.d/conda.sh
conda activate MPS

model="gpt-5.1"
reasoning_effort="minimal"
level="T1"
class="MP2"
task="MP2_Seperated"
base_path="data\smp_100_verified_non-instead\gpt-5_1\non-reasoning"
data_path="$base_path/$level/$class"
# NOTE: `expriment/inference.py` currently writes to output/<model>/<level>/<class>/<Seperated|Synthesised>
output_path="output/test/$model/non-instead/$level/$class/Seperated"
type="${level}_${task}_Evaluation_Summary"
# special_list="[24]"

echo "Start inference"
python expriment/inference.py  \
    $model \
    $reasoning_effort \
    $level \
    $class \
    $task \
    $data_path \
    $output_path
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

