import http.client
import json
import ssl
import time
import os

conn = http.client.HTTPSConnection("yunwu.ai")

payload_dict = {
   "model": "claude-sonnet-4-5-20250929-thinking",
   "messages": [
      {
         "role": "system",
         "content": "you are a helpful assistant."
      },
      {
         "role": "user",
         "content": "Find all functions $f: \\mathbb{R}^+ \\to \\mathbb{R}^+$ such that \n$$(z + 1)f(x + y) = f(xf(z) + y) + f(yf(z) + x),$$\nfor all positive real numbers $x, y, z$. Instead of determining all positive functions satisfying the given functional equation, simply find $m = c - 1$, where $c$ is the proportionality constant in the linear function that satisfies the equation. Determine all functions $f: \\mathbb{R} \\to \\mathbb{R}$ such that \n$$ f(x^(m + 3)) + f(y)^(m + 3) + f(z)^(m + 3) = (m + 3)xyz $$\nfor all real numbers $x$, $y$ and $z$ with $x+y+z=m$."
      }
   ],
   "thinking": {
      "type": "enabled",
      "budget_tokens": 1200
   }
}

payload = json.dumps(payload_dict)


headers = {
   'Content-Type': 'application/json',
   'Authorization': f"Bearer sk-qzdMKpiMSg7ued5SujXQkzB8Mqnli2T8HyMI6MjAfTCmrP6q"  
}

try:
   conn.request("POST", "/v1/chat/completions", payload, headers)
   # import pdb
   # pdb.set_trace()
   res = conn.getresponse()
   data = res.read()
   print(data.decode("utf-8"))
   
except Exception as e:
   print(f"Error: {e}")
   import traceback
   traceback.print_exc()
finally:
   try:
      conn.close()
   except Exception:
      pass