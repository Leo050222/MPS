import http.client
import json
import ssl

# 创建未验证的 SSL 上下文（解决证书验证问题）
context = ssl._create_unverified_context()

conn = http.client.HTTPSConnection("chrisapius.top", context=context)
payload = json.dumps({
   "model": "gpt-5",
   "messages": [
      {
         "role": "system",
         "content": "你是一个有帮助的助手。"
      },
      {
         "role": "user",
         "content": "Six men and their wives are sitting at a round table with 12 seats. These men and women are very jealous - no man will allow his wife to sit next to any man except for himself, and no woman will allow her husband to sit next to any woman except for herself. In how many distinct ways can these 12 people be seated such that these conditions are satisfied? Instead of determining the total number of distinct valid seating arrangements under the jealousy conditions, simply find $k = N_3 - 2879$, where $N_3$ is the number of such arrangements in the configuration consisting of six alternating blocks of exactly two persons of the same gender each, derived from the block decomposition analysis of the seating constraints. Find the value of $\\frac{k}{3^{2}+1}+\\frac{k}{4^{2}+2}+\\frac{k}{5^{2}+3}+\\cdots$."
      }
   ]
})
headers = {
   'Content-Type': 'application/json',
   'Authorization': 'Bearer sk-2XZ7ioYdwHQslVr8hUf1NO4RC15JYy3O6d9gIwX8fFNo7aWT'
}
conn.request("POST", "/v1/chat/completions", payload, headers)
res = conn.getresponse()
data = res.read()
print(data.decode("utf-8"))