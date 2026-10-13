# Short Generator — Shorts Cutter

**Long video in. Shorts out.** Paste a YouTube link or upload a video file. The app transcribes it, has an LLM find the moments viewers are most likely to stop scrolling for, and cuts them into vertical clips ready for YouTube Shorts, TikTok, and Instagram Reels.

It runs on your own computer. You get a web app in the browser, a command-line tool, and a Python library. Nothing is watermarked, and there are no per-clip credits.

> Forked from [Anil-matcha/AI-Youtube-Shorts-Generator](https://github.com/Anil-matcha/AI-Youtube-Shorts-Generator) (MIT). This fork adds the web app, video uploads, Gemini support with automatic model rotation, caching, Docker, and CI.

---

## Features

### Web app ("Shorts Cutter")
- **Paste a link or upload a file.** Use the upload button or drag a video anywhere onto the page (mp4, mov, mkv, webm, avi, m4v; up to 4 GB by default). Uploads show a progress bar. The same file is never stored twice, so uploading it again reuses the saved copy and its transcript.
- **Pick your output:** 1, 2, 3, 5, or 10 clips. The shape can be 9:16, 4:5, 1:1, or 16:9. Source quality can be 360p to 1080p. You can force a language or leave it on auto. Choose between Local or MuAPI cloud processing.
- **Live progress:** a step tracker (Download → Transcribe → Find highlights → Cut clips) that also shows which Gemini model is being asked and for how long.
- **Results page:**
  - Each clip has an in-page player, a viral score (0–100), its timestamps and length, a title, the opening hook line, and a one-sentence reason it should perform.
  - Each clip also has **Download** and **Copy hook** buttons.
  - A **cut map** shows where each clip sits on the original video's timeline. Hovering a clip highlights its spot.
  - Only one clip plays at a time.
- **Server status badge:** shows whether the server is up, which LLM it's using, and when the Gemini free-tier daily limit resets if you've hit it.
- **Clear errors:** you get readable messages for bad links, unsupported files, oversized uploads, and failed downloads, plus the reason a particular clip failed to render.

### AI pipeline
- **Virality-aware highlight picking.** Moments are ranked on hooks, emotional peaks, opinion bombs, revelations, conflict, quotable lines, story peaks, and practical value.
- **Long-video aware.** Videos over 30 minutes are split into overlapping 20-minute chunks so no moment is missed.
- **Smart dedupe.** If two clips overlap by more than 50%, only the higher-scoring one is kept.
- **Face-tracking vertical crop.** In local mode, OpenCV follows faces with smoothed motion. It falls back to a centre crop if face detection isn't available.
- **Browser-ready output.** Clips are encoded as H.264 / yuv420p with faststart, so they play in any browser or phone.

### Two ways to run it
| Step | Local mode (default in the web app) | API mode (MuAPI cloud) |
|---|---|---|
| Download | `yt-dlp` (or your uploaded / local file) | MuAPI `/youtube-download` |
| Transcribe | `faster-whisper` on CPU or CUDA | MuAPI `/openai-whisper` |
| Pick highlights | Gemini or OpenAI (your key) | MuAPI LLM |
| Crop | `ffmpeg` + OpenCV face tracking | MuAPI `/autocrop` |
| Output | mp4 files in `output/` | hosted URLs |
| Keys needed | `GEMINI_API_KEY` or `OPENAI_API_KEY` | `MUAPI_API_KEY` |

Uploaded files always run in local mode, because the cloud can't read files on your computer.

### Built to work on the Gemini free tier
- The Gemini free tier allows about 20 requests per day **per model**. The app rotates through a list of 8 Flash models (`GEMINI_MODELS`), best first.
- A model that hits its daily limit is remembered and skipped until the quota resets at midnight US Pacific time. This is stored in `output/.gemini_quota.json`.
- A model that doesn't answer within `GEMINI_TIMEOUT_SECONDS` (default 150s) is dropped for that request, and the next model is tried, so jobs don't hang.
- Each generation uses a single LLM request by default. Set `LLM_DETECT_CONTENT_TYPE=true` to add a pre-pass that first classifies the video (podcast, tutorial, …).

### Caching
- YouTube downloads are cached as `output/source_<video_id>.mp4` and reused on the next run. A cached file with no audio track is deleted and downloaded again.
- Transcripts are cached as `.srt` files next to the output and reused while they're newer than the video.
- Each job writes its clips to its own folder, `output/<job_id>/`, so runs never overwrite each other.

### Deployment
- `run.py` is a production entry point using `waitress` (Windows-friendly). It also works with `gunicorn`.
- A multi-stage `Dockerfile` with ffmpeg and a health check on `/api/status`.
- A GitHub Actions pipeline that lints (flake8, black, mypy), checks that no real API keys or `.env` file are committed, then builds and pushes a Docker image to GitHub Container Registry.

---

## Quick start

### Prerequisites
- Python 3.10+
- A **Gemini** or **OpenAI** API key for local mode. You can get a free Gemini key at [Google AI Studio](https://aistudio.google.com/apikey).
- ffmpeg doesn't need a separate install. It comes bundled through `imageio-ffmpeg`, and an `ffmpeg` on your PATH works too.
- Optional: an NVIDIA GPU + CUDA for faster transcription.

### Install

```bash
git clone https://github.com/iamkoshin/Short-Generator.git
cd Short-Generator

python -m venv venv
# Windows:
venv\Scripts\activate
# macOS / Linux:
source venv/bin/activate

pip install -r requirements-local.txt   # includes requirements.txt
```

### Configure

Copy `.env.example` to `.env` and fill in your key:

```bash
LLM_PROVIDER=gemini            # gemini or openai
GEMINI_API_KEY=your_gemini_key_here
# or
# LLM_PROVIDER=openai
# OPENAI_API_KEY=your_openai_key_here
```

Check your setup:

```bash
python env_test.py
```

This shows which keys are set, makes a test call to Gemini, and lists any missing packages.

### Run the web app

```bash
python app.py        # development, http://localhost:5000
python run.py        # production server (waitress)
```

Open **http://localhost:5000**, paste a link or drop in a video, and click **Cut shorts**.

---

## Command line

```bash
# Local mode (yt-dlp + faster-whisper + your LLM key)
python main.py "https://www.youtube.com/watch?v=VIDEO_ID" --mode local

# A video already on your computer
python main.py "C:/Videos/podcast.mp4" --mode local

# All options
python main.py "https://www.youtube.com/watch?v=VIDEO_ID" \
    --mode local --num-clips 5 --aspect-ratio 9:16 \
    --format 1080 --language en --output-json result.json

# Batch a list of links (one per line)
xargs -a urls.txt -I{} python main.py "{}" --mode local
```

| Flag | Default | Notes |
|---|---|---|
| `--mode` | `api` | `local` or `api` (the CLI defaults to `api`; the web app defaults to `local`) |
| `--num-clips` | `3` | How many shorts to make |
| `--aspect-ratio` | `9:16` | e.g. `9:16`, `4:5`, `1:1`, `16:9` |
| `--format` | `720` | Source quality: `360` / `480` / `720` / `1080` |
| `--language` | auto | Whisper language code, e.g. `en`, `ar` |
| `--output-json` | — | Save the full result (transcript, all candidates, final clips) |

Example output:

```
#1  score=92  124.3s → 187.6s
     title:  The one mistake that cost me $50K
     hook:   "Nobody talks about this, but it killed my first startup..."
     clip:   output/short_01.mp4
```

## Python library

```python
from shorts_generator import generate_shorts

result = generate_shorts(
    "https://www.youtube.com/watch?v=VIDEO_ID",   # or a local file path
    num_clips=5,
    aspect_ratio="9:16",
    mode="local",
    progress_cb=lambda pct, stage: print(pct, stage),   # optional
)
for short in result["shorts"]:
    print(short["score"], short["title"], short["clip_url"])
```

Each short contains `title`, `start_time`, `end_time`, `score`, `hook_sentence`, `virality_reason`, and `clip_url` (or `error` if it failed to render).

## HTTP API

The web app is a small JSON API you can call from other tools:

| Method & path | What it does |
|---|---|
| `POST /api/upload` | Upload a video (`multipart/form-data`, field `file`). Returns `upload_id`. |
| `POST /api/generate` | Start a job. Body: `url` **or** `upload_id`, plus optional `num_clips` (1–10), `aspect_ratio`, `download_format`, `language`, `mode`. Returns `job_id`. |
| `GET /api/jobs/<job_id>` | Job status, progress %, current stage, and the result when done. |
| `GET /api/clips/<clip_id>` | Stream a finished clip. |
| `GET /api/download/<clip_id>` | Download a finished clip as an mp4. |
| `GET /api/status` | Server health, job counts, LLM provider, Gemini quota state. |
| `POST /api/reset` | Clear all jobs and clips from memory (files on disk stay). |

```bash
curl -X POST http://localhost:5000/api/generate \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=VIDEO_ID", "num_clips": 3}'
```

---

## Configuration (`.env`)

| Variable | Default | What it does |
|---|---|---|
| `LLM_PROVIDER` | `openai` | `gemini` or `openai` for local mode |
| `GEMINI_API_KEY` | — | Your Gemini key |
| `GEMINI_MODELS` | 8 Flash models | Comma-separated list, tried in order |
| `GEMINI_TIMEOUT_SECONDS` | `150` | Give up on a slow model and try the next |
| `OPENAI_API_KEY` | — | Your OpenAI key |
| `OPENAI_MODEL` | `gpt-4o-mini` | OpenAI model for highlight picking |
| `LLM_DETECT_CONTENT_TYPE` | `false` | Extra request to classify the video first |
| `MUAPI_API_KEY` | — | Only needed for API mode |
| `MUAPI_POLL_INTERVAL` / `MUAPI_POLL_TIMEOUT` | `5` / `600` | Seconds between / before giving up on MuAPI job polls |
| `LOCAL_WHISPER_MODEL` | `base` | `tiny` / `base` / `small` / `medium` / `large-v3` (bigger = more accurate, slower) |
| `LOCAL_WHISPER_DEVICE` | `auto` | `auto` / `cpu` / `cuda` |
| `LOCAL_WHISPER_VAD_FILTER` | `false` | Skip silent parts during transcription (can cut music-heavy videos) |
| `LOCAL_OUTPUT_DIR` | `output` | Where clips, uploads, and caches are saved |
| `MAX_UPLOAD_MB` | `4096` | Largest file the browser can upload |
| `PORT` / `HOST` / `WORKERS` | `5000` / `0.0.0.0` / `2` | Server settings for `run.py` |

To tune how highlights are chosen, edit `shorts_generator/highlights.py`:
- `VIRALITY_CRITERIA` and `HIGHLIGHT_SYSTEM_PROMPT` control what the LLM looks for.
- `CHUNK_SIZE_SECONDS`, `LONG_VIDEO_THRESHOLD`, and `CHUNK_OVERLAP_SECONDS` control long-video chunking.

---

## Docker

```bash
docker build -t short-generator .
docker run -p 5000:5000 --env-file .env -v "$(pwd)/output:/app/output" short-generator
```

Every push to `main` also publishes an image to `ghcr.io/iamkoshin/short-generator` through GitHub Actions.

---

## Project structure

```
├── app.py                    Flask web server + JSON API
├── run.py                    Production entry point (waitress / gunicorn)
├── main.py                   Command-line tool
├── env_test.py               Checks your keys and installed packages
├── templates/index.html      Web app page
├── static/css/style.css      Web app styles
├── static/js/app.js          Web app logic (upload, progress, results)
├── shorts_generator/
│   ├── pipeline.py           Runs the steps, picks local or API mode
│   ├── highlights.py         Virality prompt, chunking, dedupe
│   ├── config.py             Settings from .env
│   ├── downloader.py         API mode: download via MuAPI
│   ├── transcriber.py        API mode: Whisper via MuAPI
│   ├── clipper.py            API mode: auto-crop via MuAPI
│   ├── muapi.py              MuAPI submit + poll helper
│   └── local/
│       ├── downloader.py     yt-dlp download + cache
│       ├── transcriber.py    faster-whisper + .srt cache
│       ├── llm.py            Gemini (model rotation, quota, timeout) / OpenAI
│       └── clipper.py        ffmpeg cut + OpenCV face-tracking crop
├── Dockerfile
├── .github/workflows/ci-cd.yml
├── requirements.txt          Core packages (web server, API mode)
└── requirements-local.txt    Extra packages for local mode
```

## Troubleshooting

- **"Gemini daily limit reached":** every model in `GEMINI_MODELS` has hit its free quota. Wait for the reset time shown in the app, enable billing on your Gemini key, or switch to `LLM_PROVIDER=openai`.
- **YouTube download fails:** update yt-dlp with `pip install -U yt-dlp`. YouTube changes often. As a workaround, download the video yourself and upload it.
- **No speech found / empty transcript:** set the language explicitly (e.g. `en`), or try a bigger `LOCAL_WHISPER_MODEL`.
- **Transcription is slow:** use `LOCAL_WHISPER_MODEL=tiny` or `base`, or set `LOCAL_WHISPER_DEVICE=cuda` on an NVIDIA GPU.
- **Jobs disappeared:** jobs are kept in memory, so restarting the server clears the list. Finished clip files stay in `output/`.

## Security notes

- Never commit your `.env`. It's in `.gitignore`, and CI fails if it's ever tracked.
- The app has no login. Don't expose it to the internet without adding authentication and rate limiting.

## License

MIT. See [LICENSE](LICENSE). Original project by [Anil-matcha](https://github.com/Anil-matcha/AI-Youtube-Shorts-Generator).
