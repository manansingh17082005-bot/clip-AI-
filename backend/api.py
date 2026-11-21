import os
import shutil
import tempfile
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from funasr import AutoModel
from funclip.model_selection import create_asr_model
from funclip.videoclipper import VideoClipper

APP_ROOT = Path(__file__).resolve().parents[1]
MAX_UPLOAD_BYTES = int(os.getenv("CLIP_AI_MAX_UPLOAD_MB", "500")) * 1024 * 1024
MODEL_NAME = os.getenv("CLIP_AI_ASR_MODEL", "fun-asr-nano")
LANG = os.getenv("CLIP_AI_LANG", "en")
ALLOWED_ORIGINS = os.getenv("CLIP_AI_ALLOWED_ORIGINS", "*").split(",")

app = FastAPI(title="Clip AI API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if ALLOWED_ORIGINS != ["*"] else ["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

jobs = {}
model_lock = threading.Lock()
model_instance = None
clipper_instance = None


def get_clipper():
    global model_instance, clipper_instance
    with model_lock:
        if clipper_instance is None:
            model_instance = create_asr_model(MODEL_NAME, LANG, AutoModel)
            clipper_instance = VideoClipper(model_instance)
            clipper_instance.lang = LANG
        return clipper_instance


@app.get("/api/health")
def health():
    return {"ok": True, "service": "clip-ai-api", "version": "0.1.0", "asr_model": MODEL_NAME, "language": LANG}


class ClipRequest(BaseModel):
    job_id: str
    text: str


@app.post("/api/transcribe")
async def transcribe(file: UploadFile = File(...)):
    suffix = Path(file.filename or "video.mp4").suffix.lower()
    if suffix not in {".mp4", ".mov", ".mkv", ".webm", ".avi"}:
        raise HTTPException(status_code=400, detail="Unsupported video file type.")
    work_dir = Path(tempfile.mkdtemp(prefix="clip-ai-"))
    video_path = work_dir / ("input" + suffix)
    size = 0
    try:
        with video_path.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="Video exceeds configured upload limit.")
                out.write(chunk)
        await file.close()
        if size == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")
        clipper = get_clipper()
        text, srt, state = clipper.video_recog(str(video_path), sd_switch="no", output_dir=str(work_dir))
        job_id = uuid.uuid4().hex
        jobs[job_id] = {"work_dir": work_dir, "video_path": str(video_path), "state": state, "clipper": clipper}
        segments = state.get("sentences") or []
        return {"job_id": job_id, "transcript": text, "srt": srt, "segments": segments}
    except HTTPException:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Transcription failed: {exc}") from exc


@app.post("/api/clip")
def create_clip(request: ClipRequest):
    job = jobs.get(request.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or server restarted. Transcribe the video again.")
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="Select or enter transcript text first.")
    clipper = job["clipper"]
    try:
        output_dir = job["work_dir"]
        result_path, message, clip_srt = clipper.video_clip(
            request.text.strip(), 0, 0, job["state"], output_dir=output_dir
        )
        if not result_path or not os.path.exists(result_path):
            raise HTTPException(status_code=422, detail=message or "No matching segment could be clipped.")
        return {"message": message, "clip_srt": clip_srt, "download_url": f"/api/download/{request.job_id}/{Path(result_path).name}"}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Clip export failed: {exc}") from exc


@app.get("/api/download/{job_id}/{filename}")
def download(job_id: str, filename: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    file_path = (Path(job["work_dir"]) / filename).resolve()
    if Path(job["work_dir"]).resolve() not in file_path.parents or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Output file not found.")
    return FileResponse(file_path, filename=filename, media_type="video/mp4")
