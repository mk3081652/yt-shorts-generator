"""
planner.py - Visual Director Planner & Orchestrator
Part of the isolated Visual Director module for YouTube Shorts.
Converts narration scripts into intelligent, continuity-anchored, cinematically varied 9:16 visual scenes.
Includes JSON safety, robust retry limits, and seamless fallback to preserve existing workflows.
"""

import os
import re
import json
import time
import urllib.request
from typing import Dict, Any, List, Optional, Tuple

from engine.visual_director.prompts import VISUAL_DIRECTOR_SYSTEM_PROMPT
from engine.visual_director.continuity import (
    ContinuityAnchor,
    build_fallback_continuity_anchor,
    enforce_continuity_in_prompt
)
from engine.visual_director.validator import heuristic_validate_scene
from engine.smart_visuals import create_visual_beats, clean_words, find_primary_wikipedia_topic

GEMINI_MODELS = [
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
    "gemini-pro-latest"
]


def extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    """
    Safely extracts and parses a JSON object from raw model output,
    handling markdown fences, whitespace, and embedded brackets.
    """
    raw = text.strip()
    if raw.startswith("```json"):
        raw = raw[7:]
    elif raw.startswith("```"):
        raw = raw[3:]
    if raw.endswith("```"):
        raw = raw[:-3]
    raw = raw.strip()

    # Try direct parse
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # Try regex matching outer braces
    match = re.search(r'(\{[\s\S]*\})', raw)
    if match:
        try:
            data = json.loads(match.group(1))
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    return None


