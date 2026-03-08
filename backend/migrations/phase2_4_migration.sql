-- ============================================================
-- Phase 2~4 DB 마이그레이션 스크립트
-- Supabase SQL Editor에서 실행하세요
-- ============================================================

-- 1. bug_reports 테이블 생성
CREATE TABLE IF NOT EXISTS bug_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    layer VARCHAR(20),
    error_type VARCHAR(100),
    message TEXT,
    traceback TEXT,
    context JSONB DEFAULT '{}',
    code_ref VARCHAR(200),
    status VARCHAR(20) DEFAULT 'open',
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 2. mab_feedback_loop 테이블에 피드백 컬럼 추가
ALTER TABLE mab_feedback_loop 
ADD COLUMN IF NOT EXISTS user_rating VARCHAR(10),
ADD COLUMN IF NOT EXISTS rating_reasons JSONB DEFAULT '[]';

-- 3. users 테이블에 인증 컬럼 추가
ALTER TABLE users 
ADD COLUMN IF NOT EXISTS hashed_password VARCHAR;

-- 완료 확인
SELECT 'Migration complete!' as status;
