"""tmpfiles에서 mp4 Content-Type 헤더 확인"""
import requests

# 이전 로그에서 확인된 실제 URL 패턴 (만료됐을 수 있으므로 헤더만 체크)
# 실제 파이프라인에서 쓰이는 Threads 동영상 URL도 테스트
test_urls = [
    "https://tmpfiles.org/dl/29783324/tmpibussso3.mp4",  # 이전 드라이런의 동영상
]

for url in test_urls:
    print(f"\nURL: {url}")
    try:
        r = requests.head(url, timeout=10, allow_redirects=True)
        ct = r.headers.get("Content-Type", "")
        print(f"  Status: {r.status_code}")
        print(f"  Content-Type: {ct}")
        
        # suffix 결정 로직 (embedding_utils.py의 _upload_media와 동일)
        suffix = ".jpg"
        if "png" in ct.lower(): suffix = ".png"
        elif "webp" in ct.lower(): suffix = ".webp"
        # .mp4는 체크하지 않음!
        print(f"  → suffix would be: {suffix}")
        print(f"  → 동영상인데 .jpg로 저장될까? {'YES!' if 'video' in ct.lower() and suffix == '.jpg' else 'No'}")
    except Exception as e:
        print(f"  Error: {e}")

# 로컬 mimetypes 체크
import mimetypes
for ext in ['.mp4', '.jpg', '.png', '.webp']:
    mt, _ = mimetypes.guess_type(f"test{ext}")
    print(f"\nmimetypes.guess_type('test{ext}') → {mt}")
