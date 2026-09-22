"""
engine/config.py - Centralized configuration and single .env loader.
Reads all typed getters dynamically at call time from os.environ.
"""

import os
from typing import List


def load_environment() -> None:
    """Finds and loads the root .env file once into os.environ."""
    curr = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(curr)
    env_path = os.path.join(root_dir, ".env")

    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if k not in os.environ:
                            os.environ[k] = v
        except Exception as e:
            print(f"[Config] Warning: Failed to load .env file: {e}")


# Load environment on import
load_environment()


def get_gemini_api_key() -> str:
    return os.environ.get("GEMINI_API_KEY", "").strip()


def get_gemini_model() -> str:
    return os.environ.get("GEMINI_MODEL", "gemini-3.8-flash").strip()


def get_gemini_fallback_models() -> List[str]:
    raw = os.environ.get("GEMINI_FALLBACK_MODELS", "gemini-3.7-flash,gemini-flash-latest")
    return [m.strip() for m in raw.split(",") if m.strip()]


def get_gemini_thinking_level() -> str:
    level = os.environ.get("GEMINI_THINKING_LEVEL", "low").strip().lower()
    if level in ("low", "medium", "high"):
        return level
    return "low"


def get_vision_qa() -> int:
    val = os.environ.get("VISION_QA", "0").strip().lower()
    return 1 if val in ("1", "true", "yes") else 0


def is_vision_qa_enabled() -> bool:
    return get_vision_qa() == 1


def get_cloudflare_account_id() -> str:
    return os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()


def get_cloudflare_api_token() -> str:
    return os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()


def get_flux_model() -> str:
    return os.environ.get("FLUX_MODEL", "@cf/black-forest-labs/flux-1-schnell").strip()


def get_flux_steps() -> int:
    try:
        val = int(os.environ.get("FLUX_STEPS", "4"))
        return max(1, min(8, val))  # Clamped to max 8
    except (ValueError, TypeError):
        return 4


def get_flux_timeout() -> int:
    try:
        return int(os.environ.get("FLUX_TIMEOUT", "45"))
    except (ValueError, TypeError):
        return 45


def get_flux_cooldown_seconds() -> int:
    try:
        return int(os.environ.get("FLUX_COOLDOWN_SECONDS", "900"))
    except (ValueError, TypeError):
        return 900


def get_allowed_origins() -> List[str]:
    raw = os.environ.get("ALLOWED_ORIGINS", "").strip()
    if raw:
        return [orig.strip() for orig in raw.split(",") if orig.strip()]
    return [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
        "http://127.0.0.1:3000"
    ]


def get_openai_api_key() -> str:
    return os.environ.get("OPENAI_API_KEY", "").strip()


def get_elevenlabs_api_key() -> str:
    return os.environ.get("ELEVENLABS_API_KEY", "").strip()


def get_elevenlabs_voice_id() -> str:
    return os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM").strip()


def get_tts_provider() -> str:
    p = os.environ.get("TTS_PROVIDER", "edge").strip().lower()
    if p in ("elevenlabs", "openai", "edge"):
        return p
    return "edge"


def get_motion_texture() -> str:
    t = os.environ.get("MOTION_TEXTURE", "film_grain").strip().lower()
    return "film_grain" if t in ("film_grain", "grain", "1", "true") else "none"


def get_storage_provider() -> str:
    return os.environ.get("STORAGE_PROVIDER", "local").strip().lower()


def get_s3_bucket() -> str:
    return os.environ.get("AWS_S3_BUCKET", "").strip()


def get_cloudinary_url() -> str:
    return os.environ.get("CLOUDINARY_URL", "").strip()


def get_youtube_client_secrets_path() -> str:
    """Returns absolute path to YouTube client_secrets.json."""
    custom = os.environ.get("YOUTUBE_CLIENT_SECRETS_FILE", "").strip()
    if custom and os.path.exists(custom):
        return os.path.abspath(custom)
    if os.path.exists("/etc/secrets/client_secrets.json"):
        return "/etc/secrets/client_secrets.json"
    curr = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(curr)
    return os.path.join(root_dir, "client_secrets.json")


def get_youtube_tokens_dir() -> str:
    """Returns absolute path to YouTube tokens directory for multi-channel support."""
    custom = os.environ.get("YOUTUBE_TOKENS_DIR", "").strip()
    if custom:
        return os.path.abspath(custom)
    curr = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(curr)
    return os.path.join(root_dir, "tokens")


def get_youtube_token_path() -> str:
    """Returns absolute path to YouTube token.json (cached OAuth credentials fallback)."""
    custom = os.environ.get("YOUTUBE_TOKEN_FILE", "").strip()
    if custom and os.path.exists(custom):
        return os.path.abspath(custom)
    if os.path.exists("/etc/secrets/token.json"):
        return "/etc/secrets/token.json"
    curr = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(curr)
    return os.path.join(root_dir, "token.json")


