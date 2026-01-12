from google import genai

client = genai.Client(api_key="sk-83BacHuBgJAcd5GJX5GxDLOctAD52jRxrAZKRmf3GbtrMMLW", base_url="https://chrisapius.top/v1beta")
prompt = "Explain the concept of Occam's Razor and provide a simple, everyday example."
response = client.models.generate_content(
    model="gemini-2.5-pro",
    contents=prompt
)

print(response.text)