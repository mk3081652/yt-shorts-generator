import os
import sys
import re
import socket
import time
import shutil
import urllib.request
import urllib.parse
import json
import subprocess
import imageio_ffmpeg
from typing import List, Dict, Any, Set, Tuple, Optional

# Enforce UTF-8 console output on Windows to prevent UnicodeEncodeError with web image titles
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Enforce IPv4 on Windows to prevent intermittent [Errno 11001] getaddrinfo failures
_orig_getaddrinfo = socket.getaddrinfo
def _ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
socket.getaddrinfo = _ipv4_getaddrinfo

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()

STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "up", "about", "into", "over", "after",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "will", "would", "shall", "should", "may", "might",
    "must", "can", "could", "this", "that", "these", "those", "my", "your",
    "his", "her", "its", "our", "their", "it", "they", "them", "we", "you",
    "what", "which", "who", "whom", "whose", "why", "how", "all", "any",
    "both", "each", "few", "more", "most", "other", "some", "such", "no",
    "nor", "not", "only", "own", "same", "so", "than", "too", "very", "just",
    "there", "here", "when", "where", "while", "also", "despite", "one", "later",
    "more", "than", "decade", "remains", "unanswered"
}

JUNK_IMAGE_PATTERNS = [
    'flag', 'logo', 'icon', 'symbol', 'question_mark', 'edit-clear', 
    'commons-logo', 'duplicate', 'aviacion', 'wikiquote', 'disambig',
    'stub', 'padlock', 'shackle', 'button', 'arrow', 'placeholder',
    'portal-bullet', 'crystal_clear', 'speaker', 'decrease', 'increase',
    '.pdf', '.djvu', '.svg', '.tif', '.tiff', 'document', 'monograph',
    'magazine', 'journal', 'ia_', 'book', 'text', 'scan', 'treaty',
    'act', 'letter', 'census', 'transcript', 'page_'
]


def clean_words(text: str) -> List[str]:
    """Clean and tokenize words for semantic matching."""
    clean = re.sub(r'[^a-zA-Z0-9\s]', ' ', text).lower()
    return [w for w in clean.split() if w not in STOP_WORDS and len(w) > 2]


def find_primary_wikipedia_topic(script_text: str) -> str:
    """Find the real factual subject from the script, avoiding conversational hook traps."""
    # 1. Look for capitalized multi-word named entities or flight/ship/historical entities
    # E.g. 'Malaysia Airlines Flight 370', 'SR-71 Blackbird', 'Boeing 777', 'Apollo 11'
    matches = re.findall(r'([A-Z][a-zA-Z0-9]+(?:\s+[A-Z0-9][a-zA-Z0-9]+)+)', script_text)
    if matches:
        filtered = [
            m for m in matches 
            if not any(w in m.lower() for w in [
                'on march', 'on april', 'on may', 'on june', 'on july', 'on august',
                'on september', 'on october', 'on november', 'on december',
                'what if', 'did you', 'have you', 'imagine a', 'welcome to',
                'how to', 'in 19', 'in 20', 'more than'
            ])
        ]
        if filtered:
            filtered.sort(key=len, reverse=True)
            return filtered[0]

    # 2. Extract key subject nouns from the entire script
    nouns = [
        w for w in clean_words(script_text)
        if w not in {
            'imagine', 'people', 'simply', 'vanishing', 'night', 'exactly', 'happened',
            'continued', 'flying', 'hours', 'largest', 'search', 'history', 'never',
            'found', 'really', 'mystery', 'remains', 'unsolved', 'decade', 'later',
            'world', 'today', 'think', 'know', 'ever', 'look', 'time'
        }
    ]
    if nouns:
        from collections import Counter
        counts = Counter(nouns).most_common(2)
        candidate = " ".join([c[0] for c in counts])
        if candidate:
            return candidate.title()

    return "Documentary Story"


def fetch_commons_media_pool(topic_title: str, limit: int = 35) -> List[Dict[str, Any]]:
    """
    Directly queries Wikimedia Commons File Search API for the topic.
    Returns authentic high-res photos, maps, and historical media.
    """
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    pool = []
    try:
        url = (
            "https://commons.wikimedia.org/w/api.php?action=query"
            f"&generator=search&gsrsearch={urllib.parse.quote(topic_title)}"
            f"&gsrnamespace=6&gsrlimit={limit}"
            "&prop=imageinfo&iiprop=url|size|mime&iiurlwidth=1080&format=json"
        )
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            pages = data.get('query', {}).get('pages', {})
            for k, p in pages.items():
                title = p.get('title', '')
                t_lower = title.lower()
                if any(j in t_lower for j in JUNK_IMAGE_PATTERNS):
                    continue
                infos = p.get('imageinfo', [])
                if infos:
                    info = infos[0]
                    mime = info.get('mime', '').lower()
                    u = info.get('thumburl') or info.get('url')
                    if u and any(m in mime for m in ['jpeg', 'jpg', 'png', 'webp']):
                        title_clean = title.replace('File:', '').replace('_', ' ')
                        pool.append({
                            'title': title_clean,
                            'url': u,
                            'keywords': clean_words(title_clean)
                        })
    except Exception as e:
        print(f"Error fetching Commons pool: {e}")
    return pool


