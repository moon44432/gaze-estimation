import http.server
import socketserver
import os
import sys

def start_file_server(port=8080, directory="."):
    """간단한 HTTP 파일 서버 시작"""
    os.chdir(directory)
    
    handler = http.server.SimpleHTTPRequestHandler
    
    with socketserver.TCPServer(("", port), handler) as httpd:
        print(f"🌐 HTTP File Server started")
        print(f"📁 Serving directory: {os.getcwd()}")
        print(f"🔗 Server URL: http://localhost:{port}")
        print(f"📹 Video URLs will be: http://localhost:{port}/your-video.mp4")
        print("\n💡 Press Ctrl+C to stop the server")
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n🛑 Server stopped")

if __name__ == "__main__":
    port = 8080
    directory = "."
    
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            directory = sys.argv[1]
    
    if len(sys.argv) > 2:
        directory = sys.argv[2]
    
    start_file_server(port, directory)