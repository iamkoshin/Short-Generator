"""Web API server for AI YouTube Shorts Generator."""
from __future__ import annotations

import os
import sys
import threading
import time
import glob
import hashlib
import re
import uuid
from typing import Any, Dict
from urllib.parse import urlparse

# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
# pyrefly: ignore [missing-import]
from flask import Flask, abort, jsonify, request, send_file, send_from_directory

load_dotenv()

# Reconfigure stdout/stderr for UTF-8 on Windows before any background threads start.
# The '→' character and other Unicode used in prompts will fail with the default
# charmap codec when printed from a background thread.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

app = Flask(__name__, static_folder="static", template_folder="templates")

# Uploaded videos live in <output>/uploads, named "<id>_<name>" where the id is a
# hash of the original name + size, so re-uploading the same file reuses it (and
# its cached transcript) instead of creating a copy.
UPLOAD_DIR = os.path.join(os.getenv("LOCAL_OUTPUT_DIR", "output"), "uploads")
UPLOAD_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "4096"))
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024

# In-memory job store (replace with Redis/DB in production)
jobs: Dict[str, Dict[str, Any]] = {}

# Track local clip paths for serving
clip_store: Dict[str, Dict[str, Any]] = {}


@app.route("/", methods=["GET"])
def index():
    return send_from_directory("templates", "index.html")


@app.errorhandler(413)
def upload_too_large(_e):
    return jsonify({"error": f"That file is bigger than the {MAX_UPLOAD_MB // 1024} GB upload limit (MAX_UPLOAD_MB)."}), 413


def _upload_path(upload_id: str):
    if not re.fullmatch(r"[0-9a-f]{12}", upload_id or ""):
        return None
    matches = glob.glob(os.path.join(UPLOAD_DIR, upload_id + "_*"))
    return matches[0] if matches else None


@app.route("/api/upload", methods=["POST"])
def upload_video():
    """Save an uploaded video so it can be cut in local mode."""
    from werkzeug.utils import secure_filename

    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "Choose a video file to upload."}), 400
    name = secure_filename(f.filename) or "video.mp4"
    stem, ext = os.path.splitext(name)
    if ext.lower() not in UPLOAD_EXTENSIONS:
        allowed = ", ".join(sorted(e.lstrip(".") for e in UPLOAD_EXTENSIONS))
        return jsonify({"error": f"That file type isn't supported. Upload a video ({allowed})."}), 400

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    tmp_path = os.path.join(UPLOAD_DIR, f".incoming_{uuid.uuid4().hex}{ext}")
    f.save(tmp_path)
    size = os.path.getsize(tmp_path)
    upload_id = hashlib.sha1(f"{name}:{size}".encode()).hexdigest()[:12]

    existing = _upload_path(upload_id)
    if existing:
        os.remove(tmp_path)  # same file uploaded before
        path = existing
    else:
        path = os.path.join(UPLOAD_DIR, f"{upload_id}_{stem[:80]}{ext.lower()}")
        os.replace(tmp_path, path)
    return jsonify({"upload_id": upload_id, "name": f.filename, "size": size})


