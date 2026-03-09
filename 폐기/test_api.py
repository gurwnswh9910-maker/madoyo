import requests
import json
import time

API_BASE = "http://localhost:8000/api"

def test_pipeline():
    print("=========================================")
    print("🚀 1. 카피 생성 엔드포인트(/api/generate) 테스트 시작...")
    print("=========================================")
    
    # 프론트엔드에서 보내는 데이터 형식과 동일
    payload = {
        "reference_copy": "여름용 쿨링 스틱, 바르자마자 피부 열감 -5도 감소, 끈적임 없는 쿨링감",
        "image_urls": None,
        "reference_url": None
    }
    
    try:
        start_time = time.time()
        res = requests.post(f"{API_BASE}/generate", json=payload)
        
        if res.status_code == 200:
            data = res.json()
            print(f"✅ 생성 성공! (소요시간: {data.get('processing_time', 0)}초)\n")
            
            copies = data.get('copies', [])
            for copy in copies:
                print(f"[Top {copy['rank']} - {copy['strategy']}] (예상점수: {copy['score']:.1f})")
                print(copy['copy_text'])
                print("-" * 40)
                
            if copies:
                print("\n=========================================")
                print("🧠 2. 챗봇 수정 엔드포인트(/api/refine) 테스트 시작...")
                print("=========================================")
                
                original_copy = copies[0]['copy_text']
                refine_payload = {
                    "original_copy": original_copy,
                    "user_instruction": "이 카피를 20대 타겟으로 조금 더 짧고 친근한 반말로 바꿔줘. 이모지도 많이 넣어줘.",
                    "conversation_history": [
                        {"role": "assistant", "content": "무엇을 어떻게 수정할까요?"},
                        {"role": "user", "content": "이 카피를 20대 타겟으로 조금 더 짧고 친근한 반말로 바꿔줘. 이모지도 많이 넣어줘."}
                    ]
                }
                
                refine_res = requests.post(f"{API_BASE}/refine", json=refine_payload)
                
                if refine_res.status_code == 200:
                    refine_data = refine_res.json()
                    print("✅ 수정 성공!\n")
                    print(f"[원본 카피]:\n{original_copy}\n")
                    print(f"✨ [수정된 카피 (반말, 이모지 추가)]:\n{refine_data['refined_copy']}")
                else:
                    print(f"❌ 수정 실패: {refine_res.status_code} - {refine_res.text}")
                    
        else:
            print(f"❌ 생성 실패: {res.status_code} - {res.text}")

    except Exception as e:
        print(f"❌ API 연결 오류 (서버가 켜져 있는지 확인하세요): {str(e)}")

if __name__ == "__main__":
    test_pipeline()
