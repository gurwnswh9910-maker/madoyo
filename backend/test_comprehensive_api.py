import requests
import json
import time

API_BASE_URL = "https://madoyo-api.onrender.com/api"

def test_api_case(name, payload):
    print(f"\n--- Testing Case: {name} ---")
    generate_url = f"{API_BASE_URL}/generate"
    
    try:
        # 1. POST Request
        resp = requests.post(generate_url, json=payload, timeout=30)
        print(f"POST Status: {resp.status_code}")
        data = resp.json()
        task_id = data.get("task_id")
        print(f"Task ID: {task_id}")
        
        if not task_id:
            return {"name": name, "status": "ERROR", "error": f"No task_id: {data}"}
            
        # 2. Polling
        print("Polling for results...")
        final_status = "PENDING"
        result = None
        error = None
        
        for i in range(12): # 12 * 10s = 120s max
            time.sleep(10)
            status_url = f"{API_BASE_URL}/tasks/{task_id}"
            st_resp = requests.get(status_url)
            st_data = st_resp.json()
            status = st_data.get("status")
            print(f"[{ (i+1)*10 }s] Status: {status}")
            
            if status in ("SUCCESS", "FAILURE"):
                final_status = status
                result = st_data.get("result")
                error = st_data.get("error")
                break
        
        return {
            "name": name,
            "payload": payload,
            "task_id": task_id,
            "status": final_status,
            "result": result,
            "error": error
        }
    except Exception as e:
        return {"name": name, "status": "EXCEPTION", "error": str(e)}

def main():
    test_cases = [
        {
            "name": "Text Only",
            "payload": {
                "reference_copy": "이것은 인공지능 카피 테스트입니다. 감성적이고 세련된 톤으로 바꿔주세요."
            }
        },
        {
            "name": "Media (Image) Only",
            "payload": {
                "image_urls": ["https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=500&q=80"] # 헤드폰 이미지
            }
        },
        {
            "name": "URL (Threads) Only",
            "payload": {
                "reference_url": ["https://www.threads.net/@_seheehx_/post/DVq9D18FUQi"]
            }
        }
    ]
    
    reports = []
    for case in test_cases:
        reports.append(test_api_case(case["name"], case["payload"]))
        
    # Write report to markdown
    report_file = "api_comprehensive_test_report.md"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write("# API 종합 테스트 결과 보고서\n\n")
        f.write(f"테스트 일시: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        for r in reports:
            f.write(f"## {r['name']}\n")
            if r.get('task_id'):
                f.write(f"- **Task ID**: `{r['task_id']}`\n")
            f.write(f"- **최종 상태**: `{r.get('status', 'UNKNOWN')}`\n")
            if r.get('error'):
                f.write(f"- **오류 내용**: {r['error']}\n")
            if r.get('result'):
                f.write("- **생성 결과 (상위 1개)**:\n")
                copies = r['result'].get("copies", [])
                if copies and len(copies) > 0:
                    f.write(f"  - {copies[0].get('copy_text', 'No text')}\n")
                    f.write(f"  - 전략: {copies[0].get('strategy', 'No strategy')}\n")
            f.write("\n---\n\n")
            
    print(f"\nReport generated: {report_file}")

if __name__ == "__main__":
    main()
