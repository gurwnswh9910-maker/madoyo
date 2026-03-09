import os
from google import genai
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

print("Listing available models...")
for model in client.models.list():
    print(f"Model Name: {model.name}, Supported Methods: {model.supported_actions}")
