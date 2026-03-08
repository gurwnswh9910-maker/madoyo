import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# Test cases
configs = [
    # Guess 1: IPv6 direct with encoded password (no brackets)
    "postgresql://postgres:gghyak0616%21@[2406:da12:b78:de17:b1ee:ec82:298b:a54a]:5432/postgres",
    # Guess 2: IPv6 direct with brackets in password
    "postgresql://postgres:%5Bgghyak0616%21%5D@[2406:da12:b78:de17:b1ee:ec82:298b:a54a]:5432/postgres",
    # Guess 3: Pooler with brackets in password
    "postgresql://postgres.dmphuetkyamaggverfmm:%5Bgghyak0616%21%5D@aws-0-ap-northeast-2.pooler.supabase.com:6543/postgres?sslmode=require"
]

for url in configs:
    print(f"\nTesting: {url}")
    try:
        conn = psycopg2.connect(url, connect_timeout=5)
        print("Success!")
        conn.close()
        break
    except Exception as e:
        print(f"Failed: {e}")
