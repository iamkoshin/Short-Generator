"""Local LLM backend — OpenAI or Gemini, selected by LLM_PROVIDER."""
import datetime as dt
import json
import os
import threading
import time
from typing import Callable, Dict, List, Optional

from ..config import (
    GEMINI_MODELS,
    GEMINI_TIMEOUT_SECONDS,
    LLM_PROVIDER,
    LOCAL_OUTPUT_DIR,
    OPENAI_MODEL,
    require_gemini_key,
    require_openai_key,
)

GEMINI_MAX_ATTEMPTS = 3
# Short-lived failures worth a quick retry on the same model.
RETRYABLE_CODES = (429, 500, 503)

# Optional hook so the web UI can show which model is being asked right now.
_status_cb: Optional[Callable[[str], None]] = None


def set_status_callback(fn: Optional[Callable[[str], None]]) -> None:
    global _status_cb
    _status_cb = fn


def _report(message: str) -> None:
    print(f"[llm/gemini] {message}", flush=True)
    if _status_cb:
        try:
            _status_cb(message)
        except Exception:
            pass


def call_openai_llm(prompt: str) -> str:
    """OpenAI Chat Completions backend used by --mode local."""
    try:
        from openai import OpenAI  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "openai is required for --mode local. Install it with:\n"
            "    pip install -r requirements-local.txt"
        ) from e

    client = OpenAI(api_key=require_openai_key())
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=0.7,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content or ""


# --- Gemini free-tier quota tracking -------------------------------------------

def _pacific_now() -> dt.datetime:
    """Gemini's daily quotas reset at midnight US Pacific time."""
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo("America/Los_Angeles"))
    except Exception:  # no tz database (tzdata not installed on Windows)
        return dt.datetime.now(dt.timezone(dt.timedelta(hours=-7)))


def _hours_until_reset() -> float:
    now = _pacific_now()
    midnight = (now + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return (midnight - now).total_seconds() / 3600


class _QuotaBook:
    """Remembers which models are used up today, across server restarts.

    Stored as {model: "YYYY-MM-DD" (Pacific)}; entries from earlier days are
    simply ignored, so models come back automatically after the reset.
    """

    def __init__(self, path: str):
        self.path = path
        self.lock = threading.Lock()

    def _load(self) -> Dict[str, str]:
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def exhausted_today(self) -> List[str]:
        today = _pacific_now().date().isoformat()
        # Entries are {"date", "reason"}; older files stored just the date string.
        return [
            m for m, v in self._load().items()
            if (v.get("date") if isinstance(v, dict) else v) == today
        ]

    def mark(self, model: str, reason: str) -> None:
        with self.lock:
            data = self._load()
            data[model] = {"date": _pacific_now().date().isoformat(), "reason": reason}
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)


_quota = _QuotaBook(os.path.join(LOCAL_OUTPUT_DIR, ".gemini_quota.json"))


def gemini_quota_status() -> Dict:
    exhausted = [m for m in _quota.exhausted_today() if m in GEMINI_MODELS]
    return {
        "models": GEMINI_MODELS,
        "exhausted": exhausted,
        "available": len(GEMINI_MODELS) - len(exhausted),
        "resets_in_hours": round(_hours_until_reset(), 1),
    }


def _skip_reason(e) -> Optional[str]:
    """Why this error means "stop using this model today", or None if it doesn't."""
    code = getattr(e, "code", None)
    text = str(e)
    if code == 429 and "PerDay" in text:
        return "daily limit reached"
    if code in (403, 404) or (code == 400 and ("not found" in text.lower() or "not supported" in text.lower())):
        return "not available on this key"
    return None


def call_gemini_llm(prompt: str) -> str:
    """Gemini backend used by --mode local when LLM_PROVIDER=gemini.

    Free-tier limits are per model, so walk GEMINI_MODELS and skip any model
    that has hit its daily quota (or isn't available to this key).
    """
    try:
        from google import genai  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "google-genai is required for LLM_PROVIDER=gemini. Install it with:\n"
            "    pip install -r requirements-local.txt"
        ) from e

    import httpx  # installed with google-genai
    from google.genai import errors as genai_errors  # type: ignore
    from google.genai import types as genai_types  # type: ignore

    client = genai.Client(
        api_key=require_gemini_key(),
        http_options=genai_types.HttpOptions(timeout=int(GEMINI_TIMEOUT_SECONDS * 1000)),
    )
    skipped = set(_quota.exhausted_today())
    candidates = [m for m in GEMINI_MODELS if m not in skipped]
    last_error: Optional[Exception] = None

    for i, model in enumerate(candidates):
        nxt = candidates[i + 1] if i + 1 < len(candidates) else None
        switching = f", switching to {nxt}" if nxt else ""
        _report(f"asking {model}")
        try:
            text = _gemini_generate(client, genai_errors, model, prompt)
            _report(f"answered by {model}")
            return text
        except genai_errors.APIError as e:
            last_error = e
            reason = _skip_reason(e)
            if reason:
                _quota.mark(model, reason)
            elif getattr(e, "code", None) not in RETRYABLE_CODES:
                raise
            _report(f"{model} {reason or 'still overloaded'}{switching}")
        except (httpx.TimeoutException, httpx.TransportError) as e:
            # Stalled or dropped connection: try the next model rather than hang.
            last_error = e
            _report(f"{model} didn't answer within {GEMINI_TIMEOUT_SECONDS:.0f}s{switching}")

    if isinstance(last_error, (httpx.TimeoutException, httpx.TransportError)):
        raise RuntimeError(
            "Gemini isn't answering (every model timed out). Check your internet connection, "
            "or try again in a few minutes."
        ) from last_error
    if last_error is not None and _skip_reason(last_error) is None:
        raise last_error  # every model was overloaded rather than out of quota
    raise RuntimeError(
        "All Gemini free models have hit today's limit. They reset at midnight Pacific time "
        f"(in about {_hours_until_reset():.0f}h). Enable billing on your Google AI project, "
        "or switch Run on to MuAPI cloud."
    )


def _gemini_generate(client, genai_errors, model: str, prompt: str) -> str:
    # Gemini returns 503 "high demand" / per-minute 429 spikes that usually clear
    # within seconds — retry briefly. A daily-quota 429 won't clear, so fail fast.
    for attempt in range(1, GEMINI_MAX_ATTEMPTS + 1):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config={
                    "temperature": 0.2,
                    "response_mime_type": "application/json",
                    "max_output_tokens": 8192,
                },
            )
            return response.text or ""
        except genai_errors.APIError as e:
            if (
                getattr(e, "code", None) not in RETRYABLE_CODES
                or _skip_reason(e)
                or attempt == GEMINI_MAX_ATTEMPTS
            ):
                raise
            delay = 5 * attempt
            print(f"[llm/gemini] {model}: {e.code} on attempt {attempt}/{GEMINI_MAX_ATTEMPTS}; retrying in {delay}s", flush=True)
            time.sleep(delay)
    return ""


def call_local_llm(prompt: str) -> str:
    """Dispatch to the configured local LLM provider."""
    provider = (LLM_PROVIDER or "openai").strip().lower()
    if provider == "openai":
        return call_openai_llm(prompt)
    if provider == "gemini":
        return call_gemini_llm(prompt)
    raise RuntimeError(
        f"Unknown LLM_PROVIDER={provider!r}. Use 'openai' or 'gemini'."
    )
