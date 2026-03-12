#!/usr/bin/env python3
"""
Fix bad qwen2.5-7b output files.

Bad files contain raw API responses (choices/usage) but lack Problem_ID,
output_answer, correctness, etc.  The model already produced reasoning content
but never appended the required JSON block, so regex extraction failed.

Strategy: take the existing reasoning content, make a NEW lightweight API call
asking a model to extract and format the answer from that content, then
judge correctness and rewrite the file in standard format.
"""
import sys
import os
import json
import logging
import re
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from client.client import get_client
from expriment.inference import (
    judge, get_ground_truth, get_parts_in_order,
    make_per_problem_evaluation_json, parse_task_mode,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MODEL = "qwen2.5-7b"
DATASET = "SMP_MP2_300_Modified_V2"
OUTPUT_BASE = f"output/{DATASET}/{MODEL}"
DATA_BASE = f"data/{DATASET}"

# Model used for re-extraction (cheap, fast, reliable JSON output)
EXTRACTOR_MODEL = "gpt-4o"


def is_bad_file(data: dict) -> bool:
    return "choices" in data and "Problem_ID" not in data


def infer_task_and_level(file_path: Path):
    """From output path, infer level (T1-T5), task_type (Seperated/Synthesised), task string."""
    parts = file_path.parts
    level = None
    task_type = None
    for p in parts:
        if re.match(r'^T\d+$', p):
            level = p
        if p in ("Seperated", "Synthesised"):
            task_type = p

    if not level or not task_type:
        raise ValueError(f"Cannot infer level/task_type from path: {file_path}")

    task = f"MP2_{task_type}"
    return level, task_type, task


def build_reextract_prompt(content: str, task: str, que: dict) -> list[dict]:
    """
    Build a prompt that asks gpt-4o to extract the final answer from the
    model's existing reasoning content and format it as required JSON.
    """
    _, mode = parse_task_mode(task)

    if mode == "seperated":
        parts = get_parts_in_order(que)
        problems_text = ""
        for i, part in enumerate(parts, start=1):
            problems_text += f"Problem {i}: {part}\n"

        # Determine how many answers are expected
        n_answers = len(parts)
        answer_fields = "\n".join(f'    "answer_{i}": "your answer to Problem {i}"' for i in range(1, n_answers + 1))

        format_example = '{\n' + answer_fields + '\n}'

        system_msg = "You are a mathematical answer extractor. Given a solution to math problems, extract only the final answers and output them in the specified JSON format."
        user_msg = f"""The following is a solution attempt to these problems:

{problems_text}

--- Solution content ---
{content}
--- End of solution ---

Extract the final answers and output ONLY this JSON (no other text):

{format_example}

Rules:
- Put ONLY the answer value in each field (no explanations, no units unless part of the answer, no LaTeX)
- For numerical answers, provide the exact value
- The JSON must be the only thing in your response
"""
    else:
        problem_text = que.get("Math_Problem", "")

        system_msg = "You are a mathematical answer extractor. Given a solution to a math problem, extract only the final answer and output it in the specified JSON format."
        user_msg = f"""The following is a solution attempt to this problem:

Problem: {problem_text}

--- Solution content ---
{content}
--- End of solution ---

Extract the final answer and output ONLY this JSON (no other text):

{{
    "answer": "your final answer"
}}

Rules:
- Put ONLY the answer value in the quotes (no explanations, no units unless part of the answer, no LaTeX)
- For numerical answers, provide the exact value
- The JSON must be the only thing in your response
"""

    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]


def extract_from_reextract_response(response: dict, task: str) -> list[str]:
    """Extract answer list from the re-extraction API response."""
    if not response:
        return []

    content = ""
    if isinstance(response, dict) and "choices" in response:
        content = response["choices"][0].get("message", {}).get("content", "")

    if not content:
        return []

    _, mode = parse_task_mode(task)

    if mode == "seperated":
        pattern = r'"answer_(\d+)"\s*:\s*"([^"]*)"'
        matches = re.findall(pattern, content)
        if matches:
            answer_dict = {int(idx): ans for idx, ans in matches}
            max_idx = max(answer_dict.keys())
            return [answer_dict.get(i, "") for i in range(1, max_idx + 1)]
        return []
    else:
        m = re.search(r'"answer"\s*:\s*"([^"]*)"', content)
        return [m.group(1)] if m else []


