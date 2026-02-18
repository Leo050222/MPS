"""
测试 grok-4-1-fast-reasoning 和 grok-4-1-fast-non-reasoning 跑 pipeline
从 T5 抽 5 条数据，每个模型跑 Synthesised，共 10 次请求，并行执行
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
    judge_async, parse_task_mode, make_per_problem_evaluation_json
)
from config import MODELS_COMPANIES_MAP


def flush_print(*args, **kwargs):
    print(*args, **kwargs, flush=True)


async def run_one(client, problem_data, model, task, test_id, semaphore):
    """模拟 pipeline 单次完整流程: API -> extract -> judge"""
    async with semaphore:
        pid = problem_data.get("Problem_ID", "?")
        mp, mode = parse_task_mode(task)
        label = f"[T{test_id}] {model} PID={pid}"
        model_company = MODELS_COMPANIES_MAP.get(model, "openai")

        # reasoning 参数
        reasoning = "medium" if "reasoning" in model else "minimal"

        # 构建 prompt
        if mode == "synthesised":
            C = problem_data.get("Math_Problem", "")
            prompt = build_prompt(task=task, C=C, parts=[], model=model)
        else:
            parts = get_parts_in_order(problem_data)
            prompt = build_prompt(task=task, C="", parts=parts, model=model)

        flush_print(f"{label} - 开始 ({mode}, reasoning={reasoning})...")
        start = time.time()

        # 调用 API
        try:
            response = await client.get_response_async(prompt=prompt, reasoning=reasoning, seed=42)
        except Exception as e:
            flush_print(f"{label} - API 异常: {e}")
            return {"test_id": test_id, "model": model, "pid": pid, "status": "api_error",
                    "answer_ok": False, "error": str(e)}
        elapsed_api = time.time() - start

        if response is None:
            flush_print(f"{label} - 响应 None! ({elapsed_api:.1f}s)")
            return {"test_id": test_id, "model": model, "pid": pid, "status": "null_response",
                    "answer_ok": False, "completion_tokens": 0, "reasoning_tokens": 0,
                    "finish_reason": "error", "elapsed_api": round(elapsed_api, 1),
                    "elapsed_total": round(elapsed_api, 1)}

        # 提取信息
        choices = response.get("choices", [])
        finish_reason = choices[0].get("finish_reason", "?") if choices else "?"
        content = choices[0].get("message", {}).get("content", "") if choices else ""
        usage = response.get("usage", {})
        completion_tokens = usage.get("completion_tokens", 0)
        reasoning_tokens = usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0)

        # extract
        extracted = extract(response=response, task=task, model_company=model_company)
        answer = extracted.get("answer", [])
        answer_ok = bool(answer) and answer != [""] and answer != []

        # judge
        correctness = []
        if answer_ok:
            try:
                connecting_point = problem_data.get("Connecting_Point", [])
                truth_list = get_ground_truth(que=problem_data, task=task, connecting_point=connecting_point)
                correctness = await judge_async(answer=answer, truth=truth_list, task=task, seed=42)
            except Exception as e:
                flush_print(f"{label} - Judge 异常: {e}")
                correctness = []

        elapsed_total = time.time() - start
        tag = "TRUNC" if finish_reason == "length" else ("OK" if answer_ok else "NO_ANS")

        flush_print(
            f"{label} - {tag} | fin={finish_reason} | comp={completion_tokens} | "
            f"reas={reasoning_tokens} | answer={answer} | correct={correctness} | "
            f"api={elapsed_api:.0f}s total={elapsed_total:.0f}s"
        )

        return {
            "test_id": test_id,
            "model": model,
            "pid": pid,
            "task": mode,
            "reasoning": reasoning,
            "status": tag,
            "finish_reason": finish_reason,
            "completion_tokens": completion_tokens,
            "reasoning_tokens": reasoning_tokens,
            "content_length": len(content),
            "content": content,
            "answer": answer,
            "answer_ok": answer_ok,
            "correctness": correctness,
            "elapsed_api": round(elapsed_api, 1),
            "elapsed_total": round(elapsed_total, 1),
        }


async def main():
    MODELS = ["grok-4-1-fast-reasoning", "grok-4-1-fast-non-reasoning"]
    TASK = "MP2_Synthesised"
    CONCURRENCY = 5

    # 加载 T5 的 5 条数据
    data_dir = os.path.join("data", "SMP_MP2_300_Modified_V2", "T5", "MP2")
    problem_ids = [1, 2, 3, 5, 10]
    problems = []
    for pid in problem_ids:
        path = os.path.join(data_dir, f"{pid}.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                problems.append(json.load(f))

    flush_print(f"模型: {MODELS}")
    flush_print(f"任务: {TASK}")
    flush_print(f"问题数: {len(problems)}, 总请求: {len(problems) * len(MODELS)} 次")
    flush_print(f"并行: {CONCURRENCY}")

    # 创建客户端
    clients = {}
    for m in MODELS:
        clients[m] = get_client(model=m)
        flush_print(f"  {m}: {type(clients[m]).__name__}, base_url={clients[m].base_url}")

    semaphore = asyncio.Semaphore(CONCURRENCY)
    tasks = []
    test_id = 0

    for problem_data in problems:
        for model in MODELS:
            test_id += 1
            tasks.append(run_one(clients[model], problem_data, model, TASK, test_id, semaphore))

    flush_print(f"\n开始并行执行 {len(tasks)} 个请求...\n")
    all_results = await asyncio.gather(*tasks, return_exceptions=True)

    # 过滤
    results = []
    for r in all_results:
        if isinstance(r, Exception):
            flush_print(f"异常: {r}")
        elif isinstance(r, dict):
            results.append(r)

    # 汇总
    flush_print(f"\n{'='*70}")
    flush_print(f"=== 汇总报告 ===")
    flush_print(f"{'='*70}")

    for model in MODELS:
        mr = [r for r in results if r["model"] == model]
        if not mr:
            flush_print(f"\n  [{model}] 无结果")
            continue

        ok = sum(1 for r in mr if r["answer_ok"])
        trunc = sum(1 for r in mr if r["finish_reason"] == "length")
        comp_list = [r["completion_tokens"] for r in mr]
        reas_list = [r["reasoning_tokens"] for r in mr]

        # 统计 correctness
        all_correct = []
        for r in mr:
            if r.get("correctness"):
                all_correct.extend(r["correctness"])
        correct_count = sum(1 for c in all_correct if c)

        flush_print(f"\n  [{model}]")
        flush_print(f"    请求数: {len(mr)}")
        flush_print(f"    答案提取成功: {ok}/{len(mr)}")
        flush_print(f"    截断: {trunc}")
        flush_print(f"    正确率: {correct_count}/{len(all_correct)} "
                    f"({correct_count/len(all_correct)*100:.0f}%)" if all_correct else "    正确率: N/A")
        flush_print(f"    completion_tokens: [{min(comp_list)}, {max(comp_list)}] "
                    f"avg={sum(comp_list)/len(comp_list):.0f}")
        flush_print(f"    reasoning_tokens:  [{min(reas_list)}, {max(reas_list)}] "
                    f"avg={sum(reas_list)/len(reas_list):.0f}")
        flush_print(f"    平均耗时: API={sum(r['elapsed_api'] for r in mr)/len(mr):.0f}s "
                    f"total={sum(r['elapsed_total'] for r in mr)/len(mr):.0f}s")

    # 保存
    out_file = "_test_grok_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    flush_print(f"\n结果已保存: {out_file}")


if __name__ == "__main__":
    if platform.system() == "Windows":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
