import requests
import time
import os

with open("test_img.jpg", "wb") as f:
    f.write(os.urandom(1024 * 50))  # 50KB dummy image

print("Testing catbox.moe upload...")
for i in range(3):
    try:
        t0 = time.time()
        with open("test_img.jpg", "rb") as f:
            resp = requests.post(
                "https://catbox.moe/user/api.php", 
                data={"reqtype":"fileupload"}, 
                files={"fileToUpload": ("test_img.jpg", f)},
                timeout=15
            )
        print(f"[{i+1}] {resp.status_code} | {time.time()-t0:.2f}s | {resp.text}")
    except Exception as e:
        print(f"[{i+1}] Error: {e}")
