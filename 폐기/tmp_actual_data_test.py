import os
import sys
import io
import time
from dotenv import load_dotenv

# Windows 환경에서 UTF-8 설정
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 경로 설정
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(current_dir)
sys.path.append(parent_dir)

from publisher import upload_to_threads

def test_actual_data_upload():
    # .env 파일 로드
    env_path = os.path.join(parent_dir, '.env')
    load_dotenv(env_path, override=True)
    
    user_id = os.getenv("THREADS_USER_ID")
    access_token = os.getenv("THREADS_ACCESS_TOKEN")
    
    if not user_id or not access_token:
        print("❌ .env 파일에서 Threads 정보를 찾을 수 없습니다.")
        return

    # 테스트용 1개 데이터 (실제 데이터 형식 모사)
    test_text = """심플하고 고급스러운 자석 네일 1초 완성!💖
손가락만 넣고 돌리면 샵 퀄리티 아트가 뚝딱 완성돼요.

#자석네일 #네일아트 #셀프네일 #뷰티템 #추천템"""
    
    # 실제 이미지 URL 샘플 (쿠팡 등에서 가져온 예시 이미지 하나 활용)
    # 이미지가 없다면 텍스트만 올라갑니다.
    image_urls = ["https://thumbnail7.coupangcdn.com/thumbnails/remote/492x492ex/image/vendor_inventory/842e/7018314e366a7b7364b49080c98f8cc858ad116e0da9b6af8e98218e778d.jpg"]
    
    print(f"🚀 account(@_seheehx_)에 실제 데이터 1건 업로드 시작")
    print(f"📝 내용: {test_text[:30]}...")
    
    try:
        success = upload_to_threads(
            user_id=user_id, 
            access_token=access_token, 
            text=test_text,
            image_urls=image_urls,
            reply_text="본 포스팅은 쿠팡 파트너스 활동의 일환으로 소정의 수수료를 제공받을 수 있습니다."
        )
        
        if success:
            print("\n✅ 실제 데이터 업로드 테스트 성공!")
        else:
            print("\n❌ 실제 데이터 업로드 테스트 실패")
            
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")

if __name__ == "__main__":
    test_actual_data_upload()
