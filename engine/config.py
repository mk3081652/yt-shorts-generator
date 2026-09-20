"""
engine/config.py - Centralized configuration and single .env loader
Part of the YouTube Shorts Generator.
"""

import os

def load_environment():
    """Finds and loads the root .env file once into os.environ."""
    # Find .env in project root
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
                        # Do not overwrite if already explicitly set in environment
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

def get_gemini_fallback_models() -> list[str]:
    raw = os.environ.get("GEMINI_FALLBACK_MODELS", "gemini-3.7-flash,gemini-flash-latest")
    return [m.strip() for m in raw.split(",") if m.strip()]

def get_cloudflare_account_id() -> str:
    return os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()

def get_cloudflare_api_token() -> str:
    return os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()

def get_flux_timeout() -> int:
    try:
        return int(os.environ.get("FLUX_TIMEOUT", "45"))
    except ValueError:
        return 45

def get_flux_cooldown_seconds() -> int:
    try:
        return int(os.environ.get("FLUX_COOLDOWN_SECONDS", "900"))
    except ValueError:
        return 900

def is_vision_qa_enabled() -> bool:
    return os.environ.get("VISION_QA", "0").strip().lower() in ("1", "true", "yes")