def fix_single_file(file_path: Path, client, seed: int = 42) -> str:
    """Fix a single bad file. Returns status string."""
    with open(file_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    if not is_bad_file(raw_data):
        return "skip_good"

    # Extract Problem_ID from filename
    problem_id = int(file_path.stem)

    # Infer task info from path
    level, task_type, task = infer_task_and_level(file_path)

    # Extract content from raw response
    content = raw_data.get("choices", [{}])[0].get("message", {}).get("content", "")
    if not content:
        return "skip_no_content"

    usage = raw_data.get("usage", {})

    # Load original question data
    data_path = Path(DATA_BASE) / level / "MP2" / f"{problem_id}.json"
    if not data_path.exists():
        return f"skip_no_data:{data_path}"

    with open(data_path, "r", encoding="utf-8") as f:
        que = json.load(f)

    # Build re-extraction prompt and call gpt-4o to get formatted answer
    reextract_prompt = build_reextract_prompt(content=content, task=task, que=que)
    try:
        reextract_response = client.get_response_not_stream(prompt=reextract_prompt, seed=seed)
    except Exception as e:
        logger.error(f"Re-extraction API call failed for {file_path}: {e}")
        return "skip_reextract_api_error"

    if not reextract_response:
        return "skip_reextract_no_response"

    answer = extract_from_reextract_response(reextract_response, task)

    if not answer or answer == [""] or answer == []:
        return "skip_no_answer"

    # Token info from original raw response
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)
    reasoning_tokens = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0)

    extracted_data = {
        "content": content,
        "input_token": prompt_tokens,
        "total_token": total_tokens,
        "reasoning_token": reasoning_tokens,
        "answer": answer,
    }

    # Get ground truth
    connecting_point = que.get("Connecting_Point", [])
    truth_list = get_ground_truth(que=que, task=task, connecting_point=connecting_point)

    # Judge correctness
    try:
        correctness = judge(answer=answer, truth=truth_list, task=task, seed=seed)
        if not correctness:
            return "skip_judge_failed"
    except Exception as e:
        logger.error(f"Judge failed for {file_path}: {e}")
        return "skip_judge_error"

    # Build proper output
    per_problem_json = make_per_problem_evaluation_json(
        ques=que,
        extracted_data=extracted_data,
        truth_list=truth_list,
        correctness=correctness,
        level=level,
        class_name="MP2",
        model=MODEL,
        task=task,
    )

    # Overwrite file
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(per_problem_json, f, ensure_ascii=False, indent=2)

    return "fixed"


def main():
    base = Path(OUTPUT_BASE)
    if not base.exists():
        print(f"[ERROR] Output directory not found: {base}")
        sys.exit(1)

    # Collect all JSON files (excluding summary.json)
    all_files = [
        f for f in base.rglob("*.json")
        if f.name != "summary.json"
    ]

    # Find bad files
    bad_files = []
    for f in all_files:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if is_bad_file(data):
                bad_files.append(f)
        except Exception:
            continue

    print(f"Total files: {len(all_files)}, Bad files: {len(bad_files)}")

    if not bad_files:
        print("No bad files found. Nothing to fix.")
        return

    # Create extractor client once
    client = get_client(model=EXTRACTOR_MODEL)

    # Fix each bad file
    stats = {"fixed": 0, "skipped": 0, "errors": 0}
    for i, fp in enumerate(sorted(bad_files)):
        rel = fp.relative_to(base)
        status = fix_single_file(fp, client=client)
        if status == "fixed":
            stats["fixed"] += 1
            print(f"[{i+1}/{len(bad_files)}] FIXED: {rel}")
        elif status.startswith("skip"):
            stats["skipped"] += 1
            print(f"[{i+1}/{len(bad_files)}] SKIP ({status}): {rel}")
        else:
            stats["errors"] += 1
            print(f"[{i+1}/{len(bad_files)}] ERROR ({status}): {rel}")

    print(f"\nDone. Fixed: {stats['fixed']}, Skipped: {stats['skipped']}, Errors: {stats['errors']}")


if __name__ == "__main__":
    main()
