"""
Local Qwen2.5 baseline inference script.

Processes all levels (T1-T5) and tasks (MP2_Seperated, MP2_Synthesised) in a single
terminal session. Uses asyncio + ThreadPoolExecutor to overlap I/O (judge API calls)
with GPU generation while keeping GPU usage safe and serialized.

Usage:
    python expriment/local_qwen_inference.py \
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
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from config import SEED, TOP_P, DATASET_NAME, DATA_BASE_PATH, MAX_RETRY
from inference import (
    parse_task_mode,
    get_parts_in_order,
    iter_problem_json_files,
    build_prompt,
    extract,
    get_ground_truth,
    make_per_problem_evaluation_json,
    judge_async,
    load_existing_outputs,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------

def load_local_model(model_path: str):
    """Load Qwen2.5 (or any HF causal LM) from a local directory."""
    logger.info(f"Loading tokenizer from {model_path} ...")
    tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)

    logger.info(f"Loading model from {model_path} ...")
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
        device_map="auto",
        trust_remote_code=True,
    )
    model.eval()
    logger.info("Model loaded successfully.")
    return model, tokenizer


# ---------------------------------------------------------------------------
# Generation (synchronous — runs inside ThreadPoolExecutor)
# ---------------------------------------------------------------------------

def local_generate(
    model,
    tokenizer,
    messages: list[dict],
    max_new_tokens: int = 4096,
    temperature: float = 0.7,
    top_p: float = 0.2,
    seed: int | None = None,
) -> dict:
    """Run one forward pass and return a normalized response dict.

    The returned dict has the same shape as what client.get_response_async()
    returns, so the existing extract() function works without modification.
    """
    # Apply chat template (Qwen2.5 uses its own instruct format)
    text = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    input_ids = tokenizer(text, return_tensors="pt").input_ids.to(model.device)
    input_len = input_ids.shape[1]

    if seed is not None:
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)

    with torch.no_grad():
        output_ids = model.generate(
            input_ids,
            max_new_tokens=max_new_tokens,
            do_sample=True,
            temperature=temperature,
            top_p=top_p,
            pad_token_id=tokenizer.eos_token_id,
        )

    generated_ids = output_ids[0][input_len:]
    content = tokenizer.decode(generated_ids, skip_special_tokens=True)
    output_len = len(generated_ids)

    return {
        "choices": [{"message": {"content": content}}],
        "usage": {
            "prompt_tokens": input_len,
            "completion_tokens": output_len,
            "total_tokens": input_len + output_len,
            "completion_tokens_details": {"reasoning_tokens": 0},
        },
    }


# ---------------------------------------------------------------------------
# Per-problem processing (async wrapper)
# ---------------------------------------------------------------------------

async def process_single_problem(
    que: dict,
    model,
    tokenizer,
    model_name: str,
    level: str,
    class_name: str,
    task: str,
    output_path: str,
    semaphore: asyncio.Semaphore,
    executor: ThreadPoolExecutor,
    seed: int | None = None,
    max_new_tokens: int = 4096,
    temperature: float = 0.7,
    top_p: float = 0.2,
) -> dict:
    Problem_ID = que["Problem_ID"]
    result = {"Problem_ID": Problem_ID, "status": "skipped", "correctness": []}

    async with semaphore:
        # 1. Build prompt (same logic as API pipeline)
        C = que.get("Math_Problem", "")
        parts = get_parts_in_order(que)
        try:
            prompt = build_prompt(task=task, C=C, parts=parts, model=model_name)
        except Exception as e:
            logger.error(f"[{Problem_ID}] Error building prompt: {e}")
            return result

        # 2. Generate with retries
        loop = asyncio.get_event_loop()
        response = None
        extracted_data = None

        for attempt in range(1, MAX_RETRY + 1):
            try:
                gen_fn = functools.partial(
                    local_generate,
                    model,
                    tokenizer,
                    prompt,
                    max_new_tokens,
                    temperature,
                    top_p,
                    seed,
                )
                response = await loop.run_in_executor(executor, gen_fn)
            except Exception as e:
                logger.error(f"[{Problem_ID}] Generation error on attempt {attempt}: {e}")
                response = None

            if response is None:
                logger.warning(f"[{Problem_ID}] Empty response, retrying... {attempt}/{MAX_RETRY}")
                await asyncio.sleep(2)
                continue

            # 3. Extract answer
            try:
                extracted_data = extract(response=response, task=task, model_company="openai")
                if not extracted_data or extracted_data.get("content") is None:
                    logger.warning(f"[{Problem_ID}] Extraction returned None, retrying... {attempt}/{MAX_RETRY}")
                    await asyncio.sleep(2)
                    continue
                answer = extracted_data.get("answer", [])
                if not answer or answer == [""]:
                    logger.warning(f"[{Problem_ID}] Empty answer after extraction, retrying... {attempt}/{MAX_RETRY}")
                    await asyncio.sleep(2)
                    continue
            except Exception as e:
                logger.error(f"[{Problem_ID}] Extraction error on attempt {attempt}: {e}")
                await asyncio.sleep(2)
                continue

            break  # success

        if response is None or extracted_data is None:
            logger.error(f"[{Problem_ID}] Failed after {MAX_RETRY} retries")
            return result

        answer_check = extracted_data.get("answer", [])
        if not answer_check or answer_check == [""]:
            logger.error(f"[{Problem_ID}] Answer still empty after {MAX_RETRY} retries")
            return result

        # 4. Judge correctness (calls GPT-4o via API, same as API pipeline)
        try:
            connecting_point = que.get("Connecting_Point", [])
            truth_list = get_ground_truth(que=que, task=task, connecting_point=connecting_point)
            answer_list = extracted_data.get("answer", [])
            if not isinstance(answer_list, list):
                answer_list = [str(answer_list)]

            correctness = await judge_async(answer=answer_list, truth=truth_list, task=task, seed=seed)
            if not correctness:
                logger.error(f"[{Problem_ID}] Judge returned empty correctness")
                return result
        except Exception as e:
            logger.error(f"[{Problem_ID}] Judge error: {e}")
            return result

        # 5. Build and save output JSON (identical format to API pipeline)
        try:
            per_problem_json = make_per_problem_evaluation_json(
                ques=que,
                extracted_data=extracted_data,
                truth_list=truth_list,
                correctness=correctness,
                level=level,
                class_name=class_name,
                model=model_name,
                task=task,
            )
            out_file = os.path.join(output_path, f"{Problem_ID}.json")
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(per_problem_json, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[{Problem_ID}] Error saving result: {e}")
            return result

    logger.info(f"[{Problem_ID}] Done ({level}/{class_name}/{task})")
    result["status"] = "ok"
    result["correctness"] = correctness
    return result


# ---------------------------------------------------------------------------
# Level/task runner
# ---------------------------------------------------------------------------

async def run_level_task(
    model,
    tokenizer,
    level: str,
    class_name: str,
    task: str,
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
    _, mode = parse_task_mode(task)
    mode_dir = "Seperated" if mode == "seperated" else "Synthesised"

    data_path = os.path.join(data_base, level, class_name)
    output_path = os.path.join(output_base, model_name, "non-reasoning", level, class_name, mode_dir)

    os.makedirs(output_path, exist_ok=True)

    try:
        problem_files = iter_problem_json_files(data_path)
    except Exception as e:
        logger.error(f"[{level}/{task}] Cannot list data files: {e}")
        return

    cached = load_existing_outputs(output_path)
    finished_ids = set(cached.keys())

    pending = []
    for json_path in problem_files:
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                que = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load {json_path}: {e}")
            continue
        pid = que.get("Problem_ID")
        if pid is None or pid in finished_ids:
            continue
        pending.append(que)

    if not pending:
        logger.info(f"[{level}/{task}] No pending problems.")
        return

    logger.info(f"[{level}/{task}] Processing {len(pending)} problems (concurrency={concurrency})")

    tasks_list = [
        process_single_problem(
            que=que,
            model=model,
            tokenizer=tokenizer,
            model_name=model_name,
            level=level,
            class_name=class_name,
            task=task,
            output_path=output_path,
            semaphore=semaphore,
            executor=executor,
            seed=seed,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            top_p=top_p,
        )
        for que in pending
    ]

    results = await asyncio.gather(*tasks_list, return_exceptions=True)

    ok = sum(1 for r in results if not isinstance(r, Exception) and r.get("status") == "ok")
    fail = len(results) - ok
    logger.info(f"[{level}/{task}] Completed: {ok} ok, {fail} failed/skipped")


# ---------------------------------------------------------------------------
# Main coroutine
# ---------------------------------------------------------------------------

async def main_local(
    model_path: str,
    model_name: str,
    data_base: str,
    output_base: str,
    levels: list[str],
    tasks: list[str],
    class_name: str,
    concurrency: int,
    seed: int | None,
    max_new_tokens: int,
    temperature: float,
    top_p: float,
):
    model, tokenizer = load_local_model(model_path)

    # One semaphore and one executor shared across all levels/tasks
    semaphore = asyncio.Semaphore(concurrency)
    executor = ThreadPoolExecutor(max_workers=concurrency)

    try:
        for level in levels:
            for task in tasks:
                logger.info(f"=== Starting {level} / {task} ===")
                await run_level_task(
                    model=model,
                    tokenizer=tokenizer,
                    level=level,
                    class_name=class_name,
                    task=task,
                    data_base=data_base,
                    output_base=output_base,
                    model_name=model_name,
                    concurrency=concurrency,
                    seed=seed,
                    max_new_tokens=max_new_tokens,
                    temperature=temperature,
                    top_p=top_p,
                    semaphore=semaphore,
                    executor=executor,
                )
    finally:
        executor.shutdown(wait=False)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run local Qwen2.5 inference on math problems")
    parser.add_argument("--model_path", type=str, required=True,
                        help="Path to local Qwen2.5 model directory")
    parser.add_argument("--model_name", type=str, default="qwen2.5-7b",
                        help="Display name used in output directory (default: qwen2.5-7b)")
    parser.add_argument("--data_base", type=str, default=DATA_BASE_PATH,
                        help=f"Base data directory (default: {DATA_BASE_PATH})")
    parser.add_argument("--output_base", type=str, default=f"output/{DATASET_NAME}",
                        help=f"Base output directory (default: output/{DATASET_NAME})")
    parser.add_argument("--levels", type=str, nargs="+", default=["T1", "T2", "T3", "T4", "T5"],
                        help="Levels to process (default: T1 T2 T3 T4 T5)")
    parser.add_argument("--tasks", type=str, nargs="+",
                        default=["MP2_Seperated", "MP2_Synthesised"],
                        help="Tasks to process (default: MP2_Seperated MP2_Synthesised)")
    parser.add_argument("--class_name", type=str, default="MP2",
                        help="Class name (default: MP2)")
    parser.add_argument("--concurrency", type=int, default=1,
                        help="Number of concurrent GPU workers (default: 1; try 2 on 4090+7B)")
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

    asyncio.run(main_local(
        model_path=args.model_path,
        model_name=args.model_name,
        data_base=args.data_base,
        output_base=args.output_base,
        levels=args.levels,
        tasks=args.tasks,
        class_name=args.class_name,
        concurrency=args.concurrency,
        seed=args.seed,
        max_new_tokens=args.max_new_tokens,
        temperature=args.temperature,
        top_p=args.top_p,
    ))