def fetch_authentic_article_media_pool(topic_title: str) -> List[Dict[str, Any]]:
    """
    Fetches all authentic photos embedded on the primary Wikipedia article,
    and combines with Wikimedia Commons deep search for maximum unique coverage (50+ assets).
    """
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    media_pool = []
    seen_urls = set()

    try:
        # Step 1: Query images directly embedded on the article
        img_query_url = (
            "https://en.wikipedia.org/w/api.php?action=query"
            f"&titles={urllib.parse.quote(topic_title)}"
            "&prop=images&imlimit=50&format=json"
        )
        req = urllib.request.Request(img_query_url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            pages = data.get('query', {}).get('pages', {})
            image_titles = []
            for k, p in pages.items():
                for im in p.get('images', []):
                    t = im.get('title', '')
                    t_lower = t.lower()
                    if not any(j in t_lower for j in JUNK_IMAGE_PATTERNS):
                        image_titles.append(t)

        # Step 2: Fetch 1080px thumbnail URLs for article images
        if image_titles:
            batch = image_titles[:35]
            pipe_titles = '|'.join(batch)
            res_url = (
                "https://en.wikipedia.org/w/api.php?action=query"
                f"&titles={urllib.parse.quote(pipe_titles)}"
                "&prop=imageinfo&iiprop=url|size|mime&iiurlwidth=1080&format=json"
            )
            req2 = urllib.request.Request(res_url, headers=headers)
            with urllib.request.urlopen(req2, timeout=8) as resp2:
                r_data = json.loads(resp2.read().decode('utf-8'))
                for k, p in r_data.get('query', {}).get('pages', {}).items():
                    infos = p.get('imageinfo', [])
                    if infos:
                        info = infos[0]
                        u = info.get('thumburl') or info.get('url')
                        title_clean = p.get('title', '').replace('File:', '').replace('_', ' ')
                        if u and u not in seen_urls:
                            seen_urls.add(u)
                            media_pool.append({
                                'title': title_clean,
                                'url': u,
                                'keywords': clean_words(title_clean)
                            })
    except Exception as e:
        print(f"Error fetching article media pool: {e}")

    # Step 3: Deep augment with Wikimedia Commons archive for this topic (provides 30-40+ more images)
    commons_items = fetch_commons_media_pool(topic_title, limit=35)
    for ci in commons_items:
        if ci['url'] not in seen_urls:
            seen_urls.add(ci['url'])
            media_pool.append(ci)

    # Step 4: Fallback search if still fewer than 20
    if len(media_pool) < 20:
        try:
            extra_url = (
                "https://en.wikipedia.org/w/api.php?action=query"
                f"&generator=search&gsrsearch={urllib.parse.quote(topic_title)}"
                "&prop=pageimages&pithumbsize=1080&format=json&gsrlimit=15"
            )
            req3 = urllib.request.Request(extra_url, headers=headers)
            with urllib.request.urlopen(req3, timeout=6) as resp3:
                s_data = json.loads(resp3.read().decode('utf-8'))
                for k, p in s_data.get('query', {}).get('pages', {}).items():
                    thumb = p.get('thumbnail', {}).get('source')
                    t_title = p.get('title', '')
                    if thumb and thumb not in seen_urls:
                        seen_urls.add(thumb)
                        media_pool.append({
                            'title': t_title,
                            'url': thumb,
                            'keywords': clean_words(t_title)
                        })
        except Exception:
            pass

    return media_pool


def search_targeted_scene_image(query: str, exclude_urls: Set[str]) -> Optional[Dict[str, Any]]:
    """Search Wikimedia Commons for a specific scene's phrase if pool is depleted."""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        clean_q = " ".join(clean_words(query)[:4])
        if not clean_q:
            clean_q = query[:30]
        url = (
            "https://commons.wikimedia.org/w/api.php?action=query"
            f"&generator=search&gsrsearch={urllib.parse.quote(clean_q)}"
            "&gsrnamespace=6&gsrlimit=10"
            "&prop=imageinfo&iiprop=url|size|mime&iiurlwidth=1080&format=json"
        )
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            for k, p in data.get('query', {}).get('pages', {}).items():
                title = p.get('title', '')
                t_lower = title.lower()
                if any(j in t_lower for j in JUNK_IMAGE_PATTERNS):
                    continue
                infos = p.get('imageinfo', [])
                if infos:
                    info = infos[0]
                    mime = info.get('mime', '').lower()
                    if not any(m in mime for m in ['jpeg', 'jpg', 'png', 'webp']):
                        continue
                    u = info.get('thumburl') or info.get('url')
                    if u and u not in exclude_urls:
                        clean_t = title.replace('File:', '').replace('_', ' ')
                        return {
                            'title': clean_t,
                            'url': u,
                            'keywords': clean_words(clean_t)
                        }
    except Exception:
        pass
    return None


def download_image_file(img_url: str, save_path: str, max_retries: int = 3) -> bool:
    """Download image to disk with browser User-Agent and automatic retries."""
    # If already a local file path
    if os.path.exists(img_url):
        shutil.copyfile(img_url, save_path)
        return True

    # If relative path in outputs
    if img_url.startswith("/outputs/") or img_url.startswith("outputs/"):
        local_src = img_url.lstrip("/")
        if os.path.exists(local_src):
            shutil.copyfile(local_src, save_path)
            return True

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    }
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(img_url, headers=headers)
            with urllib.request.urlopen(req, timeout=12) as resp:
                content = resp.read()
                if len(content) > 2000:
                    os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
                    with open(save_path, 'wb') as f:
                        f.write(content)
                    return True
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(0.6 * (attempt + 1))
            else:
                print(f"Failed to download {img_url} after {max_retries} attempts: {e}")
    return False


