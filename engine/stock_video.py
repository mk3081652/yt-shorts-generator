"""
engine/stock_video.py - Professional Semantic Stock Video Engine using Pexels Video API.
Provides high-retention 9:16 vertical b-roll footage for YouTube Shorts.

Architecture:
1. Director Visual Plan & Semantic Query Extraction (3-6 concrete queries per scene)
2. Multi-Candidate Search & Cross-Query Deduplication (5-15 candidates)
3. Hard Filtering (aspect ratio, duration, resolution, anti-repetition)
4. Single-Call Multimodal AI Visual Ranking with Gemini Vision
5. Deterministic Semantic Fallback (if Vision offline/rate-limited)
6. Semantic Quality Gate (rejects irrelevant footage < 45 to trigger FLUX fallback)
7. Anti-Repetition Video ID Tracking (guarantees ZERO duplicate clips across project)
"""

import os
import re
import json
import time
import base64
import logging
import urllib.request
import urllib.parse
import urllib.error
from io import BytesIO
from typing import Dict, Any, List, Optional, Set, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image

from engine.config import get_pexels_api_key, get_gemini_api_key
from engine.llm import generate_content

logger = logging.getLogger("yt_shorts.stock_video")

PEXELS_SEARCH_URL = "https://api.pexels.com/videos/search"
CACHE_DIR = os.path.abspath("outputs/stock_videos")

# In-memory query and thumbnail caches to avoid redundant API/network overhead
_SEARCH_CACHE: Dict[str, List[Dict[str, Any]]] = {}
_THUMBNAIL_CACHE: Dict[str, str] = {}

STOP_WORDS = {
    'with', 'and', 'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'of', 'across',
    'over', 'by', 'its', 'from', 'causing', 'became', 'during', 'that', 'this', 'then',
    'into', 'through', 'about', 'after', 'before', 'under', 'between', 'against', 'there',
    'their', 'they', 'what', 'which', 'who', 'where', 'when', 'how', 'all', 'any', 'both',
    'each', 'few', 'more', 'most', 'other', 'some', 'such', 'only', 'own', 'same', 'so',
    'than', 'too', 'very', 'can', 'will', 'just', 'should', 'now', 'shot', 'shots'
}


def sanitize_filename(name: str) -> str:
    """Removes unsafe characters for file paths."""
    clean = re.sub(r'[^a-zA-Z0-9_\-]', '_', name)
    return clean[:60].strip('_')


def clean_query_phrase(q: str, max_words: int = 4) -> str:
    """Cleans a search query string to 2-4 punchy alphanumeric words optimal for Pexels."""
    clean = re.sub(r'[^a-zA-Z0-9\s]', ' ', q).lower()
    words = [w for w in clean.split() if w not in STOP_WORDS and len(w) > 2]
    if not words:
        words = clean.split()[:max_words]
    return " ".join(words[:max_words]).strip()


def extract_queries_from_gemini_prompt(image_prompt: str, video_prompt: str = "") -> List[str]:
    """
    Extracts concrete 2-to-3 word physical search queries directly from Gemini's visual prompt.
    Strips FLUX boilerplate (style, resolution, camera tags, suffixes).
    """
    queries = []
    combined_raw = f"{image_prompt} {video_prompt}".strip()
    if not combined_raw:
        return []

    # 1. Strip style boilerplate & suffixes
    p = re.sub(r'^(?:Cinematic|Dramatic|Hyperrealistic|Photorealistic|Atmospheric|35mm)\b[^.]*\.\s*', '', combined_raw, flags=re.IGNORECASE)
    p = re.sub(r'\bVertical 9:16.*$', '', p, flags=re.IGNORECASE)
    p = re.sub(r'\b(?:subject centered|no text|no watermark|highly detailed|film still|gritty realism|cold tones|high-contrast lighting)\b', '', p, flags=re.IGNORECASE)
    p = re.sub(r'\b(?:close-up shot of|wide shot of|medium shot of|macro shot of|aerial shot of|POV shot of|low-angle shot of|shot of|framing)\b', '', p, flags=re.IGNORECASE)
    p = re.sub(r'\b(?:camera slowly pushes in on|camera pans|slow zoom|tilt up to|camera movement on)\b', '', p, flags=re.IGNORECASE)

    # 2. Split into distinct visual clauses
    clauses = [c.strip() for c in re.split(r'[,.;]', p) if c.strip()]
    for c in clauses:
        clean = re.sub(r'[^a-zA-Z0-9\s]', ' ', c).lower()
        w = [word for word in clean.split() if word not in STOP_WORDS and len(word) > 2]
        if len(w) >= 2:
            q1 = " ".join(w[:3])
            if q1 and q1 not in queries:
                queries.append(q1)
            if len(w) >= 4:
                q2 = " ".join(w[2:5])
                if q2 and q2 not in queries:
                    queries.append(q2)

    return queries


