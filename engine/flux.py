"""
engine/flux.py - Cloudflare Workers AI FLUX-1-schnell Image Generator
The ONLY visual generator in the system. Never falls back to third-party providers.
"""

import os
import io
import time
import base64
import json
import urllib.request
import urllib.error
from typing import Tuple

from PIL import Image

from engine.config import (
    get_cloudflare_account_id,
    get_cloudflare_api_token,
    get_flux_model,
    get_flux_steps,
    get_flux_timeout,
    get_flux_cooldown_seconds
)

# Global in-memory cooldown timestamp
_cooldown_until: float = 0.0


def is_rate_limited() -> bool:
    """Returns True if the FLUX generator is currently in cooldown."""
    global _cooldown_until
    return time.time() < _cooldown_until


def set_cooldown(seconds: int = 900) -> None:
    """Sets a temporary cooldown timestamp upon receiving HTTP 429."""
    global _cooldown_until
    _cooldown_until = time.time() + seconds


def clear_cooldown() -> None:
    """Clears any active cooldown (useful in tests)."""
    global _cooldown_until
    _cooldown_until = 0.0


def crop_to_9_16(img: Image.Image) -> Image.Image:
    """Center-cover-crop the image to 9:16 aspect ratio (e.g. 1080x1920)."""
    w, h = img.size
    target_ratio = 9.0 / 16.0
    current_ratio = w / float(h)

    if abs(current_ratio - target_ratio) < 0.01:
        return img

    if current_ratio > target_ratio:
        # Image is wider than 9:16 -> crop width
        new_w = int(h * target_ratio)
        offset = (w - new_w) // 2
        return img.crop((offset, 0, offset + new_w, h))
    else:
        # Image is taller than 9:16 -> crop height
        new_h = int(w / target_ratio)
        offset = (h - new_h) // 2
        return img.crop((0, offset, w, offset + new_h))


def _post_cf(url: str, headers: dict, payload: dict, timeout: int) -> dict:
    """Helper for Cloudflare API call, easily monkeypatched in tests."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def generate(prompt: str, out_path: str) -> Tuple[bool, str]:
    """
    Generates an image from prompt using Cloudflare Workers AI FLUX.
    Saves the image to out_path cropped to 9:16.

    Returns:
        (True, "flux") on success
        (False, reason) on failure, where reason is one of:
            "flux_not_configured"
            "flux_rate_limited"
            "flux_timeout"
            "flux_error"
            "flux_empty"
    """
    account_id = get_cloudflare_account_id()
    api_token = get_cloudflare_api_token()

    if not account_id or not api_token:
        return False, "flux_not_configured"

    if is_rate_limited():
        return False, "flux_rate_limited"

    model = get_flux_model()
    steps = get_flux_steps()
    timeout = get_flux_timeout()
    cooldown_secs = get_flux_cooldown_seconds()

    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "prompt": prompt,
        "steps": steps
    }

    last_reason = "flux_error"
    attempts = 2

    for attempt in range(attempts):
        try:
            resp_data = _post_cf(url, headers, payload, timeout=timeout)

            # Check for Cloudflare success format
            if not resp_data.get("success", False) and "result" not in resp_data:
                errors = resp_data.get("errors", [])
                err_msg = errors[0].get("message", "") if errors else "Unknown CF error"
                print(f"[FLUX] Cloudflare error (attempt {attempt+1}): {err_msg}")
                last_reason = "flux_error"
                time.sleep(1.0)
                continue

            result = resp_data.get("result", {})
            img_b64 = result.get("image")
            if not img_b64:
                print(f"[FLUX] Result missing image data (attempt {attempt+1})")
                last_reason = "flux_empty"
                time.sleep(1.0)
                continue

            # Decode image
            raw_bytes = base64.b64decode(img_b64)
            img = Image.open(io.BytesIO(raw_bytes))

            # Crop to 9:16 and resize to standard 1080x1920 if needed
            cropped = crop_to_9_16(img)
            if cropped.size != (1080, 1920):
                cropped = cropped.resize((1080, 1920), Image.Resampling.LANCZOS)

            # Ensure parent dir exists and save
            os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
            cropped.save(out_path, "JPEG", quality=92)
            return True, "flux"

        except urllib.error.HTTPError as e:
            if e.code == 429:
                print(f"[FLUX] Cloudflare rate limit (429), setting cooldown for {cooldown_secs}s")
                set_cooldown(cooldown_secs)
                return False, "flux_rate_limited"
            elif e.code in (500, 502, 503, 504):
                print(f"[FLUX] Server error HTTP {e.code} (attempt {attempt+1})")
                last_reason = "flux_error"
                time.sleep(1.5)
            else:
                print(f"[FLUX] HTTP {e.code} error: {e}")
                last_reason = "flux_error"
                break
        except urllib.error.URLError as e:
            if "timed out" in str(e).lower() or isinstance(e.reason, TimeoutError):
                print(f"[FLUX] Request timed out (attempt {attempt+1})")
                last_reason = "flux_timeout"
                time.sleep(1.0)
            else:
                print(f"[FLUX] URL error: {e}")
                last_reason = "flux_error"
                break
        except Exception as e:
            if "timed out" in str(e).lower():
                print(f"[FLUX] Timeout: {e}")
                last_reason = "flux_timeout"
            else:
                print(f"[FLUX] Unexpected error: {e}")
                last_reason = "flux_error"
            time.sleep(1.0)

    # Ensure no partial file is left on disk on failure
    if os.path.exists(out_path):
        try:
            os.remove(out_path)
        except Exception:
            pass

    return False, last_reason


def generate_flux_image(prompt: str, output_path: str = "") -> Tuple[bool, str]:
    """Backward compatibility alias for existing code."""
    return generate(prompt=prompt, out_path=output_path)


# Backward compatibility aliases for existing tests
is_flux_in_cooldown = is_rate_limited
set_flux_cooldown = set_cooldown
reset_flux_cooldown = clear_cooldown

