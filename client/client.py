from typing import Optional
from openai import OpenAI, AsyncOpenAI
import pdb
import http.client
import json
import logging
import time
import ssl

from config import API_KEYS, AVAILABLE_MODEL, BASE_URL, TOP_P
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def _reslove_base_url(model: str) -> str:
    if model in BASE_URL and BASE_URL.get(model):
        return BASE_URL[model]
    else:
        raise ValueError(f"Base URL for model {model} not found in config.BASE_URL.")

def _resolve_api_key(model: str) -> str:
    """Resolve API key strictly from config.API_KEYS.

    - Prefers exact match for the provided model name.
    - For gpt-5, falls back to gpt-5-thinking / gpt-5-non-thinking if present.
    """

    if not isinstance(model, str) or not model:
        raise ValueError(f"Invalid model name for API key lookup: {model!r}")

    if model in API_KEYS and API_KEYS.get(model):
        return API_KEYS[model]

    if model == "gpt-5":
        for alias in ("gpt-5-thinking", "gpt-5-non-thinking"):
            if API_KEYS.get(alias):
                return API_KEYS[alias]

    available = sorted([k for k, v in API_KEYS.items() if v])
    raise ValueError(
        f"API key for model '{model}' not found in config.API_KEYS. "
        f"Available (non-empty) keys: {available}"
    )

