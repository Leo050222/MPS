import http.client
import json
import ssl
import time
# 创建未验证的 SSL 上下文（解决证书验证问题）
context = ssl._create_unverified_context()

conn = http.client.HTTPSConnection("chrisapius.top", context=context)
payload = json.dumps({
   "model": "gpt-5.1-medium",
   "messages": [
      {
         "role": "system",
         "content": "you are a helpful assistant."
      },
      {
         "role": "user",
         "content": "帮我推导一下正整数n的阶乘的公式"
      }
   ]
})


headers = {
   'Content-Type': 'application/json',
   'Authorization': 'Bearer sk-KaTunSTD1e8eWpPN67kABCGEZzqz3yg8mXSRYVHPWEipIIpG'
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
   conn.close()