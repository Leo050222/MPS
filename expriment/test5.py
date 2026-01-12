import os
from openai import OpenAI

client = OpenAI(
    # 若没有配置环境变量，请用百炼API Key将下行替换为：api_key="sk-xxx"
    api_key=r"sk-9bf0fe7a4dac49c381b9a4cbed663637",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

completion = client.chat.completions.create(
    # 模型列表：https://help.aliyun.com/zh/model-studio/getting-started/models
    model="qwen-plus",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "你是谁？"},
    ],
    stream=True,
    extra_body={"enable_thinking": True},
    stream_options={"include_usage": True}
)
full_content = ""
for chunk in completion:
    # 普通内容块：处理文本增量
    if chunk.choices and chunk.choices[0].delta.content:
        delta = chunk.choices[0].delta.content
        full_content += delta
        print(delta, end="", flush=True)
    
    # 最后一个块：提取 usage 信息
    elif chunk.usage:
        import pdb; pdb.set_trace()
        print("\n\n=== Token 使用统计 ===")
        print(f"输入 Tokens: {chunk.usage.prompt_tokens}")
        print(f"输出 Tokens: {chunk.usage.completion_tokens}")

print(full_content)