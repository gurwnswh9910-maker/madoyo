import os
import requests
import tempfile
import time
import json
from google import genai
from google.genai import types

# ✅ 서버 부팅 보호: 서버 환경에 따라 cv2(OpenCV) 로드 실패 시에도 서버가 죽지 않도록 방어
try:
    import cv2
    HAS_CV2 = True
except ImportError:
    print("⚠️ Warning: OpenCV (cv2) not found or system libraries missing. Video frame extraction disabled.")
    HAS_CV2 = False

def extract_frames(video_path, max_frames=5):
    """
    동영상에서 주요 프레임을 추출합니다. (OpenCV가 사용 가능할 때만 작동)
    """
    if not HAS_CV2:
        print("    ⚠️ OpenCV가 설치되지 않아 동영상 프레임 추출을 건너뜁니다.")
        return []

    frames_paths = []
    try:
        cap = cv2.VideoCapture(video_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            return []

        # 추출할 프레임 인덱스 계산 (균등 간격, 최소 1장 ~ 최대 max_frames장)
        num_to_extract = min(total_frames, max_frames)
        indices = [int(total_frames * i / num_to_extract) for i in range(num_to_extract)]
        
        for i, idx in enumerate(indices):
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            success, frame = cap.read()
            if success:
                # 임시 파일로 저장 (분석용)
                tf = tempfile.NamedTemporaryFile(delete=False, suffix=f"_frame_{i}.jpg")
                cv2.imwrite(tf.name, frame)
                frames_paths.append(tf.name)
                tf.close()
        cap.release()
    except Exception as e:
        print(f"    ⚠️ 프레임 추출 중 오류: {e}")
    return frames_paths

def extract_marketing_focus(client: genai.Client, model_name: str, product_name: str, original_text: str, threads_images: list, coupang_images: list = None) -> dict:
    """
    LLM 비전 모델을 사용하여 스레드 본문 이미지/동영상과 텍스트 간의 관계/맥락을 분석하고
    객관적 묘사와 마케팅 인사이트가 분리된 구조화된 데이터를 반환합니다.
    """
    print(f"  [전처리] 마케팅 소구점 및 맥락 분석 시작 (대상: {product_name[:30]}...)")
    
    parts = []
    
    # 프롬프트 구성 (객관적 묘사와 주관적 인사이트 분리 강조)
    prompt_text = f"""당신은 10년 차 탑 바이럴 마케터입니다.
제공된 **'본문 사진/영상'**과 **'본문 텍스트'**를 분석하여, 다음 두 가지 관점에서 구조화된 분석 결과를 제공해 주세요.

1. **객관적 묘사 (Objective Description)**: 시각 매체(사진/영상)에 무엇이 찍혀 있는지, 어떤 상황인지 있는 그대로 객관적으로 설명하세요.
2. **마케팅 인사이트 (Marketing Insight)**: 이 사진/영상이 본문 텍스트와 어떤 시너지를 내고 있는지, 마케터로서 발견한 핵심 후킹 포인트와 유저가 반응할 만한 맥락은 무엇인지 분석하세요.

[분석 대상 데이터]
1. 본문 텍스트: {original_text}
2. 공식 상품명(참고용): {product_name}

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
        
        for url in candidate_urls:
            if not url: continue
            
            url_lower = url.lower()
            is_video = any(v_ext in url_lower for v_ext in [".mp4", ".mov", ".avi", ".wmv", ".flv", ".m4v"])
            
            try:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                r = requests.get(url, headers=headers, stream=True, timeout=10)
                if r.status_code != 200: continue
                
                ct = r.headers.get("Content-Type", "").lower()
                if "video" in ct: is_video = True
                
                if is_video:
                    print(f"    > [동영상 감지] 프레임 추출을 통한 맥락 분석 진행 중... (URL: {url[:50]}...)")
                    v_tf = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
                    for chunk in r.iter_content(chunk_size=8192):
                        v_tf.write(chunk)
                    v_tf_path = v_tf.name
                    v_tf.close()
                    temp_files.append(v_tf_path)
                    
                    # 프레임 추출 (최대 5장)
                    frames = extract_frames(v_tf_path, max_frames=5)
                    for fp in frames:
                        with open(fp, "rb") as f:
                            img_bytes = f.read()
                        parts.append(types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"))
                        temp_files.append(fp)
                    
                    if frames:
                        print(f"    ✅ 동영상에서 {len(frames)}개의 핵심 장면 추출 완료 (인라인 분석)")
                        break 
                    else:
                        continue

                # 이미지인 경우
                if "image" in ct or any(i_ext in url_lower for i_ext in [".jpg", ".jpeg", ".png", ".webp"]):
                    img_bytes = r.content # [최적화] 즉시 바이트 추출
                    mime_type = ct if "image" in ct else "image/jpeg"
                    
                    parts.append(types.Part.from_bytes(data=img_bytes, mime_type=mime_type))
                    
                    is_threads_img = (url in threads_images)
                    print(f"    > 분석 대상 이미지 선정 (인라인): {'[본문 사진]' if is_threads_img else '[참고용 쿠팡 사진]'} {url[:50]}...")
                    break # 이미지 1장 선정 완료

            except Exception as e:
                print(f"    ⚠️ 미디어 확인 중 오류: {e}")
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
            # gemini-3-flash-preview 실패 시 gemini-2.5-flash로 자동 폴백
            if model_name == "gemini-3-flash-preview":
                print(f"    ⚠️ {model_name} 분석 실패 ({e}). gemini-2.5-flash로 재시도합니다...")
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=parts,
                    config=types.GenerateContentConfig(response_mime_type="application/json")
                )
            else:
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
        test_orig = "오늘 점심은 이거다!! 진짜 너무 맛있어 ㅠㅠ"
        test_img = ["https://upload.wikimedia.org/wikipedia/commons/thumb/4/44/Hamburger_with_cheese.jpg/800px-Hamburger_with_cheese.jpg"]
        
        result = extract_marketing_focus(client, "gemini-3-flash-preview", test_product, test_orig, test_img)
        print("\n--- 결과 ---")
        print(result)
    except Exception as e:
        print(f"테스트 실패: {e}")
