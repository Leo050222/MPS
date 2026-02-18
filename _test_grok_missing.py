"""
调试 grok-4-1-fast-non-reasoning 在 T2#59 和 T3#114 上为什么跑不出来
模拟完整 pipeline：API 调用 -> extract -> 打印完整 content
"""

import asyncio
import json
import os
import sys
import platform
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from client.client import get_client
from expriment.inference import (
    extract, get_parts_in_order, build_prompt, get_ground_truth,
    judge_async, parse_task_mode
)
from config import MODELS_COMPANIES_MAP


def flush_print(*args, **kwargs):
    print(*args, **kwargs, flush=True)


async def run_one(client, problem_data, model, task, label, max_retry=3):
    """模拟 pipeline 单次完整流程，带重试"""
    pid = problem_data.get("Problem_ID", "?")
    mp, mode = parse_task_mode(task)
    model_company = MODELS_COMPANIES_MAP.get(model, "openai")

    # 构建 prompt
    if mode == "synthesised":
        C = problem_data.get("Math_Problem", "")
        prompt = build_prompt(task=task, C=C, parts=[], model=model)
    else:
        parts = get_parts_in_order(problem_data)
        prompt = build_prompt(task=task, C="", parts=parts, model=model)

    for attempt in range(1, max_retry + 1):
        flush_print(f"\n{'='*60}")
        flush_print(f"{label} - 第 {attempt}/{max_retry} 次尝试 ({mode})...")
        start = time.time()

        try:
            response = await client.get_response_async(prompt=prompt, reasoning="minimal", seed=42)
        except Exception as e:
            flush_print(f"{label} - API 异常: {e}")
            continue

        elapsed = time.time() - start

        if response is None:
            flush_print(f"{label} - 响应 None! ({elapsed:.1f}s)")
            continue

        # 解析
        choices = response.get("choices", [])
        finish_reason = choices[0].get("finish_reason", "?") if choices else "?"
        content = choices[0].get("message", {}).get("content", "") if choices else ""
        usage = response.get("usage", {})
        completion_tokens = usage.get("completion_tokens", 0)
        reasoning_tokens = usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0)

        flush_print(f"{label} - finish_reason={finish_reason} | comp={completion_tokens} | reas={reasoning_tokens} | content_len={len(content)} | time={elapsed:.1f}s")
        flush_print(f"\n--- Content 前 500 字符 ---")
        flush_print(content[:500])
        flush_print(f"\n--- Content 后 500 字符 ---")
        flush_print(content[-500:] if len(content) > 500 else "(same as above)")

        # extract
        extracted = extract(response=response, task=task, model_company=model_company)
        answer = extracted.get("answer", [])
        answer_ok = bool(answer) and answer != [""] and answer != []

        flush_print(f"\n{label} - 提取结果: answer={answer}, answer_ok={answer_ok}")

        if answer_ok:
            # judge
            try:
                connecting_point = problem_data.get("Connecting_Point", [])
                truth_list = get_ground_truth(que=problem_data, task=task, connecting_point=connecting_point)
                correctness = await judge_async(answer=answer, truth=truth_list, task=task, seed=42)
                flush_print(f"{label} - Judge: correctness={correctness}")
            except Exception as e:
                flush_print(f"{label} - Judge 异常: {e}")
                correctness = []

            return {
                "label": label, "pid": pid, "attempt": attempt,
                "status": "OK", "finish_reason": finish_reason,
                "completion_tokens": completion_tokens, "reasoning_tokens": reasoning_tokens,
                "content_length": len(content), "answer": answer,
                "correctness": correctness, "elapsed": round(elapsed, 1)
            }
        else:
            flush_print(f"{label} - 答案为空，准备重试...")

    flush_print(f"\n{label} - {max_retry} 次重试全部失败！")
    return {
        "label": label, "pid": pid, "attempt": max_retry,
        "status": "FAILED", "finish_reason": finish_reason,
        "completion_tokens": completion_tokens, "reasoning_tokens": reasoning_tokens,
        "content_length": len(content), "content_tail": content[-1000:] if content else "",
        "answer": answer, "elapsed": round(elapsed, 1)
    }


async def main():
    MODEL = "grok-4-1-fast-non-reasoning"
    TASK = "MP2_Synthesised"

    # 缺失的两道题
    missing = [
        ("T2", 59),
        ("T3", 114),
    ]

    client = get_client(model=MODEL)
    flush_print(f"模型: {MODEL}")
    flush_print(f"客户端: {type(client).__name__}, base_url={client.base_url}")
    flush_print(f"任务: {TASK}")
    flush_print(f"缺失题目: {missing}\n")

    results = []
    for tier, pid in missing:
        data_path = os.path.join("data", "SMP_MP2_300_Modified_V2", tier, "MP2", f"{pid}.json")
        if not os.path.exists(data_path):
            flush_print(f"数据文件不存在: {data_path}")
            continue

        with open(data_path, "r", encoding="utf-8") as f:
            problem_data = json.load(f)

        label = f"[{tier}#{pid}]"
        flush_print(f"加载: {data_path} (Problem_ID={problem_data.get('Problem_ID', '?')})")

        result = await run_one(client, problem_data, MODEL, TASK, label)
        results.append(result)

    # 保存
    out_file = "_test_grok_missing_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    flush_print(f"\n结果已保存: {out_file}")


if __name__ == "__main__":
    if platform.system() == "Windows":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
