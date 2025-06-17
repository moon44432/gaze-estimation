import sys
import importlib
import os

def check_package(package_name, import_name=None):
    """패키지 설치 여부 확인"""
    try:
        importlib.import_module(import_name or package_name)
        return True, "✅"
    except ImportError:
        return False, "❌"

def check_file(file_path, description):
    """파일 존재 여부 확인"""
    exists = os.path.exists(file_path)
    return exists, "✅" if exists else "❌"

def main():
    """의존성 및 환경 체크"""
    print("🔍 Checking Dependencies and Environment")
    print("=" * 50)
    
    # 파이썬 버전 확인
    print(f"🐍 Python Version: {sys.version}")
    
    print("\n📦 Python Packages:")
    packages = [
        ("fastapi", "fastapi"),
        ("uvicorn", "uvicorn"),
        ("pydantic", "pydantic"),
        ("httpx", "httpx"),
        ("opencv-python", "cv2"),
        ("torch", "torch"),
        ("torchvision", "torchvision"),
        ("ultralytics", "ultralytics"),
        ("numpy", "numpy"),
    ]
    
    all_packages_ok = True
    for package, import_name in packages:
        ok, status = check_package(package, import_name)
        print(f"  {status} {package}")
        if not ok:
            all_packages_ok = False
    
    print("\n📁 Required Files:")
    files = [
        ("config.py", "Configuration file"),
        ("utils/helpers.py", "Helper functions"),
        ("weights/mobilenetv2.pt", "Model weights"),
        ("uniface.py", "Face detection module (or __init__.py)"),
    ]
    
    all_files_ok = True
    for file_path, description in files:
        ok, status = check_file(file_path, description)
        print(f"  {status} {file_path} - {description}")
        if not ok:
            all_files_ok = False
    
    print("\n📂 Directories:")
    directories = ["weights", "temp", "logs", "utils"]
    for directory in directories:
        ok, status = check_file(directory, f"{directory} directory")
        print(f"  {status} {directory}/")
    
    print("\n" + "=" * 50)
    if all_packages_ok and all_files_ok:
        print("🎉 All dependencies and files are ready!")
        print("💡 You can now run: start_server.bat")
    else:
        print("⚠️ Some dependencies or files are missing.")
        if not all_packages_ok:
            print("📝 Install missing packages: pip install -r requirements.txt")
        if not all_files_ok:
            print("📁 Copy missing files from your original project")

if __name__ == "__main__":
    main()