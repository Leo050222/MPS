"""测试异步客户端接口是否正常工作"""
import asyncio
import json
import platform
import sys
import time

from client.client import get_client


async def test_qwen_async():
    """测试 qwenClient.get_response_async"""
    print("=" * 60)
    print("[TEST 1] qwenClient.get_response_async (qwen-plus)")
    print("=" * 60)

    client = get_client(model="qwen-plus")
    prompt = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "1+1等于几？只回答数字。"},
    ]

    start = time.perf_counter()
    response = await client.get_response_async(
        prompt=prompt,
        reasoning=False,  # 不开 thinking，快一点
        seed=42,
    )
    elapsed = time.perf_counter() - start

    if response is None:
        print("[FAIL] response is None")
        return False

    # 检查关键字段
    content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
    usage = response.get("usage", {})
    prompt_tokens = usage.get("prompt_tokens", 0)
    total_tokens = usage.get("total_tokens", 0)
    reasoning_tokens = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0)

    print(f"  content       : {content[:200]}")
    print(f"  prompt_tokens : {prompt_tokens}")
    print(f"  total_tokens  : {total_tokens}")
    print(f"  reasoning_tkns: {reasoning_tokens}")
    print(f"  elapsed       : {elapsed:.2f}s")

    ok = bool(content) and prompt_tokens > 0
    print(f"  result        : {'PASS' if ok else 'FAIL'}")
    return ok


async def test_gpt4o_async():
    """测试 BaseClient.get_response_not_stream_async (gpt-4o, judge 用)"""
    print()
    print("=" * 60)
    print("[TEST 2] gpt4oClient.get_response_not_stream_async (gpt-4o)")
    print("=" * 60)

    client = get_client(model="gpt-4o")
    prompt = [
        {"role": "system", "content": "You are a math answer checker."},
        {"role": "user", "content": '判断 42 和 42.0 是否等价，回答 {"correctness": [true]} 或 {"correctness": [false]}'},
    ]

    start = time.perf_counter()
    response = await client.get_response_not_stream_async(
        prompt=prompt,
        reasoning="minimal",
        seed=42,
    )
    elapsed = time.perf_counter() - start

    if response is None:
        print("[FAIL] response is None")
        return False

    content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
    usage = response.get("usage", {})
    prompt_tokens = usage.get("prompt_tokens", 0)
    total_tokens = usage.get("total_tokens", 0)

    print(f"  content       : {content[:200]}")
    print(f"  prompt_tokens : {prompt_tokens}")
    print(f"  total_tokens  : {total_tokens}")
    print(f"  elapsed       : {elapsed:.2f}s")

    ok = bool(content) and prompt_tokens > 0
    print(f"  result        : {'PASS' if ok else 'FAIL'}")
    return ok


async def test_qwen_concurrency():
    """测试 qwen-plus 并发调用（3 个请求同时发出）"""
    print()
    print("=" * 60)
    print("[TEST 3] qwen-plus 并发 3 个请求")
    print("=" * 60)

    client = get_client(model="qwen-plus")
    questions = [
        "2+3等于几？只回答数字。",
        "7*8等于几？只回答数字。",
        "100/4等于几？只回答数字。",
    ]

    async def single_call(q: str, idx: int):
        prompt = [{"role": "user", "content": q}]
        start = time.perf_counter()
        resp = await client.get_response_async(prompt=prompt, reasoning=False, seed=42)
        elapsed = time.perf_counter() - start
        content = ""
        if resp:
            content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        print(f"  [{idx}] {q:<30} -> {content[:50]:<20} ({elapsed:.2f}s)")
        return resp is not None

    start_all = time.perf_counter()
    results = await asyncio.gather(*[single_call(q, i) for i, q in enumerate(questions)])
    total_elapsed = time.perf_counter() - start_all

    all_ok = all(results)
    print(f"  total elapsed : {total_elapsed:.2f}s (并发)")
    print(f"  result        : {'PASS' if all_ok else 'FAIL'}")
    return all_ok


async def main():
    results = []

    r1 = await test_qwen_async()
    results.append(("qwen_async", r1))

    r2 = await test_gpt4o_async()
    results.append(("gpt4o_async", r2))

    r3 = await test_qwen_concurrency()
    results.append(("qwen_concurrency", r3))

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, ok in results:
        print(f"  {name:<25}: {'PASS' if ok else 'FAIL'}")

    all_pass = all(ok for _, ok in results)
    print(f"\n  Overall: {'ALL PASS' if all_pass else 'SOME FAILED'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    if platform.system() == "Windows":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