def create_ken_burns_motion_clip(
    image_path: str,
    duration: float,
    output_path: str,
    motion_index: int = 0
) -> bool:
    """
    Turns an image into a 1080x1920 9:16 vertical video with continuous cinematic motion:
      0: Dynamic Center Push (Zoom-in from 1.0 to 1.25)
      1: Dramatic Reveal Pull-Out (Zoom-out from 1.25 to 1.0)
      2: Horizontal Pan-Right + Zoom (Glides from left to right)
      3: Horizontal Pan-Left + Zoom (Glides from right to left)
      4: Vertical Tilt-Up + Zoom (Glides upwards)
    """
    total_frames = max(15, int(duration * 30))
    d_str = str(total_frames)
    m_type = motion_index % 5

    if m_type == 0:
        zoom_expr = "min(zoom+0.0022,1.25)"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif m_type == 1:
        zoom_expr = "max(1.25-0.0022*on,1.0)"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif m_type == 2:
        zoom_expr = "min(zoom+0.0015,1.20)"
        x_expr = f"(iw-iw/zoom)*(on/{d_str})"
        y_expr = "ih/2-(ih/zoom/2)"
    elif m_type == 3:
        zoom_expr = "min(zoom+0.0015,1.20)"
        x_expr = f"(iw-iw/zoom)*(1-on/{d_str})"
        y_expr = "ih/2-(ih/zoom/2)"
    else:
        zoom_expr = "min(zoom+0.0016,1.22)"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = f"(ih-ih/zoom)*(1-on/{d_str})"

    vf = (
        f"scale=1080:1920:force_original_aspect_ratio=increase,"
        f"crop=1080:1920,"
        f"zoompan=z='{zoom_expr}':d={d_str}:x='{x_expr}':y='{y_expr}':s=1080x1920:fps=30,"
        f"eq=contrast=1.06:saturation=1.12,"
        f"format=yuv420p"
    )

    cmd = [
        FFMPEG_EXE, "-y",
        "-loop", "1",
        "-i", os.path.abspath(image_path),
        "-vf", vf,
        "-t", f"{duration:.2f}",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-threads", "4",
        "-crf", "22",
        os.path.abspath(output_path)
    ]

    res = subprocess.run(cmd, capture_output=True)
    return res.returncode == 0 and os.path.exists(output_path)


