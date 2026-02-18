from operator import truth
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from client.client import get_client
from prompt.prompt import get_prompt_builder
import pdb
import json
import re
import logging
from tqdm import tqdm
from pathlib import Path
from datetime import datetime, timezone
from config import AVAILABLE_MODEL, TASKS, MODELS_COMPANIES_MAP
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
tasks = TASKS
import time
import asyncio
import platform

def parse_task_mode(task: str) -> tuple[str, str]:
    """Return (mp, mode) from a task like 'MP2_Seperated' or 'MP3_Synthesised'."""
    if not isinstance(task, str):
        raise TypeError(f"task must be str, got {type(task)}")
    if "_" not in task:
        raise ValueError(f"Invalid task format: {task}")
    mp, mode = task.split("_", 1)
    mode = mode.lower()
    if mode not in {"seperated", "synthesised"}:
        raise ValueError(f"Unknown task mode: {task}")
    return mp.upper(), mode


def get_parts_in_order(que: dict) -> list[str]:
    """Extract sub-problems in stable order.

    Per user guarantee: the order inside `Synthesised_By` matches `Ground_Truth`.

    Supports historical shapes:
    - list[dict]  e.g. [{'A': '...'}, {'B': '...'}]
    - dict        e.g. {'A': '...', 'B': '...'} (legacy)
    """
    sb = que.get("Synthesised_By")
    if sb is None:
        return []

    if isinstance(sb, list):
        parts: list[str] = []
        for item in sb:
            if isinstance(item, dict):
                parts.extend(str(v) for v in item.values())
            else:
                parts.append(str(item))
        return parts

    if isinstance(sb, dict):
        return [str(v) for v in sb.values()]

    raise TypeError(f"Unexpected Synthesised_By type: {type(sb)}")


def iter_problem_json_files(data_dir: str | os.PathLike) -> list[Path]:
    dir_path = Path(data_dir)
    if not dir_path.exists() or not dir_path.is_dir():
        raise FileNotFoundError(f"data_path must be a directory, got: {data_dir}")

    files = []
    for p in dir_path.iterdir():
        if not p.is_file() or p.suffix.lower() != ".json":
            continue
        # Only numeric filenames like 1.json, 20.json
        if p.stem.isdigit():
            files.append(p)

    files.sort(key=lambda x: int(x.stem))
    return files

def build_prompt(task: str, C: str = "", parts: list[str] | None = None, model: str = ""):
    prompt_builder = get_prompt_builder()

    mp, mode = parse_task_mode(task)
    parts = parts or []

    if mode == "seperated":
        prompt = prompt_builder.seperated_prompt(parts=parts, model=model)
    elif mode == "synthesised":
        prompt = prompt_builder.synthesised_prompt(problem=C, model=model)
    else:
        raise ValueError(f"Unknown mode: {mode}")
    return prompt


