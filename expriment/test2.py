import http.client
import json
import ssl
import time

conn = http.client.HTTPConnection("152.53.208.62", 9000)
payload = json.dumps({
   "model": "gpt-5.1",
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
   'Authorization': 'Bearer sk-2XZ7ioYdwHQslVr8hUf1NO4RC15JYy3O6d9gIwX8fFNo7aWT'
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