import os
import sys
import re
import time
import json
import shutil
import base64
import hashlib
import urllib.request
import urllib.parse
import subprocess
import imageio_ffmpeg
from typing import List, Dict, Any, Set, Tuple, Optional

# Enforce UTF-8 console output on Windows to prevent UnicodeEncodeError with web image titles
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

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

from engine.smart_visuals import (
    create_visual_beats,
    create_ken_burns_motion_clip,
    download_image_file
)

# Canonical visual generation and curated assets imported from generator
from engine.visual_director.generator import (
    CURATED_SCENE_ASSETS,
    get_instant_curated_visual,
    generate_cloudflare_flux_image,
    generate_pollinations_image,
    single_visual_attempt
)


def generate_scene_image_multi_tier(
    prompt: str,
    search_query: str,
    output_path: str,
    primary_topic: str = "",
    exclude_urls: Optional[Set[str]] = None,
    scene_text: str = ""
) -> bool:
    """Canonical multi-tier visual generator delegating to single_visual_attempt."""
    return single_visual_attempt(
        prompt=prompt,
        search_query=search_query,
        output_path=output_path,
        scene_text=scene_text
    )



# In-memory cache for full storyboard plans keyed by script text hash
_STORYBOARD_PLAN_CACHE: Dict[str, Dict[str, Any]] = {}

# TODO (TTS-Timestamp Sync Boundary):
# Running engine/tts.py's generate_speech_with_words() during /api/prepare_scenes (before image generation)
# would require receiving the user's voice selection, rate, and pitch—which are selected downstream in the UI.
# Furthermore, executing TTS at prepare_scenes time would double network TTS latency, synthesize redundant audio
# files before the user confirms or edits the script, and exceed the strict 512MB RAM limit on Render during
# concurrent image fetches. Therefore, the word-count duration estimate is safely maintained for scene planning,
# and real word-boundary timestamps are synchronized when /api/generate_short is triggered.

