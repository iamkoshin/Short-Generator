"""Web API server for AI YouTube Shorts Generator."""
import os
import sys
import uuid
import threading
import time

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, jsonify, send_from_directory, send_file, abort

app = Flask(__name__, static_folder="static", template_folder="templates")

# In-memory job store (replace with Redis/DB in production)
jobs: dict[str, dict] = {}

# Track local clip paths for serving
clip_store: dict[str, dict] = {}


@app.get("/")
def index():
    return send_from_directory("templates", "index.html")


@app.post("/api/generate")
def generate():
    data = request.get_json(force=True)
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "YouTube URL is required"}), 400

    num_clips = int(data.get("num_clips", 3))
    aspect_ratio = data.get("aspect_ratio", "9:16")
    mode = data.get("mode", "local")
    language = data.get("language", None) or None
    download_format = data.get("download_format", "720")

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "status": "queued",
        "progress": 0,
        "result": None,
        "error": None,
    }

    def run():
        try:
            from shorts_generator import generate_shorts

            jobs[job_id]["status"] = "running"
            jobs[job_id]["progress"] = 10

            result = generate_shorts(
                youtube_url=url,
                num_clips=num_clips,
                aspect_ratio=aspect_ratio,
                download_format=download_format,
                language=language,
                mode=mode,
            )

            # Convert local file paths to /api/clips/ URLs for the frontend
            shorts = result.get("shorts", [])
            for short in shorts:
                clip_path = short.get("clip_url")
                if clip_path and os.path.isfile(clip_path):
                    # Store the local path for serving
                    clip_id = f"{job_id}_{short.get('start_time', 0):.0f}"
                    clip_store[clip_id] = {
                        "path": clip_path,
                        "mode": result.get("mode"),
                        "title": short.get("title", ""),
                    }
                    short["clip_url"] = f"/api/clips/{clip_id}"
                    short["clip_path"] = clip_path

            jobs[job_id]["progress"] = 100
            jobs[job_id]["status"] = "completed"
            jobs[job_id]["result"] = {
                "mode": result.get("mode"),
                "source_video_url": result.get("source_video_url"),
                "highlights_count": len(result.get("highlights", [])),
                "shorts": shorts,
            }
        except Exception as e:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = str(e)

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"job_id": job_id, "status": "queued"})


@app.get("/api/jobs/<job_id>")
def get_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({
        "job_id": job_id,
        "status": job["status"],
        "progress": job["progress"],
        "result": job["result"],
        "error": job["error"],
    })


@app.get("/api/clips/<clip_id>")
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


@app.get("/api/download/<clip_id>")
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


@app.post("/api/reset")
def reset_jobs():
    """Clear all jobs and clips from memory."""
    jobs.clear()
    clip_store.clear()
    return jsonify({"status": "reset", "message": "All jobs and clips cleared"})


@app.get("/api/status")
def status():
    """Return server status and job count."""
    completed = sum(1 for j in jobs.values() if j["status"] == "completed")
    failed = sum(1 for j in jobs.values() if j["status"] == "failed")
    running = sum(1 for j in jobs.values() if j["status"] == "running")
    queued = sum(1 for j in jobs.values() if j["status"] == "queued")
    return jsonify({
        "status": "ok",
        "total_jobs": len(jobs),
        "by_status": {
            "queued": queued,
            "running": running,
            "completed": completed,
            "failed": failed,
        },
        "mode": os.getenv("LLM_PROVIDER", "openai"),
    })


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    port = int(os.getenv("PORT", 5000))
    print(f"AI YouTube Shorts Generator - serving on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=True, use_reloader=False)