class BaseClient:
    def __init__(self, api_key: Optional[str] = None, base_url: str = None, model: str = ""):
        
        # AVAILABLE_MODEL represents callable API model families; allow key aliases.
        self.models = AVAILABLE_MODEL
        if model in self.models:
            self.model = model
        else:
            raise ValueError(f"Model {model} is not available.")
        # Only read API keys from config.py (no env var fallback)
        self.api_key = api_key or _resolve_api_key(model)
        self.base_url = base_url or _reslove_base_url(model)
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
        # 异步客户端，用于并发调用
        self.async_client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

    def get_models(self):
        try:
            return self.client.models.list()
        except Exception:
            # Fallback to locally known models if remote listing is unavailable
            return self.models

    def get_response(self, prompt, reasoning: str = "medium", seed: int = None):
        try:
            # 构建请求 payload
            # prompt 可能是列表格式（OpenAI 消息格式）或字符串
            if isinstance(prompt, list):
                messages = prompt
            elif isinstance(prompt, str):
                # 如果是字符串，转换为消息格式
                messages = [{"role": "user", "content": prompt}]
            else:
                raise ValueError(f"Unsupported prompt type: {type(prompt)}")
            
            model_name = self.model
            payload = {
                "model": model_name,
                "messages": messages,
                "stream": True,
                "stream_options": {"include_usage": True},
                "top_p": TOP_P
            }

            if reasoning != "minimal":
                payload["reasoning_effort"] = reasoning
            
            # 添加 seed 参数（如果提供）
            if seed is not None:
                payload["seed"] = seed
            
            # 发送 HTTP 请求
            conn = http.client.HTTPConnection("152.53.208.62", 9000)
            payload_json = json.dumps(payload)
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json',
                'Accept': 'text/event-stream'
            }
            
            conn.request("POST", "/v1/chat/completions", payload_json, headers)
            res = conn.getresponse()
            status_code = res.status
            
            # 检查 HTTP 状态码
            if status_code != 200:
                data = res.read()
                conn.close()
                logger.error(f"API returned HTTP status code {status_code}")
                response_text = data.decode("utf-8", errors='ignore')
                logger.error(f"Response body (first 500 chars): {response_text[:500]}")
                return None
            
            # 处理流式响应（SSE 格式）
            full_content = ""
            response_id = None
            finish_reason = None
            usage_info = None
            model_name_from_response = model_name
            
            # 逐行读取流式响应
            while True:
                line = res.readline()
                if not line:
                    break
                
                line_str = line.decode("utf-8", errors='ignore').strip()
                
                # 跳过空行
                if not line_str:
                    continue
                
                # 检查 [DONE] 标记
                if line_str == "data: [DONE]":
                    break
                
                # SSE 格式：每行以 "data: " 开头
                if line_str.startswith("data: "):
                    json_str = line_str[6:]  # 移除 "data: " 前缀
                    
                    try:
                        chunk_data = json.loads(json_str)
                    except json.JSONDecodeError as e:
                        logger.warning(f"Failed to parse chunk JSON: {e}, line: {json_str[:100]}")
                        continue
                    
                    # 获取 response ID（通常在第一个 chunk）
                    if chunk_data.get("id") and not response_id:
                        response_id = chunk_data.get("id")
                    
                    # 获取 model 名称
                    if chunk_data.get("model"):
                        model_name_from_response = chunk_data.get("model")
                    
                    # 处理 choices 数据
                    if "choices" in chunk_data and len(chunk_data["choices"]) > 0:
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
                    if "usage" in chunk_data and chunk_data["usage"] is not None:
                        usage_info = chunk_data["usage"]
                        # 确保 usage_info 是字典类型
                        if isinstance(usage_info, dict):
                            print("\n\n=== Token 使用统计 ===")
                            print(f"输入 Tokens: {usage_info.get('prompt_tokens', 0)}")
                            print(f"输出 Tokens: {usage_info.get('completion_tokens', 0)}")
                            print(f"总 Tokens: {usage_info.get('total_tokens', 0)}")
                            if "completion_tokens_details" in usage_info:
                                reasoning_tokens = usage_info["completion_tokens_details"].get("reasoning_tokens", 0)
                                print(f"推理 Tokens: {reasoning_tokens}")
            
            conn.close()
            
            # 检查是否收集到内容
            if not full_content and not usage_info:
                logger.error("No content or usage information received from stream")
                return None
            
            # 构建标准非流式响应结构（与 qwenClient 格式一致）
            response = {
                "id": response_id or f"chatcmpl-{hash(str(prompt))}",
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
                
                # 确保 completion_tokens_details 总是存在（即使为空字典）
                # 这样 extract 函数可以安全地调用 .get("reasoning_tokens", 0)
                usage_dict["completion_tokens_details"] = completion_tokens_details
                response["usage"] = usage_dict
            else:
                # 如果没有 usage 信息，使用默认值，但确保 completion_tokens_details 存在
                response["usage"] = {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "completion_tokens_details": {
                        "reasoning_tokens": 0
                    }
                }
            
            logger.info(f"Response received successfully (status: {status_code})")
            return response
            
        except Exception as e:
            logger.error(f"Error getting response: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def get_response_not_stream(self, prompt, reasoning: str = "minimal", seed: int = None):
        try:
            if isinstance(prompt, list):
                messages = prompt
            elif isinstance(prompt, str):
                messages = [{"role": "user", "content": prompt}]
            else:
                raise ValueError(f"Unsupported prompt type: {type(prompt)}")
            model_name = self.model
            payload = {
                "model": model_name,
                "messages": messages,
                "top_p": TOP_P
            }

            if reasoning != "minimal":
                payload["reasoning_effort"] = reasoning
            
            # 添加 seed 参数（如果提供）
            if seed is not None:
                payload["seed"] = seed

            conn = http.client.HTTPConnection("152.53.208.62", 9000)
            payload_json = json.dumps(payload)
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            
            conn.request("POST", "/v1/chat/completions", payload_json, headers)
            res = conn.getresponse()
            status_code = res.status
            
            data = res.read()
            conn.close()
            
            if status_code != 200:
                logger.error(f"API returned HTTP status code {status_code}")
                response_text = data.decode("utf-8", errors='ignore')
                logger.error(f"Response body (first 500 chars): {response_text[:500]}")
            
            response_text = data.decode("utf-8", errors='ignore')
            response_data = json.loads(response_text)
            
            return response_data
            
        except Exception as e:
            logger.error(f"Error getting response: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    @staticmethod
    def _ensure_usage_dict(response: dict) -> dict:
        usage = response.get("usage")
        if usage:
            if not usage.get("completion_tokens_details"):
                usage["completion_tokens_details"] = {"reasoning_tokens": 0}
            elif usage["completion_tokens_details"].get("reasoning_tokens") is None:
                usage["completion_tokens_details"]["reasoning_tokens"] = 0
        else:
            response["usage"] = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "completion_tokens_details": {"reasoning_tokens": 0}
            }
        return response

    async def get_response_not_stream_async(self, prompt, reasoning: str = "minimal", seed: int = None):
        """异步非流式调用（用于 judge 等场景），返回格式与同步版 get_response_not_stream 一致。"""
        try:
            if isinstance(prompt, list):
                messages = prompt
            elif isinstance(prompt, str):
                messages = [{"role": "user", "content": prompt}]
            else:
                raise ValueError(f"Unsupported prompt type: {type(prompt)}")

            kwargs = {
                "model": self.model,
                "messages": messages,
                "top_p": TOP_P,
            }

            extra_body = {}
            if reasoning != "minimal":
                extra_body["reasoning_effort"] = reasoning
            if seed is not None:
                kwargs["seed"] = seed
            if extra_body:
                kwargs["extra_body"] = extra_body

            completion = await self.async_client.chat.completions.create(**kwargs)
            response = completion.model_dump()
            return self._ensure_usage_dict(response)

        except Exception as e:
            logger.error(f"Error in async non-stream response: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

class gpt51Client(BaseClient):
    def __init__(self, key_model: str = "gpt-5.1"):
        super().__init__(model=key_model)
    

class gpt4oClient(BaseClient):
    def __init__(self, api_key = None, base_url = None, model = ""):
        super().__init__(api_key, base_url, model)
        
class gpt5Client(BaseClient):
    def __init__(self, key_model: str = "gpt-5"):
        # key_model can be gpt-5-thinking / gpt-5-non-thinking / gpt-5
        super().__init__(model=key_model)

class geminiClient(BaseClient):
    def __init__(self, model: str = "gemini-2.5-flash") -> None:
        self.api_key = 'sk-83BacHuBgJAcd5GJX5GxDLOctAD52jRxrAZKRmf3GbtrMMLW'
        self.model = model
    def get_response(self, prompt, reasoning_effort: str = "medium"):
        model = self.model
        if reasoning_effort == "minimal":
            prompt["generationConfig"] = {
                "thinkingConfig": {
                    "includeThoughts": False,
                    "thinkingBudget": 0
                }
            }
        prompt_json = json.dumps(prompt)
        headers = {
            'Authorization': 'sk-83BacHuBgJAcd5GJX5GxDLOctAD52jRxrAZKRmf3GbtrMMLW',
            'Content-Type': 'application/json'
        }
        
        # Create a new connection for each request to avoid connection reuse issues
        client = http.client.HTTPConnection("152.53.208.62", 9000)
        client.request("POST", f"/v1beta/models/{model}:generateContent", prompt_json, headers)
        res = client.getresponse()
        data = res.read()
        client.close()
        return data.decode("utf-8")
        
class qwenClient(BaseClient):
    def __init__(self, key_model: str = "qwen-plus"):
        super().__init__(model=key_model)

    def get_response(self, prompt, reasoning: bool = True, seed: int = None):
        client = self.client
        # 将 reasoning 转换为布尔值（处理字符串 "True"/"False" 的情况）
        if isinstance(reasoning, str):
            reasoning = reasoning.lower() in ("true", "1", "yes", "on")
        elif not isinstance(reasoning, bool):
            reasoning = bool(reasoning)
        
        # 构建 extra_body，包含 enable_thinking 和可选的 seed
        extra_body = {"enable_thinking": reasoning}
        if seed is not None:
            extra_body["seed"] = seed
        
        completion = client.chat.completions.create(
            model=self.model,
            messages=prompt,
            stream=True,
            extra_body=extra_body,
            stream_options={"include_usage": True},
            top_p=TOP_P
        )
        
        # 初始化变量用于收集流式数据
        full_content = ""
        response_id = None
        finish_reason = None
        usage_info = None
        
        # 处理流式响应
        for chunk in completion:
            # 获取 response ID（通常在第一个 chunk）
            if chunk.id and not response_id:
                response_id = chunk.id
            
            # 普通内容块：处理文本增量
            if chunk.choices and len(chunk.choices) > 0:
                choice = chunk.choices[0]
                if choice.delta and choice.delta.content:
                    delta = choice.delta.content
                    full_content += delta
                    print(delta, end="", flush=True)
                
                # 获取 finish_reason（在最后一个 chunk）
                if choice.finish_reason:
                    finish_reason = choice.finish_reason
            
            # 最后一个块：提取 usage 信息
            if chunk.usage:
                usage_info = chunk.usage
                print("\n\n=== Token 使用统计 ===")
                print(f"输入 Tokens: {chunk.usage.prompt_tokens}")
                print(f"输出 Tokens: {chunk.usage.completion_tokens}")
                if hasattr(chunk.usage, 'total_tokens'):
                    print(f"总 Tokens: {chunk.usage.total_tokens}")
        
        # 构建标准非流式响应结构
        response = {
            "id": response_id or f"chatcmpl-{hash(str(prompt))}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": self.model,
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
                "prompt_tokens": usage_info.prompt_tokens,
                "completion_tokens": usage_info.completion_tokens,
                "total_tokens": getattr(usage_info, 'total_tokens', usage_info.prompt_tokens + usage_info.completion_tokens)
            }
            # 提取 completion_tokens_details，确保 reasoning_tokens 被包含
            completion_tokens_details = {}
            if hasattr(usage_info, 'completion_tokens_details') and usage_info.completion_tokens_details:
                details = usage_info.completion_tokens_details
                # 提取 reasoning_tokens（关键字段）
                reasoning_tokens = getattr(details, 'reasoning_tokens', 0)
                completion_tokens_details["reasoning_tokens"] = reasoning_tokens
                # 其他可选字段
                if hasattr(details, 'accepted_prediction_tokens'):
                    completion_tokens_details["accepted_prediction_tokens"] = details.accepted_prediction_tokens
                if hasattr(details, 'rejected_prediction_tokens'):
                    completion_tokens_details["rejected_prediction_tokens"] = details.rejected_prediction_tokens
                if hasattr(details, 'audio_tokens'):
                    completion_tokens_details["audio_tokens"] = details.audio_tokens
            
            # 确保 completion_tokens_details 总是存在（即使为空字典）
            # 这样 extract 函数可以安全地调用 .get("reasoning_tokens", 0)
            usage_dict["completion_tokens_details"] = completion_tokens_details
            response["usage"] = usage_dict
        else:
            # 如果没有 usage 信息，使用默认值，但确保 completion_tokens_details 存在
            response["usage"] = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "completion_tokens_details": {
                    "reasoning_tokens": 0
                }
            }
        
        return response

    async def get_response_async(self, prompt, reasoning: bool = True, seed: int = None):
        """异步流式调用（用于并发推理），静默收集 chunks，不打印到终端。
        返回格式与同步版 get_response 完全一致。"""
        # 将 reasoning 转换为布尔值（处理字符串 "True"/"False" 的情况）
        if isinstance(reasoning, str):
            reasoning = reasoning.lower() in ("true", "1", "yes", "on")
        elif not isinstance(reasoning, bool):
            reasoning = bool(reasoning)

        if isinstance(prompt, list):
            messages = prompt
        elif isinstance(prompt, str):
            messages = [{"role": "user", "content": prompt}]
        else:
            raise ValueError(f"Unsupported prompt type: {type(prompt)}")

        extra_body = {"enable_thinking": reasoning}
        if seed is not None:
            extra_body["seed"] = seed

        try:
            completion = await self.async_client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True,
                stream_options={"include_usage": True},
                extra_body=extra_body,
                top_p=TOP_P,
            )

            # 静默收集流式 chunks
            full_content = ""
            response_id = None
            finish_reason = None
            usage_info = None

            async for chunk in completion:
                # 获取 response ID（通常在第一个 chunk）
                if chunk.id and not response_id:
                    response_id = chunk.id

                # 拼接文本内容（不打印）
                if chunk.choices and len(chunk.choices) > 0:
                    choice = chunk.choices[0]
                    if choice.delta and choice.delta.content:
                        full_content += choice.delta.content
                    if choice.finish_reason:
                        finish_reason = choice.finish_reason

                # 最后一个 chunk 携带 usage 信息
                if chunk.usage:
                    usage_info = chunk.usage

            # 组装标准 response dict（与同步版 get_response 格式一致）
            response = {
                "id": response_id or f"chatcmpl-{hash(str(prompt))}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": self.model,
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
                    "prompt_tokens": usage_info.prompt_tokens,
                    "completion_tokens": usage_info.completion_tokens,
                    "total_tokens": getattr(usage_info, 'total_tokens',
                                            usage_info.prompt_tokens + usage_info.completion_tokens)
                }
                completion_tokens_details = {}
                if hasattr(usage_info, 'completion_tokens_details') and usage_info.completion_tokens_details:
                    details = usage_info.completion_tokens_details
                    reasoning_tokens = getattr(details, 'reasoning_tokens', 0)
                    completion_tokens_details["reasoning_tokens"] = reasoning_tokens
                    if hasattr(details, 'accepted_prediction_tokens'):
                        completion_tokens_details["accepted_prediction_tokens"] = details.accepted_prediction_tokens
                    if hasattr(details, 'rejected_prediction_tokens'):
                        completion_tokens_details["rejected_prediction_tokens"] = details.rejected_prediction_tokens
                    if hasattr(details, 'audio_tokens'):
                        completion_tokens_details["audio_tokens"] = details.audio_tokens
                usage_dict["completion_tokens_details"] = completion_tokens_details
                response["usage"] = usage_dict
            else:
                response["usage"] = {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "completion_tokens_details": {"reasoning_tokens": 0}
                }

            return response

        except Exception as e:
            logger.error(f"Error in qwen async stream response: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

class metallamaClient(BaseClient):
    def __init__(self, model: str = ""):
        super().__init__(model=model)

def get_client(model: str = ""):
    if model in {"gpt-4o", "gpt-4o-2024-08-06"}:
        return gpt4oClient(model=model)
    if model in {"gpt-5", "gpt-5-thinking", "gpt-5-non-thinking"}:
        return gpt5Client(key_model=model)
    elif model in["gpt-5.1", "gpt-5.1-medium"]:
        return gpt51Client(key_model=model)
    elif model == "gemini-2.5-flash":
        return geminiClient(model = model)
    elif model == "gemini-2.5-pro":
        return geminiClient(model = model)
    elif model == "qwen-plus":
        return qwenClient(key_model=model)
    elif model == "meta-llama/llama-3.1-70b-instruct":
        return metallamaClient(model=model)
    else:   
        raise ValueError(f"Model {model} is not supported.")
    
    
    
    