"""
engine/stock_video.py - Professional Stock Video Engine using Pexels Video API.
Provides high-retention 9:16 vertical b-roll footage for YouTube Shorts.
100% Free with commercial monetization rights.
"""

import os
import re
import json
import logging
import urllib.request
import urllib.parse
from typing import Dict, Any, List, Optional, Tuple

from engine.config import get_pexels_api_key

logger = logging.getLogger("yt_shorts.stock_video")

PEXELS_SEARCH_URL = "https://api.pexels.com/videos/search"
CACHE_DIR = os.path.abspath("outputs/stock_videos")


def sanitize_filename(name: str) -> str:
    """Removes unsafe characters for file paths."""
    clean = re.sub(r'[^a-zA-Z0-9_\-]', '_', name)
    return clean[:60].strip('_')


def search_pexels_videos(
    query: str,
    orientation: str = "portrait",
    limit: int = 5,
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

    clean_q = query.strip()
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


def extract_broll_keywords(
    scene_text: str,
    subject: str = "",
    setting: str = "",
    topic: str = ""
) -> List[str]:
    """
    Generates high-relevance search queries for stock video libraries (Pexels / Pixabay).
    Prioritizes concrete visual b-roll keywords (action, place, atmosphere).
    """
    candidates = []

    # 1. Subject + Setting combo
    sub_clean = re.sub(r'[^a-zA-Z0-9\s]', '', subject).strip()
    set_clean = re.sub(r'[^a-zA-Z0-9\s]', '', setting).strip()
    if sub_clean and set_clean:
        candidates.append(f"{sub_clean} {set_clean}")
    elif sub_clean:
        candidates.append(sub_clean)

    # 2. Key visual nouns from scene narration
    clean_text = re.sub(r'[^a-zA-Z0-9\s]', ' ', scene_text).lower()
    words = [w for w in clean_text.split() if len(w) > 3]

    # Visual priority dictionary matching high-performing b-roll categories
    KEY_VISUAL_MAP = {
        # Finance & Money
        "money": "counting cash money",
        "cash": "counting dollar bills",
        "stock": "stock market trading chart",
        "market": "stock market chart screen",
        "trading": "stock market graphs",
        "wealth": "luxury skyscraper night",
        "billionaire": "luxury penthouse office",
        "rich": "luxury gold coins",
        "discipline": "workout gym motivation",
        "success": "confident businessman city",
        # Mystery & Crime
        "airplane": "airplane flight dark sky",
        "plane": "commercial airplane dark clouds",
        "flight": "airplane cockpit night",
        "radar": "radar screen green glow",
        "tower": "airport control tower",
        "vanished": "mysterious fog dark forest",
        "disappeared": "dark silhouette mystery",
        "investigation": "detective looking at documents",
        "police": "police lights night dark",
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

    # 3. Topic fallback
    if topic:
        clean_topic = re.sub(r'[^a-zA-Z0-9\s]', '', topic).strip()
        if clean_topic:
            candidates.append(clean_topic)

    # 4. Universal atmospheric fallback
    candidates.append("cinematic dark atmosphere aerial")

    # Remove duplicates preserving order
    unique_candidates = []
    for c in candidates:
        c_strip = c.strip()
        if c_strip and c_strip.lower() not in [u.lower() for u in unique_candidates]:
            unique_candidates.append(c_strip)

    return unique_candidates


def fetch_broll_for_scene(
    scene_id: str,
    scene_text: str,
    subject: str = "",
    setting: str = "",
    topic: str = "",
    api_key: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Searches Pexels and downloads optimal vertical video clip for a scene.
    Returns dict: {"media_path": "/path/to/clip.mp4", "media_type": "video", "thumbnail": "...", "duration": 15}
    """
    key = api_key or get_pexels_api_key()
    if not key:
        return None

    os.makedirs(CACHE_DIR, exist_ok=True)

    queries = extract_broll_keywords(scene_text, subject=subject, setting=setting, topic=topic)
    logger.info(f"[StockVideo] Scene {scene_id} candidate queries: {queries}")

    for q in queries:
        videos = search_pexels_videos(q, orientation="portrait", limit=3, api_key=key)
        if not videos:
            continue

        top_vid = videos[0]
        v_url = top_vid.get("video_url")
        if not v_url:
            continue

        clean_q_name = sanitize_filename(q)
        dest_filename = f"{clean_q_name}_{top_vid['id']}.mp4"
        dest_path = os.path.join(CACHE_DIR, dest_filename)

        local_path = download_stock_video(v_url, dest_path)
        if local_path and os.path.exists(local_path):
            return {
                "media_path": local_path,
                "media_type": "video",
                "thumbnail": top_vid.get("thumbnail"),
                "duration": top_vid.get("duration", 10),
                "source": "pexels",
                "query": q
            }

    return None
