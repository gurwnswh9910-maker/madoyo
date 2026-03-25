import os
import sys
import time
import requests
import subprocess
import pandas as pd

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def run_test():
    # Read real URL from dotori.xlsx
    excel_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "데이터 참조", "dotori.xlsx")
    try:
        df = pd.read_excel(excel_path)
        link_col = [c for c in df.columns if '링크' in c][0]
        sample_url = str(df[link_col].dropna().iloc[0])
        print(f"Loaded Sample URL from dotori: {sample_url}")
    except Exception as e:
        print(f"Error reading dotori.xlsx: {e}")
        sample_url = "https://www.threads.net/@_food_jmt/post/DFXoXzGytkL"
        print(f"Using fallback URL: {sample_url}")

    # Start Server (DB not hit by /generate route!)
    print("Starting uvicorn server...")
    server_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=os.path.dirname(os.path.abspath(__file__)),
        stdout=sys.stdout,
        stderr=sys.stderr
    )
    time.sleep(6) # wait for startup

    try:
        # Make Request without token (the route is unsecured for some reason)
        headers = {}
        req_data = {
            "reference_url": sample_url
        }
        
        print("\nSending POST /api/generate ...")
        resp = requests.post("http://localhost:8000/api/generate", json=req_data, headers=headers)
        resp.raise_for_status()
        task_id = resp.json().get("task_id")
        print(f"Task ID: {task_id}")
        
        # Poll Status
        for i in range(40):
            time.sleep(3)
            st_resp = requests.get(f"http://localhost:8000/api/tasks/{task_id}", headers=headers)
            data = st_resp.json()
            status = data.get("status")
            print(f"[{i*3}s] Status: {status}")
            if status in ("SUCCESS", "FAILURE"):
                import json
                with open("result.json", "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                print("Result saved to result.json")
                break
    except Exception as e:
        print(f"Error during E2E: {e}")
    finally:
        print("Terminating server...")
        server_process.terminate()
        server_process.wait()
        print("Server terminated by test script.")

if __name__ == "__main__":
    run_test()
