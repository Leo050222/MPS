import http.client
import json
import ssl
import time

conn = http.client.HTTPConnection("152.53.208.62", 9000)
payload = json.dumps({
   "model": "grok-4-1-fast-reasoning",
   "messages": [
      {
         "role": "system",
         "content": "you are a helpful assistant."
      },
      {
         "role": "user",
         "content": "Let $ (a_{n}) $ be the sequence of reals defined by $ a_{1}=\\frac{1}{4} $ and the recurrence $ a_{n}= \\frac{1}{4}(1+a_{n-1})^{2}, n\\geq 2 $. Find the minimum real $ \\lambda $ such that for any non-negative reals $ x_{1},x_{2},\\dots,x_{2002} $, it holds\n\\[ \\sum_{k=1}^{2002}A_{k}\\leq \\lambda a_{2002}, \\]\nwhere $  A_{k}= \\frac{x_{k}-k}{(x_{k}+\\cdots+x_{2002}+\\frac{k(k-1)}{2}+1)^{2}}, k\\geq 1 $. Instead of determining the infimal constant that majorizes the aggregate of the deviation terms normalized by cumulative sums plus quadratic offsets in terms of the terminal sequence value for all non-negative inputs, simply find $\\delta = t - \\frac{4003}{2}$, where $t$ is the cardinality of the collection of non-negative real variables. Determine all functions $f: \\mathbb{Q} \\to \\mathbb{Q}$ such that\n$$f(2xy + \\delta) + f(x-y) = 4f(x)f(y) + \\delta$$\nfor all $x,y \\in \\mathbb{Q}$."
      }
   ]
})


headers = {
   'Content-Type': 'application/json',
   'Authorization': 'Bearer sk-D1RZX1sf3oIhkqCN3ac0Tibws1a1RzK5FyiVtl2Xd2a5GlXe'
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