def create_visual_beats(script_text: str, total_duration: float, min_dur: float = 1.8, max_dur: float = 2.6) -> List[Tuple[str, float]]:
    """
    Divides the script into natural 1.8s - 2.5s spoken visual beats.
    Maintains rapid pacing while respecting clause boundaries.
    """
    raw_tokens = [p.strip() for p in re.split(r'([,.!?;:\n]+)', script_text) if p.strip()]
    phrases = []
    i = 0
    while i < len(raw_tokens):
        item = raw_tokens[i]
        if i + 1 < len(raw_tokens) and re.match(r'^[,.!?;:\n]+$', raw_tokens[i+1]):
            phrases.append(item + raw_tokens[i+1])
            i += 2
        else:
            phrases.append(item)
            i += 1

    total_words = sum(max(1, len(p.split())) for p in phrases)
    beats: List[Tuple[str, float]] = []
    curr_words: List[str] = []

    for phrase in phrases:
        p_words = phrase.split()
        if len(p_words) > 7:
            for j in range(0, len(p_words), 6):
                sub = p_words[j:j+6]
                if sub:
                    curr_words.extend(sub)
                    est_dur = (len(curr_words) / total_words) * total_duration
                    if est_dur >= min_dur:
                        beats.append((" ".join(curr_words), est_dur))
                        curr_words = []
        else:
            curr_words.extend(p_words)
            est_dur = (len(curr_words) / total_words) * total_duration
            if est_dur >= min_dur:
                beats.append((" ".join(curr_words), est_dur))
                curr_words = []

    if curr_words:
        if beats:
            last_text, last_dur = beats[-1]
            extra_dur = (len(curr_words) / total_words) * total_duration
            if extra_dur < 1.2:
                beats[-1] = (f"{last_text} {' '.join(curr_words)}", last_dur + extra_dur)
            else:
                beats.append((" ".join(curr_words), extra_dur))
        else:
            beats.append((" ".join(curr_words), total_duration))

    # Normalize durations so sum equals total_duration exactly
    sum_durs = sum(d for _, d in beats)
    beats = [(t, (d / sum_durs) * total_duration) for t, d in beats]
    return beats


def score_media_for_scene(scene_text: str, media: Dict[str, Any]) -> float:
    """Scores how well an authentic image matches a spoken scene beat."""
    scene_words = clean_words(scene_text)
    s_lower = scene_text.lower()
    t_lower = media['title'].lower()

    score = sum(2 for w in scene_words if w in media['keywords'])

    # Penalize debris/wreckage images if the scene does NOT mention debris/wreckage
    is_debris_image = any(k in t_lower for k in ['flaperon', 'debris', 'wreckage', 'part no'])
    is_debris_scene = any(k in s_lower for k in ['debris', 'wreckage', 'found', 'signal', 'piece', 'part', 'remains'])
    if is_debris_image and not is_debris_scene:
        score -= 25
    elif is_debris_image and is_debris_scene:
        score += 20

    # Radar and tracking
    if any(k in s_lower for k in ['radar', 'military radar', 'detected']):
        if 'radar' in t_lower:
            score += 25
        elif any(k in t_lower for k in ['atc', 'route', 'path']):
            score += 10

    # Flight course / turning off course / transponder
    if any(k in s_lower for k in ['course', 'turning', 'transponder', 'dark', 'silence']):
        if any(k in t_lower for k in ['route', 'path', 'air routes', 'atc', 'flight path']):
            score += 15

    # Takeoff, departure, flight
    if any(k in s_lower for k in ['took off', 'take off', 'heading', 'kuala', 'beijing', 'passengers']):
        if any(k in t_lower for k in ['scheduled flight', 'routes', 'plane', 'airlines', 'boeing']):
            score += 12

    # Search operations and ocean
    if any(k in s_lower for k in ['search', 'expensive', 'history', 'naval']):
        if any(k in t_lower for k in ['ocean shield', 'bluefin', 'underwater', 'poseidon', 'search', 'orion']):
            score += 20
    if any(k in s_lower for k in ['ocean', 'indian ocean', 'miles', 'spanning']):
        if any(k in t_lower for k in ['sio search', 'indian ocean gyre', 'underwater search']):
            score += 18

    # Mystery / unsolved / vanished / trace
    if any(k in s_lower for k in ['mystery', 'unsolved', 'vanished', 'trace', 'happened']):
        if any(k in t_lower for k in ['heat map', 'inmarsat', 'hope and pray', 'initial search', 'probability']):
            score += 15

    return score


