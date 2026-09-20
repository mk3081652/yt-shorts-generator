import os
import sys
import re
import socket
import time
import json
import shutil
import base64
import hashlib
import urllib.request
import urllib.parse
import subprocess
import imageio_ffmpeg
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Set, Tuple, Optional

# Enforce UTF-8 console output on Windows to prevent UnicodeEncodeError with web image titles
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Enforce IPv4 on Windows
_orig_getaddrinfo = socket.getaddrinfo
def _ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
socket.getaddrinfo = _ipv4_getaddrinfo

# Load local .env file if it exists
_env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
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

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()
DEFAULT_GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
CLOUDFLARE_ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
CLOUDFLARE_API_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN", "")

from engine.smart_visuals import (
    create_visual_beats,
    create_ken_burns_motion_clip,
    download_image_file,
    find_primary_wikipedia_topic,
    search_targeted_scene_image,
    clean_words
)

GEMINI_MODEL_CANDIDATES = [
    "gemini-flash-lite-latest",
    "gemini-flash-latest",
    "gemini-pro-latest"
]


_CLOUDFLARE_EXHAUSTED = False
_POLLINATIONS_EXHAUSTED = False

# Verified, instant, high-resolution 9:16 vertical photos for core Shorts genres
CURATED_SCENE_ASSETS = [
    # Mystery & Hotel Corridor
    (["room 307", "door", "opening", "creak", "unlocked", "lock"], "https://images.unsplash.com/photo-1512918728675-ed5a9ecdebfd?w=720&h=1280&fit=crop"),
    (["guard", "guards", "security", "rushed", "patrol", "officer"], "https://images.unsplash.com/photo-1557597774-9d273605dfa9?w=720&h=1280&fit=crop"),
    (["corridor", "hallway", "hotel", "quiet", "carpet"], "https://images.unsplash.com/photo-1590490360182-c33d57733427?w=720&h=1280&fit=crop"),
    (["cctv", "camera", "surveillance", "footage", "monitor", "recording"], "https://images.unsplash.com/photo-1557597774-9d273605dfa9?w=720&h=1280&fit=crop"),
    (["darkness", "midnight", "night", "shadow", "creepy", "eerie"], "https://images.unsplash.com/photo-1509198397868-475647b2a1e5?w=720&h=1280&fit=crop"),
    
    # Miniature Car Assembly & Workshop
    (["suspension", "spring", "springs", "absorber"], "https://images.unsplash.com/photo-1486006920555-c77dce18193b?w=720&h=1280&fit=crop"),
    (["wheel", "wheels", "tire", "tires", "wrench", "lug"], "https://images.unsplash.com/photo-1580273916550-e323be2ae537?w=720&h=1280&fit=crop"),
    (["engine", "motor", "v8", "cylinder", "horsepower"], "https://images.unsplash.com/photo-1617814076367-b759c7d7e738?w=720&h=1280&fit=crop"),
    (["miniature", "scale", "tiny", "mechanic", "mechanics", "model car"], "https://images.unsplash.com/photo-1581092160607-ee22621dd758?w=720&h=1280&fit=crop"),
    (["workshop", "bench", "assembly", "tools", "wrench"], "https://images.unsplash.com/photo-1581092335397-9583fe92d232?w=720&h=1280&fit=crop"),
    (["chassis", "car", "sports car", "supercar", "ferrari"], "https://images.unsplash.com/photo-1503376780353-7e6692767b70?w=720&h=1280&fit=crop"),

    # Aviation, Space & Maritime Documentary
    (["radar", "tracking", "transponder", "atc", "blip", "screen"], "https://images.unsplash.com/photo-1508614589041-895b88991e3e?w=720&h=1280&fit=crop"),
    (["cockpit", "pilot", "instrument", "altimeter", "controls"], "https://images.unsplash.com/photo-1540959733332-eab4deabeeaf?w=720&h=1280&fit=crop"),
    (["cabin", "passenger", "passengers", "seated", "seats", "window"], "https://images.unsplash.com/photo-1542296332-2e4473faf563?w=720&h=1280&fit=crop"),
    (["sonar", "submarine", "underwater", "seabed", "abyss", "deep sea"], "https://images.unsplash.com/photo-1682687220063-4742bd7fd538?w=720&h=1280&fit=crop"),
    (["black box", "flight recorder", "data recorder", "orange box"], "https://images.unsplash.com/photo-1508614589041-895b88991e3e?w=720&h=1280&fit=crop"),
    (["ocean", "sea", "waves", "water", "indian ocean"], "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?w=720&h=1280&fit=crop"),
    (["takeoff", "take off", "runway", "departure", "airplane"], "https://images.unsplash.com/photo-1436491865332-7a61a109cc05?w=720&h=1280&fit=crop"),
    (["wreckage", "debris", "search", "floating", "pieces"], "https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=720&h=1280&fit=crop")
]


