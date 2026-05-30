import os
import requests
import tempfile
import time
import json
from google import genai
from google.genai import types
from app_config import GlobalConfig

def wait_for_file_active(client, file_obj, timeout=None):
    """Gemini File API 업로드 후 ACTIVE 상태가 될 때까지 대기합니다."""
    if timeout is None:
        timeout = GlobalConfig.FILE_API_TIMEOUT
    
    start_time = time.time()
    while time.time() - start_time < timeout:
        f = client.files.get(name=file_obj.name)
        if f.state.name == "ACTIVE":
            return True
        elif f.state.name == "FAILED":
            raise Exception("Gemini File processing failed.")
        time.sleep(GlobalConfig.FILE_API_POLL)
    return False

# extract_frames 함수 제거 (File API로 대체)

def extract_marketing_focus(client: genai.Client, model_name: str, product_name: str, original_text: str, threads_images: list, coupang_images: list = None, user_description: str = None) -> dict:
    """
    LLM 비전 모델을 사용하여 스레드 본문 이미지/동영상과 텍스트 간의 관계/맥락을 분석하고
    객관적 묘사와 마케팅 인사이트가 분리된 구조화된 데이터를 반환합니다.
    """
    print(f"  [전처리] 마케팅 소구점 및 맥락 분석 시작 (대상: {product_name[:30]}...)")
    
    parts = []
    
    # 상품명이 무효한 경우(수집 실패 등) 프롬프트에서 아예 빼버림
    product_section = ""
    if product_name and product_name.strip() not in ["", "상품", "Unknown"]:
        product_section = f"\n2. 공식 상품명(참고용): {product_name}"

    # 프롬프트 구성 (객관적 묘사와 주관적 인사이트 분리 강조)
    prompt_text = f"""당신은 10년 차 탑 바이럴 마케터입니다.
제공된 **'본문 사진/영상'**과 **'본문 텍스트'**를 분석하여, 다음 두 가지 관점에서 구조화된 분석 결과를 제공해 주세요.

1. **객관적 묘사 (Objective Description)**: 시각 매체(사진/영상)에 무엇이 찍혀 있는지, 어떤 상황인지 있는 그대로 객관적으로 설명하세요.
2. **마케팅 인사이트 (Marketing Insight)**: 이 사진/영상이 본문 텍스트와 어떤 시너지를 내고 있는지, 마케터로서 발견한 핵심 후킹 포인트와 유저가 반응할 만한 맥락은 무엇인지 분석하세요.

[분석 대상 데이터]
1. 본문 텍스트: {original_text}{product_section}

[출력 형식]
반드시 아래와 같은 JSON 형식으로만 답변하세요:
{{
  "objective_description": "사진/영상에 나타난 객관적인 상황 묘사 (1~2문장)",
  "marketing_insight": "마케터의 시각에서 도출한 핵심 소구점 및 맥락 분석 (1~2문장)"
}}
"""
    parts.append(prompt_text)

    # 미디어 처리 (본문 우선 순위)
    temp_files = [] # 로컬 임시 파일 추적용

    try:
        # 분석 후보군: 스레드 본문 미디어 -> 쿠팡 이미지 순서로 탐색
        candidate_urls = threads_images + (coupang_images if coupang_images else [])
        for path_or_url in candidate_urls:
            if not path_or_url: continue
            
            is_local = os.path.exists(str(path_or_url))
            path_or_url_lower = str(path_or_url).lower()
            is_video = any(v_ext in path_or_url_lower for v_ext in [".mp4", ".mov", ".avi", ".wmv", ".flv", ".m4v"])
            
            try:
                if is_local:
                    target_path = path_or_url
                    print(f"    > [로컬 미디어] {os.path.basename(target_path)} 사용")
                else:
                    # URL인 경우 다운로드
                    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                    r = requests.get(path_or_url, headers=headers, stream=True, timeout=10)
                    if r.status_code != 200: continue
                    
                    ct = r.headers.get("Content-Type", "").lower()
                    if "video" in ct: is_video = True
                    
                    suffix = ".mp4" if is_video else ".jpg"
                    if "image/png" in ct: suffix = ".png"
                    
                    tf = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                    if is_video:
                        for chunk in r.iter_content(chunk_size=8192):
                            tf.write(chunk)
                    else:
                        tf.write(r.content)
                    tf.close()
                    target_path = tf.name
                    temp_files.append(target_path)

                # Gemini File API 업로드
                mime = "video/mp4" if is_video else "image/jpeg"
                if target_path.lower().endswith(".png"): mime = "image/png"
                elif target_path.lower().endswith(".webp"): mime = "image/webp"

                print(f"    ⏳ {'영상' if is_video else '이미지'} 처리 중... ({os.path.basename(target_path)})")
                uploaded_file = client.files.upload(file=target_path)
                
                if is_video:
                    if wait_for_file_active(client, uploaded_file):
                        parts.append(uploaded_file)
                        print(f"    ✅ 영상 분석 준비 완료")
                        break # 영상은 1개로 제한
                else:
                    parts.append(uploaded_file)
                    print(f"    ✅ 이미지 분석 준비 완료")
                    if len(parts) >= 4: # 프롬프트(1) + 미디어(3) = 총 4개 파트 제한
                        break

            except Exception as e:
                print(f"    ⚠️ 미디어 처리 중 오류 ({path_or_url[:30]}): {e}")
                continue

        if len(parts) <= 1: # 프롬프트만 있는 경우
            print("    ⚠️ 분석 가능한 미디어를 찾지 못했습니다. (텍스트로만 분석 진행)")
                 
        start_time = time.time()
        print(f"    > LLM 구조화 분석 API 호출 중... (Model: {model_name})")
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=parts,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
        except Exception as e:
            # 설정된 모델로 실패 시 로그 남기고 예외 발생
            print(f"    ⚠️ {model_name} 분석 실패: {e}")
            raise e
        
        # JSON 결과 파싱
        try:
            res_json = json.loads(response.text)
            objective = res_json.get("objective_description", "")
            insight = res_json.get("marketing_insight", "")
        except:
            print("    ⚠️ JSON 파싱 실패, 텍스트 분석 시도...")
            full_text = response.text.strip()
            objective = product_name
            insight = full_text

        print(f"    ✅ 분석 완료 ({time.time() - start_time:.1f}초)")
        print(f"      - 객관적 묘사: {objective[:40]}...")
        print(f"      - 마케팅 인사이트: {insight[:40]}...")

        return {"objective_description": objective, "marketing_insight": insight}

    except Exception as e:
        print(f"    ❌ 마케팅 소구점 추출 실패: {e}")
        return {"objective_description": product_name, "marketing_insight": "마케팅 분석 실패"}
    finally:
        # 로컬 임시 파일 삭제
        for tf_name in temp_files:
            try:
                if os.path.exists(tf_name):
                    os.remove(tf_name)
            except Exception:
                pass

if __name__ == "__main__":
    try:
        from app_config import GEMINI_API_KEY
        client = genai.Client(api_key=GEMINI_API_KEY)
        test_product = "맥도날드 베이컨 토마토 디럭스 세트"
        test_orig = ""
        test_desc = "점심시간에 회사 동료들과 햄버거를 먹으며 즐거워하는 활기찬 분위기의 영상입니다."
        test_img = ["https://upload.wikimedia.org/wikipedia/commons/thumb/4/44/Hamburger_with_cheese.jpg/800px-Hamburger_with_cheese.jpg"]
        
        result = extract_marketing_focus(client, "gemini-3-flash-preview", test_product, test_orig, test_img, user_description=test_desc)
        print("\n--- 결과 ---")
        print(result)
    except Exception as e:
        print(f"테스트 실패: {e}")
