"""
DCS Experiment 2 (A'-B) local Qwen inference script.

Processes all levels (T1-T5) for the simplified DCS dataset schema.
Uses asyncio + ThreadPoolExecutor to overlap I/O (judge API calls)
with GPU generation while keeping GPU usage safe and serialized.

Usage:
    python expriment/dcs_local_qwen_inference.py \
        --model_path /path/to/Qwen2.5-7B \
        --model_name qwen2.5-7b \
        --concurrency 1 \
        --max_new_tokens 4096
"""

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import json
import logging
import asyncio
import platform
import functools
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor

from config import SEED, TOP_P, MAX_RETRY
from prompt.prompt import get_prompt_builder
from inference import (
    iter_problem_json_files,
    extract,
    judge_async,
    load_existing_outputs,
)
from local_qwen_inference import load_local_model, local_generate

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

DCS_DATA_BASE = "data/DCS_Experiment_2/A'-B/evaluation/A'-B"
DCS_OUTPUT_BASE = "output/DCS_Experiment_2"
TASK_SYNTHESISED = "MP2_Synthesised"


# ---------------------------------------------------------------------------
# Field mapping
# ---------------------------------------------------------------------------

def adapt_dcs_to_internal(raw: dict) -> dict:
    """Map the simple DCS schema to internal field names."""
    return {
        "Problem_ID": raw["id"],
        "Math_Problem": raw["problem"],
        "Ground_Truth": [raw["ground_truth"]],
        "chunk_type": raw.get("chunk_type", ""),
        "source_id": raw.get("source_id"),
    }


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_dcs_evaluation_json(
    que: dict,
    extracted_data: dict,
    truth_list: list[str],
    correctness: list[bool],
    level: str,
    model: str,
) -> dict:
    """Build output JSON for a single DCS problem evaluation."""
    return {
        "timestamp": utc_timestamp(),
        "model": model,
        "type": f"{level}_DCS_Synthesised_Evaluation",
        "Problem_ID": que["Problem_ID"],
        "chunk_type": que.get("chunk_type", ""),
        "source_id": que.get("source_id"),
        "math_problem": que["Math_Problem"],
        "reasoning_content": extracted_data.get("content", ""),
        "output_answer": extracted_data.get("answer", []),
        "ground_truth": truth_list,
        "correctness": correctness,
        "prompt_tokens": extracted_data.get("input_token", 0),
        "completion_tokens": extracted_data.get("total_token", 0) - extracted_data.get("input_token", 0),
        "reasoning_tokens": extracted_data.get("reasoning_token", 0),
    }


# ---------------------------------------------------------------------------
# Per-problem processing (async wrapper)
# ---------------------------------------------------------------------------

