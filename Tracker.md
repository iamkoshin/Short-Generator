# AI YouTube Shorts Generator — Tracker

> Last updated: 2026-09-18

## Project Overview
Turn any YouTube video into viral 9:16 Shorts using AI highlight detection (LLM-ranked virality) + Whisper transcription + ffmpeg/OpenCV clipping.

Two modes:
- **API** (default): MuAPI handles download, transcribe, LLM, autocrop — fast, pay-per-call
- **Local**: yt-dlp + faster-whisper + OpenAI/Gemini + ffmpeg/OpenCV — self-hosted

## Status Summary

| Phase | Status |
|---|---|
| Core pipeline (`shorts_generator/`) | ✅ Complete |
| Web server (`app.py`) | 🔧 In progress (fixed static routes, added endpoints) |
| Frontend UI (`templates/index.html`) | 🔧 In progress (added modal, toasts, buttons) |
| Frontend JS (`static/js/app.js`) | 🔧 In progress (fixed bugs, added download/preview/toast) |
| Frontend CSS (`static/css/style.css`) | 🔧 In progress (added animations, modal, toast styles) |
| Production entry point (`run.py`) | ✅ Created |
| Deployment readiness | 📋 Pending |

## Phases

### ✅ Phase 1: Tracker.md
- Created project tracking document

### 🔧 Phase 2: Backend Fixes (`app.py`)
- [x] Fix static file serving route conflict
- [x] Add `/api/clips/<clip_id>` endpoint (serve local + API clips)
- [x] Add `/api/download/<clip_id>` endpoint (download with Content-Disposition)
- [x] Add `/api/reset` endpoint (clear jobs)
- [x] Add `/api/status` endpoint (server status + job count)
- [x] Fix job result structure (local paths → `/api/clips/` URLs)

### 🔧 Phase 3: Frontend Overhaul (`templates/index.html`)
- [x] Add video preview modal (`<video>` player with controls)
- [x] Add toast notification container
- [x] Add Download MP4, Watch, Copy Link, Copy Hook buttons to result cards
- [x] Add clipboard copy feedback
- [x] Add generation summary header (mode, URL, count)
- [x] Add loading spinner on generate button
- [x] Add smooth transitions between sections

### 🔧 Phase 4: JavaScript Fixes (`static/js/app.js`)
- [x] Fix `setButtonLoading(false)` called too early (was inside `.then()`, should be after poll)
- [x] Fix `errorSection` retry button state reset
- [x] Fix `resetBtn` clearing progress section
- [x] Fix `clip_url` handling (local paths → `/api/clips/` URLs)
- [x] Add `downloadClip(short)` function
- [x] Add `copyToClipboard(text)` function with toast feedback
- [x] Add `openVideoModal(url)` / `closeVideoModal()` functions
- [x] Add toast notification system (`showToast(message, type)`)
- [x] Add exponential backoff for failed polls
- [x] Add keyboard shortcuts (`Ctrl+Enter` submit, `Escape` close modal)
- [x] Add cancel-on-unload cleanup

### 🔧 Phase 5: CSS Enhancements (`static/css/style.css`)
- [x] Add `@keyframes fadeIn`, `slideUp`, `spin`, `pulse` animations
- [x] Add `.modal-overlay`, `.modal-content`, close button styles
- [x] Add `.toast-container`, `.toast` with type variants
- [x] Add `.btn-download`, `.btn-watch`, `.btn-copy` button styles
- [x] Add smooth section transitions
- [x] Add better card hover effects (lift + shadow)
- [x] Add responsive improvements

### 📋 Phase 6: Deployment Readiness
- [x] Add `run.py` (gunicorn production entry point)
- [x] Add `Dockerfile` (multi-stage build with ffmpeg + gunicorn)
- [x] Add `.dockerignore` (exclude env, pycache, output)
- [x] Add CI/CD pipeline config (`.github/workflows/ci-cd.yml`)
- [x] Add `.env` security audit (`.github/env-security-audit.md`)
- [x] ⚠️ **Security finding: real API keys in `.env` — rotate immediately**

