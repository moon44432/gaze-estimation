import os
import sys
import threading
import time
import socketserver
import http.server
from urllib.parse import quote
import subprocess
import requests

class VideoFileServer:
    def __init__(self, directory=".", port=8080):
        self.directory = os.path.abspath(directory)
        self.port = port
        self.server = None
        self.thread = None
        
    def start_server(self):
        """HTTP 서버 시작"""
        os.chdir(self.directory)
        
        handler = http.server.SimpleHTTPRequestHandler
        
        try:
            self.server = socketserver.TCPServer(("", self.port), handler)
            self.thread = threading.Thread(target=self.server.serve_forever)
            self.thread.daemon = True
            self.thread.start()
            
            print(f"🌐 Local video server started")
            print(f"📁 Serving directory: {self.directory}")
            print(f"🔗 Server URL: http://localhost:{self.port}")
            print(f"🎬 Video files available:")
            
            # 비디오 파일 목록 출력
            video_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv'}
            video_files = []
            
            for file in os.listdir(self.directory):
                if any(file.lower().endswith(ext) for ext in video_extensions):
                    video_files.append(file)
                    encoded_filename = quote(file)
                    print(f"   📹 {file}")
                    print(f"      URL: http://localhost:{self.port}/{encoded_filename}")
            
            if not video_files:
                print("   ⚠️ No video files found in directory")
            
            return True
            
        except OSError as e:
            if "Address already in use" in str(e):
                print(f"⚠️ Port {self.port} is already in use")
                return False
            else:
                print(f"❌ Failed to start server: {e}")
                return False
    
    def stop_server(self):
        """서버 중지"""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            print("🛑 Server stopped")
    
    def get_video_url(self, filename):
        """파일명을 URL로 변환"""
        encoded_filename = quote(filename)
        return f"http://localhost:{self.port}/{encoded_filename}"
    
    def test_server(self):
        """서버 연결 테스트"""
        try:
            response = requests.get(f"http://localhost:{self.port}", timeout=5)
            return response.status_code == 200
        except:
            return False

def find_available_port(start_port=8080):
    """사용 가능한 포트 찾기"""
    import socket
    
    for port in range(start_port, start_port + 100):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('localhost', port))
                return port
        except OSError:
            continue
    return None

def auto_serve_video(video_path):
    """비디오 파일을 자동으로 서빙하고 URL 반환"""
    
    if not os.path.exists(video_path):
        print(f"❌ Video file not found: {video_path}")
        return None
    
    # 절대 경로로 변환
    video_path = os.path.abspath(video_path)
    directory = os.path.dirname(video_path)
    filename = os.path.basename(video_path)
    
    # 사용 가능한 포트 찾기
    port = find_available_port()
    if not port:
        print("❌ No available ports found")
        return None
    
    print(f"🎬 Setting up server for video: {filename}")
    print(f"📁 Directory: {directory}")
    
    # 서버 시작
    server = VideoFileServer(directory, port)
    if server.start_server():
        # 서버가 시작될 때까지 잠시 대기
        time.sleep(1)
        
        # 서버 테스트
        if server.test_server():
            video_url = server.get_video_url(filename)
            print(f"✅ Video URL ready: {video_url}")
            return video_url, server
        else:
            print("❌ Server test failed")
            return None
    else:
        return None

def main():
    """메인 함수"""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python local_video_server.py <video_file>           # Auto-serve single video")
        print("  python local_video_server.py <directory> [port]     # Serve directory")
        print()
        print("Examples:")
        print("  python local_video_server.py video.mp4")
        print("  python local_video_server.py ./videos")
        print("  python local_video_server.py ./videos 8081")
        return
    
    path = sys.argv[1]
    
    if os.path.isfile(path):
        # 단일 파일 서빙
        result = auto_serve_video(path)
        if result:
            video_url, server = result
            print(f"\n💡 Use this URL in your analysis:")
            print(f"   {video_url}")
            print(f"\n🧪 Test with posture analysis:")
            print(f"   python test_posture_service.py \"{video_url}\"")
            print(f"\nPress Ctrl+C to stop the server")
            
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                server.stop_server()
        
    elif os.path.isdir(path):
        # 디렉토리 서빙
        port = int(sys.argv[2]) if len(sys.argv) > 2 else 8080
        
        server = VideoFileServer(path, port)
        if server.start_server():
            print(f"\nPress Ctrl+C to stop the server")
            
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                server.stop_server()
    else:
        print(f"❌ Path not found: {path}")

if __name__ == "__main__":
    main()