async def process_single_dcs_problem(
    que: dict,
    model,
    tokenizer,
    model_name: str,
    level: str,
    output_path: str,
    semaphore: asyncio.Semaphore,
    executor: ThreadPoolExecutor,
    seed: int | None = None,
    max_new_tokens: int = 4096,
    temperature: float = 0.7,
    top_p: float = 0.2,
) -> dict:
    pid = que["Problem_ID"]
    result = {"Problem_ID": pid, "status": "skipped", "correctness": []}

    async with semaphore:
        # 1. Build prompt (synthesised mode — single problem)
        prompt_builder = get_prompt_builder()
        prompt = prompt_builder.synthesised_prompt(
            problem=que["Math_Problem"], model=model_name
        )

        # 2. Generate with retries
        loop = asyncio.get_event_loop()
        response = None
        extracted_data = None

        for attempt in range(1, MAX_RETRY + 1):
            try:
                gen_fn = functools.partial(
                    local_generate, model, tokenizer, prompt,
                    max_new_tokens, temperature, top_p, seed,
                )
                response = await loop.run_in_executor(executor, gen_fn)
            except Exception as e:
                logger.error(f"[{pid}] Generation error on attempt {attempt}: {e}")
                response = None

            if response is None:
                logger.warning(f"[{pid}] Empty response, retrying... {attempt}/{MAX_RETRY}")
                await asyncio.sleep(2)
                continue

            # 3. Extract answer
            try:
                extracted_data = extract(
                    response=response, task=TASK_SYNTHESISED, model_company="openai"
                )
                if not extracted_data or extracted_data.get("content") is None:
                    logger.warning(f"[{pid}] Extraction returned None, retrying... {attempt}/{MAX_RETRY}")
                    await asyncio.sleep(2)
                    continue
                answer = extracted_data.get("answer", [])
                if not answer or answer == [""]:
                    logger.warning(f"[{pid}] Empty answer, retrying... {attempt}/{MAX_RETRY}")
                    await asyncio.sleep(2)
                    continue
            except Exception as e:
                logger.error(f"[{pid}] Extraction error on attempt {attempt}: {e}")
                await asyncio.sleep(2)
                continue

            break  # success

        if response is None or extracted_data is None:
            logger.error(f"[{pid}] Failed after {MAX_RETRY} retries")
            return result

        answer_check = extracted_data.get("answer", [])
        if not answer_check or answer_check == [""]:
            logger.error(f"[{pid}] Answer still empty after retries")
            return result

        # 4. Judge correctness (GPT-4o)
        try:
            truth_list = que["Ground_Truth"]  # already a list from adapt_dcs_to_internal
            answer_list = extracted_data.get("answer", [])
            if not isinstance(answer_list, list):
                answer_list = [str(answer_list)]

            correctness = await judge_async(
                answer=answer_list, truth=truth_list,
                task=TASK_SYNTHESISED, seed=seed,
            )
            if not correctness:
                logger.error(f"[{pid}] Judge returned empty correctness")
                return result
        except Exception as e:
            logger.error(f"[{pid}] Judge error: {e}")
            return result

        # 5. Save output JSON
        try:
            per_problem_json = make_dcs_evaluation_json(
                que=que, extracted_data=extracted_data,
                truth_list=truth_list, correctness=correctness,
                level=level, model=model_name,
            )
            out_file = os.path.join(output_path, f"{pid}.json")
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(per_problem_json, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[{pid}] Error saving result: {e}")
            return result

    logger.info(f"[{pid}] Done ({level})")
    result["status"] = "ok"
    result["correctness"] = correctness
    return result


# ---------------------------------------------------------------------------
# Level runner
# ---------------------------------------------------------------------------

async def run_dcs_level(
    model,
    tokenizer,
    level: str,
    data_base: str,
    output_base: str,
    model_name: str,
    concurrency: int,
    seed: int | None,
    max_new_tokens: int,
    temperature: float,
    top_p: float,
    semaphore: asyncio.Semaphore,
    executor: ThreadPoolExecutor,
):
    data_path = os.path.join(data_base, level)
    output_path = os.path.join(output_base, model_name, "A'-B", level)
    os.makedirs(output_path, exist_ok=True)

    try:
        problem_files = iter_problem_json_files(data_path)
    except Exception as e:
        logger.error(f"[{level}] Cannot list data files: {e}")
        return

    cached = load_existing_outputs(output_path)
    finished_ids = set(cached.keys())

    pending = []
    for json_path in problem_files:
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load {json_path}: {e}")
            continue
        que = adapt_dcs_to_internal(raw)
        if que["Problem_ID"] in finished_ids:
            continue
        pending.append(que)

    if not pending:
        logger.info(f"[{level}] No pending problems.")
        return

    logger.info(f"[{level}] Processing {len(pending)} problems (concurrency={concurrency})")

    tasks_list = [
        process_single_dcs_problem(
            que=que, model=model, tokenizer=tokenizer,
            model_name=model_name, level=level,
            output_path=output_path, semaphore=semaphore,
            executor=executor, seed=seed,
            max_new_tokens=max_new_tokens,
            temperature=temperature, top_p=top_p,
        )
        for que in pending
    ]

    results = await asyncio.gather(*tasks_list, return_exceptions=True)
    ok = sum(1 for r in results if not isinstance(r, Exception) and r.get("status") == "ok")
    fail = len(results) - ok
    logger.info(f"[{level}] Completed: {ok} ok, {fail} failed/skipped")


# ---------------------------------------------------------------------------
# Main coroutine
# ---------------------------------------------------------------------------

async def main_dcs(
    model_path: str,
    model_name: str,
    data_base: str,
    output_base: str,
    levels: list[str],
    concurrency: int,
    seed: int | None,
    max_new_tokens: int,
    temperature: float,
    top_p: float,
):
    model, tokenizer = load_local_model(model_path)
    semaphore = asyncio.Semaphore(concurrency)
    executor = ThreadPoolExecutor(max_workers=concurrency)

    try:
        for level in levels:
            logger.info(f"=== Starting {level} ===")
            await run_dcs_level(
                model=model, tokenizer=tokenizer, level=level,
                data_base=data_base, output_base=output_base,
                model_name=model_name, concurrency=concurrency,
                seed=seed, max_new_tokens=max_new_tokens,
                temperature=temperature, top_p=top_p,
                semaphore=semaphore, executor=executor,
            )
    finally:
        executor.shutdown(wait=False)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Run local Qwen inference on DCS Experiment 2 (A'-B) dataset"
    )
    parser.add_argument("--model_path", type=str, required=True,
                        help="Path to local Qwen2.5 model directory")
    parser.add_argument("--model_name", type=str, default="qwen2.5-7b",
                        help="Display name used in output directory (default: qwen2.5-7b)")
    parser.add_argument("--data_base", type=str, default=DCS_DATA_BASE,
                        help=f"Base data directory (default: {DCS_DATA_BASE})")
    parser.add_argument("--output_base", type=str, default=DCS_OUTPUT_BASE,
                        help=f"Base output directory (default: {DCS_OUTPUT_BASE})")
    parser.add_argument("--levels", type=str, nargs="+",
                        default=["T1", "T2", "T3", "T4", "T5"],
                        help="Levels to process (default: T1 T2 T3 T4 T5)")
    parser.add_argument("--concurrency", type=int, default=1,
                        help="Number of concurrent GPU workers (default: 1)")
    parser.add_argument("--seed", type=int, default=SEED,
                        help=f"Random seed (default: {SEED})")
    parser.add_argument("--max_new_tokens", type=int, default=4096,
                        help="Max new tokens to generate (default: 4096)")
    parser.add_argument("--temperature", type=float, default=0.7,
                        help="Sampling temperature (default: 0.7)")
    parser.add_argument("--top_p", type=float, default=TOP_P,
                        help=f"Top-p sampling (default: {TOP_P})")

    args = parser.parse_args()

    if platform.system() == "Windows":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(main_dcs(
        model_path=args.model_path,
        model_name=args.model_name,
        data_base=args.data_base,
        output_base=args.output_base,
        levels=args.levels,
        concurrency=args.concurrency,
        seed=args.seed,
        max_new_tokens=args.max_new_tokens,
        temperature=args.temperature,
        top_p=args.top_p,
    ))
