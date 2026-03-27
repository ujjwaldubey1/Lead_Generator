import requests, os, json
from dotenv import load_dotenv
load_dotenv()

r = requests.post(
    "https://integrate.api.nvidia.com/v1/chat/completions",
    headers={
        "Authorization": f"Bearer {os.getenv('NVIDIA_API_KEY')}",
        "Accept": "application/json"
    },
    json={
        "model": "meta/llama-3.1-8b-instruct",
        "messages": [
            {"role": "system", "content": "Respond with valid JSON only."},
            {"role": "user", "content": 'Return: {"status": "working"}'}
        ],
        "max_tokens": 100,
        "temperature": 0.3,
        "stream": False
    },
    timeout=30
)
print("Status:", r.status_code)
print(r.json()["choices"][0]["message"]["content"])
print("Fast model working!")