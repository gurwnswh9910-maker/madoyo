import os
import time
import requests

def upload_to_threads(user_id, access_token, text, image_urls=None, reply_text=None, reply_image_url=None):
    """
    Threads API를 통해 게시물을 업로드합니다.
    이미지가 없으면 텍스트만, 이미지가 있으면 단일/슬라이드 게시물로 업로드합니다.
    """
    if not user_id or not access_token:
        raise ValueError("Threads User ID와 Access Token이 필요합니다.")
        
    base_url = "https://graph.threads.net/v1.0"
    
    # 1. 미디어 컨테이너 생성
    creation_url = f"{base_url}/{user_id}/threads"
    
    print(f"▶️ 1단계: 미디어 컨테이너 생성 중 (총 {len(image_urls) if image_urls else 0}개 미디어)")
    
    # 본문 업로드 흐름 (기본 로직 유지)
    if not image_urls:
        payload = {"media_type": "TEXT", "text": text, "access_token": access_token}
        resp = requests.post(creation_url, data=payload)
    elif len(image_urls) == 1:
        media_type = "VIDEO" if any(ext in image_urls[0].lower() for ext in ['.mp4', '.mov']) else "IMAGE"
        payload = {"media_type": media_type, "text": text, "access_token": access_token}
        if media_type == "VIDEO": payload["video_url"] = image_urls[0]
        else: payload["image_url"] = image_urls[0]
        resp = requests.post(creation_url, data=payload)
    else:
        # Carousel 로직
        item_ids = []
        for idx, url in enumerate(image_urls):
            if idx >= 10: break
            media_type = "VIDEO" if any(ext in url.lower() for ext in ['.mp4', '.mov']) else "IMAGE"
            item_payload = {"media_type": media_type, "is_carousel_item": "true", "access_token": access_token}
            if media_type == "VIDEO": item_payload["video_url"] = url
            else: item_payload["image_url"] = url
            
            item_res = requests.post(creation_url, data=item_payload)
            if item_res.status_code == 200:
                iid = item_res.json().get('id')
                item_ids.append(iid)
                print(f"    - 슬라이드 항목 #{idx+1} 생성 성공 (ID: {iid})")
            else:
                print(f"    ⚠️ 슬라이드 항목 #{idx+1} 생성 실패: {item_res.json()}")
        
        if not item_ids:
            print("    ⚠️ 생성된 슬라이드 항목이 없습니다. 텍스트 게시물로 전환합니다.")
            payload = {"media_type": "TEXT", "text": text, "access_token": access_token}
            resp = requests.post(creation_url, data=payload)
        elif len(item_ids) == 1:
            print("    ⚠️ 슬라이드 항목이 1개뿐입니다. 단일 이미지 게시물로 전환합니다.")
            media_type = "VIDEO" if any(ext in image_urls[0].lower() for ext in ['.mp4', '.mov']) else "IMAGE"
            payload = {"media_type": media_type, "text": text, "access_token": access_token}
            if media_type == "VIDEO": payload["video_url"] = image_urls[0]
            else: payload["image_url"] = image_urls[0]
            resp = requests.post(creation_url, data=payload)
        else:
            # 폴링 대기 (모든 자식 컨테이너가 FINISHED 상태여야 부모 생성이 안정적임)
            unfinished = list(item_ids)
            waited = 0
            print(f"    - {len(item_ids)}개 자식 컨테이너 처리 대기 중...", end="", flush=True)
            while unfinished and waited < 60: # 90초는 너무 길어 60초로 조정
                time.sleep(5)
                waited += 5
                still_pending = []
                for item_id in unfinished:
                    try:
                        st_resp = requests.get(f"{base_url}/{item_id}?fields=status&access_token={access_token}")
                        if st_resp.json().get("status") not in ("FINISHED", "PUBLISHED"): 
                            still_pending.append(item_id)
                    except: 
                        still_pending.append(item_id)
                unfinished = still_pending
                print(".", end="", flush=True)
            print(" 완료!")
                
            payload = {"media_type": "CAROUSEL", "children": ",".join(item_ids), "text": text, "access_token": access_token}
            resp = requests.post(creation_url, data=payload)

    if resp.status_code != 200:
        print(f"❌ 컨테이너 생성 실패: {resp.json()}")
        if "children" in payload:
            print(f"    (사용된 children ID 목록: {payload['children']})")
        return False
        
    creation_id = resp.json().get("id")
    time.sleep(30) # 서버 처리 대기
    
    # 2. 미디어 컨테이너 게시
    publish_url = f"{base_url}/{user_id}/threads_publish"
    pub_resp = requests.post(publish_url, data={"creation_id": creation_id, "access_token": access_token})
    if pub_resp.status_code != 200:
        print(f"❌ 게시물 업로드 실패: {pub_resp.json()}")
        return False
        
    media_id = pub_resp.json().get("id")
    print(f"🎉 성공! Threads에 업로드 완료 (Media ID: {media_id})")
    
    # 3. 쿠팡 파트너스 답글(댓글) 달기
    if not reply_text:
        reply_text = "이 포스팅은 쿠팡파트너스 활동의 일환으로 일정액의 수수료를 지급받습니다"
        
    print(f"▶️ 3단계: 파트너스 답글 작성 중...")
    
    # 답글 컨테이너 생성
    if reply_image_url:
        reply_media_type = "VIDEO" if any(ext in reply_image_url.lower() for ext in ['.mp4', '.mov']) else "IMAGE"
        reply_payload = {
            "media_type": reply_media_type,
            "text": reply_text,
            "reply_to_id": media_id,
            "access_token": access_token
        }
        if reply_media_type == "VIDEO": reply_payload["video_url"] = reply_image_url
        else: reply_payload["image_url"] = reply_image_url
    else:
        reply_payload = {
            "media_type": "TEXT",
            "text": reply_text,
            "reply_to_id": media_id,
            "access_token": access_token
        }
        
    reply_creation_resp = requests.post(creation_url, data=reply_payload)
    if reply_creation_resp.status_code == 200:
        reply_creation_id = reply_creation_resp.json().get("id")
        # 이미지/비디오 처리 시간 확보 (기존 10초 -> 20초로 상향)
        wait_time = 20 if reply_image_url else 3
        print(f"    - 컨테이너 생성 완료 (ID: {reply_creation_id}), {wait_time}초 대기...")
        time.sleep(wait_time)
        reply_pub_resp = requests.post(publish_url, data={"creation_id": reply_creation_id, "access_token": access_token})
        if reply_pub_resp.status_code == 200:
             print("🎉 성공! 파트너스 답글 업로드 완료")
        else:
             print(f"❌ 답글 업로드 실패: {reply_pub_resp.json()}")
    else:
        print(f"❌ 답글 컨테이너 생성 실패: {reply_creation_resp.json()}")

    return True
