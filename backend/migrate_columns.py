import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not found in .env")

engine = create_engine(DATABASE_URL)

def run_migrations():
    with engine.connect() as conn:
        # Add bulk_job_id to generations
        try:
            conn.execute(text("ALTER TABLE generations ADD COLUMN bulk_job_id VARCHAR(50);"))
            print("Added bulk_job_id to generations.")
        except Exception as e:
            print(f"bulk_job_id exists or error: {e}")
            
        try:
            conn.execute(text("CREATE INDEX ix_generations_bulk_job_id ON generations (bulk_job_id);"))
            print("Created index on bulk_job_id.")
        except Exception as e:
            print(f"Index exists or error: {e}")

        # Modify mab_feedback_loop
        try:
            conn.execute(text("ALTER TABLE mab_feedback_loop ADD CONSTRAINT uq_mab_feedback_published_url UNIQUE (published_url);"))
            print("Added UNIQUE constraint to published_url in mab_feedback_loop.")
        except Exception as e:
            print(f"UNIQUE constraint exists or error: {e}")
            
        try:
            conn.execute(text("ALTER TABLE mab_feedback_loop ADD COLUMN status VARCHAR(20) DEFAULT 'pending';"))
            print("Added status to mab_feedback_loop.")
        except Exception as e:
            print(f"status exists or error: {e}")
            
        try:
            conn.execute(text("ALTER TABLE mab_feedback_loop ADD COLUMN reward_credits INTEGER DEFAULT 0;"))
            print("Added reward_credits to mab_feedback_loop.")
        except Exception as e:
            print(f"reward_credits exists or error: {e}")

        conn.commit()
    print("Migration completed.")

if __name__ == "__main__":
    run_migrations()
