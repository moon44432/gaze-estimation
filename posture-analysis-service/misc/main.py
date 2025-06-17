# main.py - FastAPI 자세 분석 서버
from fastapi import FastAPI, HTTPException, BackgroundTasks, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import asyncio
import httpx
import logging
import os
import tempfile
import json
import uuid
import shutil
from datetime import datetime

# 자세 분석 모듈 import
try:
    from posture_analyzer import analyze_video_file
    ANALYZER_AVAILABLE = True
    print("✅ Posture analyzer loaded successfully")
except ImportError as e:
    ANALYZER_AVAILABLE = False
    print(f"⚠️ Posture analyzer not available: {e}")

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/server.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# FastAPI 앱 생성
app = FastAPI(
    title="Posture Analysis Service",
    description="AI-powered posture analysis for presentation videos",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS 설정 (개발 환경용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 데이터 모델들
class AnalysisRequest(BaseModel):
    project_id: str
    video_url: str
    callback_url: Optional[str] = None

class DirectAnalysisRequest(BaseModel):
    project_id: str
    video_path: str  # 로컬 파일 경로

class ActionPeriod(BaseModel):
    start_frame: int
    end_frame: int
    duration_frames: int
    duration_seconds: float

class ActionSummary(BaseModel):
    total_duration_seconds: float
    occurrence_count: int

class DetectedAction(BaseModel):
    action_name: str
    periods: List[ActionPeriod]
    summary: ActionSummary

class PostureEventResponse(BaseModel):
    project_id: str
    total_bad_postures: int
    total_duration_seconds: float
    detected_actions: List[DetectedAction]

class AnalysisStatus(BaseModel):
    project_id: str
    status: str  # "processing", "completed", "failed"
    progress: int  # 0-100
    message: Optional[str] = None
    result: Optional[PostureEventResponse] = None

# 전역 상태 저장소
analysis_status: Dict[str, AnalysisStatus] = {}

# 설정
TEMP_DIR = os.path.join(os.getcwd(), "temp")
UPLOAD_DIR = os.path.join(os.getcwd(), "uploads")

# 디렉토리 생성
for directory in [TEMP_DIR, UPLOAD_DIR, "logs"]:
    os.makedirs(directory, exist_ok=True)

@app.on_event("startup")
async def startup_event():
    """서버 시작 시 실행"""
    logger.info("🚀 Posture Analysis Service starting up...")
    logger.info(f"📁 Temp directory: {TEMP_DIR}")
    logger.info(f"📁 Upload directory: {UPLOAD_DIR}")
    logger.info(f"🔧 Analyzer available: {ANALYZER_AVAILABLE}")

@app.get("/")
async def root():
    """루트 엔드포인트 - 서비스 정보"""
    return {
        "service": "Posture Analysis Service",
        "status": "running",
        "version": "1.0.0",
        "analyzer_available": ANALYZER_AVAILABLE,
        "endpoints": {
            "health": "/health",
            "docs": "/docs", 
            "analyze_url": "/analyze",
            "analyze_file": "/analyze-file",
            "upload": "/upload",
            "status": "/status/{project_id}",
            "result": "/result/{project_id}",
            "analyses": "/analyses"
        }
    }

@app.get("/health")
async def health_check():
    """서버 상태 확인"""
    checks = {
        "service": "healthy",
        "analyzer_available": ANALYZER_AVAILABLE,
        "temp_dir": os.path.exists(TEMP_DIR),
        "upload_dir": os.path.exists(UPLOAD_DIR),
        "logs_dir": os.path.exists("logs"),
        "active_analyses": len(analysis_status)
    }
    
    status = "healthy" if all([checks["service"] == "healthy", checks["temp_dir"], checks["upload_dir"]]) else "warning"
    
    return {
        "status": status,
        "checks": checks,
        "timestamp": datetime.now().isoformat()
    }

@app.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    """비디오 파일 업로드"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    
    # 파일 확장자 확인
    allowed_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.webm'}
    file_extension = os.path.splitext(file.filename)[1].lower()
    
    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=400, 
            detail=f"Unsupported file format. Allowed: {', '.join(allowed_extensions)}"
        )
    
    # 안전한 파일명 생성
    safe_filename = f"{uuid.uuid4().hex}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, safe_filename)
    
    try:
        # 파일 저장
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        logger.info(f"📁 File uploaded: {safe_filename}")
        
        return {
            "message": "File uploaded successfully",
            "filename": safe_filename,
            "file_path": file_path,
            "file_size": os.path.getsize(file_path),
            "upload_time": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}")

@app.post("/analyze", response_model=Dict[str, str])
async def analyze_from_url(request: AnalysisRequest, background_tasks: BackgroundTasks):
    """URL에서 비디오를 다운로드하여 분석"""
    if not ANALYZER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Posture analyzer not available")
    
    logger.info(f"📥 Analysis request from URL for project: {request.project_id}")
    
    # 분석 상태 초기화
    analysis_status[request.project_id] = AnalysisStatus(
        project_id=request.project_id,
        status="processing",
        progress=0,
        message="Starting analysis from URL..."
    )
    
    # 백그라운드에서 분석 실행
    background_tasks.add_task(
        perform_url_analysis, 
        request.project_id, 
        request.video_url,
        request.callback_url
    )
    
    return {
        "message": "Analysis started successfully",
        "project_id": request.project_id,
        "status_url": f"/status/{request.project_id}",
        "result_url": f"/result/{request.project_id}"
    }

@app.post("/analyze-file", response_model=Dict[str, str])
async def analyze_from_file(request: DirectAnalysisRequest, background_tasks: BackgroundTasks):
    """로컬 파일을 직접 분석 (업로드된 파일 또는 로컬 경로)"""
    if not ANALYZER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Posture analyzer not available")
    
    # 파일 존재 확인
    video_path = request.video_path
    
    # 상대 경로인 경우 uploads 디렉토리에서 찾기
    if not os.path.isabs(video_path):
        potential_paths = [
            video_path,  # 현재 디렉토리
            os.path.join(UPLOAD_DIR, video_path),  # uploads 디렉토리
            os.path.join(os.getcwd(), video_path)  # 프로젝트 루트
        ]
        
        video_path = None
        for path in potential_paths:
            if os.path.exists(path):
                video_path = path
                break
        
        if not video_path:
            raise HTTPException(status_code=404, detail=f"Video file not found: {request.video_path}")
    
    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail=f"Video file not found: {video_path}")
    
    logger.info(f"📁 Analysis request from file for project: {request.project_id}")
    logger.info(f"📹 Video file: {video_path}")
    
    # 분석 상태 초기화
    analysis_status[request.project_id] = AnalysisStatus(
        project_id=request.project_id,
        status="processing",
        progress=0,
        message="Starting analysis from local file..."
    )
    
    # 백그라운드에서 분석 실행
    background_tasks.add_task(
        perform_file_analysis, 
        request.project_id, 
        video_path
    )
    
    return {
        "message": "Analysis started successfully",
        "project_id": request.project_id,
        "video_path": video_path,
        "status_url": f"/status/{request.project_id}",
        "result_url": f"/result/{request.project_id}"
    }

@app.get("/status/{project_id}", response_model=AnalysisStatus)
async def get_analysis_status(project_id: str):
    """분석 상태 조회"""
    if project_id not in analysis_status:
        raise HTTPException(status_code=404, detail="Analysis not found")
    
    return analysis_status[project_id]

@app.get("/result/{project_id}", response_model=PostureEventResponse)
async def get_analysis_result(project_id: str):
    """분석 결과 조회"""
    if project_id not in analysis_status:
        raise HTTPException(status_code=404, detail="Analysis not found")
    
    status = analysis_status[project_id]
    if status.status != "completed" or status.result is None:
        raise HTTPException(status_code=400, detail="Analysis not completed yet")
    
    return status.result

@app.get("/analyses")
async def list_analyses():
    """모든 분석 목록 조회"""
    analyses = []
    for project_id, status in analysis_status.items():
        analyses.append({
            "project_id": project_id,
            "status": status.status,
            "progress": status.progress,
            "message": status.message
        })
    
    return {
        "analyses": analyses,
        "count": len(analyses)
    }

@app.delete("/analysis/{project_id}")
async def delete_analysis(project_id: str):
    """분석 결과 삭제"""
    if project_id in analysis_status:
        del analysis_status[project_id]
        logger.info(f"🗑️ Deleted analysis for project: {project_id}")
        return {"message": "Analysis deleted successfully"}
    else:
        raise HTTPException(status_code=404, detail="Analysis not found")

@app.get("/uploads")
async def list_uploaded_files():
    """업로드된 파일 목록 조회"""
    try:
        files = []
        for filename in os.listdir(UPLOAD_DIR):
            file_path = os.path.join(UPLOAD_DIR, filename)
            if os.path.isfile(file_path):
                stat_info = os.stat(file_path)
                files.append({
                    "filename": filename,
                    "size": stat_info.st_size,
                    "created": datetime.fromtimestamp(stat_info.st_ctime).isoformat(),
                    "modified": datetime.fromtimestamp(stat_info.st_mtime).isoformat()
                })
        
        return {
            "files": files,
            "count": len(files),
            "upload_dir": UPLOAD_DIR
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list files: {str(e)}")

# 백그라운드 작업 함수들
async def perform_url_analysis(project_id: str, video_url: str, callback_url: Optional[str]):
    """URL에서 비디오 다운로드 후 분석"""
    try:
        logger.info(f"🌐 Starting URL analysis for project: {project_id}")
        
        # 상태 업데이트: 다운로드 시작
        analysis_status[project_id].progress = 10
        analysis_status[project_id].message = "Downloading video..."
        
        # 비디오 다운로드
        video_path = await download_video(video_url, project_id)
        
        # 파일 분석 실행
        await perform_file_analysis(project_id, video_path, is_temp_file=True)
        
    except Exception as e:
        logger.error(f"❌ URL analysis failed for project {project_id}: {str(e)}")
        analysis_status[project_id].status = "failed"
        analysis_status[project_id].progress = 100
        analysis_status[project_id].message = f"Analysis failed: {str(e)}"

async def perform_file_analysis(project_id: str, video_path: str, is_temp_file: bool = False):
    """로컬 파일 분석"""
    try:
        logger.info(f"🎬 Starting file analysis for project: {project_id}")
        
        # 상태 업데이트: 분석 시작
        analysis_status[project_id].progress = 30
        analysis_status[project_id].message = "Analyzing posture..."
        
        # 자세 분석 수행
        analysis_result = analyze_video_file(video_path)
        
        # 상태 업데이트: 결과 변환
        analysis_status[project_id].progress = 80
        analysis_status[project_id].message = "Converting results..."
        
        # 결과를 API 형식으로 변환
        posture_response = convert_to_api_format(project_id, analysis_result)
        
        # 임시 파일 정리
        if is_temp_file:
            try:
                os.unlink(video_path)
                logger.info(f"🧹 Cleaned up temporary file: {video_path}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to delete temp file: {e}")
        
        # 상태 업데이트: 완료
        analysis_status[project_id].status = "completed"
        analysis_status[project_id].progress = 100
        analysis_status[project_id].message = "Analysis completed successfully"
        analysis_status[project_id].result = posture_response
        
        logger.info(f"✅ Analysis completed for project: {project_id}")
        
    except Exception as e:
        logger.error(f"❌ File analysis failed for project {project_id}: {str(e)}")
        analysis_status[project_id].status = "failed"
        analysis_status[project_id].progress = 100
        analysis_status[project_id].message = f"Analysis failed: {str(e)}"

async def download_video(video_url: str, project_id: str) -> str:
    """비디오 다운로드"""
    try:
        logger.info(f"📡 Downloading video from: {video_url}")
        
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.get(video_url)
            response.raise_for_status()
            
            # 파일 확장자 결정
            suffix = '.mp4'
            content_type = response.headers.get('content-type', '')
            if 'webm' in content_type:
                suffix = '.webm'
            elif 'avi' in content_type:
                suffix = '.avi'
            elif 'mov' in content_type:
                suffix = '.mov'
            
            # 임시 파일 생성
            safe_project_id = "".join(c for c in project_id if c.isalnum() or c in ('-', '_'))
            temp_filename = f"video_{safe_project_id}_{uuid.uuid4().hex[:8]}{suffix}"
            temp_path = os.path.join(TEMP_DIR, temp_filename)
            
            # 파일 저장
            with open(temp_path, 'wb') as temp_file:
                temp_file.write(response.content)
            
            logger.info(f"💾 Video downloaded to: {temp_path}")
            return temp_path
            
    except Exception as e:
        raise Exception(f"Failed to download video: {str(e)}")

def convert_to_api_format(project_id: str, analysis_result: Dict[str, Any]) -> PostureEventResponse:
    """분석 결과를 API 응답 형식으로 변환"""
    
    detected_actions = []
    total_bad_postures = analysis_result["summary"]["total_bad_postures"]
    total_duration_seconds = analysis_result["summary"]["total_duration_seconds"]
    
    # 각 탐지된 동작을 API 형식으로 변환
    for action_key, action_data in analysis_result["detected_actions"].items():
        periods = []
        
        for period_data in action_data["periods"]:
            periods.append(ActionPeriod(
                start_frame=period_data["start_frame"],
                end_frame=period_data["end_frame"],
                duration_frames=period_data["duration_frames"],
                duration_seconds=period_data["duration_seconds"]
            ))
        
        summary = ActionSummary(
            total_duration_seconds=action_data["summary"]["total_duration_seconds"],
            occurrence_count=action_data["summary"]["occurrence_count"]
        )
        
        detected_actions.append(DetectedAction(
            action_name=action_data["action_name"],
            periods=periods,
            summary=summary
        ))
    
    return PostureEventResponse(
        project_id=project_id,
        total_bad_postures=total_bad_postures,
        total_duration_seconds=total_duration_seconds,
        detected_actions=detected_actions
    )

# 개발 환경에서만 사용
if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting FastAPI Posture Analysis Service...")
    print("📖 API Documentation: http://localhost:8000/docs")
    print("🏥 Health Check: http://localhost:8000/health")
    print("📁 File Upload: http://localhost:8000/docs#/default/upload_video_upload_post")
    
    uvicorn.run(
        app, 
        host="127.0.0.1", 
        port=8000, 
        reload=True,
        log_level="info"
    )