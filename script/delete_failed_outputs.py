#!/usr/bin/env python3
"""
删除 summary.json 中记录的失败问题的输出文件
"""
import json
import os
from pathlib import Path

def delete_failed_outputs(base_dir: str):
    """删除指定目录下所有失败问题的输出文件"""
    base_path = Path(base_dir)

    if not base_path.exists():
        print(f"[ERROR] Directory not found: {base_dir}")
        return

    # 查找所有 summary.json 文件
    summary_files = list(base_path.rglob("summary.json"))
    print(f"Found {len(summary_files)} summary.json files\n")

    total_deleted = 0

    for summary_file in summary_files:
        try:
            with open(summary_file, 'r', encoding='utf-8') as f:
                summary = json.load(f)

            # 提取失败的问题 ID
            failed_ids = summary.get("evaluation_summary", {}).get("failed_inference", {}).get("problem_ids", [])

            if not failed_ids:
                print(f"[OK] {summary_file.parent.relative_to(base_path)}: No failed problems")
                continue

            print(f"[DIR] {summary_file.parent.relative_to(base_path)}")
            print(f"   Failed IDs: {failed_ids}")

            # 删除对应的输出文件
            deleted_count = 0
            for problem_id in failed_ids:
                output_file = summary_file.parent / f"{problem_id}.json"
                if output_file.exists():
                    output_file.unlink()
                    deleted_count += 1
                    print(f"   [DEL] Deleted: {problem_id}.json")

            total_deleted += deleted_count
            print(f"   Deleted {deleted_count} files\n")

        except Exception as e:
            print(f"[ERROR] Error processing {summary_file}: {e}\n")
            continue

    print(f"\n{'='*60}")
    print(f"Total deleted: {total_deleted} files")
    print(f"{'='*60}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python delete_failed_outputs.py <base_dir>")
        sys.exit(1)

    base_dir = sys.argv[1]
    delete_failed_outputs(base_dir)
