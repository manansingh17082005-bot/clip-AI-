# Clip AI Backend (API MVP)

This service adds the first processing connection to the Clip AI website. It wraps FunClip's speech recognition and transcript-based video clipping methods behind a small HTTP API.

## Current endpoints

- `GET /api/health` — service status
- `POST /api/transcribe` — upload a video, extract speech transcript and SRT timestamps; returns a temporary in-memory job ID
- `POST /api/clip` — submit transcript text selected by the user and generate an MP4 clip
- `GET /api/download/{job_id}/{filename}` — download generated MP4

## Run locally (Windows)

1. Install Docker Desktop.
2. In the repository root, run:

```powershell
docker build -t clip-ai-api -f backend/Dockerfile .
docker run --rm -p 8000:8000 -e CLIP_AI_LANG=en clip-ai-api
```

3. Open `http://localhost:8000/api/health`. Expected response includes `ok: true`.
4. On the Clip AI site, use API URL `http://localhost:8000`, select a video and click **Transcribe with AI**.
5. Select the transcript text you want to clip and click **Create clip from selected transcript**.

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
