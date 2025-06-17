import os
import json
import sys
from posture_analyzer import analyze_video_file

def test_posture_analyzer():
    """자세 분석 모듈 단독 테스트"""
    print("🧪 Testing Posture Analyzer Module")
    print("=" * 40)
    
    # 테스트 비디오 파일 찾기
    test_videos = [
        "test.mp4",
    ]
    
    video_path = None
    for video in test_videos:
        if os.path.exists(video):
            video_path = video
            break
    
    if video_path:
        print(f"📹 Found test video: {video_path}")
        try:
            print("🔄 Starting analysis...")
            result = analyze_video_file(video_path)
            
            print("✅ Analysis completed!")
            print("\n📊 Results:")
            print(json.dumps(result, ensure_ascii=False, indent=2))
            
            # 결과를 파일로 저장
            output_file = f"analysis_result_{os.path.splitext(os.path.basename(video_path))[0]}.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"\n💾 Results saved to: {output_file}")
            
        except Exception as e:
            print(f"❌ Analysis failed: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("⚠️ No test video found.")

if __name__ == "__main__":
    test_posture_analyzer()