def prepare_scenes_data(
    script_text: str,
    total_duration: float,
    target_cut_duration: float = 2.2,
    scene_overrides: Optional[Dict[str, str]] = None
) -> List[Dict[str, Any]]:
    """
    Analyzes script, builds authentic topic media pool, and prepares
    all scenes with assigned images and timestamps for the frontend storyboard.
    """
    primary_topic = find_primary_wikipedia_topic(script_text)
    media_pool = fetch_authentic_article_media_pool(primary_topic)
    beats = create_visual_beats(script_text, total_duration, min_dur=1.8, max_dur=2.6)

    used_urls: Set[str] = set()
    result_scenes = []
    current_time = 0.0

    if scene_overrides is None:
        scene_overrides = {}

    for idx, (scene_text, dur) in enumerate(beats):
        override_key = str(idx)
        override_val = scene_overrides.get(override_key) or scene_overrides.get(idx)

        best_media = None
        is_custom = False

        if override_val:
            # User provided a custom image or URL
            is_custom = True
            img_url = override_val
            img_title = os.path.basename(override_val)
        else:
            # Match from media pool
            best_score = -999
            for m in media_pool:
                if m['url'] in used_urls:
                    continue
                score = score_media_for_scene(scene_text, m)
                if score > best_score:
                    best_score = score
                    best_media = m

            # If no match from pool or pool exhausted, query Commons for this scene
            if not best_media:
                best_media = search_targeted_scene_image(f"{primary_topic} {scene_text}", used_urls)

            # Fallback to next unused item
            if not best_media:
                for m in media_pool:
                    if m['url'] not in used_urls:
                        best_media = m
                        break

            if best_media:
                used_urls.add(best_media['url'])
                img_url = best_media['url']
                img_title = best_media['title']
            else:
                img_url = "https://images.unsplash.com/photo-1506744038136-46273834b3fb?w=1080"
                img_title = "Cinematic Visual"

        result_scenes.append({
            "scene_id": idx,
            "start_time": round(current_time, 2),
            "end_time": round(current_time + dur, 2),
            "duration": round(dur, 2),
            "text": scene_text,
            "image_url": img_url,
            "image_title": img_title,
            "is_custom": is_custom
        })
        current_time += dur

    return result_scenes


def generate_smart_broll_video(
    script_text: str,
    total_duration: float,
    output_path: str,
    temp_dir: str,
    target_cut_duration: float = 2.2,
    scene_overrides: Optional[Dict[str, str]] = None,
    preview_scenes: Optional[List[Dict[str, Any]]] = None
) -> str:
    """
    Generates an authentic documentary b-roll video:
    If preview_scenes is provided, it uses the exact previewed images that the user approved,
    scaling their durations to fit total_duration without re-querying or generating new images.
    Otherwise, it runs prepare_scenes_data to match authentic media.
    """
    os.makedirs(temp_dir, exist_ok=True)

    if preview_scenes and len(preview_scenes) > 0:
        print(f"[Smart B-Roll] Using {len(preview_scenes)} user-previewed scenes directly (locking in approved visuals)!")
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
        scenes_data = prepare_scenes_data(
            script_text=script_text,
            total_duration=total_duration,
            target_cut_duration=target_cut_duration,
            scene_overrides=scene_overrides
        )

    print(f"[Smart B-Roll] Rendering {len(scenes_data)} unique visual scenes (Total: {total_duration:.1f}s)")
    scene_clips: List[str] = []

    for idx, sc in enumerate(scenes_data):
        img_path = os.path.join(temp_dir, f"scene_{idx}.jpg")
        clip_path = os.path.join(temp_dir, f"scene_clip_{idx}.mp4")
        dur = sc["duration"]

        clean_t = sc.get('image_title', '').encode('ascii', 'replace').decode('ascii')
        clean_txt = sc.get('text', '')[:30].encode('ascii', 'replace').decode('ascii')
        print(f"[Scene {idx+1}/{len(scenes_data)}] ({dur:.1f}s) \"{clean_txt}...\" -> {clean_t}")
        ok = download_image_file(sc["image_url"], img_path)
        if ok and os.path.exists(img_path):
            motion_ok = create_ken_burns_motion_clip(
                image_path=img_path,
                duration=dur,
                output_path=clip_path,
                motion_index=idx
            )
            if motion_ok and os.path.exists(clip_path):
                scene_clips.append(clip_path)

    # Concatenate all authentic scene clips into master track
    if scene_clips:
        concat_list_file = os.path.join(temp_dir, "concat_scenes.txt")
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

    # Ultimate failsafe: create a clean dark cinematic canvas
    fallback_cmd = [
        FFMPEG_EXE, "-y",
        "-f", "lavfi",
        "-i", f"color=c=0x0a0c16:s=1080x1920:r=30:d={total_duration}",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-pix_fmt", "yuv420p",
        os.path.abspath(output_path)
    ]
    subprocess.run(fallback_cmd, capture_output=True)
    return output_path
