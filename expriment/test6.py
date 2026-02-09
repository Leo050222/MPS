import os
from openai import OpenAI

try:
    client = OpenAI(
        # 若没有配置环境变量，请用阿里云百炼API Key将下行替换为: api_key="sk-xxx",
        api_key="sk-4e91a1670ccf4ae3a9279ac7e6b553f6",
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    )

    completion = client.chat.completions.create(
        model="qwen-plus",  
        messages=[
            {'role': 'system', 'content': 'You are a math expert.'},
            {'role': 'user', 'content': 'Solve the problem below and give the answer in json format in the end.Alice Czarina is bored and is playing a game with a pile of rocks. The pile initially contains 2015 rocks. At each round, if the pile has $N$ rocks, she removes $k$ of them, where $1 \\leq k \\leq N$, with each possible $k$ having equal probability. Alice Czarina continues until there are no more rocks in the pile. Let $p$ be the probability that the number of rocks left in the pile after each round is a multiple of 5. If $p$ is of the form $5^{a} \\cdot 31^{b} \\cdot \\frac{c}{d}$, where $a, b$ are integers and $c, d$ are positive integers relatively prime to $5 \\cdot 31$, find $a+b$.'}
        ],
        extra_body=
        {
            "seed": 42,
            "enable_thinking": True,
        },
        top_p = 0.5
    )
    print(completion.choices[0].message.content)
except Exception as e:
    print(f"错误信息：{e}")
    print("请参考文档：https://www.alibabacloud.com/help/model-studio/developer-reference/error-code")