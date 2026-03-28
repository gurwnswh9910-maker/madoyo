import pandas as pd
import requests
import json
import os
import time

def run_test():
    excel_path = r"c:\Users\ding9\Desktop\madoyo\데이터 참조\dotori.xlsx"
    api_url = "https://madoyo-api.onrender.com/api/generate"
    
    print(f"Reading Excel: {excel_path}")
    try:
        df = pd.read_excel(excel_path)
        urls = df['링크'].dropna().tolist()
        if not urls:
            print("No URLs found in Excel.")
            return
        
        sample_url = urls[0]
        print(f"Sample URL: {sample_url}")
        
        # Format matching GenerateRequest
        payload = {
            "reference_url": [sample_url]
        }
        
        print(f"Sending request to {api_url} ...")
        response = requests.post(api_url, json=payload, timeout=30)
        
        print(f"Status Code: {response.status_code}")
        try:
            result = response.json()
            print("Response JSON:")
            print(json.dumps(result, indent=2, ensure_ascii=False))
            
            task_id = result.get("task_id")
            if task_id:
                print(f"\nTask ID received: {task_id}")
                print("Polling for status...")
                for i in range(10):
                    time.sleep(5)
                    status_url = f"https://madoyo-api.onrender.com/api/tasks/{task_id}"
                    st_resp = requests.get(status_url)
                    st_data = st_resp.json()
                    print(f"[{ (i+1)*5 }s] Status: {st_data.get('status')}")
                    if st_data.get('status') in ("SUCCESS", "FAILURE"):
                        print("Final Result:")
                        print(json.dumps(st_data, indent=2, ensure_ascii=False))
                        break
        except Exception as e:
            print(f"Failed to parse JSON or poll: {e}")
            if 'st_resp' in locals():
                print(f"Raw status response: {st_resp.text}")
            else:
                print(f"Raw initial response: {response.text}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    run_test()
