"""
engine/flux.py - Cloudflare Workers AI FLUX.1-schnell Client
The single, dedicated image generation provider for YouTube Shorts.
"""

import os
import time
import json
import base64
import socket
import urllib.request
import urllib.error
from typing import Tuple, Optional
from PIL import Image

from engine.config import (
    get_cloudflare_account_id,
    get_cloudflare_api_token,
    get_flux_timeout,
    get_flux_cooldown_seconds
)

# Cooldown timestamp (epoch seconds) when a 429 rate limit is received
_flux_cooldown_until: float = 0.0


def is_flux_in_cooldown() -> bool:
    global _flux_cooldown_until
    return time.time() < _flux_cooldown_until


def set_flux_cooldown(seconds: Optional[int] = None):
    global _flux_cooldown_until
    cd = seconds if seconds is not None else get_flux_cooldown_seconds()
    _flux_cooldown_until = time.time() + cd


def reset_flux_cooldown():
    global _flux_cooldown_until
    _flux_cooldown_until = 0.0


def crop_to_9_16(image_path: str):
    """Performs a center-cover-crop to 9:16 vertical aspect ratio using Pillow."""
    try:
        with Image.open(image_path) as img:
            w, h = img.size
            target_ratio = 9.0 / 16.0
            current_ratio = w / h

            if abs(current_ratio - target_ratio) < 0.01:
                return  # Already ~9:16

            if current_ratio > target_ratio:
                # Wider than 9:16 (e.g. 1:1 square) -> crop sides
                new_w = int(h * target_ratio)
                left = (w - new_w) // 2
                right = left + new_w
                box = (left, 0, right, h)
            else:
                # Taller than 9:16 -> crop top/bottom
                new_h = int(w / target_ratio)
                top = (h - new_h) // 2
                bottom = top + new_h
                box = (0, top, w, bottom)

            cropped = img.crop(box)
            cropped.save(image_path, quality=92)
    except Exception as e:
        print(f"[FLUX] Warning: Failed to crop image to 9:16: {e}")


def generate_flux_image(
    prompt: str,
    output_path: str,
    steps: int = 4,
    max_retries: int = 2
) -> Tuple[bool, str]:
    """
    Generates an image via Cloudflare Workers AI FLUX.1-schnell.
    Returns (success: bool, reason: str).
    Reason on failure: flux_not_configured | flux_rate_limited | flux_timeout | flux_error | flux_empty
    Reason on success: flux
    """
    clean_prompt = prompt.strip()
    if not clean_prompt:
        return False, "flux_empty"

    account_id = get_cloudflare_account_id()
    api_token = get_cloudflare_api_token()

    if not account_id or not api_token:
        return False, "flux_not_configured"

    if is_flux_in_cooldown():
        return False, "flux_rate_limited"

    suffix = "subject centered, vertical composition, no text, no watermark"
    if suffix not in clean_prompt:
        clean_prompt = f"{clean_prompt}, {suffix}"

    safe_steps = min(8, max(1, steps))
    model = os.environ.get("FLUX_MODEL", "@cf/black-forest-labs/flux-1-schnell").strip()
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }
    body = json.dumps({"prompt": clean_prompt, "steps": safe_steps}).encode("utf-8")
    timeout = get_flux_timeout()

    last_reason = "flux_error"

    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                img_b64 = data.get("result", {}).get("image")
                if not img_b64:
                    last_reason = "flux_empty"
                    continue

                img_bytes = base64.b64decode(img_b64)
                if len(img_bytes) < 1000:
                    last_reason = "flux_empty"
                    continue

                os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
                with open(output_path, "wb") as f:
                    f.write(img_bytes)

                crop_to_9_16(output_path)
                print(f"[FLUX] Successfully generated via Cloudflare FLUX ({len(img_bytes)} bytes)")
                return True, "flux"

        except urllib.error.HTTPError as e:
            if e.code == 429:
                print(f"[FLUX] Cloudflare rate limit (429) hit. Entering cooldown for {get_flux_cooldown_seconds()}s.")
                set_flux_cooldown()
                return False, "flux_rate_limited"
            print(f"[FLUX] Cloudflare HTTP {e.code} on attempt {attempt + 1}: {e}")
            last_reason = "flux_error"
            if attempt + 1 < max_retries:
                time.sleep(1.0 * (attempt + 1))

        except (socket.timeout, TimeoutError):
            print(f"[FLUX] Cloudflare request timed out on attempt {attempt + 1}")
            last_reason = "flux_timeout"
            if attempt + 1 < max_retries:
                time.sleep(1.0 * (attempt + 1))

        except urllib.error.URLError as e:
            if isinstance(e.reason, socket.timeout) or "timed out" in str(e.reason).lower():
                print(f"[FLUX] Cloudflare request timed out on attempt {attempt + 1}")
                last_reason = "flux_timeout"
            else:
                print(f"[FLUX] Cloudflare URL error on attempt {attempt + 1}: {e}")
                last_reason = "flux_error"
            if attempt + 1 < max_retries:
                time.sleep(1.0 * (attempt + 1))

        except Exception as e:
            print(f"[FLUX] Cloudflare error on attempt {attempt + 1}: {e}")
            last_reason = "flux_error"
            if attempt + 1 < max_retries:
                time.sleep(1.0 * (attempt + 1))

    return False, last_reason
