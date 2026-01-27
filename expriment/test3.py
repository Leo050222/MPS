import http.client
import json
import urllib.parse

# API 配置
API_KEY = "sk-qyq6QZ5Of8zKMgVaZhHMc470DCUF4OLBF2cSqp5XHXfB02Z3"
MODEL_NAME = "gemini-3-pro-preview"
HOST = "152.53.83.72"
PORT = 9998

# 构建请求体
payload = json.dumps({
    "contents": [
        {
            "role": "user",
            "parts": [
                {
                    "text": "如何哄女朋友开心？"
                }
            ]
        }
    ]
}, ensure_ascii=False)

# 尝试多种认证方式
auth_methods = [
    {
        "name": "方式1: Query 参数（URL编码）",
        "headers": {'Content-Type': 'application/json'},
        "path": f"/v1beta/models/{MODEL_NAME}:generateContent?key={urllib.parse.quote(API_KEY)}"
    },
    {
        "name": "方式2: Query 参数（不编码）",
        "headers": {'Content-Type': 'application/json'},
        "path": f"/v1beta/models/{MODEL_NAME}:generateContent?key={API_KEY}"
    },
    {
        "name": "方式3: Authorization Header（直接key）",
        "headers": {
            'Content-Type': 'application/json',
            'Authorization': API_KEY
        },
        "path": f"/v1beta/models/{MODEL_NAME}:generateContent"
    },
    {
        "name": "方式4: Authorization Header（Bearer格式）",
        "headers": {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {API_KEY}'
        },
        "path": f"/v1beta/models/{MODEL_NAME}:generateContent"
    }
]

# 尝试每种方式
for method in auth_methods:
    print(f"\n{'='*60}")
    print(f"尝试: {method['name']}")
    print(f"{'='*60}")
    
    try:
        # 创建新的连接
        conn = http.client.HTTPConnection(HOST, PORT)
        
        print(f"请求 URL: http://{HOST}:{PORT}{method['path']}")
        print(f"请求头: {method['headers']}")
        
        conn.request("POST", method['path'], payload.encode('utf-8'), method['headers'])
        res = conn.getresponse()
        data = res.read()
        
        response_text = data.decode("utf-8")
        print(f"\n状态码: {res.status}")
        
        if res.status == 200:
            print("✅ 成功！")
            print("\n响应内容:")
            try:
                response_json = json.loads(response_text)
                print(json.dumps(response_json, indent=2, ensure_ascii=False))
            except json.JSONDecodeError:
                print(response_text)
            conn.close()
            break  # 成功则退出循环
        else:
            print(f"❌ 失败: {response_text[:200]}")
            try:
                error_json = json.loads(response_text)
                print(json.dumps(error_json, indent=2, ensure_ascii=False))
            except:
                pass
        conn.close()
        
    except Exception as e:
        print(f"❌ 请求出错: {e}")
        try:
            conn.close()
        except:
            pass
else:
    print("\n所有认证方式都失败了，请检查 API key 是否正确")