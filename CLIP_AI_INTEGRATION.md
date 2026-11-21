# Clip AI web preview and integration roadmap

This branch adds a small, responsive Clip AI frontend to the repository so GitHub Pages has an `index.html` entry point. It preserves the existing Python FunClip source.

## Current frontend behavior
- Responsive Clip AI-branded UI
- Local video file selection and browser-only preview
- Drag-and-drop file selection
- Clear selection button
- Explicitly indicates that processing is not yet connected; the selected video is not uploaded

## GitHub Pages
After this PR is reviewed and merged:
1. Open repository **Settings → Pages**.
2. Select **Deploy from a branch**.
3. Choose branch **main** and folder **/(root)**, then save.
4. Wait for the Pages workflow/deployment to finish.
5. Open the Pages URL shown in Settings → Pages.

This frontend commit alone does not configure Pages settings or connect the Python service.

## Planned backend integration
- Keep the Gradio/FunClip engine as a Python processing service, not run it in GitHub Pages.
- Build a backend API layer with upload limits, temporary storage, processing job status and cleanup.
- Connect the frontend to the backend API after deployment hosting for Python is chosen and configured.
- Implement transcript/timestamps, segment selection, clip extraction, subtitles, vertical output and MP4 downloads incrementally.

## Notes
The current UI is a frontend preview. The Generate button is intentionally disabled until a real backend exists; it must not imply a working AI clip pipeline.
