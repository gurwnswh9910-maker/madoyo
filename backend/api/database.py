import os
from sqlalchemy import create_engine, Column, String, Integer, Float, Boolean, Text, ForeignKey, TIMESTAMP, func, text as sql_text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from pgvector.sqlalchemy import Vector
from dotenv import load_dotenv
import uuid

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not found in .env")

engine = create_engine(
    DATABASE_URL, 
    pool_size=10, 
    max_overflow=20,
    pool_recycle=3600
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- Database Models ---

class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String, nullable=True)  # 자체 인증용
    plan = Column(String, default="free")
    credits = Column(Integer, default=10)
    created_at = Column(TIMESTAMP, server_default=func.now())

class MABEmbedding(Base):
    __tablename__ = "mab_embeddings"
    id = Column(Integer, primary_key=True, autoincrement=True)
    uploader_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    is_global = Column(Boolean, default=False)
    content_text = Column(Text, nullable=False)
    embedding = Column(Vector(3072)) 
    mss_score = Column(Float, default=0.0)
    metadata_json = Column(JSONB, default=dict)

class Generation(Base):
    __tablename__ = "generations"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bulk_job_id = Column(String(50), nullable=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    input_config = Column(JSONB, default=dict)
    results = Column(JSONB, default=dict)
    status = Column(String, default="processing")
    created_at = Column(TIMESTAMP, server_default=func.now())

class MABFeedback(Base):
    __tablename__ = "mab_feedback_loop"
    gen_id = Column(UUID(as_uuid=True), ForeignKey("generations.id"), primary_key=True)
    is_copied = Column(Boolean, default=False)
    user_rating = Column(String, nullable=True)     # "good" | "bad" | null
    rating_reasons = Column(JSONB, default=list)       # ["어색한 표현", "주제 무관"]
    published_url = Column(Text, nullable=True, unique=True)
    status = Column(String(20), default="pending")  # pending, processing, completed, rejected, error
    reward_credits = Column(Integer, default=0)
    performance = Column(JSONB, default=dict)
    scheduled_at = Column(TIMESTAMP, nullable=True)  # 성과 체크 실행 예약 시각 (24시간 뒤)

class BugReport(Base):
    __tablename__ = "bug_reports"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    layer = Column(String(20))          # backend | worker | frontend | pipeline
    error_type = Column(String(100))
    message = Column(Text)
    traceback = Column(Text, nullable=True)
    context = Column(JSONB, default=dict)
    code_ref = Column(String(200), nullable=True)
    status = Column(String(20), default="open")
    created_at = Column(TIMESTAMP, server_default=func.now())

class RefineChat(Base):
    __tablename__ = "refine_chats"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    gen_id = Column(UUID(as_uuid=True), ForeignKey("generations.id"), index=True)
    user_instruction = Column(Text, nullable=False)
    refined_copy = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())

# --- Helper Functions ---

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
