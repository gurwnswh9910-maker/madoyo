import os
import shutil
import uuid
from fastapi import APIRouter, UploadFile, File, HTTPException

router = APIRouter()

UPLOAD_DIR = "temp_uploads/media"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/media", response_model=dict)
async def upload_media(file: UploadFile = File(...)):
    """
    프론트엔드에서 업로드한 이미지/동영상 파일을 저장하고
    접근 가능한 URL 경로를 반환합니다.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="파일이 없습니다.")
        
    ext = os.path.splitext(file.filename)[1].lower()
    allowed_exts = ['.jpg', '.jpeg', '.png', '.webp', '.gif', '.mp4', '.mov']
    
    if ext not in allowed_exts:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 파일 형식입니다: {ext}")
        
    file_id = str(uuid.uuid4())
    filename = f"{file_id}{ext}"
    file_path = os.path.join(UPLOAD_DIR, filename)
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # 서버에서 서빙되는 URL 경로 반환 (예: http://localhost:8000/media/...)
        url = f"/media/{filename}"
        return {"url": url, "filename": filename}
        
    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"파일 업로드 중 오류 발생: {str(e)}")
