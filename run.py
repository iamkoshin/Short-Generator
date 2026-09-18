"""Production entry point for AI YouTube Shorts Generator.

Usage:
    python run.py                      # direct execution
    gunicorn run:app -w 2 -b 0.0.0.0:5000  # gunicorn
    waitress-serve --port=5000 run:app        # waitress
"""
import os
import sys

# Windows: reconfigure stdout for UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv()

port = int(os.getenv("PORT", 5000))
host = os.getenv("HOST", "0.0.0.0")
workers = int(os.getenv("WORKERS", 2))

# Import Flask app after environment variables are loaded
from app import app


if __name__ == "__main__":
    try:
        from waitress import serve
        print(f"AI YouTube Shorts Generator - serving on http://{host}:{port} (waitress, {workers} workers)")
        serve(app, host=host, port=port, threads=workers)
    except ImportError:
        print("waitress not installed, falling back to Flask dev server...")
        app.run(host=host, port=port, debug=False, use_reloader=False)