@app.route("/api/generate", methods=["POST"])
def generate():
    data = request.get_json(force=True, silent=True) or {}
    url = str(data.get("url") or "").strip()
    upload_id = str(data.get("upload_id") or "").strip()
    if upload_id:
        url = _upload_path(upload_id) or ""
        if not url:
            return jsonify({"error": "That upload is no longer on the server. Upload the video again."}), 400
        data["mode"] = "local"  # MuAPI can't read files on this computer
    elif not url:
        return jsonify({"error": "Paste a YouTube link or upload a video."}), 400

    parsed = urlparse(url)
    if upload_id:
        pass
    elif parsed.scheme in ("http", "https"):
        host = (parsed.hostname or "").lower()
        own_host = (request.host.split(":")[0] or "").lower()
        if host in ("localhost", "127.0.0.1", "0.0.0.0", "::1", own_host):
            return jsonify({"error": "That's the address of this app, not a video. Paste a YouTube link instead."}), 400
    elif "://" in url:
        return jsonify({"error": "Paste a YouTube link that starts with https://"}), 400

    try:
        num_clips = int(data.get("num_clips", 3))
    except (TypeError, ValueError):
        return jsonify({"error": "num_clips must be a number"}), 400
    if not 1 <= num_clips <= 10:
        return jsonify({"error": "num_clips must be between 1 and 10"}), 400

    mode = str(data.get("mode") or "local").lower()
    if mode not in ("local", "api"):
        return jsonify({"error": "mode must be 'local' or 'api'"}), 400

    aspect_ratio = data.get("aspect_ratio", "9:16")
    language = data.get("language", None) or None
    download_format = str(data.get("download_format", "720"))

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "status": "queued",
        "progress": 0,
        "stage": "Queued",
        "result": None,
        "error": None,
    }

    def on_progress(pct: int, stage: str) -> None:
        jobs[job_id]["progress"] = pct
        jobs[job_id]["stage"] = stage

    def run():
        try:
            from shorts_generator import generate_shorts

            jobs[job_id]["status"] = "running"
            on_progress(5, "Starting")

            result = generate_shorts(
                youtube_url=url,
                num_clips=num_clips,
                aspect_ratio=aspect_ratio,
                download_format=download_format,
                language=language,
                mode=mode,
                progress_cb=on_progress,
                job_id=job_id,
            )

            # Convert local file paths to /api/clips/ URLs for the frontend
            shorts = result.get("shorts", [])
            for i, short in enumerate(shorts):
                clip_path = short.get("clip_url")
                if clip_path and os.path.isfile(clip_path):
                    # Store the local path for serving
                    clip_id = f"{job_id}_{i}"
                    clip_store[clip_id] = {
                        "path": clip_path,
                        "mode": result.get("mode"),
                        "title": short.get("title", ""),
                    }
                    short["clip_url"] = f"/api/clips/{clip_id}"
                    short["clip_path"] = clip_path

            if shorts and not any(s.get("clip_url") for s in shorts):
                first_error = next((s.get("error") for s in shorts if s.get("error")), "unknown error")
                raise RuntimeError(f"All {len(shorts)} clips failed to render: {first_error}")

            on_progress(100, "Done")
            jobs[job_id]["status"] = "completed"
            jobs[job_id]["result"] = {
                "mode": result.get("mode"),
                "source_video_url": result.get("source_video_url"),
                "highlights_count": len(result.get("highlights", [])),
                "duration": (result.get("transcript") or {}).get("duration"),
                "aspect_ratio": aspect_ratio,
                "shorts": shorts,
            }
        except Exception as e:
            import traceback
            traceback.print_exc()
            jobs[job_id]["status"] = "failed"
            # Strip terminal colour codes some libraries (yt-dlp) put in messages.
            jobs[job_id]["error"] = re.sub(r"\x1b\[[0-9;]*m", "", str(e)).strip()

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"job_id": job_id, "status": "queued"})


@app.route("/api/jobs/<job_id>", methods=["GET"])
def get_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({
        "job_id": job_id,
        "status": job["status"],
        "progress": job["progress"],
        "stage": job.get("stage"),
        "result": job["result"],
        "error": job["error"],
    })


@app.route("/api/clips/<clip_id>", methods=["GET"])
def serve_clip(clip_id: str):
    """Serve a generated clip file (local mode) or proxy to URL (API mode)."""
    clip = clip_store.get(clip_id)
    if not clip:
        # Try to find it by checking if any stored clip matches
        for cid, cdata in clip_store.items():
            if cid == clip_id:
                clip = cdata
                break

    if not clip:
        abort(404, description="Clip not found")

    path = clip.get("path")
    if path and os.path.isfile(path):
        return send_file(path, as_attachment=False, mimetype="video/mp4")

    abort(404, description="Clip file not found on disk")


@app.route("/api/download/<clip_id>", methods=["GET"])
def download_clip(clip_id: str):
    """Download a generated clip file."""
    clip = clip_store.get(clip_id)
    if not clip:
        abort(404, description="Clip not found")

    path = clip.get("path")
    if path and os.path.isfile(path):
        title = clip.get("title", "short").replace(" ", "_")
        return send_file(
            path,
            as_attachment=True,
            download_name=f"{title}_{clip_id}.mp4",
            mimetype="video/mp4",
        )

    abort(404, description="Clip file not found on disk")


@app.route("/api/reset", methods=["POST"])
def reset_jobs():
    """Clear all jobs and clips from memory."""
    jobs.clear()
    clip_store.clear()
    return jsonify({"status": "reset", "message": "All jobs and clips cleared"})


@app.route("/api/status", methods=["GET"])
def status():
    """Return server status and job count."""
    completed = sum(1 for j in jobs.values() if j["status"] == "completed")
    failed = sum(1 for j in jobs.values() if j["status"] == "failed")
    running = sum(1 for j in jobs.values() if j["status"] == "running")
    queued = sum(1 for j in jobs.values() if j["status"] == "queued")
    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()
    gemini = None
    if provider == "gemini":
        from shorts_generator.local.llm import gemini_quota_status
        gemini = gemini_quota_status()
    return jsonify({
        "status": "ok",
        "total_jobs": len(jobs),
        "by_status": {
            "queued": queued,
            "running": running,
            "completed": completed,
            "failed": failed,
        },
        "mode": provider,
        "gemini": gemini,
    })


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"AI YouTube Shorts Generator - serving on http://localhost:{port}")
    # The reloader restarts the process on file changes, wiping the in-memory
    # job store mid-run - keep it off.
    app.run(host="0.0.0.0", port=port, debug=True, use_reloader=False)