def extract_broll_keywords(
    scene_text: str,
    image_prompt: str = "",
    video_prompt: str = "",
    subject: str = "",
    action: str = "",
    setting: str = "",
    shot: str = "",
    mood: str = "",
    visual_type: str = "literal",
    visual_priority: str = "medium",
    must_show: Optional[List[str]] = None,
    should_avoid: Optional[List[str]] = None,
    search_queries: Optional[List[str]] = None,
    broll_keywords: Optional[List[str]] = None,
    continuity_group: str = "",
    topic: str = "",
    scene_id: str = ""
) -> List[str]:
    """
    Generates high-relevance search queries for stock video libraries (Pexels).
    Priority Hierarchy:
    DIRECTOR SCENE DATA > SCENE-SPECIFIC QUERY GENERATION > KEY VISUAL MAP > GENERIC TOPIC
    """
    candidates = []

    # 1. Direct search_queries & broll_keywords from Gemini Director (highest priority)
    if search_queries:
        for sq in search_queries:
            if isinstance(sq, str) and sq.strip():
                clean_sq = clean_query_phrase(sq, max_words=4)
                if clean_sq and clean_sq not in candidates:
                    candidates.append(clean_sq)

    if broll_keywords:
        for kw in broll_keywords:
            if isinstance(kw, str) and kw.strip():
                clean_kw = clean_query_phrase(kw, max_words=3)
                if clean_kw and clean_kw not in candidates:
                    candidates.append(clean_kw)

    # 2. must_show combinations with setting or action
    if must_show and isinstance(must_show, list):
        for ms in must_show:
            clean_ms = clean_query_phrase(ms, max_words=3)
            if clean_ms and clean_ms not in candidates:
                candidates.append(clean_ms)
            if setting:
                clean_set = clean_query_phrase(setting, max_words=2)
                combo = f"{clean_ms} {clean_set}".strip()
                if combo and combo not in candidates:
                    candidates.append(combo)

    # 3. Subject + Action / Setting combos
    sub_clean = clean_query_phrase(subject, max_words=2)
    act_clean = clean_query_phrase(action, max_words=2)
    set_clean = clean_query_phrase(setting, max_words=2)
    if sub_clean and act_clean:
        combo = f"{sub_clean} {act_clean}"
        if combo not in candidates:
            candidates.append(combo)
    if sub_clean and set_clean:
        combo = f"{sub_clean} {set_clean}"
        if combo not in candidates:
            candidates.append(combo)
    elif sub_clean and sub_clean not in candidates:
        candidates.append(sub_clean)

    # 4. Extract concrete visual phrases from Gemini image_prompt & video_prompt
    if image_prompt or video_prompt:
        prompt_queries = extract_queries_from_gemini_prompt(image_prompt, video_prompt)
        for pq in prompt_queries:
            clean_pq = clean_query_phrase(pq, max_words=3)
            if clean_pq and clean_pq not in candidates:
                candidates.append(clean_pq)

    # 5. Specialized Visual Strategy Translations
    vtype = str(visual_type or "literal").lower()
    if vtype == "conceptual":
        if any(w in scene_text.lower() for w in ["economy", "recession", "market", "crash", "value", "lost"]):
            candidates.extend(["stock market chart screen", "trading floor busy", "financial charts falling red"])
    elif vtype == "data":
        if any(w in scene_text.lower() for w in ["signal", "radar", "monitor", "frequency"]):
            candidates.extend(["radar screen green glow", "control room radar", "screen digital signal"])
        elif any(w in scene_text.lower() for w in ["document", "classified", "archive", "file"]):
            candidates.extend(["classified documents archive", "hands opening confidential file", "detective archive documents"])
    elif vtype == "historical":
        if any(w in scene_text.lower() for w in ["roman", "soldier", "army", "warrior"]):
            candidates.extend(["roman soldiers marching", "ancient warriors armor", "historical battle soldiers"])
    elif vtype == "abstract":
        if any(w in scene_text.lower() for w in ["alone", "waiting", "window", "answer"]):
            candidates.extend(["person looking out window alone", "solitary silhouette room window", "person waiting thinking"])

    # 6. Domain & Action Keyword Mapping from scene narration & prompt
    full_context = f"{scene_text} {image_prompt} {subject} {action}".lower()
    words = [w for w in re.sub(r'[^a-zA-Z0-9\s]', ' ', full_context).split() if len(w) > 2]

    KEY_VISUAL_MAP = {
        # Aviation & Cockpit
        "cockpit": "airplane cockpit night",
        "airbus": "commercial airplane dark clouds",
        "boeing": "commercial airplane flight",
        "727": "commercial airplane dark clouds",
        "a330": "airplane cockpit flight night",
        "airplane": "commercial airplane dark clouds",
        "plane": "commercial airplane flight",
        "aircraft": "commercial airplane dark clouds",
        "flight": "airplane cockpit night",
        "pilot": "airplane pilot cockpit",
        "sensors": "cockpit control panel",
        "sensor": "cockpit control panel",
        "instruments": "cockpit control panel",
        "instrument": "cockpit instrument panel",
        "readings": "cockpit control panel",
        "radar": "radar screen green glow",
        "runway": "airport runway night lights",
        "engine": "jet airplane engine",
        "tower": "airport control tower",
        # Marine & Ships
        "ship": "ship sailing stormy ocean",
        "boat": "ship stormy dark waves",
        "vessel": "ship stormy ocean waves",
        "ocean": "deep ocean dark water waves",
        "sea": "dark stormy ocean waves",
        "atlantic": "dark stormy ocean waves",
        "pacific": "deep ocean waves aerial",
        "sailing": "ship stormy ocean waves",
        "submarine": "submarine deep underwater",
        # Weather & Elements
        "weather": "lightning storm clouds",
        "storm": "lightning storm dark clouds",
        "stormy": "dark storm clouds timelapse",
        "lightning": "lightning strike dark sky",
        "thunder": "lightning storm dark clouds",
        "rain": "heavy rain window night",
        "ice": "ice frost frozen storm",
        "crystals": "ice frost frozen storm",
        # Finance, Economy & Wealth
        "economy": "stock market trading chart",
        "recession": "stock market chart screen",
        "stocks": "stock market graphs screen",
        "stock": "stock market trading chart",
        "market": "stock market chart screen",
        "trading": "stock market graphs screen",
        "money": "counting cash dollar bills",
        "cash": "counting cash dollar bills",
        "wealth": "luxury skyscraper city night",
        "billionaire": "luxury penthouse office",
        "rich": "luxury gold coins",
        "loss": "financial charts red screen",
        "crash": "stock market chart red",
        # Investigation, Archives & Documents
        "classified": "old confidential file archive",
        "document": "classified documents magnifying glass",
        "documents": "classified documents archive",
        "archive": "vintage archive documents library",
        "investigation": "detective looking at documents",
        "investigators": "detective magnifying glass documents",
        "evidence": "detective investigation dark room",
        "police": "police lights car night",
        "detective": "detective investigation dark",
        "secret": "classified documents magnifying glass",
        "file": "old confidential file archive",
        # Technology & Signals
        "signal": "radar screen green glow",
        "frequency": "audio frequency oscilloscope monitor",
        "screen": "computer screen digital glitch",
        "monitor": "control room computer monitors",
        "satellite": "earth orbit satellite space",
        "space": "deep space galaxy stars",
        "alien": "mysterious lights night sky",
        # Human Reaction & Emotion
        "alone": "person looking out window alone",
        "waiting": "person waiting window dark",
        "window": "looking through window night rain",
        "thinking": "person thinking dark room",
        "fear": "shadowy silhouette dark hallway",
        "mystery": "mysterious fog dark forest",
        "vanished": "mysterious fog dark forest",
        "disappeared": "dark silhouette mystery",
        # Historical & Military
        "roman": "roman soldiers marching",
        "soldiers": "ancient warriors armor",
        "soldier": "military soldiers marching",
        "army": "army marching ancient",
        "pyramid": "ancient egypt pyramids aerial",
        "sphinx": "egypt sphinx desert sand"
    }

    matched_visuals = []
    for w in words:
        if w in KEY_VISUAL_MAP and KEY_VISUAL_MAP[w] not in matched_visuals:
            matched_visuals.append(KEY_VISUAL_MAP[w])

    candidates.extend(matched_visuals)

    # 7. Topic keyword (lowest priority, truncated to 3 words)
    if topic:
        clean_top = clean_query_phrase(topic, max_words=3)
        if clean_top and clean_top not in candidates:
            candidates.append(clean_top)

    # 8. Context-Aware Diverse Fallbacks (rotating hash avoids duplicate fallbacks)
    hash_idx = sum(ord(c) for c in (scene_id or scene_text[:10]))
    if any(k in full_context for k in ["airbus", "plane", "airplane", "flight", "cockpit", "aircraft", "jet"]):
        aviation_fallbacks = [
            "airplane cockpit night",
            "cockpit control panel",
            "commercial airplane dark clouds",
            "airplane flying clouds aerial",
            "airport runway night lights"
        ]
        candidates.append(aviation_fallbacks[hash_idx % len(aviation_fallbacks)])
    elif any(k in full_context for k in ["ship", "boat", "vessel", "ocean", "sea", "atlantic", "water"]):
        ocean_fallbacks = [
            "ship sailing stormy ocean",
            "dark stormy ocean waves",
            "deep ocean dark water waves",
            "aerial stormy sea water"
        ]
        candidates.append(ocean_fallbacks[hash_idx % len(ocean_fallbacks)])
    elif any(k in full_context for k in ["storm", "weather", "lightning", "rain", "ice"]):
        storm_fallbacks = [
            "lightning storm clouds",
            "heavy rain window night",
            "dark storm clouds timelapse",
            "lightning strike dark sky"
        ]
        candidates.append(storm_fallbacks[hash_idx % len(storm_fallbacks)])
    elif any(k in full_context for k in ["economy", "market", "stock", "trade", "money", "cash", "wealth"]):
        finance_fallbacks = [
            "stock market chart screen",
            "trading floor busy screens",
            "luxury skyscraper city night",
            "counting cash dollar bills"
        ]
        candidates.append(finance_fallbacks[hash_idx % len(finance_fallbacks)])
    elif any(k in full_context for k in ["document", "classified", "investig", "archive", "file", "secret"]):
        investig_fallbacks = [
            "classified documents archive",
            "detective looking at documents",
            "vintage archive library files",
            "magnifying glass confidential document"
        ]
        candidates.append(investig_fallbacks[hash_idx % len(investig_fallbacks)])
    else:
        general_fallbacks = [
            "cinematic dark atmosphere aerial",
            "foggy forest dark aerial",
            "mysterious silhouette night",
            "dramatic clouds sunset aerial"
        ]
        candidates.append(general_fallbacks[hash_idx % len(general_fallbacks)])

    # Remove duplicates preserving priority order
    unique_candidates = []
    for c in candidates:
        c_strip = c.strip()
        if c_strip and c_strip.lower() not in [u.lower() for u in unique_candidates]:
            unique_candidates.append(c_strip)

    return unique_candidates


