"""Local YouTube download via yt-dlp.

Returns a local mp4 path so the rest of the local pipeline can read it
directly off disk.
"""
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
from typing import Optional

from ..config import LOCAL_OUTPUT_DIR


def _import_ytdlp():
    try:
        import yt_dlp  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "yt-dlp is required for --mode local. Install it with:\n"
            "    pip install -r requirements-local.txt"
        ) from e
    return yt_dlp


def ffmpeg_exe() -> str:
    """Bundled imageio-ffmpeg binary if installed, else rely on ffmpeg on PATH."""
    try:
        import imageio_ffmpeg  # type: ignore
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return "ffmpeg"


def has_audio(path: str) -> bool:
    """True if the media file contains at least one audio stream."""
    # `ffmpeg -i` with no output exits non-zero but prints the stream list to stderr.
    proc = subprocess.run(
        [ffmpeg_exe(), "-hide_banner", "-i", path],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return re.search(r"Stream #\d+:\d+.*: Audio:", proc.stderr) is not None


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _friendly_download_error(message: str) -> str:
    """Strip yt-dlp's terminal colours / prefix and explain the common cases."""
    text = _ANSI_RE.sub("", message).strip()
    text = re.sub(r"^ERROR:\s*", "", text)
    if text.startswith("Unsupported URL"):
        return (
            "That link isn't a video page we can download. "
            "Paste a YouTube video link, like https://www.youtube.com/watch?v=..."
        )
    if "Private video" in text or "Sign in" in text:
        return "That video is private or needs a sign-in, so it can't be downloaded."
    if "Video unavailable" in text:
        return "That video is unavailable. It may have been removed or blocked in your region."
    return f"Download failed: {text}"


def _format_for(fmt: str) -> str:
    """Map our '720' / '1080' shorthand to a yt-dlp format selector.

    Prefers H.264 + m4a (decodes everywhere) and never accepts a silent,
    video-only file — Whisper needs the audio track.
    """
    try:
        height = int(fmt)
    except ValueError:
        height = 720
    return (
        f"bestvideo[height<={height}][vcodec^=avc1]+bestaudio[ext=m4a]/"
        f"bestvideo[height<={height}]+bestaudio/"
        f"best[height<={height}][acodec!=none]/"
        f"best[acodec!=none]"
    )


def _extract_youtube_video_id(source: str) -> Optional[str]:
    """Best-effort extraction of a YouTube video id from a URL."""
    parsed = urlparse(source)
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]

    if host in ("youtu.be", "www.youtu.be"):
        video_id = parsed.path.lstrip("/").split("/", 1)[0]
        return video_id or None

    if "youtube.com" in host:
        if parsed.path.startswith("/watch"):
            qs = parse_qs(parsed.query)
            video_id = qs.get("v", [""])[0]
            return video_id or None
        match = re.search(r"/(?:shorts|embed|live)/([^/?#&]+)", parsed.path)
        if match:
            return match.group(1)

    return None


def _resolve_local_path(source: str) -> Optional[str]:
    """Return a local filesystem path if the input already points at one."""
    parsed = urlparse(source)
    if parsed.scheme == "file":
        raw_path = unquote(parsed.path)
        if parsed.netloc and parsed.netloc not in ("", "localhost"):
            raw_path = f"//{parsed.netloc}{raw_path}"
        candidate = Path(raw_path).expanduser()
        if candidate.exists() and candidate.is_file():
            return str(candidate.resolve())
        raise RuntimeError(f"Local file URL does not exist: {source}")

    if parsed.scheme in ("http", "https"):
        return None

    candidate = Path(source).expanduser()
    if candidate.exists() and candidate.is_file():
        return str(candidate.resolve())

    if any(sep in source for sep in (os.sep, "/")) or source.startswith("~") or source.startswith("."):
        raise RuntimeError(f"Local file path does not exist: {source}")

    return None


def _existing_download(out_dir: str, video_id: str) -> Optional[str]:
    """Return a cached download path if we already have this YouTube id."""
    for ext in (".mp4", ".mkv", ".webm"):
        candidate = os.path.join(out_dir, f"source_{video_id}{ext}")
        if os.path.exists(candidate):
            if has_audio(candidate):
                return candidate
            # Earlier runs could cache a video-only file; purge it so we re-download.
            print(f"[download/local] cached file has no audio, deleting: {candidate}", flush=True)
            os.remove(candidate)
    return None


def download_youtube_local(video_url: str, fmt: str = "720", out_dir: Optional[str] = None) -> str:
    """Download a remote URL or return a local file path unchanged."""
    local_path = _resolve_local_path(video_url)
    if local_path:
        print(f"[download/local] using local file: {local_path}", flush=True)
        return local_path

    yt_dlp = _import_ytdlp()
    out_dir = out_dir or LOCAL_OUTPUT_DIR
    os.makedirs(out_dir, exist_ok=True)

    video_id = _extract_youtube_video_id(video_url)
    if video_id:
        cached = _existing_download(out_dir, video_id)
        if cached:
            print(f"[download/local] reusing cached download: {cached}", flush=True)
            return cached

    print(f"[download/local] {video_url} @ {fmt}p -> {out_dir}/", flush=True)
    ydl_opts = {
        "format": _format_for(fmt),
        "outtmpl": os.path.join(out_dir, "source_%(id)s.%(ext)s"),
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "retries": 10,
        "fragment_retries": 10,
        "js_runtimes": {"node": {}},
        # YouTube's signature/n challenges need the EJS solver script; without it
        # audio formats go missing and downloads come back silent.
        "remote_components": ["ejs:github"],
    }
    exe = ffmpeg_exe()
    if exe != "ffmpeg":
        ydl_opts["ffmpeg_location"] = exe

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(video_url, download=True)
        except yt_dlp.utils.DownloadError as e:
            raise RuntimeError(_friendly_download_error(str(e))) from e
        path = ydl.prepare_filename(info)
        # merge_output_format may rename the extension after merge
        if not os.path.exists(path):
            stem, _ = os.path.splitext(path)
            for ext in (".mp4", ".mkv", ".webm"):
                if os.path.exists(stem + ext):
                    path = stem + ext
                    break

    if not has_audio(path):
        os.remove(path)
        raise RuntimeError(
            "Downloaded video has no audio track, so it can't be transcribed. "
            "Try updating yt-dlp (pip install -U yt-dlp) or a different quality."
        )

    print(f"[download/local] ready: {path}", flush=True)
    return path
