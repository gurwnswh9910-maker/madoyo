import time
from datetime import datetime, timedelta
import subprocess
import sys
import os
import io

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.detach(), encoding="utf-8")

def get_target_time():
    now = datetime.now()
    # 6시 정각 설정
    target_hour = int(os.getenv("SCHEDULE_TARGET_HOUR", "6"))
    target_minute = int(os.getenv("SCHEDULE_TARGET_MINUTE", "30"))
    target = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    
    # 이미 6시가 지났다면 다음날 6시로 설정
    if now >= target:
        target += timedelta(days=1)
        
    return target

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    target_time = get_target_time()
    print("==================================================")
    print("⏰ 쓰레드 '자동화 파이프라인' 예약 대기 스크립트")
    print(f"✅ 목표 실행 시간: {target_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("⚠️ 주의: 이 창을 닫으면 예약 자동화가 취소됩니다!")
    print("==================================================")
    
    while True:
        now = datetime.now()
        if now >= target_time:
            print("\n🚀 목표 시간에 도달했습니다! 전체 자동화 파이프라인을 시작합니다...\n")
            break
            
        remaining = target_time - now
        hours, remainder = divmod(remaining.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        sys.stdout.write(f"\r⏳ 남은 시간: {hours}시간 {minutes:02d}분 {seconds:02d}초 (현재 시간: {now.strftime('%H:%M:%S')})  ")
        sys.stdout.flush()
        
        time.sleep(1)
        
    command = [
        sys.executable,
        os.path.join(script_dir, "threads_auto_pipeline.py"),
    ]
    
    print(f"\n실행 명령어: {' '.join(command)}\n")
    print("==================================================")
    
    try:
        # subprocess.run을 사용하여 현재 터미널에서 실행 로그가 보이도록 함
        result = subprocess.run(command, cwd=script_dir)
        print(f"\n✅ 자동화 파이프라인 프로세스가 종료되었습니다. (종료 코드: {result.returncode})")
    except Exception as e:
        print(f"\n❌ 스크립트 실행 중 오류 발생: {e}")

if __name__ == "__main__":
    main()
