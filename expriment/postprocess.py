import sys
import os
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

# Ensure repo-root imports (e.g., `config.py`) work no matter the current working directory.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import TASKS
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def is_synthesised_task(task: str) -> bool:
    return isinstance(task, str) and task.endswith("_Synthesised")


def to_seperated_task(task: str) -> str:
    if not is_synthesised_task(task):
        return task
    return task.replace("_Synthesised", "_Seperated")


def derive_seperated_output_dir_from_synthesised(output_dir: str) -> str:
    p = Path(output_dir)
    parts = list(p.parts)
    replaced = False
    for i, part in enumerate(parts):
        if part.lower() == "synthesised":
            parts[i] = "Seperated"
            replaced = True
            break
    if not replaced:
        return str(p.parent / "Seperated")
    return str(Path(*parts))


def load_outputs_by_filename(output_dir: str) -> dict[str, dict]:
    output_path = Path(output_dir)
    if not output_path.exists() or not output_path.is_dir():
        logger.error(f"Output directory does not exist: {output_dir}")
        return {}

    results: dict[str, dict] = {}
    for json_file in output_path.glob("*.json"):
        if json_file.name == "eval.json" or json_file.name == "summary.json":
            continue
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                results[json_file.name] = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load {json_file}: {e}")
            continue
    return results


def extract_category_from_problem_type(problem_type) -> str:
    """
    从 problem_type 中提取类别名称
    
    Args:
        problem_type: 问题类型，格式如 [{"A2743": ["Mathematics -> Applied Mathematics -> Math Word Problems"]}]
    
    Returns:
        类别名称，例如 "Applied-Mathematics"，如果无法提取则返回 "Unknown"
    """
    if not problem_type or not isinstance(problem_type, list):
        return "Unknown"
    
    # 遍历所有子问题的类别
    for item in problem_type:
        if isinstance(item, dict):
            for sub_id, paths in item.items():
                if isinstance(paths, list) and len(paths) > 0:
                    # 取第一个路径，例如 "Mathematics -> Applied Mathematics -> Math Word Problems"
                    path = paths[0]
                    if isinstance(path, str) and "->" in path:
                        # 分割路径，取第二个部分（第一个是 "Mathematics"）
                        parts = [p.strip() for p in path.split("->")]
                        if len(parts) >= 2:
                            # 返回第二个部分，例如 "Applied Mathematics"
                            category = parts[1].replace(" ", "-")
                            return category
    
    return "Unknown"


def load_all_outputs(output_dir: str) -> list[dict]:
    """
    加载输出目录下所有的 JSON 文件
    
    Args:
        output_dir: 输出目录路径
    
    Returns:
        所有问题的评估结果列表
    """
    output_path = Path(output_dir)
    if not output_path.exists() or not output_path.is_dir():
        logger.error(f"Output directory does not exist: {output_dir}")
        return []
    
    results = []
    for json_file in output_path.glob("*.json"):
        if json_file.name == "eval.json" or json_file.name == "summary.json":
            continue
        
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                results.append(data)
        except Exception as e:
            logger.warning(f"Failed to load {json_file}: {e}")
            continue
    
    return results


def calculate_correctness(correctness_list: list[bool]) -> bool:
    """
    根据 correctness 列表判断问题是否正确
    
    Args:
        correctness_list: 布尔值列表，表示每个答案是否正确
    
    Returns:
        如果所有答案都正确返回 True，否则返回 False
    """
    if not correctness_list:
        return False
    return all(correctness_list)


def main(model: str, type: str, output_dir: str, task: str):
    """
    后处理函数，统计评估结果并生成汇总 JSON
    
    Args:
        model: 模型名称
        type: 评估类型，例如 "T5_MP2_Separated/Synthesised_Evaluation_Summary"
        output_dir: 输出目录路径
        task: 任务类型，例如 "MP2_Seperated" / "MP2_Synthesised"
    """
    logger.info(f"Processing outputs from: {output_dir}")

    if task not in TASKS:
        logger.warning(f"Unknown task '{task}'. Expected one of: {TASKS}")
    
    # 加载所有输出文件
    results = load_all_outputs(output_dir)
    
    if not results:
        logger.error("No output files found!")
        return
    
    logger.info(f"Loaded {len(results)} evaluation results")
    
    # 统计变量
    total_count = 0
    correct_count = 0
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_reasoning_tokens = 0
    total_cost = 0.0
    
    # 按类别统计
    category_stats = defaultdict(lambda: {"correct": 0, "total": 0})

    # 处理每个结果
    for result in results:
        filename = result.get("Problem_ID")
        # 提取 correctness（可能是列表或单个布尔值）
        correctness = result.get("correctness", [])
        if not isinstance(correctness, list):
            correctness = [correctness] if correctness else [False]
        
        # 判断是否正确（当前结果本身）
        is_correct = calculate_correctness(correctness)
        
        # 统计 token 使用量
        total_prompt_tokens += result.get("prompt_tokens", 0)
        total_completion_tokens += result.get("completion_tokens", 0)
        total_reasoning_tokens += result.get("reasoning_tokens", 0)
        total_cost += result.get("cost", 0.0)

        total_count += 1
        if is_correct:
            correct_count += 1
        
        # 按类别统计
        problem_type = result.get("problem_type", [])
        category = extract_category_from_problem_type(problem_type)
        category_stats[category]["total"] += 1
        if is_correct:
            category_stats[category]["correct"] += 1
    
    # 计算总体准确率
    overall_accuracy = (correct_count / total_count * 100) if total_count > 0 else 0.0
    
    # 构建类别准确率列表
    category_accuracies = []
    for category, stats in sorted(category_stats.items()):
        category_accuracy = (stats["correct"] / stats["total"] * 100) if stats["total"] > 0 else 0.0
        category_accuracies.append({
            "category": category,
            "value": round(category_accuracy, 2),
            "correct_count": stats["correct"],
            "total_count": stats["total"]
        })
    
    # 构建汇总 JSON
    summary = {
        "evaluation_metadata": {
            "timestamp": int(datetime.now(timezone.utc).timestamp()),
            "model_name": model,
            "type": type
        },
        "evaluation_summary": {
            "overall_accuracy": {
                "value": round(overall_accuracy, 2),
                "correct_count": correct_count,
                "total_count": total_count
            },
            "category_accuracies": category_accuracies,
            "total_token_usage": {
                "total_prompt_tokens": total_prompt_tokens,
                "total_completion_tokens": total_completion_tokens,
                "total_reasoning_tokens": total_reasoning_tokens,
                "total_cost": round(total_cost, 4)
            }
        }
    }
    
    # 保存汇总 JSON
    summary_path = Path(output_dir) / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    logger.info(f"✅️ Summary saved to: {summary_path}")
    
    logger.info(f"Summary saved to: {summary_path}")
    logger.info(f"Overall accuracy: {overall_accuracy:.2f}% ({correct_count}/{total_count})")
    logger.info(f"Total cost: {total_cost:.4f}")
    logger.info(f"Categories: {len(category_accuracies)}")


if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Usage: python postprocess.py <model> <type> <output_dir> <task>")
        sys.exit(1)
    
    model = sys.argv[1]
    type = sys.argv[2]
    output_dir = sys.argv[3]
    task = sys.argv[4]
    
    main(model=model, type=type, output_dir=output_dir, task=task)
