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
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

APP_DIR = Path(os.getenv("CLIPAI_DATA_DIR", "/tmp/clipai-data"))
MAX_BYTES = int(os.getenv("MAX_VIDEO_BYTES", str(500 * 1024 * 1024)))
MAX_DURATION = int(os.getenv("MAX_VIDEO_SECONDS", "7200"))
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".webm", ".m4v", ".mkv"}
APP_DIR.mkdir(parents=True, exist_ok=True)
JOBS: dict[str, dict] = {}

app = FastAPI(title="CLIP AI API", version="0.2.0")
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


class InspectSource(BaseModel):
    source_url: str = Field(min_length=8, max_length=2048)


def classify_source(raw: str) -> dict:
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    if parsed.scheme != "https" or not host or parsed.username or parsed.password:
        raise ValueError("Enter a valid public HTTPS link.")

    if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}:
        return {
            "provider": "youtube",
            "kind": "platform_video_page",
            "can_process": False,
            "message": "YouTube watch links are not downloadable through the YouTube Data API. For a video you own, export the original in YouTube Studio or provide a creator-authorized media file URL, then upload it here.",
            "next_step": "Upload an authorized source file or use a creator-provided direct media URL."
        }
    if host == "twitch.tv" or host.endswith(".twitch.tv"):
        return {
            "provider": "twitch",
            "kind": "platform_video_page",
            "can_process": False,
            "message": "A Twitch channel, clip or VOD page is not a direct media file. Twitch's public API does not give this app permission to download arbitrary VODs. Use a source file or download link supplied by the channel owner/campaign.",
            "next_step": "Upload an authorized source file or use a creator-provided direct media URL."
        }
    campaign_hosts = ("vyro.com", "contentrewards.com", "app.contentrewards.com")
    if any(host == d or host.endswith("." + d) for d in campaign_hosts):
        return {
            "provider": "campaign",
            "kind": "campaign_page",
            "can_process": False,
            "message": "This is a campaign page, not the campaign's video file. Campaign platforms use different access rules and APIs; CLIP AI will not guess credentials or scrape private campaign media.",
            "next_step": "Open the campaign and use its authorized footage download/source link, or upload a permitted source file."
        }
    if path.endswith(tuple(ALLOWED_EXTENSIONS)):
        check_public_url(raw)
        return {
            "provider": "direct_media",
            "kind": "video_file",
            "can_process": True,
            "message": "This looks like a direct video-file URL. The backend will still verify its response and file size before processing.",
            "next_step": "Submit this link to create clips."
        }
    return {
        "provider": "unknown",
        "kind": "web_page_or_unknown",
        "can_process": False,
        "message": "This link is a webpage or an unrecognized source, not a direct video file. CLIP AI needs a creator-authorized media URL or an uploaded source file.",
        "next_step": "Upload an authorized source file or paste a direct MP4/MOV/WebM URL."
    }


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
        async with client.stream("GET", url, headers={"User-Agent": "CLIP-AI/0.2"}) as response:
            if response.status_code in (301, 302, 303, 307, 308):
                raise ValueError("This link redirects. Use a direct, authorized video-file URL.")
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if not (content_type.startswith("video/") or "application/octet-stream" in content_type):
                raise ValueError("The URL did not return a video file. Use a direct MP4/MOV/WebM file URL.")
            with destination.open("wb") as out:
                async for chunk in response.aiter_bytes(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_BYTES:
                        raise ValueError(f"Video exceeds the {MAX_BYTES // (1024*1024)} MB limit.")
                    out.write(chunk)
    if total == 0:
        raise ValueError("The video file was empty.")


def run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if result.returncode:
        raise RuntimeError((result.stderr or "Media processing failed")[-2500:])
    return result.stdout


def render_source(job_id: str, source: Path, clip_length: int, max_clips: int) -> None:
    folder = APP_DIR / job_id
    try:
        JOBS[job_id]["status"] = "analyzing"
        probe = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(source)])
        duration = float(probe.strip())
        if duration <= 0 or duration > MAX_DURATION:
            raise ValueError(f"Video duration must be under {MAX_DURATION // 60} minutes.")
        count = min(max_clips, max(1, int(duration // clip_length)))
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


def process_url_job(job_id: str, url: str, clip_length: int, max_clips: int) -> None:
    folder = APP_DIR / job_id
    folder.mkdir(parents=True, exist_ok=True)
    source = folder / "source-video"
    try:
        JOBS[job_id]["status"] = "downloading"
        asyncio.run(download_video(url, source))
        render_source(job_id, source, clip_length, max_clips)
    except Exception as exc:
        JOBS[job_id].update(status="failed", error=str(exc)[:1000])


def process_uploaded_job(job_id: str, source: Path, clip_length: int, max_clips: int) -> None:
    render_source(job_id, source, clip_length, max_clips)


def new_job(job_id: str) -> None:
    JOBS[job_id] = {"id": job_id, "status": "queued", "clips": []}


@app.get("/")
def root():
    return {"service": "CLIP AI API", "version": "0.2.0", "docs": "/docs", "health": "/api/health"}


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "clip-ai-api", "version": "0.2.0", "ffmpeg": shutil.which("ffmpeg") is not None}


@app.get("/api/sources/capabilities")
def source_capabilities():
    return {
        "direct_video_url": {"available": True, "formats": sorted(ALLOWED_EXTENSIONS)},
        "upload": {"available": True, "max_bytes": MAX_BYTES},
        "youtube": {"available": False, "reason": "Watch-page URLs are not downloadable through the YouTube Data API. Use an authorized export/upload or creator-provided media URL."},
        "twitch": {"available": False, "reason": "VOD/clip pages require source media supplied by the channel owner or an authorized provider."},
        "campaign_pages": {"available": False, "reason": "Provider-specific authorization/API integration is required; campaign pages are not media files."}
    }


@app.post("/api/sources/inspect")
def inspect_source(payload: InspectSource):
    try:
        return classify_source(payload.source_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/jobs", status_code=202)
def create_job(payload: CreateJob, background: BackgroundTasks):
    try:
        info = classify_source(payload.video_url)
        if not info["can_process"]:
            raise HTTPException(status_code=422, detail=info["message"] + " " + info["next_step"])
        safe_url = check_public_url(payload.video_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    job_id = uuid.uuid4().hex
    new_job(job_id)
    background.add_task(process_url_job, job_id, safe_url, payload.clip_length, payload.max_clips)
    return {"job_id": job_id, "status": "queued", "status_url": f"/api/jobs/{job_id}"}


@app.post("/api/jobs/upload", status_code=202)
async def create_upload_job(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    clip_length: int = 30,
    max_clips: int = 5
):
    if clip_length < 15 or clip_length > 90 or max_clips < 1 or max_clips > 10:
        raise HTTPException(status_code=400, detail="Clip length must be 15–90 seconds and clip count 1–10.")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Upload MP4, MOV, WebM, M4V or MKV files only.")
    job_id = uuid.uuid4().hex
    folder = APP_DIR / job_id
    folder.mkdir(parents=True, exist_ok=False)
    destination = folder / ("source" + suffix)
    total = 0
    try:
        with destination.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_BYTES:
                    raise HTTPException(status_code=413, detail=f"Video exceeds the {MAX_BYTES // (1024*1024)} MB upload limit.")
                out.write(chunk)
        if total == 0:
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    except Exception:
        destination.unlink(missing_ok=True)
        shutil.rmtree(folder, ignore_errors=True)
        raise
    finally:
        await file.close()
    new_job(job_id)
    JOBS[job_id]["source_name"] = Path(file.filename or "uploaded video").name
    background.add_task(process_uploaded_job, job_id, destination, clip_length, max_clips)
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
