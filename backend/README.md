# Clip AI Backend (API MVP)

This service adds the first processing connection to the Clip AI website. It wraps FunClip's speech recognition and transcript-based video clipping methods behind a small HTTP API.

## Current endpoints

- `GET /api/health` — service status
- `POST /api/transcribe` — upload a video, extract speech transcript and SRT timestamps; returns a temporary in-memory job ID
- `POST /api/clip` — submit transcript text selected by the user and generate an MP4 clip
- `GET /api/download/{job_id}/{filename}` — download generated MP4

## Run locally on Windows (without Docker — recommended for the current setup)

1. Install Python **3.11 or 3.12** (Python 3.14 is not supported by this dependency set yet).
2. Install FFmpeg and ensure `ffmpeg.exe` is available in PATH. One Windows package-manager option is:

```powershell
winget install Gyan.FFmpeg.Shared
``

3. From the repository root, run the setup/start script:

```powershell
powershell -ExecutionPolicy Bypass -File .\\backend\\start_windows.ps1
``

The script creates an isolated `.venv-clip-ai` environment, installs CPU-only PyTorch and the FunClip/API requirements, runs `pip check`, and starts the local API. It reuses the environment on later launches.

4. Keep the PowerShell window open. Visit `http://127.0.0.1:8000/api/health`; expect `ok: true`.
5. On the Clip AI website, keep API URL set to `http://localhost:8000`, choose a video, click **Transcribe with AI**, then select transcript text and click **Create clip from selected transcript**.

### Docker option (optional)

If Docker Desktop is installed, from the repository root run:

```powershell
docker build -t clip-ai-api -f backend/Dockerfile .
docker run --rm -p 8000:8000 -e CLIP_AI_LANG=en clip-ai-api
```


## Configuration

- `CLIP_AI_ASR_MODEL`: default `fun-asr-nano`
- `CLIP_AI_LANG`: default `en`
- `CLIP_AI_MAX_UPLOAD_MB`: default `500`
- `CLIP_AI_ALLOWED_ORIGINS`: comma-separated origin list (default `*`; set to your deployed Pages origin for production)

The first model load downloads the ASR model weights, so it can take several minutes and needs sufficient disk, RAM and CPU/GPU resources. Model files are not included in this repository or Docker image.

## MVP limitations / production checklist

- Job state and generated files are stored in process memory/temp storage; restarting the server invalidates active job IDs and files.
- This MVP has no authentication, persistent job storage, queue, rate limiting or multi-user isolation. Do not expose it publicly without adding these.
- The frontend is static on GitHub Pages; the Python API must be deployed on a separate host that supports Docker and persistent/adequate CPU/RAM.
- API has a 500 MB upload limit by default.
- Transcript-based clipping requires selecting matching text. Automatic highlight scoring, vertical 9:16 reframing, styled captions, progress events and a durable job queue are future phases.
