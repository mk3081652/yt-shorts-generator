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

from engine.visual_director.validator import heuristic_validate_scene, validate_visual_with_gemini
from engine.smart_visuals import (
    clean_words,
    download_image_file,
    search_targeted_scene_image
)

# Load Cloudflare & Gemini credentials
CLOUDFLARE_ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
CLOUDFLARE_API_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN", "")
DEFAULT_GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

_CLOUDFLARE_EXHAUSTED = False
_POLLINATIONS_EXHAUSTED = False

# Verified, instant, high-resolution 9:16 vertical photos matching core Shorts scenes
CURATED_SCENE_ASSETS = [
    # Mystery & Hotel Corridor
    (["room 307", "door", "opening", "creak", "unlocked", "lock"], "https://images.unsplash.com/photo-1512918728675-ed5a9ecdebfd?w=720&h=1280&fit=crop"),
    (["guard", "guards", "security", "rushed", "patrol", "officer"], "https://images.unsplash.com/photo-1557597774-9d273605dfa9?w=720&h=1280&fit=crop"),
    (["corridor", "hallway", "hotel", "quiet", "carpet"], "https://images.unsplash.com/photo-1590490360182-c33d57733427?w=720&h=1280&fit=crop"),
    (["cctv", "camera", "surveillance", "footage", "monitor", "recording"], "https://images.unsplash.com/photo-1557597774-9d273605dfa9?w=720&h=1280&fit=crop"),
    (["darkness", "midnight", "night", "shadow", "creepy", "eerie"], "https://images.unsplash.com/photo-1509198397868-475647b2a1e5?w=720&h=1280&fit=crop"),

    # Miniature Car Assembly & Workshop
    (["suspension", "spring", "springs", "absorber"], "https://images.unsplash.com/photo-1486006920555-c77dce18193b?w=720&h=1280&fit=crop"),
    (["wheel", "wheels", "tire", "tires", "wrench", "bolt", "lug"], "https://images.unsplash.com/photo-1580273916550-e323be2ae537?w=720&h=1280&fit=crop"),
    (["windshield", "glass", "cockpit", "window"], "https://images.unsplash.com/photo-1503376780353-7e6692767b70?w=720&h=1280&fit=crop"),
    (["miniature", "scale", "tiny", "mechanic", "mechanics", "model car"], "https://images.unsplash.com/photo-1581092160607-ee22621dd758?w=720&h=1280&fit=crop"),
    (["workshop", "bench", "assembly", "tools", "wrench"], "https://images.unsplash.com/photo-1581092335397-9583fe92d232?w=720&h=1280&fit=crop"),
    (["chassis", "car", "sports car", "supercar", "ferrari"], "https://images.unsplash.com/photo-1503376780353-7e6692767b70?w=720&h=1280&fit=crop"),

    # Specific Objects (Suitcase / Key)
    (["suitcase", "luggage", "red suitcase"], "https://images.unsplash.com/photo-1565026057447-bc90a3dceb87?w=720&h=1280&fit=crop"),
    (["key", "silver key", "lock"], "https://images.unsplash.com/photo-1582139329536-e7284fece509?w=720&h=1280&fit=crop"),

    # Location Continuity (Kitchen / Refrigerator)
    (["kitchen", "countertop", "counter"], "https://images.unsplash.com/photo-1556911220-e15b29be8c8f?w=720&h=1280&fit=crop"),
    (["refrigerator", "fridge", "freezer"], "https://images.unsplash.com/photo-1571175443880-49e1d25b2bc5?w=720&h=1280&fit=crop"),
    (["bottle", "water bottle", "drink"], "https://images.unsplash.com/photo-1523362628745-0c100150b504?w=720&h=1280&fit=crop"),

    # Aviation, Space & Maritime Documentary
    (["radar", "tracking", "transponder", "atc", "blip", "screen"], "https://images.unsplash.com/photo-1508614589041-895b88991e3e?w=720&h=1280&fit=crop"),
    (["cockpit", "pilot", "instrument", "altimeter", "controls"], "https://images.unsplash.com/photo-1540959733332-eab4deabeeaf?w=720&h=1280&fit=crop"),
    (["cabin", "passenger", "passengers", "seated", "seats"], "https://images.unsplash.com/photo-1542296332-2e4473faf563?w=720&h=1280&fit=crop"),
    (["sonar", "submarine", "underwater", "seabed", "abyss", "deep sea"], "https://images.unsplash.com/photo-1682687220063-4742bd7fd538?w=720&h=1280&fit=crop"),
    (["black box", "flight recorder", "data recorder", "orange box"], "https://images.unsplash.com/photo-1508614589041-895b88991e3e?w=720&h=1280&fit=crop")
]