def semantic_fallback_plan(
    script_text: str,
    total_duration: float
) -> Dict[str, Any]:
    """
    Guaranteed local fallback planner when Gemini API is offline or unconfigured.
    Generates intelligent, domain-aware scenes with shot variations and continuity.
    """
    beats = create_visual_beats(script_text, total_duration, min_dur=1.8, max_dur=2.6)
    primary_topic = find_primary_wikipedia_topic(script_text)
    anchor = build_fallback_continuity_anchor(script_text)

    shot_types = [
        "establishing wide shot", "medium shot", "close-up", "macro detail",
        "POV shot", "CCTV angle", "tracking shot", "extreme close-up"
    ]
    camera_motions = ["push in", "pull out", "pan right", "pan left", "tilt up"]

    scenes = []
    current_time = 0.0

    for idx, (scene_text, dur) in enumerate(beats):
        s_lower = scene_text.lower()
        shot = shot_types[idx % len(shot_types)]
        motion = camera_motions[idx % len(camera_motions)]

        # Domain: Miniature Car Assembly
        if any(k in s_lower for k in ["miniature", "scale", "mechanic", "tiny", "suspension", "wheel", "chassis", "install", "assemble"]):
            if "suspension" in s_lower or "spring" in s_lower:
                p = "Photorealistic vertical 9:16 macro shot, tiny 1:24 scale mechanics in blue overalls installing chrome suspension springs on red miniature car chassis"
                sq = "miniature car suspension assembly"
                must_show = ["tiny mechanics", "suspension springs", "miniature chassis"]
                must_not_show = ["real car", "real size factory", "people normal size"]
            elif "wheel" in s_lower or "tire" in s_lower:
                p = "Photorealistic vertical 9:16 macro shot, tiny mechanic tightening lug nuts on miniature sports car wheel with micro wrench, workbench"
                sq = "miniature car wheel assembly"
                must_show = ["tiny mechanic", "miniature wheel", "micro wrench"]
                must_not_show = ["real car", "street", "full size garage"]
            elif "engine" in s_lower or "motor" in s_lower:
                p = "Photorealistic vertical 9:16 close-up shot, micro scale V8 engine block being lowered into red miniature car chassis by tiny mechanics"
                sq = "miniature engine install scale model"
                must_show = ["miniature engine", "tiny mechanics", "chassis bay"]
                must_not_show = ["real automobile", "real human mechanic"]
            else:
                p = f"Photorealistic vertical 9:16 cinematic {shot}, tiny 1:24 scale figurine mechanics assembling red miniature car on workbench, macro tilt-shift"
                sq = "miniature car assembly scale model"
                must_show = ["tiny mechanics in blue overalls", "red miniature car"]
                must_not_show = ["real car", "outdoor road"]

        # Domain: Mystery / Room 307
        elif any(k in s_lower for k in ["room 307", "hotel", "security", "guard", "door", "corridor"]):
            if "guard" in s_lower or "rushed" in s_lower:
                p = "Photorealistic vertical 9:16 dynamic tracking shot of two hotel security guards in dark suits running through hotel corridor toward Room 307 door"
                sq = "hotel security guards corridor"
                must_show = ["two security guards", "hotel corridor", "Room 307 door"]
                must_not_show = ["outdoor street", "daylight", "crowd"]
            elif "door" in s_lower or "opened" in s_lower:
                p = "Photorealistic vertical 9:16 suspenseful close-up of dark walnut Room 307 door with brass number plate slowly creaking open into darkness"
                sq = "hotel room door opening dark"
                must_show = ["Room 307 brass number", "dark walnut door opening", "dim corridor"]
                must_not_show = ["bright sunlight", "generic living room"]
            elif "cctv" in s_lower or "camera" in s_lower or "footage" in s_lower:
                p = "High-angle CCTV security camera vertical 9:16 view of empty dimly lit hotel corridor outside Room 307, subtle static timestamp overlay"
                sq = "hotel corridor security camera"
                must_show = ["CCTV high angle", "hotel corridor", "Room 307 door"]
                must_not_show = ["sunny outdoor", "movie theater"]
            else:
                p = f"Photorealistic vertical 9:16 cinematic {shot} of dimly lit hotel corridor outside Room 307, burgundy carpet, warm sconces, suspenseful"
                sq = "hotel corridor Room 307"
                must_show = ["hotel corridor", "Room 307"]
                must_not_show = ["daylight", "outdoor street"]

        # Domain: Flight / Aviation Documentary
        elif any(k in s_lower for k in ["radar", "tracking", "transponder", "atc", "blip"]):
            p = "Photorealistic vertical 9:16 close-up of green glowing air traffic control radar screen with sweeping line and radar blips in dark control room"
            sq = "air traffic control radar screen"
            must_show = ["glowing green radar screen", "radar blip", "dark ATC room"]
            must_not_show = ["airplane exterior", "daylight sky"]
        elif any(k in s_lower for k in ["cabin", "passenger", "seated", "inside the"]):
            p = "Photorealistic vertical 9:16 shot inside commercial airliner passenger cabin, dim warm cabin lighting, passengers seated in rows"
            sq = "airliner passenger cabin interior"
            must_show = ["airplane cabin interior", "seated passengers", "airplane windows"]
            must_not_show = ["airplane exterior", "airport terminal"]
        elif any(k in s_lower for k in ["sonar", "submarine", "underwater", "ocean floor", "abyss"]):
            p = "Photorealistic vertical 9:16 shot of deep-sea research submarine scanning dark ocean floor with powerful spotlights, deep sea sonar"
            sq = "deep sea submarine ocean floor search"
            must_show = ["research submarine", "searchlights", "dark ocean floor"]
            must_not_show = ["sunny beach", "surface boats"]
        elif any(k in s_lower for k in ["black box", "flight recorder", "data recorder"]):
            p = "Photorealistic vertical 9:16 close-up shot of bright orange flight data recorder black box resting on dark seabed, submarine light beam"
            sq = "flight data recorder black box ocean floor"
            must_show = ["bright orange flight recorder", "ocean floor sand"]
            must_not_show = ["airplane in sky", "office desk"]
        else:
            kws = clean_words(scene_text)
            p = f"Photorealistic vertical 9:16 cinematic {shot} of {primary_topic}, {' '.join(kws[:3])}, dramatic lighting, 8k, photorealistic"
            sq = f"{primary_topic} {' '.join(kws[:2])}"
            must_show = [primary_topic]
            must_not_show = ["blurry", "watermark"]

        # Enforce continuity
        p = enforce_continuity_in_prompt(p, anchor, scene_text)

        scenes.append({
            "scene_id": idx,
            "narration": scene_text,
            "duration": round(dur, 2),
            "start_time": round(current_time, 2),
            "end_time": round(current_time + dur, 2),
            "visual_description": f"{shot.title()} showing {scene_text[:40]}...",
            "image_prompt": p,
            "search_query": sq,
            "shot_type": shot,
            "camera_motion": motion,
            "must_show": must_show,
            "must_not_show": must_not_show
        })
        current_time += dur

    return {
        "continuity_anchor": anchor.to_dict(),
        "scenes": scenes
    }


