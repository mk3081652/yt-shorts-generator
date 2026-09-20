"""
engine/flux.py - Cloudflare Workers AI FLUX.1-schnell Client
The single, dedicated image generation provider for YouTube Shorts.
"""

import os
import time
import json
import base64
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


def generate_pollinations_flux_image(
    prompt: str,
    output_path: str,
    timeout: int = 40
) -> Tuple[bool, str]:
    """
    Generates a 9:16 vertical image via Pollinations.ai FLUX model.
    Free, no API key required, reliable FLUX provider.
    """
    import urllib.parse
    clean_prompt = prompt.strip()
    if not clean_prompt:
        return False, "flux_empty"

    # Enforce vertical composition & quality hints
    suffix = "subject centered, vertical composition, 9:16, no text, no watermark"
    if suffix not in clean_prompt:
        clean_prompt = f"{clean_prompt}, {suffix}"

    encoded = urllib.parse.quote(clean_prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=1080&height=1920&model=flux&nologo=true"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            if len(data) < 1000:
                return False, "flux_empty"
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(data)
            crop_to_9_16(output_path)
            print(f"[FLUX] Successfully generated via Pollinations FLUX ({len(data)} bytes)")
            return True, "flux"
    except Exception as e:
        print(f"[FLUX] Pollinations FLUX error: {e}")
        return False, "flux_error"


def generate_flux_image(
    prompt: str,
    output_path: str,
    steps: int = 4,
    max_retries: int = 2
) -> Tuple[bool, str]:
    """
    Generates an image via FLUX.
    Attempts Cloudflare Workers AI FLUX.1-schnell first (if configured and not in cooldown).
    Seamlessly falls back to Pollinations FLUX if Cloudflare is unconfigured, rate-limited (429), or errors.
    Returns (success: bool, tier_or_reason: str).
    """
    clean_prompt = prompt.strip()
    if not clean_prompt:
        return False, "flux_empty"

    account_id = get_cloudflare_account_id()
    api_token = get_cloudflare_api_token()

    # Try Cloudflare Workers AI FLUX if configured and not cooling down
    if account_id and api_token and not is_flux_in_cooldown():
        suffix = "subject centered, vertical composition, no text, no watermark"
        if suffix not in clean_prompt:
            clean_prompt = f"{clean_prompt}, {suffix}"

        safe_steps = min(8, max(1, steps))
        url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/@cf/black-forest-labs/flux-1-schnell"
        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }
        body = json.dumps({"prompt": clean_prompt, "steps": safe_steps}).encode("utf-8")
        timeout = get_flux_timeout()

        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(url, data=body, headers=headers)
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    img_b64 = data.get("result", {}).get("image")
                    if not img_b64:
                        continue

                    img_bytes = base64.b64decode(img_b64)
                    if len(img_bytes) < 1000:
                        continue

                    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
                    with open(output_path, "wb") as f:
                        f.write(img_bytes)

                    crop_to_9_16(output_path)
                    print(f"[FLUX] Successfully generated via Cloudflare FLUX ({len(img_bytes)} bytes)")
                    return True, "flux"

            except urllib.error.HTTPError as e:
                if e.code == 429:
                    print(f"[FLUX] Cloudflare rate limit (429) hit. Entering cooldown for {get_flux_cooldown_seconds()}s. Falling back to Pollinations FLUX...")
                    set_flux_cooldown()
                    break  # Fall back to Pollinations immediately
                print(f"[FLUX] Cloudflare HTTP {e.code} on attempt {attempt + 1}: {e}")
                time.sleep(1.0 * (attempt + 1))

            except Exception as e:
                print(f"[FLUX] Cloudflare error on attempt {attempt + 1}: {e}")
                time.sleep(1.0 * (attempt + 1))

    # Fallback Tier: Pollinations FLUX (always available, free, no API key needed)
    print(f"[FLUX] Using Pollinations FLUX for: {clean_prompt[:60]}...")
    ok, reason = generate_pollinations_flux_image(clean_prompt, output_path)
    if ok:
        return True, "flux"

    return False, reason
