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
