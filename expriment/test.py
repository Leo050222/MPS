import http.client
import json

conn = http.client.HTTPSConnection("chrisapius.top")
payload = json.dumps({
   "contents": [
      {
         "role": "user",
         "parts": [
            {
               "text": "Consider four positive real numbers \\(x_1, x_2, x_3, x_4\\) satisfying the equation\n\\[\nx_1 + x_2 + x_3 + x_4 = 48\n\\]\nand the relations\n\\[\nx_1 + 3 = x_2 - 3 = 3x_3 = \\frac{x_4}{3}.\n\\]\nLet \\(N = x_4 + 1988\\).\n\nThe set of ordered pairs of positive integers \\((i, j)\\) is enumerated by first ordering them according to increasing values of the sum \\(s = i + j \\geq 2\\), and within each fixed \\(s\\), ordering by increasing \\(i\\) from 1 to \\(s-1\\) (with \\(j = s - i\\)). This enumeration assigns the positive integers starting from 1 consecutively to the pairs in this order. Let \\(n(i, j)\\) denote the position assigned to the pair \\((i, j)\\).\n\nDetermine the values of \\(i\\) and \\(j\\) such that \\(n(i, j) = N\\)"
            }
         ]
      }
   ],
   "generationConfig": {
       # 其他参数随需要加，这里只演示 thinkingBudget
       "thinkingConfig": {
           "includeThoughts": False,      # 要不要把思考内容返回给你（如果接口支持）
           "thinkingBudget": 0         # 思考 token 数，比如 256、512、1024
       }
   }
})
headers = {
   'Authorization': 'sk-83BacHuBgJAcd5GJX5GxDLOctAD52jRxrAZKRmf3GbtrMMLW',
   'Content-Type': 'application/json'
}
conn.request("POST", "/v1beta/models/gemini-2.5-flash:generateContent", payload, headers)
res = conn.getresponse()
data = res.read()
print(data.decode("utf-8"))