def search_pexels_videos(
    query: str,
    orientation: str = "portrait",
    limit: int = 10,
    api_key: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Queries Pexels Video API for video clips matching the query.
    Uses in-memory cache to eliminate duplicate network calls.
    Returns list of candidate dicts with duration, thumbnail, dimensions, orientation, and mp4 url.
    """
    key = api_key or get_pexels_api_key()
    if not key:
        logger.warning("Pexels API key not configured.")
        return []

    clean_q = clean_query_phrase(query, max_words=4)
    if not clean_q:
        return []

    cache_key = f"{clean_q}_{orientation}_{limit}"
    if cache_key in _SEARCH_CACHE:
        return [dict(v) for v in _SEARCH_CACHE[cache_key]]

    params: Dict[str, Any] = {
        "query": clean_q,
        "per_page": min(15, max(1, limit)),
        "size": "medium"
    }
    if orientation in ("portrait", "landscape"):
        params["orientation"] = orientation

    url = f"{PEXELS_SEARCH_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": key,
            "User-Agent": "YouTubeShortsStudio/2.0"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            if response.status != 200:
                logger.warning(f"Pexels API returned status {response.status}")
                return []
            data = json.loads(response.read().decode("utf-8"))
            videos = data.get("videos", [])
            results = []

            for v in videos:
                v_id = str(v.get("id"))
                dur = float(v.get("duration", 0))
                thumb = v.get("image", "")
                files = v.get("video_files", [])
                if not files:
                    continue

                # Identify portrait files (height > width) vs high-res landscape
                portrait_files = [
                    f for f in files
                    if f.get("height", 0) > f.get("width", 0) and f.get("file_type") == "video/mp4"
                ]

                candidate_files = portrait_files if portrait_files else [
                    f for f in files if f.get("file_type") == "video/mp4"
                ]

                if not candidate_files:
                    continue

                # Sort by resolution favoring 1080p
                candidate_files.sort(
                    key=lambda x: (x.get("width", 0) <= 1080, x.get("width", 0) * x.get("height", 0)),
                    reverse=True
                )
                best_file = candidate_files[0]
                w = int(best_file.get("width", 1080))
                h = int(best_file.get("height", 1920))

                results.append({
                    "id": v_id,
                    "duration": dur,
                    "thumbnail": thumb,
                    "video_url": best_file.get("link"),
                    "width": w,
                    "height": h,
                    "orientation": "portrait" if h >= w else "landscape",
                    "query": clean_q
                })

            _SEARCH_CACHE[cache_key] = results
            return results
    except Exception as e:
        logger.error(f"Error querying Pexels Video API for '{clean_q}': {e}")
        return []


def collect_candidate_videos(
    queries: List[str],
    used_video_ids: Optional[Set[str]] = None,
    max_candidates: int = 15,
    api_key: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Executes multiple Pexels search queries, deduplicating candidate clips across queries.
    Skips any clip ID present in used_video_ids to guarantee ZERO clip repetition.
    """
    seen_ids = set()
    if used_video_ids:
        seen_ids.update(str(vid) for vid in used_video_ids)

    all_candidates = []

    for q in queries:
        if len(all_candidates) >= max_candidates:
            break

        # 1. Search portrait/vertical first
        vids = search_pexels_videos(q, orientation="portrait", limit=8, api_key=api_key)

        # 2. If zero results, search without orientation constraint for high-res landscape
        if not vids:
            vids = search_pexels_videos(q, orientation="", limit=6, api_key=api_key)

        for v in vids:
            vid_id = str(v.get("id"))
            if vid_id in seen_ids:
                continue
            seen_ids.add(vid_id)
            all_candidates.append(v)
            if len(all_candidates) >= max_candidates:
                break

    return all_candidates


def filter_candidates(
    candidates: List[Dict[str, Any]],
    target_duration: float = 3.0
) -> List[Dict[str, Any]]:
    """
    Hard filtering before AI ranking:
    - Eliminates missing/corrupt URLs
    - Eliminates clips under 1.5s
    - Eliminates clips with unusable low resolution (< 480p)
    - Accepts portrait videos and high-res landscape videos suitable for 9:16 center cropping
    """
    filtered = []
    for c in candidates:
        url = c.get("video_url") or ""
        if not url.startswith("http"):
            continue

        dur = float(c.get("duration", 0))
        if dur < 1.5:
            continue

        w = int(c.get("width", 0))
        h = int(c.get("height", 0))
        if w < 480 and h < 480:
            continue

        # If landscape, require at least 720p resolution for high quality center cropping
        if h < w and w < 1280 and h < 720:
            continue

        filtered.append(c)

    return filtered


def fetch_thumbnail_base64(url: str, timeout: int = 6) -> Optional[str]:
    """
    Downloads candidate thumbnail image and returns base64 encoded JPEG string.
    Uses memory cache to avoid downloading the same thumbnail multiple times.
    """
    if not url or not url.startswith("http"):
        return None

    if url in _THUMBNAIL_CACHE:
        return _THUMBNAIL_CACHE[url]

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "YouTubeShortsStudio/2.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            if data and len(data) > 400:
                # Resize if unnecessarily large (> 150KB) to minimize token footprint
                if len(data) > 150_000:
                    img = Image.open(BytesIO(data))
                    img.thumbnail((360, 640), Image.Resampling.BILINEAR)
                    buf = BytesIO()
                    img.convert("RGB").save(buf, format="JPEG", quality=80)
                    data = buf.getvalue()
                b64 = base64.b64encode(data).decode("utf-8")
                _THUMBNAIL_CACHE[url] = b64
                return b64
    except Exception as e:
        logger.debug(f"Failed to fetch thumbnail from {url}: {e}")

    return None


def rank_candidates_with_vision(
    candidates: List[Dict[str, Any]],
    scene_context: Dict[str, Any],
    api_key: Optional[str] = None
) -> Tuple[Optional[Dict[str, Any]], Optional[int], Optional[str]]:
    """
    AI Multimodal Vision Ranking using Gemini 3.8 Flash.
    Sends multiple candidate thumbnails in ONE unified evaluation request.
    Evaluates what is ACTUALLY VISIBLE against scene subject, action, setting, must_show, and should_avoid.
    Returns (best_candidate, best_score, reason) or (None, None, None) on failure.
    """
    resolved_key = api_key or get_gemini_api_key()
    if not resolved_key or not candidates:
        return None, None, None

    # Consider top 3 to 5 candidates for Vision evaluation to keep latency low
    top_candidates = candidates[:5]

    # Download thumbnails concurrently
    thumbnails: Dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        future_map = {
            executor.submit(fetch_thumbnail_base64, c.get("thumbnail", "")): c["id"]
            for c in top_candidates
        }
        for future in as_completed(future_map):
            cand_id = future_map[future]
            try:
                b64 = future.result()
                if b64:
                    thumbnails[cand_id] = b64
            except Exception:
                pass

    valid_candidates = [c for c in top_candidates if c["id"] in thumbnails]
    if not valid_candidates:
        return None, None, None

    scene_text = scene_context.get("scene_text", "")
    subject = scene_context.get("subject", "")
    action = scene_context.get("action", "")
    setting = scene_context.get("setting", "")
    shot = scene_context.get("shot", "")
    mood = scene_context.get("mood", "")
    vtype = scene_context.get("visual_type", "literal")
    must_show = scene_context.get("must_show", [])
    should_avoid = scene_context.get("should_avoid", [])

    prompt_text = f"""You are an elite film visual director evaluating stock video candidate thumbnails for a vertical (9:16) YouTube Short.

SCENE TO VISUALIZE:
- Spoken Narration: "{scene_text}"
- Required Subject: {subject}
- Required Action: {action}
- Required Setting: {setting}
- Shot Framing: {shot} | Mood: {mood} | Visual Strategy: {vtype}
- MUST-SHOW Elements: {', '.join(must_show) if must_show else 'Subject in setting'}
- SHOULD-AVOID Elements: {', '.join(should_avoid) if should_avoid else 'Generic unrelated footage, incorrect vehicles/places'}

TASK:
Examine what is ACTUALLY VISIBLE in each candidate image below. Do not guess what might be outside the frame.
Grade each candidate strictly on semantic visual relevance to what the viewer should literally see.

Scoring Criteria (0 to 100):
- subject_match (0-30): Does the candidate visibly show the required subject?
- action_match (0-30): Does the candidate visibly portray the specific action or dynamic?
- setting_match (0-15): Is the setting/environment accurate?
- composition_match (0-10): Framing, lighting, visual interest for 9:16 vertical video?
- shot_match (0-5): Does the framing match the intended shot scale?
- quality_match (0-5): Visual clarity, professional cinematography?
- duration_match (0-5): Clip duration suitability?
- penalty (0 to -30): Heavily penalize if it contains any SHOULD-AVOID elements or misleading visuals!

Total Score = subject_match + action_match + setting_match + composition_match + shot_match + quality_match + duration_match + penalty (bounded 0 to 100).

Return strict JSON only:
{{
  "ranked_candidates": [
    {{
      "id": "<candidate_id as string>",
      "score": <0 to 100>,
      "subject_match": <0 to 30>,
      "action_match": <0 to 30>,
      "setting_match": <0 to 15>,
      "composition_match": <0 to 10>,
      "shot_match": <0 to 5>,
      "quality_match": <0 to 5>,
      "duration_match": <0 to 5>,
      "penalty": <0 or negative integer>,
      "reason": "<one concise sentence explaining what is literally visible and why this score was awarded>"
    }}
  ],
  "best_id": "<id of top candidate>"
}}"""

    parts: List[Dict[str, Any]] = [{"text": prompt_text}]
    for cand in valid_candidates:
        c_id = str(cand["id"])
        parts.append({"text": f"Candidate ID: {c_id}"})
        parts.append({
            "inlineData": {
                "mimeType": "image/jpeg",
                "data": thumbnails[c_id]
            }
        })

    contents = [{"parts": parts}]

    try:
        raw_text, _ = generate_content(
            prompt_or_contents=contents,
            thinking_level="low",
            max_output_tokens=2000,
            json_mode=True,
            api_key=resolved_key,
            timeout=20
        )
        if not raw_text:
            return None, None, None

        clean_json = raw_text.strip()
        if clean_json.startswith("```"):
            clean_json = re.sub(r'^```(?:json)?\s*', '', clean_json)
            clean_json = re.sub(r'\s*```$', '', clean_json)

        data = json.loads(clean_json)
        ranked = data.get("ranked_candidates", [])
        best_id = str(data.get("best_id", ""))

        scores_map = {}
        reasons_map = {}
        for r in ranked:
            r_id = str(r.get("id"))
            # Normalize score: if model returned 0.0 - 1.0 float, scale to 0 - 100
            raw_s = float(r.get("score", 50))
            if raw_s <= 1.0 and raw_s > 0.0:
                raw_s = raw_s * 100.0
            scores_map[r_id] = int(round(raw_s))
            reasons_map[r_id] = str(r.get("reason", "Semantic visual match"))

        chosen_candidate = next((c for c in valid_candidates if str(c["id"]) == best_id), None)
        if not chosen_candidate and scores_map:
            # Fallback to candidate with highest score
            best_by_score = max(scores_map.items(), key=lambda x: x[1])[0]
            chosen_candidate = next((c for c in valid_candidates if str(c["id"]) == best_by_score), None)

        if chosen_candidate:
            c_id = str(chosen_candidate["id"])
            score = scores_map.get(c_id, 80)
            reason = reasons_map.get(c_id, "Selected by Gemini Vision for strong semantic match")
            return chosen_candidate, score, reason

    except Exception as e:
        logger.warning(f"[StockVideo] Gemini Vision ranking error: {e}")

    return None, None, None


def rank_candidates_deterministically(
    candidates: List[Dict[str, Any]],
    scene_context: Dict[str, Any]
) -> Tuple[Optional[Dict[str, Any]], int, str]:
    """
    Deterministic scoring fallback when Gemini Vision is offline, rate-limited, or disabled.
    Ranks based on keyword overlap with must_show, subject, action, query relevance, orientation, and resolution.
    """
    if not candidates:
        return None, 0, "No candidates"

    must_show = [w.lower() for w in scene_context.get("must_show", [])]
    should_avoid = [w.lower() for w in scene_context.get("should_avoid", [])]
    subject = scene_context.get("subject", "").lower()
    action = scene_context.get("action", "").lower()
    scene_text = scene_context.get("scene_text", "").lower()
    target_dur = float(scene_context.get("duration", 3.0))

    best_cand = None
    best_score = -1
    best_reason = ""

    for idx, c in enumerate(candidates):
        score = 55  # Base score for valid Pexels footage
        reasons = []

        q = str(c.get("query", "")).lower()

        # Query matches must_show
        for ms in must_show:
            ms_words = ms.split()
            if any(w in q for w in ms_words):
                score += 15
                reasons.append(f"matches '{ms}'")

        # Query matches subject / action
        if subject and any(w in q for w in subject.split() if len(w) > 3):
            score += 10
            reasons.append("matches subject")
        if action and any(w in q for w in action.split() if len(w) > 3):
            score += 10
            reasons.append("matches action")

        # Penalty for should_avoid
        for sa in should_avoid:
            sa_words = sa.split()
            if any(w in q for w in sa_words):
                score -= 25
                reasons.append(f"penalty for '{sa}'")

        # Orientation: portrait preference for vertical Shorts
        if c.get("orientation") == "portrait":
            score += 10
            reasons.append("vertical 9:16")
        else:
            score -= 5

        # Duration match
        dur = float(c.get("duration", 0))
        if dur >= target_dur:
            score += 5

        # Earlier query order bonus (higher priority queries get slight bonus)
        score += max(0, 5 - idx)

        score = max(0, min(100, score))
        if score > best_score:
            best_score = score
            best_cand = c
            best_reason = f"Deterministic match: {', '.join(reasons) if reasons else 'Keyword relevance'}"

    return best_cand, best_score, best_reason


def download_stock_video(
    video_url: str,
    output_path: str,
    timeout: int = 40
) -> Optional[str]:
    """
    Downloads MP4 video file from URL to output_path.
    Returns absolute path to downloaded file if successful, None otherwise.
    """
    if not video_url or not video_url.startswith("http"):
        return None

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    if os.path.exists(output_path) and os.path.getsize(output_path) > 100_000:
        return os.path.abspath(output_path)

    temp_path = f"{output_path}.tmp"
    req = urllib.request.Request(
        video_url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            with open(temp_path, "wb") as out_file:
                while True:
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break
                    out_file.write(chunk)

        if os.path.exists(temp_path) and os.path.getsize(temp_path) > 50_000:
            if os.path.exists(output_path):
                os.remove(output_path)
            os.rename(temp_path, output_path)
            logger.info(f"Downloaded stock video: {output_path} ({os.path.getsize(output_path)} bytes)")
            return os.path.abspath(output_path)
    except Exception as e:
        logger.error(f"Failed to download stock video from {video_url[:60]}: {e}")
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
    return None


def fetch_broll_for_scene(
    scene_id: str,
    scene_text: str,
    image_prompt: str = "",
    video_prompt: str = "",
    subject: str = "",
    action: str = "",
    setting: str = "",
    shot: str = "",
    mood: str = "",
    visual_type: str = "literal",
    visual_priority: str = "medium",
    must_show: Optional[List[str]] = None,
    should_avoid: Optional[List[str]] = None,
    search_queries: Optional[List[str]] = None,
    broll_keywords: Optional[List[str]] = None,
    continuity_group: str = "",
    topic: str = "",
    used_video_ids: Optional[Set[str]] = None,
    api_key: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    High-relevance cinematic stock video pipeline:
    1. Extracts 3-6 concrete search queries prioritizing Gemini Director visual plan.
    2. Retrieves 5-15 candidate videos across queries.
    3. Performs hard filtering (duration, resolution, aspect ratio, anti-repetition).
    4. Evaluates candidate thumbnails using Gemini Multimodal Vision (or deterministic fallback).
    5. Semantic Quality Gate: Rejects footage with score < 45 to trigger FLUX AI fallback.
    6. Downloads selected video and tracks video ID to guarantee ZERO clip repetition.
    """
    key = api_key or get_pexels_api_key()
    if not key:
        logger.warning("[StockVideo] Pexels API key not configured.")
        return None

    os.makedirs(CACHE_DIR, exist_ok=True)

    print(f"\n[VisualPlanner] Scene ID: {scene_id[:8]} | Narration: '{scene_text[:60]}...'")
    print(f"[VisualPlanner] Subject: '{subject}' | Action: '{action}' | Setting: '{setting}' | Strategy: {visual_type}/{visual_priority}")

    # 1. Generate 3-6 concrete queries
    queries = extract_broll_keywords(
        scene_text=scene_text,
        image_prompt=image_prompt,
        video_prompt=video_prompt,
        subject=subject,
        action=action,
        setting=setting,
        shot=shot,
        mood=mood,
        visual_type=visual_type,
        visual_priority=visual_priority,
        must_show=must_show,
        should_avoid=should_avoid,
        search_queries=search_queries,
        broll_keywords=broll_keywords,
        continuity_group=continuity_group,
        topic=topic,
        scene_id=scene_id
    )
    print(f"[StockSearch] Generated {len(queries)} queries: {queries}")

    # 2. Collect candidates across queries
    candidates = collect_candidate_videos(
        queries=queries,
        used_video_ids=used_video_ids,
        max_candidates=15,
        api_key=key
    )

    # 3. Hard filter candidates
    filtered_candidates = filter_candidates(candidates)
    print(f"[Candidates] Retrieved {len(candidates)} raw, {len(filtered_candidates)} passed hard filtering")

    if not filtered_candidates:
        print(f"[VisualPlanner] No suitable stock footage found on Pexels for scene {scene_id[:8]}. Triggering AI generator (FLUX) fallback.")
        return None

    scene_context = {
        "scene_text": scene_text,
        "subject": subject,
        "action": action,
        "setting": setting,
        "shot": shot,
        "mood": mood,
        "visual_type": visual_type,
        "visual_priority": visual_priority,
        "must_show": must_show or [],
        "should_avoid": should_avoid or []
    }

    # 4. AI Multimodal Vision Ranking (with deterministic fallback)
    chosen_vid = None
    chosen_score = None
    chosen_reason = None

    if len(filtered_candidates) > 1:
        chosen_vid, chosen_score, chosen_reason = rank_candidates_with_vision(
            candidates=filtered_candidates,
            scene_context=scene_context,
            api_key=api_key
        )

    if not chosen_vid or chosen_score is None:
        chosen_vid, chosen_score, chosen_reason = rank_candidates_deterministically(
            candidates=filtered_candidates,
            scene_context=scene_context
        )

    if not chosen_vid:
        return None

    print(f"[AI Ranking] Candidate ID {chosen_vid['id']} selected with score {chosen_score}/100: {chosen_reason}")

    # 5. Semantic Quality Gate: If best available footage scores below 45, reject to trigger FLUX fallback
    if chosen_score < 45:
        print(f"[VisualPlanner] Best candidate score ({chosen_score}/100) below semantic relevance threshold (45). Rejecting stock video to trigger FLUX fallback.")
        return None

    v_url = chosen_vid.get("video_url")
    if not v_url:
        return None

    chosen_query = chosen_vid.get("query") or "pexels"
    clean_q_name = sanitize_filename(chosen_query)
    dest_filename = f"{clean_q_name}_{chosen_vid['id']}.mp4"
    dest_path = os.path.join(CACHE_DIR, dest_filename)

    # 6. Download selected video
    local_path = download_stock_video(v_url, dest_path)
    if local_path and os.path.exists(local_path):
        vid_id_str = str(chosen_vid["id"])
        if used_video_ids is not None:
            used_video_ids.add(vid_id_str)

        print(f"[Selected] Video ID: {vid_id_str} | Query: '{chosen_query}' | Score: {chosen_score} | Path: {local_path}")
        return {
            "media_path": local_path,
            "media_type": "video",
            "video_id": vid_id_str,
            "thumbnail": chosen_vid.get("thumbnail"),
            "duration": chosen_vid.get("duration", 10),
            "source": "pexels",
            "query": chosen_query,
            "score": chosen_score,
            "reason": chosen_reason,
            "candidate_count": len(filtered_candidates),
            "ai_score": chosen_score
        }

    return None
