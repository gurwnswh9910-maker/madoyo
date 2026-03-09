import os
import shutil
import uuid
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from api.schemas import TaskResponse
from api.worker import process_excel_task

router = APIRouter()

# 업로드된 임시 파일을 저장할 디렉토리
UPLOAD_DIR = "temp_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/excel", response_model=TaskResponse)
async def upload_excel(file: UploadFile = File(...)):
    """
    엑셀 파일을 업로드하여 DB에 벌크로 저장합니다 (비동기 처리).
    본문(또는 내용), MSS(또는 성과지표) 컬럼이 포함되어야 합니다.
    """
    if not file.filename.endswith(('.xlsx', '.csv')):
        raise HTTPException(status_code=400, detail="엑셀(.xlsx) 또는 CSV(.csv) 파일만 업로드 가능합니다.")
    
    # 임시 파일 경로 생성
    file_id = str(uuid.uuid4())
    ext = os.path.splitext(file.filename)[1]
    temp_file_path = os.path.join(UPLOAD_DIR, f"{file_id}{ext}")
    
    try:
        # 파일 저장
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # 비동기 태스크 시작
        task = process_excel_task.delay(temp_file_path, is_global=True)
        
        return TaskResponse(task_id=task.id, status="PENDING")
        
    except Exception as e:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        raise HTTPException(status_code=500, detail=f"파일 업로드 중 오류 발생: {str(e)}")

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
