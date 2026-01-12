TASKS = [
    "MP2_Seperated",
    "MP3_Seperated",
    "MP2_Synthesised",
    "MP3_Synthesised",
]


AVAILABLE_MODEL = [
    "gpt-5",
    "gpt-4o",
    "qwen-plus",
    "gpt-5.1-medium",
    "gpt-5.1",
    "meta-llama/llama-3.1-70b-instruct",
    "gpt-4o-2024-08-06"
    # "gemini-2.5-flash",
    # "gemini-2.5-pro"
]

MODELS_COMPANIES_MAP = {
    "gpt-5": "openai",
    "gpt-5-thinking": "openai",
    "gpt-5-non-thinking": "openai",
    "gpt-4o": "openai",
    "gemini-2.5-flash": "google",
    "gemini-2.5-pro": "google",
    "qwen-plus": "openai",
    "gpt-5.1-medium": "openai",
    "gpt-5.1": "openai",
    "meta-llama/llama-3.1-70b-instruct": "openai",
    "gpt-4o-2024-08-06": "openai",
}
BASE_URL = {
    "gpt-5": "https://chrisapius.top/v1",
    "gpt-4o": "https://chrisapius.top/v1",
    "gpt-5-thinking": "https://chrisapius.top/v1",
    "gpt-5-non-thinking": "https://chrisapius.top/v1",
    "gemini-2.5-flash": "https://chrisapius.top/v1beta",
    "gemini-2.5-pro": "https://chrisapius.top/v1beta",
    "qwen-plus": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "gpt-5.1-medium": "https://chrisapius.top/v1",
    "gpt-5.1": "https://chrisapius.top/v1",
    "meta-llama/llama-3.1-70b-instruct": "https://chrisapius.top/v1",
    "gpt-4o-2024-08-06": "https://chrisapius.top/v1",
}
API_KEYS = {
    # "gpt-5-thinking": "sk-2XZ7ioYdwHQslVr8hUf1NO4RC15JYy3O6d9gIwX8fFNo7aWT",
    "gpt-5-thinking": "sk-KaTunSTD1e8eWpPN67kABCGEZzqz3yg8mXSRYVHPWEipIIpG",
    "gpt-4o": "sk-Y9bJREvWa5H0tDNScxixHM4TxcIoJ7wKVq89DnUbEfdBdnjk",
    "gpt-4o-2024-08-06": "sk-dZ6GLLgCE5Xe5x0iaxNsKdnlH6PFgIwrFVfFZXCYaTcqGee5",
    "gpt-5.1-medium": "sk-2XZ7ioYdwHQslVr8hUf1NO4RC15JYy3O6d9gIwX8fFNo7aWT",
    "gpt-5.1": "sk-2XZ7ioYdwHQslVr8hUf1NO4RC15JYy3O6d9gIwX8fFNo7aWT",
    "gpt-5-non-thinking": "",
    "gemini-3-pro":"",
    "claude-4.5-sonnet": "",
    "glm-4.5":"",
    "deepseek-v3.1-thinking": "",
    "dolphin-3.0-r1-mistral-24B": "",
    "qwen-plus": "sk-9bf0fe7a4dac49c381b9a4cbed663637",
    "llama-4-maverick": "",
    "meta-llama/llama-3.1-70b-instruct": "sk-dZ6GLLgCE5Xe5x0iaxNsKdnlH6PFgIwrFVfFZXCYaTcqGee5"
}