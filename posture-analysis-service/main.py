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

try:
    from posture_analyzer import analyze_video_file
    ANALYZER_AVAILABLE = True
except ImportError:
    ANALYZER_AVAILABLE = False

app = FastAPI(
    title="Posture Analysis Service",
    description="Simple posture analysis for presentation videos",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AnalysisRequest(BaseModel):
    project_id: str
    video_url: str

class LocalTestRequest(BaseModel):
    project_id: str
    video_path: str

class ActionPeriodResponse(BaseModel):
    startFrame: int
    endFrame: int
    durationSeconds: float

class ActionSummaryResponse(BaseModel):
    totalDurationSeconds: float
    occurrenceCount: int

class DetectedActionResponse(BaseModel):
    actionName: str
    periods: List[ActionPeriodResponse]
    summary: ActionSummaryResponse

class PostureEventResponse(BaseModel):
    projectId: str
    totalBadPostures: int
    totalDurationSeconds: float
    detectedActions: List[DetectedActionResponse]

analysis_results: Dict[str, PostureEventResponse] = {}

@app.get("/")
async def root():
    """서비스 정보"""
    return {
        "service": "Posture Analysis Service",
        "status": "running",
        "analyzer_available": ANALYZER_AVAILABLE,
        "endpoints": [
            "POST /analyze - 비디오 URL 분석",
            "GET /result/{project_id} - 분석 결과 조회", 
            "POST /analyze-local - 로컬 파일 테스트"
        ]
    }

@app.get("/health")
async def health_check():
    """서버 상태 확인"""
    return {
        "status": "healthy" if ANALYZER_AVAILABLE else "limited",
        "analyzer_available": ANALYZER_AVAILABLE,
        "stored_results": len(analysis_results)
    }

@app.post("/analyze", response_model=PostureEventResponse)
async def analyze_video_from_url(request: AnalysisRequest, background_tasks: BackgroundTasks):
    """
    백엔드에서 비디오 URL을 받아 분석하고 결과 반환
    백엔드의 POST /api/projects/{projectId}/video 이후 호출됨
    """
    if not ANALYZER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Analyzer not available")
    
    print(f"Starting analysis for project: {request.project_id}")
    print(f"Video URL: {request.video_url}")
    
    try:
        # 1. 비디오 다운로드
        print("Downloading video...")
        video_path = await download_video(request.video_url)
        
        # 2. 자세 분석
        print("Analyzing posture...")
        analysis_result = analyze_video_file(video_path)
        
        # 3. 백엔드 API 형식으로 변환
        posture_response = convert_to_backend_format(request.project_id, analysis_result)
        
        # 4. 결과 저장 (백엔드에서 나중에 조회할 수 있도록)
        analysis_results[request.project_id] = posture_response
        
        # 5. 임시 파일 정리
        os.unlink(video_path)
        
        print(f"Analysis completed for project: {request.project_id}")
        return posture_response
        
    except Exception as e:
        print(f"Analysis failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@app.get("/result/{project_id}", response_model=PostureEventResponse)
async def get_posture_events(project_id: str):
    """
    백엔드의 GET /api/projects/{projectId}/posture-events 에 대응
    분석 결과를 백엔드에 제공
    """
    if project_id not in analysis_results:
        raise HTTPException(status_code=404, detail="Analysis result not found")
    
    return analysis_results[project_id]

@app.post("/analyze-local", response_model=PostureEventResponse)
async def analyze_local_video(request: LocalTestRequest):
    """
    로컬 비디오 파일로 테스트하는 기능
    개발/테스트 용도
    """
    if not ANALYZER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Analyzer not available")
    
    if not os.path.exists(request.video_path):
        raise HTTPException(status_code=404, detail=f"Video file not found: {request.video_path}")
    
    print(f"Testing with local file: {request.video_path}")
    
    try:
        # 로컬 파일 분석
        analysis_result = analyze_video_file(request.video_path)
        
        # 백엔드 API 형식으로 변환
        posture_response = convert_to_backend_format(request.project_id, analysis_result)
        
        # 결과 저장
        analysis_results[request.project_id] = posture_response
        
        print(f"Local test completed for project: {request.project_id}")
        return posture_response
        
    except Exception as e:
        print(f"Local test failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

async def download_video(video_url: str) -> str:
    """비디오 다운로드"""
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.get(video_url)
            response.raise_for_status()
            
            suffix = '.mp4'
            content_type = response.headers.get('content-type', '')
            if 'webm' in content_type:
                suffix = '.webm'
            elif 'avi' in content_type:
                suffix = '.avi'
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                temp_file.write(response.content)
                return temp_file.name
                
    except Exception as e:
        raise Exception(f"Failed to download video: {str(e)}")

def convert_to_backend_format(project_id: str, analysis_result: Dict[str, Any]) -> PostureEventResponse:
    """
    자세 분석 결과를 백엔드 API 스키마에 맞게 변환
    백엔드의 PostureEventResponse 형식으로 변환
    """
    detected_actions = []
    
    for action_key, action_data in analysis_result.get("detected_actions", {}).items():
        periods = []
        
        # 각 발생 구간을 백엔드 형식으로 변환
        for period_data in action_data.get("periods", []):
            periods.append(ActionPeriodResponse(
                startFrame=period_data["start_frame"],
                endFrame=period_data["end_frame"],
                durationSeconds=period_data["duration_seconds"]
            ))
        
        # 요약 정보
        summary = ActionSummaryResponse(
            totalDurationSeconds=action_data["summary"]["total_duration_seconds"],
            occurrenceCount=action_data["summary"]["occurrence_count"]
        )
        
        # 액션 정보
        detected_actions.append(DetectedActionResponse(
            actionName=action_data["action_name"],
            periods=periods,
            summary=summary
        ))
    
    # 백엔드 API 형식으로 반환
    return PostureEventResponse(
        projectId=project_id,
        totalBadPostures=analysis_result["summary"]["total_bad_postures"],
        totalDurationSeconds=analysis_result["summary"]["total_duration_seconds"],
        detectedActions=detected_actions
    )

# 개발용 실행
if __name__ == "__main__":
    import uvicorn
    print("Starting Simple Posture Analysis Service...")
    print("API Docs: http://localhost:8000/docs")
    print("Health: http://localhost:8000/health")
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=True)