#!/usr/bin/env python3
"""
scripts/live_check.py - Verify live Gemini 3.8 Flash and Cloudflare FLUX credentials.
Usage:
    python scripts/live_check.py
"""

import os
import sys
import tempfile

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.config import (
    get_gemini_api_key,
    get_gemini_model,
    get_cloudflare_account_id,
    get_cloudflare_api_token
)
from engine.gemini_client import generate_content
from engine.flux import generate_flux_image


def check_gemini() -> bool:
    print("\n--- 1. Testing Gemini (Text JSON output) ---")
    key = get_gemini_api_key()
    if not key:
        print("FAIL: GEMINI_API_KEY is not set in environment or .env")
        return False

    model = get_gemini_model()
    print(f"Using model: {model}")
    prompt = 'Return a JSON object: {"status": "ok", "message": "Gemini connection successful"}'
    
    text, used_model = generate_content(
        prompt_or_contents=prompt,
        thinking_level="low",
        max_output_tokens=200,
        json_mode=True
    )

    if text and "ok" in text.lower():
        print(f"PASS: Gemini responded successfully via {used_model}!")
        print(f"Response: {text.strip()}")
        return True
    else:
        print(f"FAIL: Gemini failed to return expected response. Got: {text}")
        return False


def check_flux() -> bool:
    print("\n--- 2. Testing Cloudflare FLUX.1-schnell ---")
    account_id = get_cloudflare_account_id()
    token = get_cloudflare_api_token()

    if not account_id or not token:
        print("FAIL: CLOUDFLARE_ACCOUNT_ID or CLOUDFLARE_API_TOKEN is not set")
        return False

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        prompt = "A red apple resting on a clean wooden table, vertical composition, 9:16"
        print(f"Generating test image: '{prompt}'...")
        ok, reason = generate_flux_image(prompt, tmp_path)

        if ok and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 1000:
            size_kb = os.path.getsize(tmp_path) / 1024
            print(f"PASS: FLUX successfully generated image ({size_kb:.1f} KB, saved to {tmp_path})!")
            return True
        else:
            print(f"FAIL: FLUX generation failed. Reason: {reason}")
            return False
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


def main():
    print("========================================")
    print("  YouTube Shorts Generator Live Check   ")
    print("========================================")

    gemini_ok = check_gemini()
    flux_ok = check_flux()

    print("\n========================================")
    print(f"Gemini: {'PASS' if gemini_ok else 'FAIL'}")
    print(f"FLUX:   {'PASS' if flux_ok else 'FAIL'}")
    print("========================================")

    if not gemini_ok or not flux_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
