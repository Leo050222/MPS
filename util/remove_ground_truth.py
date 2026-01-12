import json
import os
from glob import glob

OUTPUT_ROOT = r"output"


def remove_Ground_Truth_in_dir(dir_path: str):
    pattern = os.path.join(dir_path, "*.json")
    for path in glob(pattern):
        if os.path.basename(path) == "eval.json":
            continue

        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)

        if "Ground_Truth" in obj:
            obj.pop("Ground_Truth", None)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(obj, f, ensure_ascii=False, indent=4)
            print(f"Removed Ground_Truth from {path}")


def main():
    # 遍历 output 下所有子目录
    for entry in os.listdir(OUTPUT_ROOT):
        subdir = os.path.join(OUTPUT_ROOT, entry)
        if not os.path.isdir(subdir):
            continue
        remove_Ground_Truth_in_dir(subdir)

    print("All 'Ground_Truth' fields removed.")


if __name__ == "__main__":
    main()