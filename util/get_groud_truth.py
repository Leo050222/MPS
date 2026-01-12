path = r'C:\Users\Leo\Desktop\work\Mathematical_Problem_Synthesis\data\SMP_50\SMP_1762836970_WithTA_Filtered_50.json'
base_dir = r'C:\Users\Leo\Desktop\work\Mathematical_Problem_Synthesis\output\gpt-5_AandB_reason'
import os
import json

with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)

for idx, item in enumerate(data, start=1):
    groud_truth = item["Ground_Truth"]
    groud_truth_list = [v for gt_item in groud_truth for v in gt_item.values()]
    
    # 读取现有文件内容（如果存在）
    json_file_path = os.path.join(base_dir, f'{idx}.json')
    existing_data = {}
    if os.path.exists(json_file_path):
        with open(json_file_path, 'r', encoding='utf-8') as f:
            existing_data = json.load(f)
    
    # 添加 Ground_Truth 字段
    existing_data["Ground_Truth"] = groud_truth_list
    
    # 写回文件
    with open(json_file_path, 'w', encoding='utf-8') as f:
        json.dump(existing_data, f, ensure_ascii=False, indent=4)
