# simple_web_test.py
import requests
import json
import time

# 서버 상태 확인
response = requests.get("http://localhost:8000/health")
print("Health:", response.json())

# 로컬 파일 분석 (파일이 프로젝트 폴더에 있는 경우)
analyze_data = {
    "project_id": "simple-test",
    "video_path": "test.mp4"  # 실제 파일명으로 변경
}

response = requests.post("http://localhost:8000/analyze-file", json=analyze_data)
print("Analysis started:", response.json())

# 결과 확인
project_id = "simple-test"
while True:
    response = requests.get(f"http://localhost:8000/status/{project_id}")
    status = response.json()
    print(f"Progress: {status['progress']}%")
    
    if status["status"] == "completed":
        response = requests.get(f"http://localhost:8000/result/{project_id}")
        print("Result:", json.dumps(response.json(), indent=2))
        break
    elif status["status"] == "failed":
        print("Failed:", status["message"])
        break
    
    time.sleep(3)