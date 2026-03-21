import os
import shutil
import uuid
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Depends
from api.schemas import TaskResponse
from api.worker import process_excel_task
from api.auth_middleware import get_current_user
from api.config import USE_CELERY

router = APIRouter()

# 업로드된 임시 파일을 저장할 디렉토리
UPLOAD_DIR = "temp_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/excel", response_model=TaskResponse)
async def upload_excel(background_tasks: BackgroundTasks, file: UploadFile = File(...), current_user=Depends(get_current_user)):
    """
    엑셀 파일을 업로드하여 URL 병렬 추출 및 대량 학습/생성 워커에 전달합니다.
    """
    if not file.filename.endswith(('.xlsx', '.csv')):
        raise HTTPException(status_code=400, detail="엑셀(.xlsx) 또는 CSV(.csv) 파일만 업로드 가능합니다.")
    
    # 임시 파일 저장 (pandas 읽기용)
    import pandas as pd
    file_id = str(uuid.uuid4())
    bulk_job_id = f"bulk_{file_id}"
    ext = os.path.splitext(file.filename)[1]
    temp_file_path = os.path.join(UPLOAD_DIR, f"{file_id}{ext}")
    
    try:
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # 1. 즉시 엑셀 읽기
        if ext == '.csv':
            df = pd.read_csv(temp_file_path)
        else:
            df = pd.read_excel(temp_file_path)
            
        # 2. URL 추출 고도화 (컬럼명 기반 + 데이터 기반)
        url_col = None
        # 일단 컬럼명으로 시도
        for col in df.columns:
            c = str(col).lower()
            if any(k in c for k in ['링크', 'url', '링크주소', '게시물', 'link']):
                url_col = col
                break
        
        # 컬럼명으로 못찾으면 첫 번째 행의 데이터를 뒤져서 http로 시작하는 컬럼 찾기
        if not url_col and not df.empty:
            for col in df.columns:
                first_val = str(df[col].iloc[0]).strip()
                if first_val.startswith("http"):
                    url_col = col
                    break
        
        if not url_col:
            raise HTTPException(status_code=400, detail="'링크' 또는 'URL' 컬럼을 찾을 수 없습니다. (헤더명을 'URL'로 수정해 보세요.)")
            
        urls = [str(u).strip() for u in df[url_col].dropna().tolist() if str(u).strip().startswith("http")]
        
        if not urls:
             raise HTTPException(status_code=400, detail="유효한 URL이 담긴 데이터가 1건도 없습니다.")

        # 3. DB 선입력 (Pending 상태로 바로 시각화되게 함)
        from api.database import SessionLocal, Generation
        from api.worker import scrape_and_generate_single_task
        db = SessionLocal()
        try:
            for url in urls:
                url_str = str(url).strip()
                if not url_str.startswith("http"): continue
                
                new_gen = Generation(
                    bulk_job_id=bulk_job_id,
                    user_id=current_user.id,
                    input_config={"url": url_str, "scraped_text": "💡 처리 대기 중..."},
                    results={},
                    status="pending"
                )
                db.add(new_gen)
                db.commit()
                db.refresh(new_gen)
                
                # 4. 개별 작업 던지기
                if USE_CELERY:
                    scrape_and_generate_single_task.delay(
                        url=url_str,
                        bulk_job_id=bulk_job_id,
                        uploader_id=str(current_user.id),
                        is_global=True,
                        generation_id=str(new_gen.id)
                    )
                else:
                    # Celery 없이 백그라운드 태스크로 직접 실행
                    background_tasks.add_task(
                        scrape_and_generate_single_task,
                        url=url_str,
                        bulk_job_id=bulk_job_id,
                        uploader_id=str(current_user.id),
                        is_global=True,
                        generation_id=str(new_gen.id)
                    )
        finally:
            db.close()
            
        return TaskResponse(task_id=bulk_job_id, status="STARTED")
        
    except HTTPException as he:
        # 400 에러 등은 그대로 전달
        raise he
    except Exception as e:
        # 그 외 내부 오류
        raise HTTPException(status_code=500, detail=f"데이터 처리 중 오류: {str(e)}")
    finally:
        # 어떤 경우에도 파일은 삭제 (메모리 로딩 완료했으므로)
        if os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except:
                pass

@router.get("/bulk-status/{bulk_job_id}")
async def get_bulk_status(bulk_job_id: str):
    """
    대량 작업의 진행 완료 현황을 DB에서 조회하여 반환합니다.
    """
    from api.database import SessionLocal, Generation
    db = SessionLocal()
    try:
        # 전체 개수와 완료된 개수를 함께 반환
        total = db.query(Generation).filter(Generation.bulk_job_id == bulk_job_id).count()
        completed = db.query(Generation).filter(Generation.bulk_job_id == bulk_job_id, Generation.status == 'completed').count()
        return {
            "bulk_job_id": bulk_job_id, 
            "total_count": total, 
            "completed_count": completed,
            "is_finished": total > 0 and total == completed
        }
    finally:
        db.close()

@router.get("/excel/sample")
async def get_excel_sample():
    """
    업로드용 엑셀 샘플 양식을 안내합니다 (추후 파일 다운로드로 대체 가능).
    """
    return {
        "required_columns": ["본문", "MSS"],
        "optional_columns": ["출처", "날짜"],
        "message": "엑셀 파일의 첫 번째 시트에 해당 컬럼이 포함되어야 합니다."
    }
