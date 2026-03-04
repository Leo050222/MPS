import http.client
import json
import ssl
import time
import os

conn = http.client.HTTPSConnection("yunwu.ai")

payload_dict = {
   "model": "gemini-3-pro-preview-thinking",
   "stream": True,
   "stream_options": {"include_usage": True},
   "messages": [
      {
         "role": "system",
         "content": "you are a helpful assistant."
      },
      {
         "role": "user",
         "content": "Find all functions $f: \\mathbb{R}^+ \\to \\mathbb{R}^+$ such that \n$$(z + 1)f(x + y) = f(xf(z) + y) + f(yf(z) + x),$$\nfor all positive real numbers $x, y, z$. Instead of determining all positive functions satisfying the given functional equation, simply find $m = c - 1$, where $c$ is the proportionality constant in the linear function that satisfies the equation. Determine all functions $f: \\mathbb{R} \\to \\mathbb{R}$ such that \n$$ f(x^(m + 3)) + f(y)^(m + 3) + f(z)^(m + 3) = (m + 3)xyz $$\nfor all real numbers $x$, $y$ and $z$ with $x+y+z=m$."
      }
   ]
   # ],
   # "thinking": {
   #    "type": "enabled",
   #    "budget_tokens": 1200
   # }
}

payload = json.dumps(payload_dict)


headers = {
   'Content-Type': 'application/json',
   'Authorization': f"Bearer sk-Tw2ztDrUfDYTLLGJ16n0UieZrNJ7XTM03O2mU0w5rh8e0uma"  
}

try:
   conn.request("POST", "/v1/chat/completions", payload, headers)
   res = conn.getresponse()
   usage = None
   for raw_line in res:
      line = raw_line.decode("utf-8").strip()
      if not line.startswith("data: "):
         continue
      data_str = line[6:]
      if data_str == "[DONE]":
         break
      try:
         chunk = json.loads(data_str)
         if chunk.get("usage"):
            usage = chunk["usage"]
         if not chunk.get("choices"):
            continue
         delta = chunk["choices"][0]["delta"]
         # deepseek thinking 模式会先输出 reasoning_content，再输出 content
         if delta.get("reasoning_content"):
            print(delta["reasoning_content"], end="", flush=True)
         if delta.get("content"):
            print(delta["content"], end="", flush=True)
      except (json.JSONDecodeError, KeyError):
         pass
   print()
   if usage:
      print(f"\n[Usage] prompt={usage.get('prompt_tokens')} completion={usage.get('completion_tokens')} total={usage.get('total_tokens')}")
   
except Exception as e:
   print(f"Error: {e}")
   import traceback
   traceback.print_exc()
finally:
   try:
      conn.close()
   except Exception:
      pass