def extract(response, task: str, model_company: str = "openai") -> dict:
    """
    根据模型类型提取响应内容和 token 使用信息
    
    Args:
        response: API 响应对象（OpenAI 或 Gemini 格式）
        task: 任务类型
        model_company: "openai" 或 "google"
    
    Returns:
        包含 content, input_token, total_token, reasoning_token, answer 的字典
    """
    
    # ===== OpenAI 格式 (字典格式) =====
    if model_company == "openai":
        # 响应是字典格式：{"choices": [{"message": {"content": "..."}}], "usage": {...}}
        # pdb.set_trace()
        if isinstance(response, dict):
            # 提取 content
            if "choices" in response and len(response["choices"]) > 0:
                choice = response["choices"][0]
                message = choice.get("message", {})
                content = message.get("content", "")
            else:
                content = ""
            
            # 提取 token 信息
            usage = response.get("usage", {}) or {}
            input_token = usage.get("prompt_tokens", usage.get("input_tokens", 0))
            total_token = usage.get("total_tokens", 0)
            completion_details = usage.get("completion_tokens_details") or {}
            reasoning_token = completion_details.get("reasoning_tokens", 0)
        else:
            # 兼容旧的对象格式（如果还有的话）
            input_token = response.usage.input_tokens
            total_token = response.usage.total_tokens
            reasoning_token = response.usage.output_tokens_details.reasoning_tokens
            content = response.output[1].content[0].text
    
    # ===== Gemini 格式 =====
    elif model_company == "google":
        # Gemini 的响应是个 dict，需要先判断是不是已经解析成对象
        if isinstance(response, dict):
            resp_dict = response
        else:
            # 如果是 JSON 字符串，先解析
            import json
            resp_dict = json.loads(response)
        
        # 提取 token 信息
        usage = resp_dict.get("usageMetadata", {})
        input_token = usage.get("promptTokenCount", 0)
        output_token = usage.get("candidatesTokenCount", 0)
        reasoning_token = usage.get("thoughtsTokenCount", 0)  # Gemini 的思考 token
        total_token = usage.get("totalTokenCount", 0)
        
        # 提取回复文本
        candidates = resp_dict.get("candidates", [])
        if candidates and len(candidates) > 0:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts and len(parts) > 0:
                content = parts[0].get("text", "")
            else:
                content = ""
        else:
            content = ""
    
    else:
        raise ValueError(f"Unknown model_company: {model_company}")
    
    mp, mode = parse_task_mode(task)

    if mode == "seperated":
        # 提取所有 answer_N 格式的答案，按数字顺序排序
        # 匹配 "answer_1": "...", "answer_2": "...", 等
        pattern = r'"answer_(\d+)"\s*:\s*"([^"]*)"'
        matches = re.findall(pattern, content)
        
        if matches:
            # 将匹配结果转换为 (索引, 答案) 的元组列表，并按索引排序
            answer_dict = {int(idx): ans for idx, ans in matches}
            # 按索引顺序提取答案
            max_idx = max(answer_dict.keys()) if answer_dict else 0
            answer = [answer_dict.get(i, "") for i in range(1, max_idx + 1)]
        else:
            answer = []
    else:
        m = re.search(r'"answer"\s*:\s*"([^"]*)"', content)
        answer = [m.group(1) if m else ""]
    
    # pdb.set_trace()

    return {
        "content": content,
        "input_token": input_token,
        "total_token": total_token,
        "reasoning_token": reasoning_token,
        "answer": answer
    }

def get_ground_truth(que: dict, task: str, connecting_point: list = []) -> list[str]:
    truth_list_tmp = que.get("Ground_Truth") or []
    truth_list = []
    mp, mode = parse_task_mode(task)
    for item in truth_list_tmp:
        if isinstance(item, dict):
            truth_list.append(list(item.values())[0])
        else:
            truth_list.append(item)
    
    conns = []
    # pdb.set_trace()
    if mode == "seperated" and connecting_point:
        for inner in connecting_point[0].values():
            for k in inner.keys():
                conns.append(k)
        
        for inx, conn in enumerate(conns):
            truth_list[inx] = conn
        
        return truth_list
    else:
        return truth_list

