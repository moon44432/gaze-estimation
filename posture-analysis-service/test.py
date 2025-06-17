import requests
import json
import time

def quick_test(video_url, server_url="http://localhost:8000"):
    """빠른 테스트 함수"""
    
    print(f"🧪 Quick Test: {video_url}")
    
    # 서비스 상태 확인
    try:
        health_response = requests.get(f"{server_url}/health", timeout=5)
        if health_response.status_code != 200:
            print("❌ Service not healthy")
            return
    except:
        print("❌ Cannot connect to service")
        return
    
    # 분석 요청
    request_data = {
        "project_id": f"quick_test_{int(time.time())}",
        "video_url": video_url
    }
    
    print("🔄 Analyzing video...")
    start_time = time.time()
    
    try:
        response = requests.post(f"{server_url}/analysis/action", json=request_data, timeout=300)
        
        if response.status_code == 200:
            result = response.json()
            elapsed = time.time() - start_time
            
            print(f"✅ Success! ({elapsed:.1f}s)")
            print(f"Bad postures: {result.get('totalBadPostures', 0)}")
            print(f"Duration: {result.get('totalDurationSeconds', 0):.1f}s")
            print(f"Actions detected: {len(result.get('detectedActions', []))}")
            
            return result
        else:
            print(f"❌ Failed: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    # 테스트할 비디오 URL들
    test_urls = [
        "https://sample-videos.com/zip/10/mp4/SampleVideo_720x480_1mb.mp4",
        "https://www.learningcontainer.com/wp-content/uploads/2020/05/sample-mp4-file.mp4"
    ]
    
    for url in test_urls:
        quick_test(url)
        print("-" * 50)