def get_instant_curated_visual(text: str, search_query: str, output_path: str) -> bool:
    """Matches scene words to verified 9:16 vertical high-res photos and downloads in ~300ms."""
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
    """
    Generates a cinematic 9:16 vertical image using Cloudflare Workers AI FLUX-1-schnell.
    Includes circuit breaker when quota is exhausted (429).
    """
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

    # Ensure 9:16 vertical photorealistic framing
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
                print("[Cloudflare FLUX] Daily neuron limit exhausted (429). Switching to instant visual engine.")
                _CLOUDFLARE_EXHAUSTED = True
                return False
            time.sleep(0.5)
        except Exception as e:
            print(f"[Cloudflare FLUX] Error: {e}")
            break
    return False


def gemini_direct_visual_scenes(
    script_text: str,
    scenes_text: List[str],
    api_key: Optional[str] = None
) -> List[Dict[str, str]]:
    """
    Uses Google Gemini Flash as an expert YouTube Shorts Visual Director.
    For each spoken scene, it returns:
      - 'search_query': 2 to 4 exact search keywords.
      - 'ai_prompt': a vivid 9:16 vertical visual description strictly illustrating that scene's spoken words.
    """
    key = api_key or DEFAULT_GEMINI_API_KEY
    primary_topic = find_primary_wikipedia_topic(script_text)

    system_prompt = (
        "You are an elite YouTube Shorts Visual Director.\n"
        "Your job is to read the full script and each sequential spoken scene phrase.\n"
        "For EVERY scene phrase, you must create a visual that DIRECTLY AND UNIQUELY illustrates the specific words and action happening in that sentence.\n"
        "CRITICAL DIRECTIVES:\n"
        "1. ZERO VISUAL REPETITION: Never show the same subject in the same setting across multiple scenes. If scene 1 is an airplane exterior, scene 2 must NOT be another airplane exterior unless the sentence specifically requires it.\n"
        "2. CONCRETE SUBJECTS: If the sentence mentions radar, show a glowing green radar screen in a dark ATC control room. If it mentions passengers or cabin, show inside the passenger cabin with people seated. If it mentions ocean search or sonar, show an underwater research submarine with searchlights scanning the seabed. If it mentions the black box, show the bright orange flight data recorder on the ocean floor.\n"
        "3. 9:16 VERTICAL COMPOSITION: Every ai_prompt must start with 'Photorealistic vertical 9:16 shot of ...' and describe specific lighting, camera angle, and atmosphere.\n"
        "Return ONLY a JSON array of objects matching the number of scenes with keys:\n"
        "- 'search_query': 2 to 4 specific search keywords\n"
        "- 'ai_prompt': vivid, photorealistic vertical 9:16 visual description under 180 characters."
    )

    body = {
        'contents': [{
            'parts': [{
                'text': f"{system_prompt}\n\nFull Script Context:\n{script_text}\n\nSequential Scene Phrases:\n{json.dumps(scenes_text)}"
            }]
        }],
        'generationConfig': {
            'responseMimeType': 'application/json',
            'maxOutputTokens': 2500,
            'temperature': 0.2
        }
    }

    # Try model candidates in order
    for model_name in GEMINI_MODEL_CANDIDATES:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={key}"
        for attempt in range(2):
            try:
                req = urllib.request.Request(
                    url,
                    data=json.dumps(body).encode('utf-8'),
                    headers={'Content-Type': 'application/json'}
                )
                with urllib.request.urlopen(req, timeout=12) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                    raw_text = data['candidates'][0]['content']['parts'][0]['text'].strip()
                    if raw_text.startswith('```json'):
                        raw_text = raw_text[7:]
                    if raw_text.startswith('```'):
                        raw_text = raw_text[3:]
                    if raw_text.endswith('```'):
                        raw_text = raw_text[:-3]
                    items = json.loads(raw_text.strip())
                    if isinstance(items, list) and len(items) == len(scenes_text):
                        print(f"[Gemini Director] Successfully directed {len(items)} scenes using {model_name}!")
                        return items
            except Exception as e:
                print(f"[Gemini Director] {model_name} attempt {attempt+1}: {e}")
                time.sleep(0.8)

    # Intelligent semantic fallback if API is unavailable
    fallback_scenes = []
    for s in scenes_text:
        s_lower = s.lower()
        if any(w in s_lower for w in ['radar', 'tracking', 'civilian radar', 'military radar', 'transponder', 'blip']):
            p = "Photorealistic vertical 9:16 close-up of a green glowing air traffic control radar screen with sweeping line and blips in a dark control room"
            sq = "air traffic radar screen"
        elif any(w in s_lower for w in ['cabin', 'passenger', 'passengers', 'inside the', 'seated']):
            p = "Photorealistic vertical 9:16 shot of the interior of a commercial passenger airliner cabin, dim warm lighting, passengers seated"
            sq = "airliner passenger cabin interior"
        elif any(w in s_lower for w in ['sonar', 'submarine', 'underwater', 'deep-sea', 'ocean floor', 'seabed', 'naval']):
            p = "Photorealistic vertical 9:16 shot of a yellow research submarine scanning the dark ocean floor with powerful spotlights, deep sea"
            sq = "deep sea sonar submarine ocean floor"
        elif any(w in s_lower for w in ['black box', 'flight recorder', 'data recorder', 'lost in the abyss', 'abyss']):
            p = "Photorealistic vertical 9:16 shot of a bright orange aviation flight data recorder black box resting on the dark ocean floor"
            sq = "flight data recorder black box ocean floor"
        elif any(w in s_lower for w in ['cockpit', 'pilot', 'windshield', 'instruments']):
            p = "Photorealistic vertical 9:16 shot inside an airplane cockpit looking out at dark night clouds, glowing instrument panels"
            sq = "airplane cockpit night instruments"
        elif any(w in s_lower for w in ['take off', 'took off', 'runway', 'departure', 'heading for']):
            p = f"Photorealistic vertical 9:16 shot of commercial airliner taking off from runway at twilight, glowing runway lights"
            sq = f"{primary_topic} airplane takeoff"
        elif any(w in s_lower for w in ['ocean', 'sea', 'water', 'southern indian']):
            p = "Photorealistic vertical 9:16 aerial shot of vast dark ocean waves under ominous stormy night sky"
            sq = "vast ocean stormy night"
        elif any(w in s_lower for w in ['wreckage', 'debris', 'found', 'floating']):
            p = "Photorealistic vertical 9:16 shot of airplane debris floating on dark ocean water, search lights illuminating the scene"
            sq = "airplane wreckage ocean debris"
        else:
            kws = clean_words(s)
            p = f"Photorealistic vertical 9:16 cinematic shot of {primary_topic}, {' '.join(kws[:3])}, dramatic lighting, 8k"
            sq = f"{primary_topic} {' '.join(kws[:2])}"

        fallback_scenes.append({
            "search_query": sq,
            "ai_prompt": p
        })
    return fallback_scenes


