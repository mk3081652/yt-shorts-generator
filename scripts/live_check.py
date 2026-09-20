"""
scripts/live_check.py - Verification script for Gemini and Cloudflare FLUX live calls.
Run by the user to verify real API keys and connectivity:
    python scripts/live_check.py
"""

import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.config import (
    get_gemini_api_key,
    get_gemini_model,
    get_cloudflare_account_id,
    get_cloudflare_api_token,
    get_flux_model
)
from engine.llm import generate_content
from engine.flux import generate as generate_flux


def check_gemini():
    print("=" * 60)
    print("1. CHECKING GEMINI 3.8 FLASH API")
    print("=" * 60)

    key = get_gemini_api_key()
    if not key:
        print("FAIL: GEMINI_API_KEY is not set in environment or .env file.")
        return False

    model = get_gemini_model()
    print(f"Model: {model}")
    print("Sending test request (JSON-mode)...")

    prompt = 'Return a JSON object with key "status" set to "online" and "message" set to "hello from gemini".'
    try:
        text, used_model = generate_content(
            prompt,
            thinking_level="low",
            max_output_tokens=200,
            json_mode=True
        )
        if text:
            print(f"PASS: Gemini responded successfully via {used_model}!")
            print(f"Response: {text}")
            return True
        else:
            print("FAIL: Gemini call returned None (check API key or quotas).")
            return False
    except Exception as e:
        print(f"FAIL: Exception during Gemini call: {e}")
        return False


def check_flux():
    print("\n" + "=" * 60)
    print("2. CHECKING CLOUDFLARE WORKERS AI FLUX")
    print("=" * 60)

    account_id = get_cloudflare_account_id()
    token = get_cloudflare_api_token()
    if not account_id or not token:
        print("FAIL: CLOUDFLARE_ACCOUNT_ID or CLOUDFLARE_API_TOKEN not set.")
        return False

    model = get_flux_model()
    print(f"Model: {model}")
    print("Generating test 9:16 frame (prompt: 'cinematic neon spaceship in deep space')...")

    test_out = os.path.abspath("outputs/live_check_test.jpg")
    try:
        ok, reason = generate_flux("cinematic neon spaceship in deep space, vertical 9:16, centered, high quality", test_out)
        if ok and os.path.exists(test_out):
            size_kb = os.path.getsize(test_out) / 1024
            print(f"PASS: FLUX image generated successfully ({size_kb:.1f} KB)!")
            print(f"Output saved to: {test_out}")
            return True
        else:
            print(f"FAIL: FLUX generation failed with reason: {reason}")
            return False
    except Exception as e:
        print(f"FAIL: Exception during FLUX generation: {e}")
        return False


def main():
    print("YouTube Shorts Generator - Live API Health Check\n")
    gemini_ok = check_gemini()
    flux_ok = check_flux()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Gemini 3.8 Flash: {'[PASS]' if gemini_ok else '[FAIL]'}")
    print(f"Cloudflare FLUX:  {'[PASS]' if flux_ok else '[FAIL]'}")

    if gemini_ok and flux_ok:
        print("\nAll live services are verified and operational!")
        sys.exit(0)
    else:
        print("\nOne or more services failed. Please check your credentials in .env.")
        sys.exit(1)


if __name__ == "__main__":
    main()
