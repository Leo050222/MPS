from client.client import get_client

client = get_client(model="gpt-4o")

prompt = [{"role": "user", "content": "Hello, GPT-4o! How are you today?"}]

reponse = client.get_response(prompt, reasoning="minimal")

print(reponse)
