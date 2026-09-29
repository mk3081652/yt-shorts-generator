"""
engine/stock_video.py - Professional Stock Video Engine using Pexels Video API.
Provides high-retention 9:16 vertical b-roll footage for YouTube Shorts.
Takes Gemini visual prompts as base queries and guarantees ZERO clip repetition.
100% Free with commercial monetization rights.
"""

import os
import re
import json
import logging
import urllib.request
import urllib.parse
from typing import Dict, Any, List, Optional, Set

from engine.config import get_pexels_api_key

logger = logging.getLogger("yt_shorts.stock_video")

PEXELS_SEARCH_URL = "https://api.pexels.com/videos/search"
CACHE_DIR = os.path.abspath("outputs/stock_videos")

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
    setting: str = "",
    topic: str = "",
    broll_keywords: Optional[List[str]] = None,
    scene_id: str = ""
) -> List[str]:
    """
    Generates high-relevance search queries for stock video libraries (Pexels).
    Prioritizes Gemini's generated visual prompt and Director broll_keywords.
    """
    candidates = []

    # 1. Direct broll_keywords from Gemini Director (highest accuracy)
    if broll_keywords:
        for kw in broll_keywords:
            if isinstance(kw, str) and kw.strip():
                clean_kw = clean_query_phrase(kw, max_words=3)
                if clean_kw:
                    candidates.append(clean_kw)

    # 2. Extract concrete visual phrases from Gemini image_prompt & video_prompt
    if image_prompt or video_prompt:
        prompt_queries = extract_queries_from_gemini_prompt(image_prompt, video_prompt)
        for pq in prompt_queries:
            clean_pq = clean_query_phrase(pq, max_words=3)
            if clean_pq and clean_pq not in candidates:
                candidates.append(clean_pq)

    # 3. Subject + Setting combo
    sub_clean = clean_query_phrase(subject, max_words=2)
    set_clean = clean_query_phrase(setting, max_words=2)
    if sub_clean and set_clean:
        candidates.append(f"{sub_clean} {set_clean}")
    elif sub_clean:
        candidates.append(sub_clean)

    # 4. Domain & Action Keyword Mapping from scene narration & prompt
    full_context = f"{scene_text} {image_prompt} {subject}".lower()
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
        # Weather & Elements
        "weather": "lightning storm clouds",
        "storm": "lightning storm dark clouds",
        "stormy": "dark storm clouds timelapse",
        "lightning": "lightning strike dark sky",
        "thunder": "lightning storm dark clouds",
        "rain": "heavy rain window night",
        "ice": "ice frost frozen storm",
        "crystals": "ice frost frozen storm",
        "atlantic": "dark stormy ocean waves",
        # Finance & Wealth
        "money": "counting cash dollar bills",
        "cash": "counting cash dollar bills",
        "stock": "stock market trading chart",
        "market": "stock market chart screen",
        "trading": "stock market graphs screen",
        "wealth": "luxury skyscraper city night",
        "billionaire": "luxury penthouse office",
        "rich": "luxury gold coins",
        "discipline": "workout gym motivation",
        "success": "confident businessman city",
        # Mystery & Crime
        "vanished": "mysterious fog dark forest",
        "disappeared": "dark silhouette mystery",
        "investigation": "detective looking at documents",
        "police": "police lights car night",
        "detective": "detective investigation dark",
        "secret": "classified documents magnifying glass",
        "classified": "old confidential file archive",
        "forest": "dark foggy pine forest",
        "ocean": "deep ocean dark water waves",
        "sea": "dark stormy ocean waves",
        "ship": "ship sailing stormy ocean",
        "space": "deep space galaxy stars",
        "alien": "mysterious lights night sky",
        "pyramid": "ancient egypt pyramids aerial",
        "sphinx": "egypt sphinx desert sand",
        "satellite": "earth orbit satellite space"
    }

    matched_visuals = []
    for w in words:
        if w in KEY_VISUAL_MAP and KEY_VISUAL_MAP[w] not in matched_visuals:
            matched_visuals.append(KEY_VISUAL_MAP[w])

    candidates.extend(matched_visuals)

    # 5. Topic keyword
    if topic:
        clean_top = clean_query_phrase(topic, max_words=3)
        if clean_top and clean_top not in candidates:
            candidates.append(clean_top)

    # 6. Context-Aware Diverse Fallbacks (avoids identical fallback for multiple scenes)
    hash_idx = sum(ord(c) for c in (scene_id or scene_text[:10]))
    if any(k in full_context for k in ["airbus", "plane", "airplane", "flight", "cockpit", "aircraft", "jet"]):
        aviation_fallbacks = [
            "commercial airplane dark clouds",
            "airplane cockpit night",
            "cockpit control panel",
            "airplane flying clouds aerial",
            "airport runway night lights"
        ]
        candidates.append(aviation_fallbacks[hash_idx % len(aviation_fallbacks)])
    elif any(k in full_context for k in ["storm", "weather", "lightning", "rain", "ice"]):
        storm_fallbacks = [
            "lightning storm clouds",
            "heavy rain window night",
            "dark storm clouds timelapse",
            "lightning strike dark sky"
        ]
        candidates.append(storm_fallbacks[hash_idx % len(storm_fallbacks)])
    elif any(k in full_context for k in ["ocean", "sea", "water", "atlantic"]):
        ocean_fallbacks = [
            "dark stormy ocean waves",
            "deep ocean dark water waves",
            "aerial stormy sea water"
        ]
        candidates.append(ocean_fallbacks[hash_idx % len(ocean_fallbacks)])
    elif any(k in full_context for k in ["money", "cash", "stock", "wealth", "trading"]):
        finance_fallbacks = [
            "stock market chart screen",
            "luxury skyscraper city night",
            "counting cash dollar bills"
        ]
        candidates.append(finance_fallbacks[hash_idx % len(finance_fallbacks)])
    else:
        general_fallbacks = [
            "cinematic dark atmosphere aerial",
            "foggy forest dark aerial",
            "mysterious silhouette night",
            "dramatic clouds sunset aerial"
        ]
        candidates.append(general_fallbacks[hash_idx % len(general_fallbacks)])

    # Remove duplicates preserving order
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
    Queries Pexels Video API for portrait/vertical video clips matching the query.
    Returns list of dicts: [{"id": 123, "duration": 12, "thumbnail": "...", "video_url": "...", "width": 1080, "height": 1920}]
    """
    key = api_key or get_pexels_api_key()
    if not key:
        logger.warning("Pexels API key not configured.")
        return []

    clean_q = clean_query_phrase(query, max_words=4)
    if not clean_q:
        return []

    params = {
        "query": clean_q,
        "orientation": orientation,
        "per_page": min(15, max(1, limit)),
        "size": "medium"
    }
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
                v_id = v.get("id")
                dur = v.get("duration", 0)
                thumb = v.get("image", "")
                files = v.get("video_files", [])
                if not files:
                    continue

                # Filter for portrait/vertical files (height > width) or 1080x1920 / 720x1280
                portrait_files = [
                    f for f in files
                    if f.get("height", 0) > f.get("width", 0) and f.get("file_type") == "video/mp4"
                ]

                # Fallback to any mp4 if no strict portrait
                candidate_files = portrait_files if portrait_files else [
                    f for f in files if f.get("file_type") == "video/mp4"
                ]

                if not candidate_files:
                    continue

                # Pick highest quality <= 1080p
                candidate_files.sort(
                    key=lambda x: (x.get("width", 0) <= 1080, x.get("width", 0) * x.get("height", 0)),
                    reverse=True
                )
                best_file = candidate_files[0]
                results.append({
                    "id": v_id,
                    "duration": dur,
                    "thumbnail": thumb,
                    "video_url": best_file.get("link"),
                    "width": best_file.get("width", 1080),
                    "height": best_file.get("height", 1920)
                })

            return results
    except Exception as e:
        logger.error(f"Error querying Pexels Video API for '{clean_q}': {e}")
        return []


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
    setting: str = "",
    topic: str = "",
    broll_keywords: Optional[List[str]] = None,
    used_video_ids: Optional[Set[str]] = None,
    api_key: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Searches Pexels and downloads the optimal vertical video clip for a scene.
    Takes Gemini visual prompts as base queries and guarantees ZERO clip repetition.
    Returns dict: {"media_path": "/path/to/clip.mp4", "media_type": "video", "video_id": "123", "thumbnail": "...", "duration": 15}
    """
    key = api_key or get_pexels_api_key()
    if not key:
        return None

    os.makedirs(CACHE_DIR, exist_ok=True)

    queries = extract_broll_keywords(
        scene_text=scene_text,
        image_prompt=image_prompt,
        video_prompt=video_prompt,
        subject=subject,
        setting=setting,
        topic=topic,
        broll_keywords=broll_keywords,
        scene_id=scene_id
    )
    logger.info(f"[StockVideo] Scene {scene_id} candidate queries: {queries}")

    chosen_vid = None
    chosen_query = None

    for q in queries:
        videos = search_pexels_videos(q, orientation="portrait", limit=10, api_key=key)
        if not videos:
            continue

        # Find first video not in used_video_ids
        for v in videos:
            vid_id = str(v.get("id"))
            if used_video_ids is not None and vid_id in used_video_ids:
                continue  # Skip already used clip!
            chosen_vid = v
            chosen_query = q
            break

        if chosen_vid:
            break

    # If all candidates across all queries were already used, pick best from first query to avoid failing
    if not chosen_vid and queries:
        videos = search_pexels_videos(queries[0], orientation="portrait", limit=5, api_key=key)
        if videos:
            chosen_vid = videos[0]
            chosen_query = queries[0]

    if not chosen_vid:
        return None

    v_url = chosen_vid.get("video_url")
    if not v_url:
        return None

    clean_q_name = sanitize_filename(chosen_query or "pexels")
    dest_filename = f"{clean_q_name}_{chosen_vid['id']}.mp4"
    dest_path = os.path.join(CACHE_DIR, dest_filename)

    local_path = download_stock_video(v_url, dest_path)
    if local_path and os.path.exists(local_path):
        vid_id_str = str(chosen_vid["id"])
        if used_video_ids is not None:
            used_video_ids.add(vid_id_str)
        return {
            "media_path": local_path,
            "media_type": "video",
            "video_id": vid_id_str,
            "thumbnail": chosen_vid.get("thumbnail"),
            "duration": chosen_vid.get("duration", 10),
            "source": "pexels",
            "query": chosen_query
        }

    return None