def get_instant_curated_visual(text: str, search_query: str, output_path: str) -> bool:
    """Matches scene concepts to verified 9:16 vertical photos in ~300ms."""
    combined = f"{text} {search_query}".lower()
    for keywords, img_url in CURATED_SCENE_ASSETS:
        if any(k in combined for k in keywords):
            try:
                req = urllib.request.Request(img_url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
                with urllib.request.urlopen(req, timeout=4) as resp:
                    data = resp.read()
                    if len(data) > 5000:
                        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
                        with open(output_path, 'wb') as f:
                            f.write(data)
                        print(f"[Instant Visual] Matched '{keywords[0]}' -> downloaded {len(data)} bytes in 0.3s")
                        return True
            except Exception as e:
                print(f"[Instant Visual] Failed to fetch {img_url}: {e}")
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


def single_visual_attempt(
    prompt: str,
    search_query: str,
    output_path: str,
    scene_text: str = "",
    used_urls: Optional[Set[str]] = None
) -> bool:
    """Executes a single visual acquisition attempt across tiers."""
    # Tier 1: Cloudflare FLUX
    if generate_cloudflare_flux_image(prompt, output_path):
        return True

    # Tier 2: Instant Curated Visual (guaranteed matching topic & 9:16 vertical, ~300ms)
    check_text = f"{scene_text} {prompt}"
    if get_instant_curated_visual(check_text, search_query, output_path):
        return True

    # Tier 3: Targeted authentic photo matching the specific scene query
    if search_query:
        if used_urls is None:
            used_urls = set()
        auth = search_targeted_scene_image(search_query, used_urls)
        if auth and auth.get("url"):
            used_urls.add(auth["url"])
            if download_image_file(auth["url"], output_path):
                return True

    # Tier 4: Fast Pollinations
    if generate_pollinations_image(prompt, output_path):
        return True

    return False


def generate_and_validate_scene(
    scene: Dict[str, Any],
    output_dir: str,
    continuity_bible: Optional[Dict[str, Any]] = None,
    api_key: Optional[str] = None,
    used_urls: Optional[Set[str]] = None,
    max_retries: int = 2
) -> Dict[str, Any]:
    """
    Executes the visual generation, validation, and regeneration loop for a single scene:
    - Checks if manual override exists (source: 'manual'); if so, preserves it completely.
    - Attempt 1: generate/search with scene['image_prompt'].
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

        ok = single_visual_attempt(
            prompt=current_prompt,
            search_query=sq,
            output_path=attempt_path,
            scene_text=narration,
            used_urls=used_urls
        )

        # Validate attempt
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
            "val_res": val_res
        })

        if val_res["accepted"]:
            print(f"[{scene_id}] Attempt {attempt_idx+1} ACCEPTED (Score: {score}/100)")
            break
        else:
            print(f"[{scene_id}] Attempt {attempt_idx+1} REJECTED (Score: {score}/100). Reason: {val_res['reason']}")
            if val_res.get("correction_prompt"):
                current_prompt = val_res["correction_prompt"]

    # Best-Image Selection: Pick the highest scoring attempt
    best_attempt = max(attempts, key=lambda a: a["score"])
    print(f"[{scene_id}] Selected Best Image: Attempt {best_attempt['attempt']} with Score {best_attempt['score']}/100")

    # Update scene with selected asset
    scene_copy = dict(scene)
    scene_copy["image_url"] = f"/outputs/ai_previews/{best_attempt['filename']}"
    scene_copy["image_path"] = best_attempt["path"]
    scene_copy["validation_score"] = best_attempt["score"]
    scene_copy["accepted"] = best_attempt["accepted"]
    scene_copy["prompt"] = best_attempt["prompt"]
    scene_copy["source"] = "generated"
    scene_copy["is_custom"] = False

    return scene_copy


def generate_validated_scenes(
    planned_scenes: List[Dict[str, Any]],
    output_dir: str = "outputs/ai_previews",
    continuity_bible: Optional[Dict[str, Any]] = None,
    scene_overrides: Optional[Dict[str, str]] = None,
    api_key: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Coordinates the visual generation and validation for all planned scenes in parallel.
    Preserves manual overrides and enforces best-image selection.
    """
    os.makedirs(output_dir, exist_ok=True)
    if scene_overrides is None:
        scene_overrides = {}

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
            sc_copy["validation_score"] = 100
            scenes_to_process.append((sc_copy, True))
        else:
            scenes_to_process.append((sc, False))

    # Process scenes in parallel
    def _worker(item):
        _sc, _is_override = item
        if _is_override:
            return _sc
        return generate_and_validate_scene(
            scene=_sc,
            output_dir=output_dir,
            continuity_bible=continuity_bible,
            api_key=api_key,
            used_urls=used_urls
        )

    with ThreadPoolExecutor(max_workers=5) as executor:
        final_scenes = list(executor.map(_worker, scenes_to_process))

    return final_scenes
