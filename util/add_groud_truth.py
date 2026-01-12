import json
import os
from glob import glob

DATA_PATH = r"data\SMP_50\SMP_1762836970_WithTA_Filtered_50.json"
OUTPUT_ROOT = r"output"


def load_problem_map():
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    problem_map = {}
    for item in data:
        pid = item.get("Problem_ID")
        if pid is None:
            continue
        problem_map[pid] = item
    return problem_map


def gt_AandB(problem):
    gt_list = problem.get("Ground_Truth", [])
    return [v for item in gt_list for v in item.values()]


def gt_C(problem):
    gt_list = problem.get("Ground_Truth", [])
    if len(gt_list) < 2:
        return ""
    return list(gt_list[1].values())[0]


def detect_task_from_dir(dir_name: str) -> str:
    """返回 'AandB' / 'C' / 'C_reason' / 'unknown'"""
    name = dir_name.lower()
    if "aandb" in name:
        return "AandB"
    if "c_reason" in name:
        return "C_reason"
    if name.endswith("_c") or name.endswith("c") or "gpt-5_c" in name:
        return "C"
    return "unknown"


def process_one_dir(problem_map, dir_path):
    dir_name = os.path.basename(dir_path)
    task = detect_task_from_dir(dir_name)
    if task == "unknown":
        print(f"Skip dir (unknown task type): {dir_path}")
        return

    pattern = os.path.join(dir_path, "*.json")
    for path in glob(pattern):
        if os.path.basename(path) == "eval.json":
            continue

        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)

        pid = obj.get("Problem_ID")
        print(f"Processing {path} Problem_ID: {pid} (task={task})")

        if pid is None or pid not in problem_map:
            print("  -> skip, Problem_ID not in problem_map")
            continue

        problem = problem_map[pid]
        if task == "AandB":
            gt = gt_AandB(problem)
        else:  # C or C_reason
            gt = gt_C(problem)

        obj["ground_truth"] = gt

        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=4)

        print("  -> written ground_truth:", gt)


def main():
    problem_map = load_problem_map()

    # 扫描 output 下所有子目录
    for entry in os.listdir(OUTPUT_ROOT):
        subdir = os.path.join(OUTPUT_ROOT, entry)
        if not os.path.isdir(subdir):
            continue
        process_one_dir(problem_map, subdir)

    print("All ground truth additions completed.")


if __name__ == "__main__":
    main()