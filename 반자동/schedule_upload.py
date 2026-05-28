import time
from datetime import datetime, timedelta
import subprocess
import sys
from pathlib import Path

def get_target_time():
    now = datetime.now()
    # Set target to 6:00 AM
    target = now.replace(hour=6, minute=0, second=0, microsecond=0)
    
    # If it's already past 6:00 AM today, schedule for tomorrow
    if now >= target:
        target += timedelta(days=1)
        
    return target

def main():
    script_dir = Path(__file__).resolve().parent
    target_time = get_target_time()
    print("==================================================")
    print("⏰ 쓰레드 예약 업로드 대기 스크립트 실행")
    print(f"✅ 목표 실행 시간: {target_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("⚠️ 주의: 이 창을 닫으면 예약 업로드가 취소됩니다!")
    print("==================================================")
    
    while True:
        now = datetime.now()
        if now >= target_time:
            print("\n🚀 목표 시간에 도달했습니다! 업로드를 시작합니다...\n")
            break
            
        remaining = target_time - now
        hours, remainder = divmod(remaining.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        sys.stdout.write(f"\r⏳ 남은 시간: {hours}시간 {minutes:02d}분 {seconds:02d}초 (현재 시간: {now.strftime('%H:%M:%S')})  ")
        sys.stdout.flush()
        
        # Sleep short intervals to be responsive and immune to system sleep issues
        time.sleep(1)
        
    # Execute the actual upload command
    command = [
        sys.executable,
        str(script_dir / "semi_auto_publish.py"),
        "--input-excel",
        str(script_dir / "반자동참조" / "final_ready_to_upload.xlsx"),
        "--hours",
        "1.5",
        "--move-done"
    ]
    
    print(f"\n실행 명령어: {' '.join(command)}\n")
    print("==================================================")
    
    try:
        # Use subprocess.run to execute it visibly in the current terminal
        result = subprocess.run(command, cwd=script_dir)
        print(f"\n✅ 예약 업로드 프로세스가 종료되었습니다. (종료 코드: {result.returncode})")
    except Exception as e:
        print(f"\n❌ 스크립트 실행 중 오류 발생: {e}")

if __name__ == "__main__":
    main()