def extract_correctness(response) -> list[bool]:
    """
    从模型响应中提取 correctness 列表
    
    Args:
        response: API 响应对象（字典格式）
    
    Returns:
        布尔值列表，表示每个答案是否正确
    """
    if response is None:
        logger.warning("extract_correctness: response is None")
        return []
    
    try:
        # 从字典格式的响应中提取 content
        if isinstance(response, dict):
            if "choices" in response and len(response["choices"]) > 0:
                choice = response["choices"][0]
                message = choice.get("message", {})
                content = message.get("content", "")
            else:
                logger.warning("extract_correctness: no choices in response")
                return []
        else:
            # 兼容旧的对象格式（如果还有的话）
            if hasattr(response, 'output') and len(response.output) > 1:
                if hasattr(response.output[1], 'content') and len(response.output[1].content) > 0:
                    content = response.output[1].content[0].text
                elif isinstance(response.output[1], dict):
                    content_list = response.output[1].get("content", [])
                    if len(content_list) > 0:
                        content = content_list[0].get("text", "")
                    else:
                        logger.warning("extract_correctness: content list is empty")
                        return []
                else:
                    logger.warning(f"extract_correctness: unsupported response format: {type(response.output[1])}")
                    return []
            else:
                logger.warning("extract_correctness: response has no valid output structure")
                return []
        
        if not content:
            logger.warning("extract_correctness: extracted content is empty")
            return []
            
    except (AttributeError, IndexError, KeyError) as e:
        logger.error(f"Error extracting content from response: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return []
    
    # 使用正则表达式匹配 "correctness": [...] 中的列表内容
    pattern = r'"correctness"\s*:\s*\[([^\]]+)\]'
    match = re.search(pattern, content)
    
    if match:
        list_content = match.group(1)
        # 提取列表中的 true/false 值（按顺序提取）
        values = re.findall(r'true|false', list_content, re.IGNORECASE)
        # 转换为布尔值列表（保持原有顺序）
        result = [v.lower() == 'true' for v in values]
        logger.info(f"extract_correctness: found {len(result)} correctness values: {result}")
        return result
    
    # 如果正则匹配失败，尝试直接解析 JSON
    try:
        json_match = re.search(r'\{[^{}]*"correctness"[^{}]*\}', content, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            result = json.loads(json_str)
            correctness = result.get("correctness", [])
            if isinstance(correctness, list):
                result_bool = [bool(c) if isinstance(c, (bool, int)) else False for c in correctness]
                logger.info(f"extract_correctness: extracted from JSON: {result_bool}")
                return result_bool
    except Exception as e:
        logger.warning(f"extract_correctness: JSON parsing failed: {e}")
    
    logger.warning(f"extract_correctness: no correctness found in content (length: {len(content)})")
    logger.debug(f"extract_correctness: content preview: {content[:500]}")
    return []

def judge(answer: list[str], truth: list[str], task: str, seed: int = None) -> list[bool]:
    """
    判断答案是否正确
    
    Args:
        answer: 模型给出的答案列表
        truth: 正确答案列表
        task: 任务类型
        seed: 随机种子（用于 GPT-4o 判断的确定性）
    
    Returns:
        布尔值列表，表示每个答案是否正确
    """
    prompt_builder = get_prompt_builder()
    mp, mode = parse_task_mode(task)
    # pdb.set_trace()
    if mode == "synthesised":
        truth = [truth[-1]]
    prompt = prompt_builder.judge_prompt(answer=answer, truth=truth)
    client = get_client(model="gpt-4o")
    response = client.get_response_not_stream(prompt=prompt, seed=seed)
    
    if response is None:
        logger.warning("judge: response is None, returning empty list")
        return []
    
    correctness = extract_correctness(response=response)
    logger.info(f"judge: extracted correctness = {correctness}")
    # pdb.set_trace()
    return correctness


async def judge_async(answer: list[str], truth: list[str], task: str, seed: int = None) -> list[bool]:
    """judge 的异步版本，使用 get_response_not_stream_async 调用 GPT-4o。"""
    prompt_builder = get_prompt_builder()
    mp, mode = parse_task_mode(task)
    if mode == "synthesised":
        truth = [truth[-1]]
    prompt = prompt_builder.judge_prompt(answer=answer, truth=truth)
    client = get_client(model="gpt-4o")
    response = await client.get_response_not_stream_async(prompt=prompt, seed=seed)

    if response is None:
        logger.warning("judge_async: response is None, returning empty list")
        return []

    correctness = extract_correctness(response=response)
    if correctness == []:
        pdb.set_trace()
    logger.info(f"judge_async: extracted correctness = {correctness}")
    return correctness


def per_answer_judgements(answer_list: list[str], truth_list: list[str]) -> list[bool]:
    if len(answer_list) != len(truth_list):
        return [False for _ in range(max(len(answer_list), len(truth_list)))]
    return [a.strip() == t.strip() for a, t in zip(answer_list, truth_list)]


def to_type_label(level: str, task: str) -> str:
    mp, mode = parse_task_mode(task)
    # Normalize spelling for output label
    mode_label = "Separated" if mode == "seperated" else "Synthesised"
    return f"{level}_{mp}_{mode_label}_Evaluation"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_existing_outputs(output_dir: str) -> dict:
    existing = {}
    if not os.path.isdir(output_dir):
        return existing
    for fname in os.listdir(output_dir):
        if not fname.endswith(".json") or fname == "eval.json":
            continue
        fpath = os.path.join(output_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                record = json.load(f)
            pid = record.get("Problem_ID")
            if pid is not None:
                existing[int(pid)] = record
        except Exception as e:
            logger.warning(f"Failed to load cached result {fpath}: {e}")
    return existing 


def build_problem_type(que: dict) -> list[dict]:
    """Build `problem_type` in the requested shape.

    Expected shape is a list like:
      [ {"A2743": ["Mathematics -> ..."]}, {"A2746": ["Mathematics -> ..."]} ]

    If the source field is missing, returns [].
    """

    # Prefer a normalized mapping if present; otherwise keep existing field.
    src = que.get("Problem_Type")
    if isinstance(src, list):
        return src

    class_map = que.get("Class")
    if isinstance(class_map, dict):
        out: list[dict] = []
        for sub_id, paths in class_map.items():
            if paths is None:
                out.append({str(sub_id): []})
            elif isinstance(paths, list):
                out.append({str(sub_id): [str(p) for p in paths]})
            else:
                out.append({str(sub_id): [str(paths)]})
        return out

    return []


def compute_cost_cny(model: str, input_tokens: int, completion_tokens: int, reasoning_tokens: int) -> float:
    """Compute cost in CNY (¥) based on a price table.

    Current table (user provided):
    - gpt-5-thinking: input: ¥0.6250 / 1M tokens, output: ¥5.0000 / 1M tokens
    - gpt-5: input: ¥0.6250 / 1M tokens, output: ¥5.0000 / 1M tokens (假设与 gpt-5-thinking 相同)
    - gpt-4o: 需要根据实际价格表设置

    Note: `reasoning_tokens` are reported separately but are usually included in output;
    we do not bill them separately unless an explicit third price is provided.
    """

    model_key = (model or "").lower()
    
    # 价格表配置（每百万token的价格）
    price_table = {
        "gpt-5-thinking": {
            "input": 0.6250,
            "output": 5.0000
        },
        "gpt-5": {
            "input": 0.6250,
            "output": 5.0000
        },
        "gpt-4o": {
            "input": 0.6250,  # 需要根据实际价格调整
            "output": 5.0000   # 需要根据实际价格调整
        },
        "qwen-plus": {
            "input": 0.8,     # 0.0008 每千token = 0.8 每百万token
            "output": 8.0     # 0.008 每千token = 8.0 每百万token
        }
    }
    
    if model_key not in price_table:
        return 0.0
    
    prices = price_table[model_key]
    input_price_per_m = prices["input"]
    output_price_per_m = prices["output"]

    cost = (max(input_tokens, 0) / 1_000_000.0) * input_price_per_m + (
        max(completion_tokens, 0) / 1_000_000.0
    ) * output_price_per_m
    return float(cost)


def make_per_problem_evaluation_json(ques, extracted_data, truth_list, correctness,level: str, class_name: str, model: str, task: str) -> dict:
    mp, mode = parse_task_mode(task)
    type = f"{level}_{class_name}_{mode}_Evaluation"
    if mode == "seperated":
        math_problem = ques.get("Synthesised_By")
    else:
        math_problem = ques.get("Math_Problem")
    return {
        "timestamp":utc_timestamp(),
        "model": model,
        "type": type,
        "Problem_ID": ques.get("Problem_ID"),
        "math_problem": math_problem,
        "reasoning_content": extracted_data.get("content", ""),
        "problem_type": ques.get("Problem_Type"),
        "output_answer": extracted_data.get("answer", []),
        "ground_truth": truth_list,
        "correctness": correctness,
        "prompt_tokens": extracted_data.get("input_token", 0),
        "completion_tokens": extracted_data.get("total_token", 0) - extracted_data.get("input_token", 0),
        "reasoning_tokens": extracted_data.get("reasoning_token", 0),
        "cost": compute_cost_cny(model=model, input_tokens=extracted_data.get("input_token", 0), completion_tokens=extracted_data.get("total_token", 0) - extracted_data.get("input_token", 0), reasoning_tokens=extracted_data.get("reasoning_token", 0))
    }

async def process_single_problem_async(
    que: dict,
    client,
    judge_client,
    model: str,
    model_company: str,
    reasoning: str,
    level: str,
    class_name: str,
    task: str,
    output_path: str,
    seed: int = None,
    semaphore: asyncio.Semaphore = None,
) -> dict:
    """处理单个问题的完整异步流程：推理 → 提取答案 → 评判 → 保存结果。
    
    Returns:
        {"Problem_ID": int, "status": "ok"|"skipped", "correctness": list[bool]} 或出错时返回 skipped。
    """
    Problem_ID = que["Problem_ID"]
    result = {"Problem_ID": Problem_ID, "status": "skipped", "correctness": []}

    async with semaphore:
        # 1. 构建 prompt
        C = que.get("Math_Problem", "")
        parts = get_parts_in_order(que)
        try:
            prompt = build_prompt(task=task, C=C, parts=parts, model=model)
        except Exception as e:
            logger.error(f"[{Problem_ID}] Error building prompt: {e}")
            return result

        # 2. 调用模型推理（带重试，含 answer 为空时的重试）
        response = None
        extracted_data = None
        max_retry = 20
        for attempt in range(1, max_retry + 1):
            try:
                response = await client.get_response_async(prompt=prompt, reasoning=reasoning, seed=seed)
            except Exception as e:
                logger.error(f"[{Problem_ID}] Exception on attempt {attempt}: {e}")
                response = None

            if response is None:
                logger.warning(f"[{Problem_ID}] Empty response, retrying... {attempt}/{max_retry}")
                await asyncio.sleep(3)
                continue

            status_code = response.get("status_code", 0)
            if status_code == 429:
                logger.warning(f"[{Problem_ID}] Rate limited (429), retrying... {attempt}/{max_retry}")
                await asyncio.sleep(5)
                continue

            # 3. 提取答案，如果 answer 为空则重试
            try:
                extracted_data = extract(response=response, task=task, model_company=model_company)
                if not extracted_data or extracted_data.get("content") is None:
                    logger.warning(f"[{Problem_ID}] extracted_data is None or empty, retrying... {attempt}/{max_retry}")
                    await asyncio.sleep(2)
                    continue
                # 检查 answer 是否为空（空列表、或列表中只有空字符串）
                answer = extracted_data.get("answer", [])
                if not answer or answer == [""] or answer == []:
                    logger.warning(f"[{Problem_ID}] answer is empty after extraction, retrying... {attempt}/{max_retry}")
                    await asyncio.sleep(2)
                    continue
            except Exception as e:
                logger.error(f"[{Problem_ID}] Error extracting on attempt {attempt}: {e}")
                await asyncio.sleep(2)
                continue

            break  # 成功拿到响应且 answer 非空

        if response is None or extracted_data is None:
            logger.error(f"[{Problem_ID}] Failed after {max_retry} retries")
            return result

        # 再次确认 answer
        answer_check = extracted_data.get("answer", [])
        if not answer_check or answer_check == [""] or answer_check == []:
            logger.error(f"[{Problem_ID}] answer still empty after {max_retry} retries")
            return result
        # 4. 获取标准答案 & 评判
        try:
            connecting_point = que.get("Connecting_Point", [])
            truth_list = get_ground_truth(que=que, task=task, connecting_point=connecting_point)

            answer_list = extracted_data.get("answer", [])
            if not isinstance(answer_list, list):
                answer_list = [str(answer_list)]

            correctness = await judge_async(answer=answer_list, truth=truth_list, task=task, seed=seed)
            if not correctness:
                logger.error(f"[{Problem_ID}] judge returned empty correctness")
                return result
        except Exception as e:
            logger.error(f"[{Problem_ID}] Error judging: {e}")
            return result

        # 5. 构建并保存结果
        try:
            per_problem_json = make_per_problem_evaluation_json(
                ques=que, extracted_data=extracted_data, truth_list=truth_list,
                correctness=correctness, level=level, class_name=class_name,
                model=model, task=task,
            )
            out_file = os.path.join(output_path, f"{Problem_ID}.json")
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(per_problem_json, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[{Problem_ID}] Error saving result: {e}")
            return result

    logger.info(f"[{Problem_ID}] Done for {level}/{class_name}")
    result["status"] = "ok"
    result["correctness"] = correctness
    return result


async def main_async(
    model: str,
    reasoning: str,
    level: str,
    class_name: str,
    task: str,
    data_path: str,
    output_path: str,
    specific_list,
    write_run_summary: bool = False,
    seed: int = None,
    concurrency: int = 5,
):
    """main 的并发版本，使用 asyncio 并发处理问题。"""
    client = get_client(model=model)
    judge_client = get_client(model="gpt-4o")
    model_company = MODELS_COMPANIES_MAP.get(model, "openai")

    try:
        problem_files = iter_problem_json_files(data_path)
    except Exception as e:
        logger.error(f"Error listing json files under {data_path}: {e}")
        return

    os.makedirs(output_path, exist_ok=True)
    cached_outputs = load_existing_outputs(output_path)
    finished_ids = set(cached_outputs.keys())

    specific_ids = None
    if specific_list is not None and len(specific_list) > 0:
        specific_ids = set(int(id) for id in specific_list)
        logger.info(f"Processing only specific Problem_IDs: {sorted(specific_ids)}")

    # 加载所有待处理的问题
    pending_questions = []
    for json_path in problem_files:
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                que = json.load(f)
        except Exception as e:
            logger.error(f"Error loading {json_path}: {e}")
            continue

        pid = que.get("Problem_ID")
        if pid is None:
            continue
        if specific_ids is not None and pid not in specific_ids:
            continue
        if pid in finished_ids:
            logger.info(f"Skipping Problem_ID {pid} (already processed).")
            continue
        pending_questions.append(que)

    if not pending_questions:
        logger.info("No pending problems to process.")
        return

    logger.info(f"Pending: {len(pending_questions)} problems, concurrency: {concurrency}")

    semaphore = asyncio.Semaphore(concurrency)

    tasks_list = [
        process_single_problem_async(
            que=que, client=client, judge_client=judge_client,
            model=model, model_company=model_company,
            reasoning=reasoning, level=level, class_name=class_name,
            task=task, output_path=output_path, seed=seed,
            semaphore=semaphore,
        )
        for que in pending_questions
    ]

    results = await asyncio.gather(*tasks_list, return_exceptions=True)

    # 统计结果
    ok_count = 0
    fail_count = 0
    for r in results:
        if isinstance(r, Exception):
            logger.error(f"Task raised exception: {r}")
            fail_count += 1
        elif r.get("status") == "ok":
            ok_count += 1
        else:
            fail_count += 1

    logger.info(f"Completed: {ok_count} ok, {fail_count} failed/skipped, total {len(results)}")


def main(
    model: str,
    reasoning: str,
    level: str,
    class_name: str,
    task: str,
    data_path: str,
    output_path: str,
    specific_list,
    write_run_summary: bool = False,
    seed: int = None,
):
    client = get_client(model=model)
    model_company = MODELS_COMPANIES_MAP.get(model, "openai")
    try:
        problem_files = iter_problem_json_files(data_path)
    except Exception as e:
        logger.error(f"Error listing json files under {data_path}: {e}")
        return

    # Ensure output directory exists before writing per-problem JSON files.
    os.makedirs(output_path, exist_ok=True)
    # 解析 task 获取 mode (Synthesised 或 Seperated)
    mp, mode = parse_task_mode(task)
    # 在 class_name 下添加 mode 层级
    cached_outputs = load_existing_outputs(output_path)
    finished_ids = set(cached_outputs.keys())
    
    # 如果提供了 specific_list，转换为集合以便快速查找
    specific_ids = None
    if specific_list is not None and len(specific_list) > 0:
        specific_ids = set(int(id) for id in specific_list)
        logger.info(f"Processing only specific Problem_IDs: {sorted(specific_ids)}")
    
    input_token = sum(item.get("input_token", 0) for item in cached_outputs.values())
    correct_count = sum(1 for item in cached_outputs.values() if item.get("correctness"))
    total_count = len(cached_outputs)
    total_reasoning_token = sum(item.get("reasoning_token", 0) for item in cached_outputs.values())
    total_model_token = sum(item.get("total_token", 0) for item in cached_outputs.values())
    skipped_id = []

    # Note: user requested NO global evaluation file; per-problem only.
    
    
    #主循环处理每个问题
    for json_path in tqdm(problem_files):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                que = json.load(f)
        except Exception as e:
            logger.error(f"Error loading problem json {json_path}: {e}")
            continue

        output ={}
        C = que.get("Math_Problem", "")
        parts = get_parts_in_order(que)
        Problem_ID = que["Problem_ID"]
        
        # 如果提供了 specific_list，只处理列表中的 ID
        if specific_ids is not None and Problem_ID not in specific_ids:
            logger.info(f"Skipping Problem_ID {Problem_ID} (not in specific_list).")
            continue
        
        if Problem_ID in finished_ids:
            logger.info(f"Skipping Problem_ID {Problem_ID} (already processed).")
            continue
        
        try:
            prompt = build_prompt(task=task, C=C, parts=parts, model=model)
        except Exception as e:
            logger.error(f"Error building prompt for Problem_ID {Problem_ID}: {e}")
            skipped_id.append(Problem_ID)
            continue
        
        try:
            max_retry = 20
            i = 1
            extracted_data = None
            while i <= max_retry:
                response = client.get_response(prompt=prompt, reasoning=reasoning, seed=seed)
                # 检查 response 是否为 None（可能是 429 或其他错误）
                if response is None:
                    logger.warning(f"Empty response for Problem_ID {Problem_ID}, retrying... {i}/{max_retry}")
                    time.sleep(5)
                    i += 1
                    continue
                
                # 检查是否有 status_code 字段（某些错误响应可能包含）
                status_code = response.get("status_code", 0)
                if status_code == 429:
                    logger.warning(f"Rate limit exceeded for Problem_ID {Problem_ID}, retrying... {i}/{max_retry}")
                    time.sleep(5)
                    i += 1
                    continue

                # 提取答案，如果 answer 为空则重试
                try:
                    extracted_data = extract(response=response, task=task, model_company=model_company)
                    if not extracted_data or extracted_data.get("content") is None:
                        logger.warning(f"extracted_data is None for Problem_ID {Problem_ID}, retrying... {i}/{max_retry}")
                        time.sleep(3)
                        i += 1
                        continue
                    answer_tmp = extracted_data.get("answer", [])
                    if not answer_tmp or answer_tmp == [""] or answer_tmp == []:
                        logger.warning(f"answer is empty for Problem_ID {Problem_ID}, retrying... {i}/{max_retry}")
                        time.sleep(3)
                        i += 1
                        continue
                except Exception as e:
                    logger.error(f"Error extracting for Problem_ID {Problem_ID}: {e}")
                    time.sleep(3)
                    i += 1
                    continue

                break  # 成功拿到响应且 answer 非空

        except Exception as e:
            logger.error(f"Error getting response for Problem_ID {Problem_ID}: {e}")
            skipped_id.append(Problem_ID)
            continue

        if response is None or extracted_data is None:
            logger.error(f"Failed for Problem_ID {Problem_ID} after retries")
            skipped_id.append(Problem_ID)
            continue
        
        # 再次确认 answer
        answer_final_check = extracted_data.get("answer", [])
        if not answer_final_check or answer_final_check == [""] or answer_final_check == []:
            logger.error(f"answer still empty for Problem_ID {Problem_ID} after {max_retry} retries")
            skipped_id.append(Problem_ID)
            continue
        
        try:
            groud_truth = que.get("Ground_Truth", [])
            conneccting_point = que.get("Connecting_Point", [])
            groud_truth_list: list[str] = []
            if isinstance(groud_truth, list):
               for item in groud_truth:
                    if isinstance(item, dict):
                        groud_truth_list.extend(str(v) for v in item.values())
                    else:
                        groud_truth_list.append(str(item))

            truth_list = get_ground_truth(que=que, task=task, connecting_point=conneccting_point)
            logger.info(f"Ground truth for Problem_ID {Problem_ID}: {truth_list}")

            answer_list = extracted_data.get("answer", [])
            if not isinstance(answer_list, list):
                answer_list = [str(answer_list)]
            
            try:
                correctness = judge(answer=answer_list, truth=truth_list, task=task, seed=seed)
                if not correctness:
                    logger.error(f"Error judging correctness for Problem_ID {Problem_ID}: correctness is empty")
                    skipped_id.append(Problem_ID)
                    continue
            except Exception as e:
                logger.error(f"Error judging correctness for Problem_ID {Problem_ID}: {e}")
                skipped_id.append(Problem_ID)
                continue
        except Exception as e:
            logger.error(f"Error judging correctness for Problem_ID {Problem_ID}: {e}")
            skipped_id.append(Problem_ID)
            continue
        
        try:
            per_problem_json = make_per_problem_evaluation_json(ques=que, extracted_data=extracted_data, truth_list=truth_list, correctness=correctness, level=level, class_name=class_name, model=model, task=task)
        except Exception as e:
            logger.error(f"Error making per problem evaluation json for Problem_ID {Problem_ID}: {e}")
            skipped_id.append(Problem_ID)
            continue

        
        with open(f"{output_path}/{Problem_ID}.json", "w", encoding="utf-8") as f:
            json.dump(per_problem_json, f, ensure_ascii=False, indent=2)
        finished_ids.add(Problem_ID)
            
        logger.info(f"✅️{Problem_ID} for level {level} class {class_name}.")
    
    logger.info(f"Completed processing for level {level} class {class_name} with model {model}.")
    
    if write_run_summary:
        accuracy = correct_count / total_count if total_count > 0 else 0
        eval = {
            "accuracy": accuracy,
            "correct_count": correct_count,
            "total_count": total_count,
            "total_reasoning_token": total_reasoning_token,
            "total_input_token": input_token,
            "total_model_token": total_model_token,
            "skipped_id": skipped_id,
        }
        logger.info(f"Accuracy for level {level} class {class_name} with model {model}: {accuracy:.4f}")
        os.makedirs(output_path, exist_ok=True)
        with open(f"{output_path}/eval.json", "w", encoding="utf-8") as f:
            json.dump(eval, f, ensure_ascii=False, indent=2)
        logger.info(f"Run summary saved to {output_path}/eval.json")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Run inference on math problems")
    parser.add_argument("model", type=str, help="Model name")
    parser.add_argument("reasoning", type=str, help="Reasoning parameter")
    parser.add_argument("level", type=str, help="Level (e.g., T1, T2)")
    parser.add_argument("class_name", type=str, help="Class name (e.g., MP2)")
    parser.add_argument("task", type=str, help="Task (e.g., MP2_Seperated)")
    parser.add_argument("data_path", type=str, help="Path to data directory")
    parser.add_argument("output_path", type=str, help="Path to output directory")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for model sampling")
    parser.add_argument("--specific_list", type=str, default=None, help="JSON list of specific Problem_IDs")
    parser.add_argument("--use_async", action="store_true", help="Use async concurrent mode")
    parser.add_argument("--concurrency", type=int, default=5, help="Max concurrent requests (only for async mode)")
    
    args = parser.parse_args()
    
    # 解析 specific_list
    specific_list = None
    if args.specific_list:
        try:
            specific_list = json.loads(args.specific_list)
            if not isinstance(specific_list, list):
                logger.warning(f"specific_list should be a list, got {type(specific_list)}. Ignoring.")
                specific_list = None
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse specific_list as JSON: {e}. Ignoring.")
            specific_list = None
    
    if args.use_async:
        if platform.system() == "Windows":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main_async(
            model=args.model,
            reasoning=args.reasoning,
            level=args.level,
            class_name=args.class_name,
            task=args.task,
            data_path=args.data_path,
            output_path=args.output_path,
            specific_list=specific_list,
            write_run_summary=False,
            seed=args.seed,
            concurrency=args.concurrency,
        ))
    else:
        main(
            model=args.model,
            reasoning=args.reasoning,
            level=args.level,
            class_name=args.class_name,
            task=args.task,
            data_path=args.data_path,
            output_path=args.output_path,
            specific_list=specific_list,
            write_run_summary=False,
            seed=args.seed,
        )