## Known Bugs (Fixed)
| Bug | Status | File |
|---|---|---|
| `setButtonLoading(false)` called immediately after fetch, not during poll | ✅ Fixed | `app.js` |
| `static_files` route conflicts with Flask's built-in static serving | ✅ Fixed | `app.py` |
| `clip_url` for local mode was a filesystem path, not a URL | ✅ Fixed | `app.py`, `app.js` |
| `errorSection` retry button didn't reset UI properly | ✅ Fixed | `app.js` |
| `resetBtn` didn't clear progress section | ✅ Fixed | `app.js` |
| No download functionality for generated clips | ✅ Fixed | `app.py`, `app.js` |
| No video preview capability | ✅ Fixed | `app.py`, `app.js`, `index.html` |

## Feature Backlog
| Feature | Priority | Status |
|---|---|---|
| Download MP4 per clip | 🔴 High | ✅ Done |
| Video preview modal | 🔴 High | ✅ Done |
| Copy hook to clipboard | 🟡 Medium | ✅ Done |
| Toast notifications | 🟡 Medium | ✅ Done |
| Keyboard shortcuts | 🟢 Low | ✅ Done |
| Docker deployment | 🟡 Medium | ⬜ Pending |
| History/previous generations | 🟢 Low | ⬜ Pending |
| Dark/light theme toggle | 🟢 Low | ⬜ Pending |
| Share to social media | 🟢 Low | ⬜ Pending |

## Deploy Checklist
- [ ] Set `FLASK_ENV=production`
- [ ] Set `SECRET_KEY` for Flask sessions
- [ ] Use `gunicorn` or `waitress` as WSGI server
- [ ] Set `HOST=0.0.0.0` and `PORT` from environment
- [ ] Use HTTPS with reverse proxy (nginx)
- [ ] Set up proper `.env` with real API keys (never commit `.env`)
- [ ] Configure `LOCAL_OUTPUT_DIR` with sufficient disk space
- [ ] Set up log rotation
- [ ] Add rate limiting for `/api/generate`
- [ ] Add authentication if exposing publicly
- [ ] Set `LOCAL_WHISPER_DEVICE=cuda` for GPU machines
- [ ] Install all `requirements-local.txt` dependencies for local mode

## Pipeline Fixes (2026-09-30)
| Bug | Status | File |
|---|---|---|
| yt-dlp couldn't solve YouTube JS challenges → silent video-only download → Whisper crash | ✅ Fixed (`remote_components: ejs:github`, audio-required format chain, audio check purges bad cache) | `local/downloader.py` |
| OpenCV 5 removed `cv2.CascadeClassifier` → every clip failed | ✅ Fixed (pinned `<5`, centre-crop fallback) | `local/clipper.py`, `requirements-local.txt` |
| Capture not released on error → WinError 32 masked real error | ✅ Fixed | `local/clipper.py` |
| Clips encoded as mp4v → not playable in browser | ✅ Fixed (H.264 yuv420p + faststart) | `local/clipper.py` |
| Every job overwrote `output/short_NN.mp4` | ✅ Fixed (`output/<job_id>/`) | `pipeline.py` |
| `gemini-2.5-flash` retired for new users (404) | ✅ Fixed (`gemini-3.8-flash`, retry + `GEMINI_FALLBACK_MODEL`) | `config.py`, `local/llm.py` |
| UI stuck on 400/404, no stage text, per-clip errors hidden | ✅ Fixed | `app.py`, `app.js` |
| Flask reloader wiped in-memory jobs mid-run | ✅ Fixed (`use_reloader=False`) | `app.py` |
| ⚠️ Gemini free tier = 20 requests/day/model; one generation uses ~2+ | ⬜ Open (enable billing or switch provider) | `.env` |
| Gemini free tier is 20 requests/day **per model** | ✅ Rotates through 8 Flash models (`GEMINI_MODELS`), remembers exhausted ones until midnight Pacific (`output/.gemini_quota.json`); content-type pre-pass off by default, so 1 request per generation (`LLM_DETECT_CONTENT_TYPE`) | `config.py`, `local/llm.py`, `highlights.py`, `app.py`, `app.js` |
