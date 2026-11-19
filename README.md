# CLIP AI

A GitHub Pages frontend prototype for an AI-assisted short-form video clipping workspace.

## Current status

- Responsive dark dashboard
- Video URL input validation
- Local file selection UI
- Browser-local project list
- Navigation for projects, exports and settings

**Important:** This repository currently contains the frontend prototype only. It does not download video URLs, upload files to a cloud processor, transcribe media, find viral moments, render MP4s, or publish to social networks. Those capabilities require a separately hosted backend and secured integrations.

## Architecture planned

- Frontend: GitHub Pages (static HTML/CSS/JS)
- API: separately hosted FastAPI service
- Queue/worker: cloud job queue and video worker
- Analysis: speech transcription + scene analysis + moment ranking
- Rendering: FFmpeg in a cloud worker
- Storage: private object storage with expiring download links

## Safety and rights

Only process videos you own or are authorized to edit. Do not bypass DRM, access controls, or platform download restrictions. A URL adapter should use an official or permitted source; otherwise ask the user to upload an authorized source file.

## Deploy

In GitHub, open **Settings → Pages**, choose **Deploy from a branch**, select **main** and **/(root)**, then Save. The site will be published at:

https://manansingh17082005-bot.github.io/clip-AI-/

GitHub Pages serves the frontend only; it is not a video-processing server.


## Backend API (first working MVP)

A Dockerized FastAPI service is in `backend/`. It accepts a **direct HTTPS video-file URL**, downloads it in the cloud, probes its duration, and renders evenly spaced vertical 9:16 MP4 segments using FFmpeg.

### Deploy on Render

1. Create a new **Web Service** from this repository.
2. Choose Docker and set Dockerfile path to `backend/Dockerfile` (Docker context `backend`).
3. Set `CORS_ORIGINS` to the exact GitHub Pages origin: `https://manansingh17082005-bot.github.io`.
4. Deploy and test `/api/health`.

The included `backend/render.yaml` is an optional Blueprint starting point. Free instances may sleep, have limited CPU/disk and are not suitable for reliable long video jobs. The MVP keeps job state and output files in local memory/disk, so a restart loses them.

### Current backend limitations

- It accepts direct public HTTPS video-file URLs only. A Vyro campaign page URL is not a direct video file; private/login-only links, redirects, and sites that block direct access will not work. Use an authorized direct file URL.
- It creates evenly spaced segments, **not AI-ranked viral highlights**. Speech transcription, highlight scoring, animated captions, persistent storage, authentication, a durable job queue and social publishing are future integrations.
- Do not use it to bypass platform restrictions or process content without permission.
- Configure authentication, rate limiting, durable storage and a persistent queue before public/production use.
