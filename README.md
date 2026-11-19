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