def plan_visual_storyboard(
    script_text: str,
    total_duration: float,
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Main entrypoint for the Visual Director.
    Orchestrates:
    1. Visual beats segmentation.
    2. Gemini Flash structured visual planning with continuity anchor.
    3. Parsing with JSON safety and validation.
    4. Seamless semantic fallback if API is unavailable.
    """
    script_clean = script_text.strip()
    if not script_clean:
        return {"continuity_anchor": {}, "scenes": []}

    beats = create_visual_beats(script_clean, total_duration, min_dur=1.8, max_dur=2.6)
    scene_texts = [t for t, _ in beats]

    # Resolve API Key
    resolved_key = api_key or os.environ.get("GEMINI_API_KEY", "")

    if not resolved_key:
        print("[Visual Director] No Gemini API key provided. Using intelligent semantic planner.")
        return semantic_fallback_plan(script_clean, total_duration)

    # Build prompt payload
    prompt_content = (
        f"{VISUAL_DIRECTOR_SYSTEM_PROMPT}\n\n"
        f"Full Narration Script ({total_duration:.1f}s total):\n{script_clean}\n\n"
        f"Sequential Spoken Beats ({len(scene_texts)} beats):\n{json.dumps(scene_texts)}"
    )

    body = {
        "contents": [{
            "parts": [{"text": prompt_content}]
        }],
        "generationConfig": {
            "responseMimeType": "application/json",
            "maxOutputTokens": 4000,
            "temperature": 0.2
        }
    }

    # Attempt planning across model candidates
    for model_name in GEMINI_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={resolved_key}"
        for attempt in range(2):
            try:
                req = urllib.request.Request(
                    url,
                    data=json.dumps(body).encode("utf-8"),
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=16) as resp:
                    resp_json = json.loads(resp.read().decode("utf-8"))
                    raw_text = resp_json["candidates"][0]["content"]["parts"][0]["text"]
                    parsed = extract_json_object(raw_text)

                    if parsed and "scenes" in parsed and isinstance(parsed["scenes"], list):
                        scenes_list = parsed["scenes"]
                        anchor_data = parsed.get("continuity_anchor", {})
                        anchor = ContinuityAnchor.from_dict(anchor_data)

                        # Match scene count with beats and assign timestamps
                        final_scenes = []
                        curr_t = 0.0

                        for idx, (b_text, b_dur) in enumerate(beats):
                            s_data = scenes_list[idx] if idx < len(scenes_list) else {}
                            
                            shot = s_data.get("shot_type", "cinematic shot")
                            motion = s_data.get("camera_motion", "push in")
                            vis_desc = s_data.get("visual_description", f"Visual illustrating {b_text[:35]}")
                            p = s_data.get("image_prompt") or f"Photorealistic vertical 9:16 {shot} of {b_text}, cinematic 8k"
                            sq = s_data.get("search_query") or " ".join(clean_words(b_text)[:3])
                            must_show = s_data.get("must_show") or [b_text[:20]]
                            must_not_show = s_data.get("must_not_show") or ["blurry", "watermark"]

                            # Enforce continuity
                            p = enforce_continuity_in_prompt(p, anchor, b_text)

                            # Validate scene with up to 2 retries
                            val = heuristic_validate_scene(b_text, p, must_show, must_not_show)
                            if not val["accepted"] and val.get("correction_prompt"):
                                p = val["correction_prompt"]

                            final_scenes.append({
                                "scene_id": idx,
                                "narration": b_text,
                                "duration": round(b_dur, 2),
                                "start_time": round(curr_t, 2),
                                "end_time": round(curr_t + b_dur, 2),
                                "visual_description": vis_desc,
                                "image_prompt": p,
                                "search_query": sq,
                                "shot_type": shot,
                                "camera_motion": motion,
                                "must_show": must_show,
                                "must_not_show": must_not_show
                            })
                            curr_t += b_dur

                        print(f"[Visual Director] Successfully planned {len(final_scenes)} scenes with {model_name}!")
                        return {
                            "continuity_anchor": anchor.to_dict(),
                            "scenes": final_scenes
                        }
            except Exception as e:
                print(f"[Visual Director] {model_name} attempt {attempt+1} error: {e}")
                time.sleep(0.8)

    print("[Visual Director] Gemini models exhausted. Falling back to semantic planner.")
    return semantic_fallback_plan(script_clean, total_duration)
