import os
from google import genai
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

try:
    print("Testing Gemini Embedding API (gemini-embedding-001)...")
    result = client.models.embed_content(
        model="gemini-embedding-001",
        contents="안녕하세요, 제미나이 테스트 문구입니다."
    )
    vector = result.embeddings[0].values
    print(f"Success! Vector length: {len(vector)}")
    print(f"Sample values: {vector[:5]}")
except Exception as e:
    print(f"Failure! Error: {e}")
