import http.client
import json
import ssl
import time
context = ssl._create_unverified_context()
conn = http.client.HTTPSConnection("chrisapius.top", context=context)
payload = json.dumps({
   "model": "gpt-5",
   "messages": [
      {
         "role": "user",
         "content": "你是一个有帮助的助手。"
      },
      {
         "role": "user",
         "content": "你好！"
      }
   ],
   "stream": True
})
headers = {
   'Content-Type': 'application/json',
   'Authorization': 'Bearer sk-KaTunSTD1e8eWpPN67kABCGEZzqz3yg8mXSRYVHPWEipIIpG'
}
conn.request("POST", "/v1/chat/completions", payload, headers)
res = conn.getresponse()
data = res.read()


# 处理流式响应（SSE 格式）
full_content = ""
response_id = None
finish_reason = None
usage_info = None
model_name_from_response = "gpt-5"  # 直接使用请求中的模型名，防止未定义变量

            
# 逐行读取流式响应
import pdb;
pdb.set_trace()
while True:
    print(1)
    line = res.readline()
    if not line:
        # 修正缩进和循环逻辑：break前的处理需要正确对齐
        line_str = line.decode("utf-8", errors='ignore').strip()
        
        # 跳过空行和 [DONE] 标记
        if not line_str or line_str == "[DONE]":
            if not line_str:
                continue
            if line_str == "[DONE]":
                break
                
            # SSE 格式：每行以 "data: " 开头
            if line_str.startswith("data: "):
                json_str = line_str[6:]  # 移除 "data: " 前缀
                    
                # 跳过 [DONE] 标记
                if json_str.strip() == "[DONE]":
                        break
                    
                try:
                    chunk_data = json.loads(json_str)
                except json.JSONDecodeError as e:
                    print(f"Failed to parse chunk JSON: {e}, line: {json_str[:100]}")
                    continue
                    
                # 获取 response ID（通常在第一个 chunk）
                if chunk_data.get("id") and not response_id:
                    response_id = chunk_data.get("id")
                                    # 获取 model 名称
                if chunk_data.get("model"):
                    model_name_from_response = chunk_data.get("model")
                
                # 处理 choices 数据                    if "choices" in chunk_data and len(chunk_data["choices"]) > 0:
                    choice = chunk_data["choices"][0]
                    
                    # 提取内容增量
                    delta = choice.get("delta", {})
                    if delta.get("content"):
                        delta_content = delta["content"]
                        full_content += delta_content
                        print(delta_content, end="", flush=True)
                    
                    # 获取 finish_reason
                    if choice.get("finish_reason"):
                        finish_reason = choice.get("finish_reason")
                
                # 提取 usage 信息（在最后一个数据包中）
                if "usage" in chunk_data:
                    usage_info = chunk_data["usage"]
                    print("\n\n=== Token 使用统计 ===")
                    print(f"输入 Tokens: {usage_info.get('prompt_tokens', 0)}")
                    print(f"输出 Tokens: {usage_info.get('completion_tokens', 0)}")
                    print(f"总 Tokens: {usage_info.get('total_tokens', 0)}")
                    if "completion_tokens_details" in usage_info:
                        reasoning_tokens = usage_info["completion_tokens_details"].ge("reasoning_tokens", 0)
                        print(f"推理 Tokens: {reasoning_tokens}")
            
        conn.close()
            
        # 检查是否收集到内容
        if not full_content and not usage_info:
            print("No content or usage information received from stream")
    
        # 构建标准非流式响应结构
        response = {
            "id": 1,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model_name_from_response,
           "choices": [{
            "index": 0,
                "message": {
                    "role": "assistant",
                    "content": full_content
                },
                "finish_reason": finish_reason or "stop"
            }]
        }
        
        # 添加 usage 信息
        if usage_info:
            usage_dict = {
            "prompt_tokens": usage_info.get("prompt_tokens", 0),
                "completion_tokens": usage_info.get("completion_tokens", 0),
                "total_tokens": usage_info.get("total_tokens", 0)
            }
            
            # 提取 completion_tokens_details，确保 reasoning_tokens 被包含
            completion_tokens_details = {}
            if "completion_tokens_details" in usage_info and usage_info["completion_tokens_details"]:
                details = usage_info["completion_tokens_details"]
                # 提取 reasoning_tokens（关键字段）
                reasoning_tokens = details.get("reasoning_tokens", 0)
                completion_tokens_details["reasoning_tokens"] = reasoning_tokens
                # 其他可选字段
                if "accepted_prediction_tokens" in details:
                    completion_tokens_details["accepted_prediction_tokens"] = details["accepted_prediction_tokens"]
                if "rejected_prediction_tokens" in details:
                    completion_tokens_details["rejected_prediction_tokens"] = details["rejected_prediction_tokens"]
                if "audio_tokens" in details:
                    completion_tokens_details["audio_tokens"] = details["audio_tokens"]
                
            # 确保 completion_tokens_details 总是存在
            usage_dict["completion_tokens_details"] = completion_tokens_details
            response["usage"] = usage_dict
        else:
                # 如果没有 usage 信息，使用默认值
            response["usage"] = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "completion_tokens_details": {
                    "reasoning_tokens": 0
                }
            }
            
        print(f"Response received successfully (status: ")

print(response)