# .env Security Audit — 2026-09-18

## Findings

### ⚠️ CRITICAL: Real API keys present in `.env`

The `.env` file at the project root contains **actual API keys**:

| Key | Status | Risk |
|---|---|---|
| `MUAPI_API_KEY` | **Real key exposed** | ⛔ HIGH — anyone with repo access can see this |
| `GEMINI_API_KEY` | **Real key exposed** | ⛔ HIGH — anyone with repo access can see this |
| `OPENAI_API_KEY` | Not present | ✅ Safe |

**Important:** `.env` is already listed in `.gitignore`, so it should NOT be committed to git. However, if it was ever committed in the past, the keys are permanently in git history and must be rotated.

### ✅ Good Practices Already in Place

| Item | Status |
|---|---|
| `.gitignore` excludes `.env` | ✅ Confirmed |
| `.env.example` has placeholder values only | ✅ Confirmed |
| Code reads secrets via `os.getenv()`, not hardcoded | ✅ Confirmed |
| `app.py` calls `load_dotenv()` | ✅ Confirmed |

## Recommended Actions

1. **Rotate exposed keys immediately** — regenerate `MUAPI_API_KEY` and `GEMINI_API_KEY` from their respective providers
2. **Check git history** — if `.env` was ever committed:
   ```bash
   git log --all --oneline -- .env
   git filter-branch --force --index-filter 'git rm --cached --ignore-unmatch .env' --prune-empty --tag-name-callback 'true' -- -- .env
   ```
3. **Add pre-commit hook** — prevent accidental `.env` commits:
   ```bash
   # .git/hooks/pre-commit
   if git diff --cached --name-only | grep -q "^\.env$"; then
     echo "ERROR: .env file detected in staging area!"
     exit 1
   fi
   ```
4. **Consider GitHub Secrets** — for CI/CD, store keys as `secrets.MUAPI_API_KEY`, `secrets.GEMINI_API_KEY` instead of in `.env`
5. **Set `SECRET_KEY`** for Flask sessions if any session-based features are added

## .env File Contents (redacted)

```
MUAPI_API_KEY=<REDACTED — real key>
LLM_PROVIDER=gemini
OPENAI_MODEL=gpt-4o-mini
GEMINI_API_KEY=<REDACTED — real key>
GEMINI_MODEL=gemini-3.6-flash
LOCAL_WHISPER_MODEL=base
LOCAL_WHISPER_DEVICE=auto
LOCAL_OUTPUT_DIR=output
```

## Audit Date
- **Date:** 2026-09-18
- **Auditor:** Claude Code
- **Result:** ⚠️ KEYS EXPOSED — ROTATE IMMEDIATELY
