"""
generator.py - Visual Generation, Search, Validation & Regeneration Pipeline
Part of the Visual Director module for YouTube Shorts.

Implements:
1. Multi-tier visual search and generation:
   - Tier 1: Cloudflare FLUX-1-schnell (9:16 vertical, photorealistic)
   - Tier 2: Instant Curated 9:16 Photos (verified match for room 307, tiny mechanics, suspension, etc.)
   - Tier 3: Targeted authentic photo matching specific scene query
   - Tier 4: Pollinations AI fallback
2. Visual Relevance Validation:
   - Scores 0-100 against narration, must_show, must_not_show, and continuity bible.
   - If score >= 80: ACCEPT.
   - If score < 80: REGENERATE with correction_prompt (max 2 retries).
   - Best-Image Selection: Picks highest scoring attempt.
3. Strict protection for manual replacements:
   - Scenes with source: "manual" are NEVER overwritten.
"""

import os
import re
import json
import time
import base64
import shutil
import hashlib
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, List, Optional, Set, Tuple

from engine.visual_director.validator import (
    heuristic_validate_scene,
    validate_image_with_gemini_vision
)
from engine.smart_visuals import (
    clean_words,
    download_image_file
)

# Load local .env file if it exists
_env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")
if os.path.exists(_env_file):
    try:
        with open(_env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except Exception:
        pass

# Load Cloudflare & Gemini credentials
CLOUDFLARE_ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
CLOUDFLARE_API_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN", "")
DEFAULT_GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

_CLOUDFLARE_EXHAUSTED = False
_POLLINATIONS_EXHAUSTED = False

from engine.log_utils import log_tier_failure

def create_dark_canvas_image(output_path: str) -> bool:
    """Creates a clean 1080x1920 dark cinematic canvas (#0d1117) as failsafe."""
    try:
        from PIL import Image
        img = Image.new("RGB", (1080, 1920), color=(13, 17, 23))
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        img.save(output_path, "JPEG", quality=90)
        return True
    except Exception as e:
        print(f"[Dark Canvas] Error creating failsafe image: {e}")
        return False


def generate_cloudflare_flux_image(prompt: str, output_path: str, max_retries: int = 1) -> bool:
    """Generates a vertical 9:16 image via Cloudflare Workers AI FLUX-1-schnell."""
    global _CLOUDFLARE_EXHAUSTED
    if _CLOUDFLARE_EXHAUSTED:
        return False

    if not CLOUDFLARE_ACCOUNT_ID or not CLOUDFLARE_API_TOKEN:
        return False

    url = f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/ai/run/@cf/black-forest-labs/flux-1-schnell"
    headers = {
        "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
        "Content-Type": "application/json"
    }
    clean_prompt = prompt.strip()
    if not clean_prompt:
        return False

    if "vertical" not in clean_prompt.lower() and "9:16" not in clean_prompt:
        clean_prompt = f"Vertical 9:16 composition, cinematic 8k photorealistic shot of {clean_prompt}, dramatic atmospheric lighting"

    body = json.dumps({"prompt": clean_prompt, "steps": 4}).encode('utf-8')

    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as resp:
                res_data = json.loads(resp.read().decode('utf-8'))
                img_b64 = res_data.get('result', {}).get('image')
                if img_b64:
                    img_bytes = base64.b64decode(img_b64)
                    if len(img_bytes) > 5000:
                        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
                        with open(output_path, 'wb') as f:
                            f.write(img_bytes)
                        print(f"[Cloudflare FLUX] Successfully generated ({len(img_bytes)} bytes) for: {clean_prompt[:50]}...")
                        return True
        except urllib.error.HTTPError as e:
            if e.code == 429:
                print("[Cloudflare FLUX] Daily neuron limit exhausted (429).")
                _CLOUDFLARE_EXHAUSTED = True
                return False
            time.sleep(0.5)
        except Exception as e:
            print(f"[Cloudflare FLUX] Error: {e}")
            break
    return False


def generate_pollinations_image(prompt: str, output_path: str, max_retries: int = 1) -> bool:
    """Generates a vertical 9:16 image via Pollinations AI with fast timeout."""
    global _POLLINATIONS_EXHAUSTED
    if _POLLINATIONS_EXHAUSTED:
        return False

    clean_prompt = re.sub(r'[^a-zA-Z0-9\s,.-]', '', prompt)[:120].strip()
    encoded = urllib.parse.quote(clean_prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=720&height=1280&model=turbo&nologo=true"

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as resp:
                content = resp.read()
                if len(content) > 5000:
                    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
                    with open(output_path, 'wb') as f:
                        f.write(content)
                    return True
        except urllib.error.HTTPError as e:
            if e.code == 429:
                _POLLINATIONS_EXHAUSTED = True
                return False
        except Exception:
            pass
    return False


def generate_google_imagen_image(prompt: str, output_path: str, api_key: Optional[str] = None) -> bool:
    """
    Generates a vertical 9:16 photorealistic image using Google's Imagen 3 model
    (imagen-3.0-generate-002) via Google AI Studio / Generative Language API.
    """
    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not key or not key.startswith("AIzaSy"):
        return False
    url = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-002:predict?key={key}"
    body = json.dumps({
        "instances": [{"prompt": prompt}],
        "parameters": {
            "sampleCount": 1,
            "aspectRatio": "9:16"
        }
    }).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            preds = data.get("predictions", [])
            if preds:
                b64_data = preds[0].get("bytesBase64Encoded")
                if b64_data:
                    img_bytes = base64.b64decode(b64_data)
                    if len(img_bytes) > 5000:
                        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
                        with open(output_path, "wb") as f:
                            f.write(img_bytes)
                        print(f"[Google Imagen 3] Generated {len(img_bytes)} bytes for: {prompt[:45]}...")
                        return True
    except Exception as e:
        print(f"[Google Imagen 3] Error: {e}")
    return False


def single_visual_attempt(
    prompt: str,
    search_query: str = "",
    output_path: str = "",
    scene_text: str = "",
    used_urls: Optional[Set[str]] = None,
    api_key: Optional[str] = None,
    generation_mode: str = "ai_flux_primary"
) -> Tuple[bool, str]:
    """
    Executes a single visual acquisition attempt using AI generation ONLY:
    1. Google Imagen 3 (if generate_google_imagen_image exists and is configured)
    2. Cloudflare FLUX (generate_cloudflare_flux_image)
    3. Pollinations AI (generate_pollinations_image)
    4. Dark cinematic canvas failsafe (if all AI tiers fail)
    Zero stock/archive photo fallback tiers.
    """
    # Tier 1: Google Imagen 3
    if generate_google_imagen_image(prompt, output_path, api_key=api_key):
        return True, "ai_imagen"

    # Tier 2: Cloudflare FLUX
    if generate_cloudflare_flux_image(prompt, output_path):
        return True, "ai_flux"

    # Tier 3: Pollinations AI
    if generate_pollinations_image(prompt, output_path):
        return True, "ai_pollinations"

    # Tier 4: Dark cinematic canvas failsafe
    if create_dark_canvas_image(output_path):
        return True, "dark_canvas_failsafe"

    return False, "ai_failed"


def generate_and_validate_scene(
    scene: Dict[str, Any],
    output_dir: str,
    continuity_bible: Optional[Dict[str, Any]] = None,
    api_key: Optional[str] = None,
    used_urls: Optional[Set[str]] = None,
    max_retries: int = 2,
    generation_mode: str = "ai_flux_primary",
    call_stats: Optional[Dict[str, int]] = None
) -> Dict[str, Any]:
    """
    Executes the visual generation, validation, and regeneration loop for a single scene:
    - Checks if manual override exists (source: 'manual'); if so, preserves it completely.
    - Attempt 1: generate with scene['image_prompt'] using AI-only tiers.
    - Validate against narration, must_show, must_not_show.
    - If score < 80: regenerate using correction_prompt (up to 2 retries = 3 attempts total).
    - Best-Image Selection: picks the attempt with the highest validation score.
    """
    scene_id = scene.get("scene_id", "scene_01")
    narration = scene.get("narration", "")
    vis_desc = scene.get("visual_description", "")
    must_show = scene.get("must_show", [])
    must_not_show = scene.get("must_not_show", [])
    sq = scene.get("search_query", "")

    # If already manual, do not touch
    if scene.get("source") == "manual" or scene.get("is_custom"):
        return scene

    attempts: List[Dict[str, Any]] = []
    current_prompt = scene.get("image_prompt", "")

    for attempt_idx in range(1 + max_retries):
        p_hash = hashlib.md5(f"{scene_id}_{attempt_idx}_{current_prompt}".encode('utf-8')).hexdigest()[:8]
        attempt_filename = f"{scene_id}_att{attempt_idx}_{p_hash}.jpg"
        attempt_path = os.path.join(output_dir, attempt_filename)

        ok, tier = single_visual_attempt(
            prompt=current_prompt,
            search_query=sq,
            output_path=attempt_path,
            scene_text=narration,
            used_urls=used_urls,
            api_key=api_key,
            generation_mode=generation_mode
        )

        if tier in ("dark_canvas_failsafe", "ai_failed"):
            val_res = {
                "score": 0,
                "accepted": False,
                "reason": "AI generation failed across all tiers; dark canvas failsafe used.",
                "correction_prompt": ""
            }
        else:
            # Validate attempt: real Gemini Vision if API key and image file exist, else heuristic
            resolved_key = api_key or os.environ.get("GEMINI_API_KEY", "")
            if resolved_key and os.path.exists(attempt_path) and os.path.getsize(attempt_path) > 1000:
                val_res = validate_image_with_gemini_vision(
                    narration=narration,
                    visual_description=vis_desc,
                    must_show=must_show,
                    must_not_show=must_not_show,
                    image_path=attempt_path,
                    continuity_bible=continuity_bible,
                    api_key=resolved_key,
                    call_stats=call_stats
                )
            else:
                val_res = heuristic_validate_scene(
                    narration=narration,
                    prompt=current_prompt,
                    must_show=must_show,
                    must_not_show=must_not_show,
                    continuity_bible=continuity_bible,
                    visual_description=vis_desc
                )
        score = val_res["score"]
        attempts.append({
            "attempt": attempt_idx + 1,
            "path": attempt_path,
            "filename": attempt_filename,
            "prompt": current_prompt,
            "score": score,
            "accepted": val_res["accepted"],
            "source_tier": tier,
            "val_res": val_res
        })

        if val_res["accepted"]:
            print(f"[{scene_id}] Attempt {attempt_idx+1} ACCEPTED (Score: {score}/100, Tier: {tier})")
            break
        else:
            print(f"[{scene_id}] Attempt {attempt_idx+1} REJECTED (Score: {score}/100, Tier: {tier}). Reason: {val_res['reason']}")
            if val_res.get("correction_prompt"):
                current_prompt = val_res["correction_prompt"]

    # Best-Image Selection: Pick the highest scoring attempt
    best_attempt = max(attempts, key=lambda a: a["score"])
    print(f"[{scene_id}] Selected Best Image: Attempt {best_attempt['attempt']} with Score {best_attempt['score']}/100 (Tier: {best_attempt.get('source_tier', 'ai_flux')})")

    # Update scene with selected asset
    scene_copy = dict(scene)
    scene_copy["image_url"] = f"/outputs/ai_previews/{best_attempt['filename']}"
    scene_copy["image_path"] = best_attempt["path"]
    scene_copy["validation_score"] = best_attempt["score"]
    scene_copy["accepted"] = best_attempt["accepted"]
    scene_copy["prompt"] = best_attempt["prompt"]
    scene_copy["source"] = "generated"
    scene_copy["source_tier"] = best_attempt.get("source_tier", "ai_flux")
    scene_copy["is_custom"] = False

    return scene_copy


def generate_validated_scenes(
    planned_scenes: List[Dict[str, Any]],
    output_dir: str = "outputs/ai_previews",
    continuity_bible: Optional[Dict[str, Any]] = None,
    scene_overrides: Optional[Dict[str, str]] = None,
    api_key: Optional[str] = None,
    generation_mode: Optional[str] = None,
    call_stats: Optional[Dict[str, int]] = None
) -> List[Dict[str, Any]]:
    """
    Coordinates the visual generation and validation for all planned scenes in parallel.
    Preserves manual overrides and enforces best-image selection and consistent generation_mode.
    """
    os.makedirs(output_dir, exist_ok=True)
    if scene_overrides is None:
        scene_overrides = {}

    has_cf = bool(os.environ.get("CLOUDFLARE_ACCOUNT_ID") and os.environ.get("CLOUDFLARE_API_TOKEN"))
    resolved_mode = generation_mode or ("ai_flux_primary" if has_cf else "ai_primary")

    used_urls: Set[str] = set()
    scenes_to_process = []

    for idx, sc in enumerate(planned_scenes):
        sc_id_str = str(idx)
        override_val = scene_overrides.get(sc_id_str) or scene_overrides.get(idx) or scene_overrides.get(sc.get("scene_id"))

        if override_val:
            sc_copy = dict(sc)
            sc_copy["image_url"] = override_val
            sc_copy["image_title"] = os.path.basename(override_val)
            sc_copy["is_custom"] = True
            sc_copy["source"] = "manual"
            sc_copy["source_tier"] = "manual_upload"
            sc_copy["validation_score"] = 100
            scenes_to_process.append((sc_copy, True))
        else:
            scenes_to_process.append((sc, False))

    # Process scenes in parallel
    def _worker(item):
        _sc, _is_override = item
        if _is_override:
            return _sc
        try:
            return generate_and_validate_scene(
                scene=_sc,
                output_dir=output_dir,
                continuity_bible=continuity_bible,
                api_key=api_key,
                used_urls=used_urls,
                generation_mode=resolved_mode,
                call_stats=call_stats
            )
        except Exception as err:
            log_tier_failure("Generator Worker", err, context=_sc.get('scene_id'))
            return _sc

    with ThreadPoolExecutor(max_workers=2) as executor:
        final_scenes = list(executor.map(_worker, scenes_to_process))

    return final_scenes
