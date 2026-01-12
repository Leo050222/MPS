import http.client
import json
import ssl

# 如果你现在还在 SSL mismatch，就先用这个 ctx（仅调试）
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE  # ⚠️

conn = http.client.HTTPSConnection("chrisapius.top", context=ctx)

payload = json.dumps({
    "model": "gpt-4.1",
    "messages": [
        {"role": "system", "content": "你是一个有帮助的助手。"},
        {"role": "user", "content": "从开始到结束完整的构建推理等差数列求和公式，把我当傻子，并且给出3个例子"}
    ],
    "stream": True,
    "stream_options": {"include_usage": True}
})

headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer sk-KaTunSTD1e8eWpPN67kABCGEZzqz3yg8mXSRYVHPWEipIIpG",
    "Accept": "text/event-stream",
}

conn.request("POST", "/v1/chat/completions", payload, headers)
res = conn.getresponse()

print("STATUS:", res.status, res.reason)
print("HEADERS:", res.getheaders())

# 逐行读取 SSE
while True:
    line = res.readline()
    if not line:
        break

    line = line.decode("utf-8", errors="ignore").strip()
    if not line:
        continue

    # 打印每一个“数据包”（SSE 行）
    print("SSE:", line)

    if line == "data: [DONE]":
        break

    if line.startswith("data: "):
        data_str = line[len("data: "):]
        try:
            obj = json.loads(data_str)
            # 可选：打印增量文本
            delta = obj.get("choices", [{}])[0].get("delta", {}).get("content")
            if delta:
                import time; now = time.time()
                print("DELTA_TEXT:", delta, "TIME:", now)
            # 可选：最后 usage（如果 include_usage 生效，通常会在最后一个 data chunk 里出现）
            if obj.get("usage"):
                print("USAGE:", obj["usage"])
        except json.JSONDecodeError:
            pass
