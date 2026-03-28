import os
from sqlalchemy import create_engine, Column, String, Integer, Float, Boolean, Text, ForeignKey, TIMESTAMP, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base, sessionmaker
from pgvector.sqlalchemy import Vector
from dotenv import load_dotenv
import uuid

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not found in .env")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 1. Users Table
class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True)
    plan = Column(String, default="free") # free, pro, enterprise
    credits = Column(Integer, default=10)
    created_at = Column(TIMESTAMP, server_default=func.now())

# 2. MAB Embeddings Table
class MABEmbedding(Base):
    __tablename__ = "mab_embeddings"
    __table_args__ = (
        UniqueConstraint('content_text', 'embedding_type', name='uq_content_embedding_type'),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    uploader_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    is_global = Column(Boolean, default=False)
    content_text = Column(Text, nullable=False)
    embedding_type = Column(String(10), nullable=False, default="multi")  # text / visual / multi
    embedding = Column(Vector(3072)) # Gemini embedding-001 dimension
    mss_score = Column(Float, default=0.0)
    metadata_json = Column(JSONB, default={}) # source type, original url, etc.

# 3. Generations Table
class Generation(Base):
    __tablename__ = "generations"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    input_config = Column(JSONB, default={})
    results = Column(JSONB, default={})
    status = Column(String, default="processing") # processing, completed, failed
    created_at = Column(TIMESTAMP, server_default=func.now())

# 4. MAB Feedback Loop Table
class MABFeedback(Base):
    __tablename__ = "mab_feedback_loop"
    gen_id = Column(UUID(as_uuid=True), ForeignKey("generations.id"), primary_key=True)
    is_copied = Column(Boolean, default=False)
    published_url = Column(Text, nullable=True)
    performance = Column(JSONB, default={})

from sqlalchemy import create_engine, Column, String, Integer, Float, Boolean, Text, ForeignKey, TIMESTAMP, func, text

def init_db():
    print("Checking for pgvector extension...")
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        conn.commit()
    
    print("Creating tables...")
    Base.metadata.create_all(bind=engine)
    print("DB Initialization complete!")

if __name__ == "__main__":
    init_db()
