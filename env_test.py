"""Quick environment test for the YouTube Shorts Generator."""
import os
import sys

from dotenv import load_dotenv
load_dotenv()

print("=== Environment Check ===\n")

gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
openai_key = os.getenv("OPENAI_API_KEY", "").strip()
llm_provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()
muapi_key = os.getenv("MUAPI_API_KEY", "").strip()
whisper_model = os.getenv("LOCAL_WHISPER_MODEL", "base")
whisper_device = os.getenv("LOCAL_WHISPER_DEVICE", "auto")

print(f"LLM_PROVIDER:    {llm_provider}")
print(f"GEMINI_API_KEY:  {'SET' if gemini_key and gemini_key != 'your_gemini_key_here' else 'NOT SET (placeholder)'}")
print(f"OPENAI_API_KEY:  {'SET' if openai_key and openai_key != 'your_openai_key_here' else 'NOT SET (placeholder)'}")
print(f"MUAPI_API_KEY:   {'SET' if muapi_key else 'NOT SET'}")
print(f"WHISPER_MODEL:   {whisper_model}")
print(f"WHISPER_DEVICE:  {whisper_device}")

if llm_provider == "gemini" and gemini_key and gemini_key != "your_gemini_key_here":
    print("\n-> Testing Gemini API connection...")
    try:
        import google.genai as genai
        client = genai.Client(api_key=gemini_key)
        response = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
            contents="Reply with exactly: API connection successful",
        )
        print(f"-> Gemini response: {response.text.strip()}")
        print("\nGemini API key is valid and working!")
    except Exception as e:
        print(f"\nGemini API test FAILED: {e}")
elif llm_provider == "gemini" and gemini_key == "your_gemini_key_here":
    print("\n-> Gemini key is still the placeholder!")
    print("   Put your actual Gemini API key in the .env file:")
    print("   GEMINI_API_KEY=<your_actual_key>")
elif llm_provider == "openai":
    print(f"\n-> LLM_PROVIDER is 'openai', not 'gemini'.")
    print("   To use Gemini, set in .env: LLM_PROVIDER=gemini")
    print("   And ensure GEMINI_API_KEY is your real key.")
else:
    print("\n-> Unexpected configuration.")

# Check core dependencies
print("\n=== Dependency Check ===")
deps = {
    "requests": "requests",
    "dotenv": "python-dotenv",
    "google.genai": "google-genai",
    "openai": "openai",
    "faster_whisper": "faster-whisper",
    "yt_dlp": "yt-dlp",
    "cv2": "opencv-python",
}
for mod, pkg in deps.items():
    try:
        __import__(mod)
        print(f"  {pkg:20s} OK")
    except ImportError:
        print(f"  {pkg:20s} NOT INSTALLED")

print("\n=== Done ===")