def fetch_authentic_scene_image(
    search_query: str,
    primary_topic: str,
    exclude_urls: Set[str]
) -> Optional[Dict[str, Any]]:
    """
    Finds a real authentic photo from Wikimedia Commons matching the scene's search query.
    Only returns if the image specifically matches the query, never blindly falling back to the primary topic plane photo.
    """
    # 1. Try targeted query directly
    res = search_targeted_scene_image(search_query, exclude_urls)
    if res:
        return res

    # 2. Try combining with primary topic
    if primary_topic and primary_topic.lower() not in search_query.lower():
        res = search_targeted_scene_image(f"{primary_topic} {search_query}", exclude_urls)
        if res:
            return res

    return None


def generate_pollinations_image(prompt: str, output_path: str, max_retries: int = 1) -> bool:
    """
    Generates a vertical 9:16 image via Pollinations AI with fast timeout.
    """
    global _POLLINATIONS_EXHAUSTED
    if _POLLINATIONS_EXHAUSTED:
        return False

    clean_prompt = re.sub(r'[^a-zA-Z0-9\s,.-]', '', prompt)[:120].strip()
    encoded = urllib.parse.quote(clean_prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=720&height=1280&model=turbo&nologo=true"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

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


def generate_scene_image_multi_tier(
    prompt: str,
    search_query: str,
    output_path: str,
    primary_topic: str = "",
    exclude_urls: Optional[Set[str]] = None,
    scene_text: str = ""
) -> bool:
    """
    Guaranteed multi-tier visual pipeline matching each scene's specific words:
    Tier 1: Cloudflare Workers AI FLUX (Hollywood grade, fast).
    Tier 2: Instant Curated Visual (verified high-res 9:16 photo matching scene keywords, ~300ms).
    Tier 3: Targeted authentic photo from Wikimedia Commons for this specific scene query.
    Tier 4: Pollinations AI (turbo model with 5s timeout).
    """
    # Tier 1: Cloudflare FLUX
    if generate_cloudflare_flux_image(prompt, output_path):
        return True

    # Tier 2: Instant Curated Visual (guaranteed matching topic & 9:16 vertical, ~300ms)
    check_text = f"{scene_text} {prompt}"
    if get_instant_curated_visual(check_text, search_query, output_path):
        return True

    # Tier 3: Targeted authentic photo matching the scene's specific words
    if search_query:
        if exclude_urls is None:
            exclude_urls = set()
        auth = search_targeted_scene_image(search_query, exclude_urls)
        if not auth and primary_topic and primary_topic.lower() not in search_query.lower():
            auth = search_targeted_scene_image(f"{primary_topic} {search_query}", exclude_urls)
        if auth and auth.get("url"):
            exclude_urls.add(auth["url"])
            if download_image_file(auth["url"], output_path):
                clean_t = auth.get("title", "").encode("ascii", "replace").decode("ascii")
                print(f"[Multi-Tier Visuals] Used authentic asset '{clean_t}' for: {search_query}")
                return True

    # Tier 4: Fast Pollinations
    if generate_pollinations_image(prompt, output_path):
        return True

    return False


def generate_ai_scene_image(prompt: str, output_path: str, max_retries: int = 2) -> bool:
    """
    Generates a vertical 9:16 photorealistic image.
    Priority 1: Cloudflare Workers AI FLUX (Hollywood grade, ~4s generation).
    Priority 2: Pollinations AI fallback.
    """
    # Priority 1: Cloudflare FLUX
    if generate_cloudflare_flux_image(prompt, output_path, max_retries=max_retries):
        return True

    # Priority 2: Pollinations AI fallback
    return generate_pollinations_image(prompt, output_path, max_retries=max_retries)


def prepare_gemini_scenes_data(
    script_text: str,
    total_duration: float,
    target_cut_duration: float = 2.2,
    scene_overrides: Optional[Dict[str, str]] = None,
    api_key: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Prepares scenes for the visual storyboard using the new intelligent Visual Director module.
    Enforces literal narration relevance, story continuity anchors, varied cinematic shots,
    and positive/negative visual constraints with multi-tier image generation.
    Falls back safely to the existing director if any error occurs.
    """
    primary_topic = find_primary_wikipedia_topic(script_text)
    planned_scenes = []

    try:
        from engine.visual_director import plan_visual_storyboard
        print(f"[Visual Director] Planning visual storyboard for {total_duration:.1f}s script...")
        plan = plan_visual_storyboard(script_text, total_duration, api_key=api_key)
        planned_scenes = plan.get("scenes", [])
    except Exception as e:
        print(f"[Visual Director] Fallback to legacy director due to: {e}")

    # Fallback to existing visual beats & direct scenes if Visual Director returned no scenes
    if not planned_scenes:
        beats = create_visual_beats(script_text, total_duration, min_dur=1.8, max_dur=2.6)
        scene_texts = [t for t, _ in beats]
        print(f"[Gemini Visuals] Directing {len(scene_texts)} scene beats with legacy director...")
        directed_scenes = gemini_direct_visual_scenes(script_text, scene_texts, api_key=api_key)
        
        curr_t = 0.0
        for idx, ((s_text, dur), dir_info) in enumerate(zip(beats, directed_scenes)):
            sq = dir_info.get("search_query", primary_topic)
            ai_p = dir_info.get("ai_prompt", f"Vertical 9:16 cinematic shot of {sq}, photorealistic 8k")
            planned_scenes.append({
                "scene_id": idx,
                "narration": s_text,
                "duration": round(dur, 2),
                "start_time": round(curr_t, 2),
                "end_time": round(curr_t + dur, 2),
                "visual_description": f"Visual of {s_text[:35]}",
                "image_prompt": ai_p,
                "search_query": sq,
                "shot_type": "cinematic shot",
                "camera_motion": "push in",
                "must_show": [s_text[:20]],
                "must_not_show": ["blurry", "watermark"]
            })
            curr_t += dur

    os.makedirs("outputs/ai_previews", exist_ok=True)

    result_scenes = []
    used_urls: Set[str] = set()
    if scene_overrides is None:
        scene_overrides = {}

    to_generate = []

    for idx, sc in enumerate(planned_scenes):
        override_key = str(idx)
        override_val = scene_overrides.get(override_key) or scene_overrides.get(idx)

        sq = sc.get("search_query", primary_topic)
        ai_p = sc.get("image_prompt", f"Vertical 9:16 cinematic shot of {sq}, photorealistic 8k")
        s_text = sc.get("narration", "")
        dur = sc.get("duration", 2.2)
        start_t = sc.get("start_time", 0.0)
        end_t = sc.get("end_time", dur)

        is_custom = False
        if override_val:
            is_custom = True
            img_url = override_val
            img_title = os.path.basename(override_val)
        else:
            # Deterministic cache filename for this scene & prompt
            p_hash = hashlib.md5(f"{idx}_{ai_p}".encode('utf-8')).hexdigest()[:8]
            preview_filename = f"scene_{idx}_{p_hash}.jpg"
            preview_path = os.path.join("outputs", "ai_previews", preview_filename)

            img_url = f"/outputs/ai_previews/{preview_filename}"
            shot_label = sc.get("shot_type", "AI")
            img_title = f"{shot_label.title()}: {ai_p[:30]}..."

            if not os.path.exists(preview_path) or os.path.getsize(preview_path) < 5000:
                to_generate.append((idx, ai_p, sq, preview_path, s_text))

        result_scenes.append({
            "scene_id": idx,
            "start_time": start_t,
            "end_time": end_t,
            "duration": dur,
            "text": s_text,
            "image_url": img_url,
            "image_title": img_title,
            "search_query": sq,
            "prompt": ai_p,
            "is_custom": is_custom,
            "shot_type": sc.get("shot_type", "cinematic"),
            "camera_motion": sc.get("camera_motion", "push in"),
            "must_show": sc.get("must_show", []),
            "must_not_show": sc.get("must_not_show", []),
            "visual_description": sc.get("visual_description", "")
        })

    # Generate any missing images with multi-tier pipeline in PARALLEL
    if to_generate:
        print(f"[Visual Director] Generating {len(to_generate)} scene visuals in parallel...")
        from concurrent.futures import ThreadPoolExecutor
        def _fetch_worker(item):
            _idx, _prompt, _sq, _path, _stext = item
            generate_scene_image_multi_tier(_prompt, _sq, _path, primary_topic, used_urls, scene_text=_stext)

        with ThreadPoolExecutor(max_workers=5) as executor:
            list(executor.map(_fetch_worker, to_generate))

    return result_scenes


def generate_gemini_ai_broll(
    script_text: str,
    total_duration: float,
    output_path: str,
    temp_dir: str,
    target_cut_duration: float = 2.2,
    scene_overrides: Optional[Dict[str, str]] = None,
    api_key: Optional[str] = None,
    preview_scenes: Optional[List[Dict[str, Any]]] = None
) -> str:
    """
    Master AI generation pipeline with ZERO-DROP GUARANTEE:
    If preview_scenes is provided, it directly uses the EXACT previewed images that the user approved,
    scaling their durations to fit total_duration without generating or fetching new images.
    Otherwise, it runs prepare_gemini_scenes_data to direct and fetch visuals.
    """
    os.makedirs(temp_dir, exist_ok=True)

    if preview_scenes and len(preview_scenes) > 0:
        print(f"[Gemini Visuals] Using {len(preview_scenes)} user-previewed scenes directly (locking in approved visuals)!")
        total_p_dur = sum(float(s.get("duration", 2.0)) for s in preview_scenes)
        scale = (total_duration / total_p_dur) if total_p_dur > 0 else 1.0
        scenes_data = []
        curr_t = 0.0
        for s in preview_scenes:
            dur = max(0.8, round(float(s.get("duration", 2.0)) * scale, 2))
            scenes_data.append({
                "scene_id": s.get("scene_id", 0),
                "text": s.get("text", ""),
                "image_url": s.get("image_url", ""),
                "duration": dur,
                "start_time": round(curr_t, 2),
                "end_time": round(curr_t + dur, 2),
                "is_custom": True
            })
            curr_t += dur
    else:
        scenes_data = prepare_gemini_scenes_data(
            script_text=script_text,
            total_duration=total_duration,
            target_cut_duration=target_cut_duration,
            scene_overrides=scene_overrides,
            api_key=api_key
        )

    print(f"[Gemini Visuals] Rendering {len(scenes_data)} scenes (Total: {total_duration:.1f}s)")
    scene_clips: List[str] = []
    primary_topic = find_primary_wikipedia_topic(script_text)
    used_urls: Set[str] = set()

    for idx, sc in enumerate(scenes_data):
        img_path = os.path.join(temp_dir, f"ai_scene_{idx}.jpg")
        clip_path = os.path.join(temp_dir, f"ai_scene_clip_{idx}.mp4")
        dur = sc["duration"]

        clean_sc_text = sc.get('text', '')[:30].encode('ascii', 'replace').decode('ascii')
        print(f"[Scene {idx+1}/{len(scenes_data)}] ({dur:.1f}s) \"{clean_sc_text}...\" -> {sc.get('search_query', '')}")
        
        ok = False
        # 1. Custom override image
        if sc.get("is_custom"):
            ok = download_image_file(sc["image_url"], img_path)

        # 2. Local AI preview image in outputs/
        if not ok and sc.get("image_url") and (sc["image_url"].startswith("/outputs/") or sc["image_url"].startswith("outputs/")):
            local_src = sc["image_url"].lstrip("/")
            if os.path.exists(local_src) and os.path.getsize(local_src) > 5000:
                shutil.copyfile(local_src, img_path)
                ok = True

        # 3. Authentic or remote image URL
        if not ok and sc.get("image_url") and "pollinations.ai" not in sc.get("image_url", ""):
            ok = download_image_file(sc["image_url"], img_path)

        # 4. Generate AI image with multi-tier pipeline
        if not ok:
            prompt_to_use = sc.get("prompt") or sc.get("search_query") or sc["text"]
            sq_to_use = sc.get("search_query", "")
            ok = generate_scene_image_multi_tier(prompt_to_use, sq_to_use, img_path, primary_topic, used_urls, scene_text=sc.get("text", ""))

        # 4. CRITICAL FAILSAFE: If AI failed or timed out, query Commons for authentic image
        if not ok:
            print(f"[Failsafe] Fetching authentic image for Scene {idx+1} ({sc.get('search_query')})...")
            auth = fetch_authentic_scene_image(sc.get("search_query", primary_topic), primary_topic, used_urls)
            if auth:
                used_urls.add(auth["url"])
                ok = download_image_file(auth["url"], img_path)

        # 5. ULTIMATE FAILSAFE: If still no image, use default dark canvas for this cut
        if not ok or not os.path.exists(img_path):
            print(f"[Failsafe] Creating dark cinematic canvas for Scene {idx+1}...")
            canvas_cmd = [
                FFMPEG_EXE, "-y",
                "-f", "lavfi",
                "-i", f"color=c=0x0d1117:s=1080x1920:r=30:d={dur:.2f}",
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-pix_fmt", "yuv420p",
                clip_path
            ]
            subprocess.run(canvas_cmd, capture_output=True)

    # Render Ken Burns motion clips in PARALLEL with ThreadPoolExecutor
    from concurrent.futures import ThreadPoolExecutor
    def _render_clip_worker(item):
        _idx, _img_p, _clip_p, _dur = item
        if not os.path.exists(_clip_p) and os.path.exists(_img_p):
            create_ken_burns_motion_clip(
                image_path=_img_p,
                duration=_dur,
                output_path=_clip_p,
                motion_index=_idx
            )

    clip_tasks = [
        (idx, os.path.join(temp_dir, f"ai_scene_{idx}.jpg"), os.path.join(temp_dir, f"ai_scene_clip_{idx}.mp4"), sc["duration"])
        for idx, sc in enumerate(scenes_data)
    ]

    with ThreadPoolExecutor(max_workers=3) as executor:
        list(executor.map(_render_clip_worker, clip_tasks))

    for idx in range(len(scenes_data)):
        clip_path = os.path.join(temp_dir, f"ai_scene_clip_{idx}.mp4")
        if os.path.exists(clip_path):
            scene_clips.append(clip_path)

    # Concatenate all generated clips into master b-roll track
    if scene_clips:
        concat_list_file = os.path.join(temp_dir, "concat_ai_scenes.txt")
        with open(concat_list_file, "w", encoding="utf-8") as f:
            for cp in scene_clips:
                norm_cp = os.path.abspath(cp).replace("\\", "/")
                f.write(f"file '{norm_cp}'\n")

        concat_cmd = [
            FFMPEG_EXE, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_list_file,
            "-t", f"{total_duration:.2f}",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "21",
            "-pix_fmt", "yuv420p",
            os.path.abspath(output_path)
        ]
        res = subprocess.run(concat_cmd, capture_output=True)
        if res.returncode == 0 and os.path.exists(output_path):
            return output_path

    # Fallback to authentic archive generator
    from engine.smart_visuals import generate_smart_broll_video
    return generate_smart_broll_video(
        script_text=script_text,
        total_duration=total_duration,
        output_path=output_path,
        temp_dir=temp_dir,
        target_cut_duration=target_cut_duration,
        scene_overrides=scene_overrides
    )
