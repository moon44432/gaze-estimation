import httpx
import asyncio
import json
import time
import os
from typing import Dict, Any

class PostureAPITester:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        
    async def test_health(self) -> bool:
        """서버 상태 확인"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/health")
                result = response.json()
                print("🏥 Health Check:")
                print(json.dumps(result, indent=2))
                return response.status_code == 200
        except Exception as e:
            print(f"❌ Health check failed: {e}")
            return False
    
    async def test_basic_endpoints(self):
        """기본 엔드포인트 테스트"""
        try:
            async with httpx.AsyncClient() as client:
                # 루트 엔드포인트
                response = await client.get(f"{self.base_url}/")
                print("🏠 Root endpoint:")
                print(json.dumps(response.json(), indent=2))
                
                # 분석 목록
                response = await client.get(f"{self.base_url}/analyses")
                print("\n📋 Analyses list:")
                print(json.dumps(response.json(), indent=2))
                
        except Exception as e:
            print(f"❌ Basic endpoint test failed: {e}")
    
    async def test_video_analysis(self, project_id: str, video_url: str):
        """비디오 분석 테스트"""
        try:
            print(f"\n🎬 Testing video analysis for project: {project_id}")
            
            # 분석 요청
            request_data = {
                "project_id": project_id,
                "video_url": video_url,
                "callback_url": None  # 콜백 없이 테스트
            }
            
            async with httpx.AsyncClient() as client:
                # 1. 분석 시작
                response = await client.post(f"{self.base_url}/analyze", json=request_data)
                if response.status_code != 200:
                    print(f"❌ Analysis start failed: {response.text}")
                    return
                
                start_result = response.json()
                print("🚀 Analysis started:")
                print(json.dumps(start_result, indent=2))
                
                # 2. 상태 모니터링
                max_wait_time = 300  # 최대 5분 대기
                start_time = time.time()
                
                while time.time() - start_time < max_wait_time:
                    # 상태 확인
                    status_response = await client.get(f"{self.base_url}/status/{project_id}")
                    if status_response.status_code != 200:
                        print(f"❌ Status check failed: {status_response.text}")
                        break
                        
                    status_data = status_response.json()
                    print(f"📊 Progress: {status_data['progress']}% - {status_data['message']}")
                    
                    if status_data["status"] == "completed":
                        print("✅ Analysis completed!")
                        
                        # 3. 결과 조회
                        result_response = await client.get(f"{self.base_url}/result/{project_id}")
                        if result_response.status_code == 200:
                            result_data = result_response.json()
                            print("🎯 Analysis results:")
                            print(json.dumps(result_data, ensure_ascii=False, indent=2))
                        else:
                            print(f"❌ Failed to get results: {result_response.text}")
                        break
                        
                    elif status_data["status"] == "failed":
                        print(f"❌ Analysis failed: {status_data['message']}")
                        break
                    
                    await asyncio.sleep(5)  # 5초마다 상태 확인
                else:
                    print("⏰ Analysis timed out")
                    
        except Exception as e:
            print(f"❌ Video analysis test failed: {e}")
    
    async def test_with_local_video(self, video_path: str):
        """로컬 비디오 파일로 테스트"""
        if not os.path.exists(video_path):
            print(f"❌ Video file not found: {video_path}")
            return
        
        # 파일을 HTTP 서버로 임시 제공 (실제로는 클라우드 스토리지 URL 사용)
        print("⚠️ For local testing, you need to serve the video file via HTTP")
        print(f"   You can use: python -m http.server 8080")
        print(f"   Then use URL: http://localhost:8080/{os.path.basename(video_path)}")

async def main():
    """메인 테스트 함수"""
    tester = PostureAPITester()
    
    print("🧪 Starting Posture Analysis API Tests")
    print("=" * 50)
    
    # 1. 서버 상태 확인
    if not await tester.test_health():
        print("❌ Server is not healthy. Please start the server first.")
        return
    
    # 2. 기본 엔드포인트 테스트
    await tester.test_basic_endpoints()
    
    # 3. 샘플 비디오로 분석 테스트
    sample_videos = [
        # 공개 샘플 비디오들 (테스트용)
        "https://sample-videos.com/zip/10/mp4/SampleVideo_720x480_1mb.mp4",
        "https://www.learningcontainer.com/wp-content/uploads/2020/05/sample-mp4-file.mp4",
    ]
    
    for i, video_url in enumerate(sample_videos):
        project_id = f"test-project-{i+1}"
        print(f"\n{'='*50}")
        print(f"Testing with video {i+1}: {video_url}")
        
        try:
            await tester.test_video_analysis(project_id, video_url)
        except Exception as e:
            print(f"⚠️ Skipping video {i+1} due to error: {e}")
    
    print("\n🎉 Tests completed!")

if __name__ == "__main__":
    asyncio.run(main())