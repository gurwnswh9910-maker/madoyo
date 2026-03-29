import requests
import sys

def check_status():
    headers = {
        'Authorization': 'Bearer rnd_lhSqIrcpHns4mPQvr0vKqZs6IzyB',
        'Accept': 'application/json'
    }
    svc_id = 'srv-d6moqo450q8c73annt00'
    url = f'https://api.render.com/v1/services/{svc_id}/deploys?limit=1'
    
    try:
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        data = r.json()
        if not data:
            print("No deploys found.")
            return
            
        deploy = data[0]['deploy']
        status = deploy['status']
        commit_id = deploy['commit']['id']
        created_at = deploy['createdAt']
        
        print(f"--- Render Deploy Status ---")
        print(f"ID: {deploy['id']}")
        print(f"STATUS: {status}")
        print(f"COMMIT: {commit_id}")
        print(f"CREATED_AT: {created_at}")
        print("-" * 30)
        
    except Exception as e:
        print(f"ERROR checking status: {e}")

if __name__ == "__main__":
    check_status()
