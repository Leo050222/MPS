import http.client
import json
import ssl
import socket

try:
    # 创建未验证的 SSL 上下文（解决证书验证问题）
    context = ssl._create_unverified_context()
    
    # 添加超时设置（30秒）
    conn = http.client.HTTPSConnection("chrisapius.top", context=context, timeout=30)
    
    payload = json.dumps({
       "model": "gpt-5.1",
       "messages": [
          {
             "role": "system",
             "content": "你是一个有帮助的助手。"
          },
          {
             "role": "user",
             "content": "你能做什么？"
          }
       ]
    })
    headers = {
       'Content-Type': 'application/json',
       'Authorization': 'Bearer sk-2XZ7ioYdwHQslVr8hUf1NO4RC15JYy3O6d9gIwX8fFNo7aWT'
    }
    
    print("正在连接服务器...")
    conn.request("POST", "/v1/chat/completions", payload, headers)
    print("已发送请求，等待响应...")
    
    res = conn.getresponse()
    status_code = res.status
    data = res.read()
    conn.close()
    
    if status_code != 200:
        print(f"错误: HTTP 状态码 {status_code}")
        print(data.decode("utf-8", errors='ignore'))
    else:
        print("响应成功:")
        print(data.decode("utf-8"))
        
except socket.timeout:
    print("错误: 连接超时 - 服务器没有响应")
    print("可能的原因:")
    print("1. 网络连接问题")
    print("2. 服务器暂时不可用")
    print("3. 防火墙阻止了连接")
    try:
        conn.close()
    except:
        pass
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
    try:
        conn.close()
    except:
        pass