def prepare_gemini_scenes_data(
    script_text: str,
    total_duration: float,
    target_cut_duration: float = 2.2,
    scene_overrides: Optional[Dict[str, str]] = None,
    api_key: Optional[str] = None,
    force_refresh: bool = False,
    call_stats: Optional[Dict[str, int]] = None
) -> List[Dict[str, Any]]:
    """
    Prepares scenes for the visual storyboard using the new Visual Director pipeline.
    Flow:
      Script -> Story Analysis -> Continuity Bible -> Visual Beats -> Visual Plan ->
      Exact Prompts -> Generate/Search -> Relevance Validation (score >= 80, max 2 retries) ->
      Best-Image Selection -> Output Scenes.
    Preserves manual overrides with source: "manual".
    """
    from engine.visual_director import plan_visual_storyboard, generate_validated_scenes

    script_clean = script_text.strip()
    script_hash = hashlib.sha256(script_clean.encode("utf-8")).hexdigest()[:16]

    if not force_refresh and script_hash in _STORYBOARD_PLAN_CACHE:
        print(f"[Visual Director] Using cached visual storyboard plan for hash {script_hash}")
        plan = json.loads(json.dumps(_STORYBOARD_PLAN_CACHE[script_hash]))
    else:
        print(f"[Visual Director] Planning visual storyboard for {total_duration:.1f}s script...")
        plan = plan_visual_storyboard(script_clean, total_duration, api_key=api_key, call_stats=call_stats)
        _STORYBOARD_PLAN_CACHE[script_hash] = plan

    scenes = plan.get("scenes", [])
    continuity_bible = plan.get("continuity_bible", {})

    has_cf = bool(os.environ.get("CLOUDFLARE_ACCOUNT_ID") and os.environ.get("CLOUDFLARE_API_TOKEN"))
    generation_mode = "ai_flux_primary" if has_cf else "ai_primary"

    print(f"[Visual Director] Generating and validating {len(scenes)} scenes (Mode: {generation_mode})...")
    validated = generate_validated_scenes(
        planned_scenes=scenes,
        output_dir="outputs/ai_previews",
        continuity_bible=continuity_bible,
        scene_overrides=scene_overrides,
        api_key=api_key,
        generation_mode=generation_mode,
        call_stats=call_stats
    )

    result_scenes = []
    for sc in validated:
        result_scenes.append({
            "scene_id": sc.get("scene_id"),
            "start_time": sc.get("start_time"),
            "end_time": sc.get("end_time"),
            "duration": sc.get("duration"),
            "text": sc.get("narration", sc.get("text", "")),
            "narration": sc.get("narration", sc.get("text", "")),
            "image_url": sc.get("image_url"),
            "image_title": sc.get("visual_description", "")[:35] or f"{sc.get('shot_type', 'Shot').title()}",
            "search_query": sc.get("search_query", ""),
            "prompt": sc.get("image_prompt") or sc.get("prompt", ""),
            "image_prompt": sc.get("image_prompt") or sc.get("prompt", ""),
            "is_custom": sc.get("is_custom", False),
            "source": sc.get("source", "generated"),
            "source_tier": sc.get("source_tier", "ai_primary"),
            "validation_score": sc.get("validation_score", 85),
            "shot_type": sc.get("shot_type", "cinematic"),
            "camera_motion": sc.get("camera_motion", "push in"),
            "must_show": sc.get("must_show", []),
            "must_not_show": sc.get("must_not_show", []),
            "visual_description": sc.get("visual_description", "")
        })

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
    Visual Director AI B-Roll rendering pipeline:
    - If preview_scenes is provided, directly uses the exact user-approved visuals.
    - Otherwise, plans, generates, and validates scenes with the Visual Director.
    - Renders Ken Burns continuous camera motion per scene.
    - Concatenates into 1080x1920 vertical video.
    """
    os.makedirs(temp_dir, exist_ok=True)

    if preview_scenes and len(preview_scenes) > 0:
        print(f"[Visual Director] Using {len(preview_scenes)} approved preview scenes directly.")
        total_p_dur = sum(float(s.get("duration", 2.0)) for s in preview_scenes)
        scale = (total_duration / total_p_dur) if total_p_dur > 0 else 1.0
        scenes_data = []
        curr_t = 0.0
        for s in preview_scenes:
            dur = max(0.8, round(float(s.get("duration", 2.0)) * scale, 2))
            scenes_data.append({
                "scene_id": s.get("scene_id", 0),
                "text": s.get("text", s.get("narration", "")),
                "image_url": s.get("image_url", ""),
                "duration": dur,
                "start_time": round(curr_t, 2),
                "end_time": round(curr_t + dur, 2),
                "is_custom": True,
                "source": s.get("source", "manual")
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

    print(f"[Visual Director] Rendering {len(scenes_data)} scenes (Total: {total_duration:.1f}s)")
    scene_clips: List[str] = []

    for idx, sc in enumerate(scenes_data):
        img_path = os.path.join(temp_dir, f"ai_scene_{idx}.jpg")
        clip_path = os.path.join(temp_dir, f"ai_scene_clip_{idx}.mp4")
        dur = sc["duration"]

        clean_sc_text = sc.get('text', '')[:30].encode('ascii', 'replace').decode('ascii')
        print(f"[Scene {idx+1}/{len(scenes_data)}] ({dur:.1f}s) \"{clean_sc_text}...\"")

        ok = False
        # 1. Custom or preview image from local outputs
        if sc.get("image_url") and (sc["image_url"].startswith("/outputs/") or sc["image_url"].startswith("outputs/")):
            local_src = sc["image_url"].lstrip("/")
            if os.path.exists(local_src) and os.path.getsize(local_src) > 5000:
                shutil.copyfile(local_src, img_path)
                ok = True

        # 2. Remote URL download
        if not ok and sc.get("image_url") and "pollinations.ai" not in sc.get("image_url", ""):
            ok = download_image_file(sc["image_url"], img_path)

        # 3. Generate multi-tier if still needed
        if not ok:
            from engine.visual_director.generator import single_visual_attempt
            prompt_to_use = sc.get("prompt") or sc.get("image_prompt") or sc.get("text", "")
            sq_to_use = sc.get("search_query", "")
            ok = single_visual_attempt(prompt_to_use, sq_to_use, img_path, scene_text=sc.get("text", ""))

        # 4. Ultimate failsafe: clean dark cinematic canvas for this cut
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

    # Render Ken Burns motion clips sequentially to stay strictly within 512MB RAM limit on Render
    for idx, sc in enumerate(scenes_data):
        img_p = os.path.join(temp_dir, f"ai_scene_{idx}.jpg")
        clip_p = os.path.join(temp_dir, f"ai_scene_clip_{idx}.mp4")
        dur = sc["duration"]
        if not os.path.exists(clip_p) and os.path.exists(img_p):
            create_ken_burns_motion_clip(
                image_path=img_p,
                duration=dur,
                output_path=clip_p,
                motion_index=idx
            )
        if os.path.exists(clip_p):
            scene_clips.append(clip_p)

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

    # Failsafe: dark cinematic canvas
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
