import os
from google import genai
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

print("Searching for embedding models...")
found = False
for model in client.models.list():
    if 'embedContent' in model.supported_actions:
        print(f"Model ID: {model.name}")
        found = True

if not found:
    print("No models found with 'embedContent' support for this key.")
