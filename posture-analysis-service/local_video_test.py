import os
import sys
import subprocess
import time
import threading
import requests
from local_video_server import auto_serve_video

def one_command_test(video_path):
    """하나의 명령어로 서버 시작 + 분석 + 정리"""
    
    print("🚀 One-Command Local Video Analysis")
    print("=" * 50)
    
    # 1. 파일 존재 확인
    if not os.path.exists(video_path):
        print(f"❌ Video file not found: {video_path}")
        return False
    
    # 2. 자세 분석 서비스 확인
    print("🏥 Checking posture analysis service...")
    try:
        response = requests.get("http://localhost:8000/health", timeout=5)
        if response.status_code != 200:
            print("❌ Posture analysis service not running")
            print("💡 Please start it first: python main.py")
            return False
        print("✅ Posture analysis service is ready")
    except:
        print("❌ Cannot connect to posture analysis service")
        print("💡 Please start it first: python main.py")
        return False
    
    # 3. 로컬 서버 시작
    print(f"\n📁 Setting up local server for: {video_path}")
    result = auto_serve_video(video_path)
    if not result:
        return False
    
    video_url, server = result
    
    try:
        # 4. 분석 실행
        print(f"\n🔍 Running posture analysis...")
        
        project_id = f"one_cmd_{int(time.time())}"
        analysis_request = {
            "project_id": project_id,
            "video_url": video_url
        }
        
        start_time = time.time()
        response = requests.post(
            "http://localhost:8000/analysis/action",
            json=analysis_request,
            timeout=600
        )
        
        if response.status_code == 200:
            result_data = response.json()
            elapsed = time.time() - start_time
            
            print(f"✅ Analysis completed successfully!")
            print(f"⏱️  Processing time: {elapsed:.1f} seconds")
            print(f"📊 Results:")
            print(f"   Bad postures: {result_data.get('totalBadPostures', 0)}")
            print(f"   Total duration: {result_data.get('totalDurationSeconds', 0):.1f}s")
            print(f"   Actions detected: {len(result_data.get('detectedActions', []))}")
            
            # 상세 결과 출력
            for action in result_data.get('detectedActions', []):
                action_name = action.get('actionName', 'Unknown')
                occurrences = action.get('summary', {}).get('occurrenceCount', 0)
                duration = action.get('summary', {}).get('totalDurationSeconds', 0)
                print(f"   - {action_name}: {occurrences}회, {duration:.1f}초")
            
            # 결과 저장
            import json
            output_file = f"one_command_result_{project_id}.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(result_data, f, ensure_ascii=False, indent=2)
            print(f"\n💾 Full result saved to: {output_file}")
            
            return True
        else:
            print(f"❌ Analysis failed: {response.status_code}")
            print(f"Error: {response.text}")
            return False
            
    finally:
        # 5. 정리
        print(f"\n🧹 Cleaning up...")
        server.stop_server()
        print(f"✅ Local server stopped")

def main():
    if len(sys.argv) < 2:
        print("Usage: python one_command_test.py <video_file>")
        print()
        print("Examples:")
        print("  python one_command_test.py video.mp4")
        print("  python one_command_test.py ./videos/presentation.mp4")
        print("  python one_command_test.py \"C:\\Users\\Videos\\demo.mp4\"")
        print()
        print("Note: Make sure posture analysis service is running (python main.py)")
        return
    
    video_path = sys.argv[1]
    success = one_command_test(video_path)
    
    if success:
        print("\n🎉 One-command test completed successfully!")
    else:
        print("\n❌ One-command test failed!")

if __name__ == "__main__":
    main()