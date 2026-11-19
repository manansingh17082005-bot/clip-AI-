import asyncio
import ipaddress
import os
import shutil
import socket
import subprocess
import uuid
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

APP_DIR = Path(os.getenv("CLIPAI_DATA_DIR", "/tmp/clipai-data"))
MAX_BYTES = int(os.getenv("MAX_VIDEO_BYTES", str(500 * 1024 * 1024)))
MAX_DURATION = int(os.getenv("MAX_VIDEO_SECONDS", "7200"))
APP_DIR.mkdir(parents=True, exist_ok=True)
JOBS: dict[str, dict] = {}

app = FastAPI(title="CLIP AI API", version="0.1.0")
origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "*").split(",") if x.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

class CreateJob(BaseModel):
    video_url: str = Field(min_length=12, max_length=2048)
    clip_length: int = Field(default=30, ge=15, le=90)
    max_clips: int = Field(default=5, ge=1, le=10)

def check_public_url(raw: str) -> str:
    parsed = urlparse(raw)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Use a public HTTPS direct-video URL.")
    host = parsed.hostname.lower()
    if host in {"localhost", "metadata.google.internal"}:
        raise ValueError("This host is not allowed.")
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("The video host could not be resolved.") from exc
    for item in addresses:
        ip = ipaddress.ip_address(item[4][0])
        if not ip.is_global:
            raise ValueError("Private or local network addresses are not allowed.")
    return raw

async def download_video(url: str, destination: Path) -> None:
    total = 0
    async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=15), follow_redirects=False) as client:
        async with client.stream("GET", url, headers={"User-Agent": "CLIP-AI/0.1"}) as response:
            if response.status_code in (301, 302, 303, 307, 308):
                raise ValueError("This link redirects. Use a direct, authorized video-file URL.")
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if not (content_type.startswith("video/") or "application/octet-stream" in content_type):
                raise ValueError("The URL did not return a video file. Use a direct MP4/MOV/WebM file URL.")
            async for chunk in response.aiter_bytes(1024 * 1024):
                total += len(chunk)
                if total > MAX_BYTES:
                    raise ValueError(f"Video exceeds the {MAX_BYTES // (1024*1024)} MB limit.")
                destination.write_bytes(destination.read_bytes() + chunk) if False else None
                with destination.open("ab") as out:
                    out.write(chunk)
    if total == 0:
        raise ValueError("The video file was empty.")

def run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if result.returncode:
        raise RuntimeError((result.stderr or "Media processing failed")[-2500:])
    return result.stdout

def process_job(job_id: str, url: str, clip_length: int, max_clips: int) -> None:
    folder = APP_DIR / job_id
    folder.mkdir(parents=True, exist_ok=True)
    source = folder / "source-video"
    try:
        JOBS[job_id]["status"] = "downloading"
        asyncio.run(download_video(url, source))
        JOBS[job_id]["status"] = "analyzing"
        probe = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(source)])
        duration = float(probe.strip())
        if duration <= 0 or duration > MAX_DURATION:
            raise ValueError(f"Video duration must be under {MAX_DURATION // 60} minutes.")
        count = min(max_clips, max(1, int(duration // clip_length)))
        # MVP selection: evenly spaced segments. AI highlight ranking and speech-aware
        # selection will be added as a separate analysis provider integration.
        starts = [max(0, min(duration - clip_length, i * max(clip_length, (duration - clip_length) / max(1, count - 1)))) for i in range(count)]
        JOBS[job_id]["status"] = "rendering"
        outputs = []
        for index, start in enumerate(starts, 1):
            name = f"clip-{index:02d}.mp4"
            target = folder / name
            run([
                "ffmpeg", "-y", "-ss", str(start), "-i", str(source), "-t", str(min(clip_length, duration-start)),
                "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(target)
            ])
            outputs.append({"name": name, "download_url": f"/api/jobs/{job_id}/clips/{name}", "start_seconds": round(start, 2)})
        JOBS[job_id].update(status="completed", clips=outputs, source_duration=round(duration, 2))
    except Exception as exc:
        JOBS[job_id].update(status="failed", error=str(exc)[:1000])

@app.get("/")
def root():
    return {"service": "CLIP AI API", "docs": "/docs", "health": "/api/health"}

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "clip-ai-api", "ffmpeg": shutil.which("ffmpeg") is not None}

@app.post("/api/jobs", status_code=202)
def create_job(payload: CreateJob, background: BackgroundTasks):
    try:
        safe_url = check_public_url(payload.video_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    job_id = uuid.uuid4().hex
    JOBS[job_id] = {"id": job_id, "status": "queued", "clips": []}
    background.add_task(process_job, job_id, safe_url, payload.clip_length, payload.max_clips)
    return {"job_id": job_id, "status": "queued", "status_url": f"/api/jobs/{job_id}"}

@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found. Jobs are currently stored in memory and reset when the service restarts.")
    return job

@app.get("/api/jobs/{job_id}/clips/{filename}")
def get_clip(job_id: str, filename: str):
    if not filename.startswith("clip-") or not filename.endswith(".mp4") or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid clip filename.")
    path = APP_DIR / job_id / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Clip is not ready or no longer available.")
    return FileResponse(path, media_type="video/mp4", filename=filename)
