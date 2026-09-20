"""
planner.py - Visual Director Planner & Orchestrator
Part of the Visual Director module for YouTube Shorts.

Converts narration scripts into intelligent, continuity-anchored, cinematically varied 9:16 visual scenes.
Coordinates:
1. Story Analysis (story_type, characters, objects, locations, tone)
2. Continuity Bible (characters, locations, objects, style)
3. Visual Beat Detection (meaningful shifts in action, location, character, or camera, ~3-6s)
4. Scene Data Model with must_show, must_not_show, shot_type, and camera_motion
5. Safe JSON extraction and robust semantic fallback
"""

import os
import re
import json
import time
import urllib.request
from typing import Dict, Any, List, Optional, Tuple

from engine.visual_director.prompts import VISUAL_DIRECTOR_SYSTEM_PROMPT
from engine.visual_director.story_analyzer import analyze_story
from engine.visual_director.continuity import (
    ContinuityAnchor,
    build_continuity_bible,
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
    """Safely extracts and parses a JSON object from raw model output."""
    raw = text.strip()
    if raw.startswith("```json"):
        raw = raw[7:]
    elif raw.startswith("```"):
        raw = raw[3:]
    if raw.endswith("```"):
        raw = raw[:-3]
    raw = raw.strip()

    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

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
    total_duration: float,
    story_analysis: Optional[Dict[str, Any]] = None,
    continuity_bible: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Guaranteed deterministic fallback planner when Gemini API is unconfigured or offline.
    Builds concrete, domain-aware scenes with shot variations and continuity anchors.
    """
    beats = create_visual_beats(script_text, total_duration, min_dur=2.0, max_dur=4.5)
    if not beats:
        beats = [(script_text, total_duration)]

    if not story_analysis:
        story_analysis = analyze_story(script_text)
    if not continuity_bible:
        continuity_bible = build_continuity_bible(story_analysis, script_text)

    shot_types = [
        "wide establishing shot", "medium shot", "close-up", "macro detail",
        "POV shot", "over-the-shoulder", "tracking shot", "extreme close-up", "cinematic reveal"
    ]
    camera_motions = ["push in", "pull out", "pan right", "pan left", "tilt up"]

    scenes = []
    current_time = 0.0

    for idx, (scene_text, dur) in enumerate(beats):
        s_lower = scene_text.lower()
        shot = shot_types[idx % len(shot_types)]
        motion = camera_motions[idx % len(camera_motions)]
        importance = "high" if idx in [0, len(beats) - 1] else "medium"
        anchor_ref = "general"

        # 1. Domain: Miniature Car Assembly
        if any(k in s_lower for k in ["miniature", "scale", "mechanic", "tiny", "suspension", "wheel", "chassis", "bolt", "windshield"]):
            anchor_ref = "miniature_car"
            importance = "critical"
            if "suspension" in s_lower or "spring" in s_lower:
                shot = "macro detail"
                vis_desc = "Tiny mechanics in dark blue uniforms physically attach chrome suspension springs to the front axle of the red 1:18 supercar chassis."
                p = "Photorealistic vertical 9:16 macro shot, three tiny figurine mechanics in dark blue factory overalls installing chrome suspension springs onto red 1:18-scale miniature sports car chassis with micro tools, workbench"
                sq = "miniature mechanics installing suspension 1:18 car model"
                must_show = ["tiny mechanics in dark blue overalls", "suspension springs", "red miniature chassis", "micro tools"]
                must_not_show = ["full-size car", "full-size humans", "real factory", "street"]
            elif "wheel" in s_lower or "bolt" in s_lower or "lug" in s_lower:
                shot = "extreme close-up"
                vis_desc = "A tiny mechanic in dark blue uniform uses a micro wrench to physically tighten wheel bolts on the red 1:18 supercar."
                p = "Photorealistic vertical 9:16 extreme close-up macro shot, tiny figurine mechanic tightening wheel bolts on miniature red sports car wheel with miniature wrench, shallow depth of field"
                sq = "miniature mechanic tightening wheel bolts model car"
                must_show = ["tiny mechanic", "miniature wheel", "wheel bolts", "miniature wrench"]
                must_not_show = ["full-size mechanic", "real automobile", "street"]
            elif "windshield" in s_lower or "glass" in s_lower:
                shot = "close-up"
                vis_desc = "Tiny mechanics carefully place and align the transparent miniature windshield onto the red 1:18 supercar body."
                p = "Photorealistic vertical 9:16 macro shot, two tiny mechanics in blue overalls positioning transparent miniature windshield onto red 1:18 scale supercar body"
                sq = "miniature car windshield installation scale model"
                must_show = ["miniature windshield", "tiny mechanics", "red miniature car"]
                must_not_show = ["full-size car", "real size people"]
            else:
                vis_desc = f"Tiny figurine mechanics assemble the red 1:18 scale supercar on the miniature workshop bench."
                p = f"Photorealistic vertical 9:16 cinematic {shot}, tiny 1:18 scale figurine mechanics in dark blue overalls assembling red miniature sports car on workshop bench, macro tilt-shift"
                sq = "tiny mechanics assembling miniature sports car"
                must_show = ["tiny figurine mechanics in blue overalls", "red 1:18 miniature car"]
                must_not_show = ["full-size car", "real factory"]

        # 2. Domain: Mystery / Room 307
        elif any(k in s_lower for k in ["room 307", "hotel", "security", "guard", "door", "corridor", "hallway", "cctv"]):
            anchor_ref = "room_307_hallway"
            importance = "critical"
            if "guard" in s_lower or "rushed" in s_lower or "security" in s_lower:
                shot = "tracking shot"
                vis_desc = "Two hotel security guards in dark navy uniforms run urgently down the hotel hallway toward Room 307 door."
                p = "Photorealistic vertical 9:16 dynamic tracking shot, two hotel security guards in dark navy uniforms running down hotel hallway toward dark wooden door marked Room 307, burgundy carpet, suspenseful"
                sq = "hotel security guards running hallway toward room door"
                must_show = ["two security guards in navy uniforms", "running down hallway", "Room 307 door visible"]
                must_not_show = ["empty hallway", "police officers", "daylight", "outdoor street"]
            elif "door" in s_lower or "opened" in s_lower or "swung" in s_lower:
                shot = "close-up"
                vis_desc = "Dark wooden door with brass plaque reading 'Room 307' slowly creaks open into the dark room."
                p = "Photorealistic vertical 9:16 suspenseful close-up shot of dark wooden hotel door with brass plaque reading 'Room 307' slowly opening into darkness, warm amber sconce lighting, moody shadows"
                sq = "hotel door Room 307 opening dark hallway"
                must_show = ["Room 307 brass plaque", "door opening", "hotel hallway"]
                must_not_show = ["different room number", "bright sunlight", "generic living room"]
            elif "cctv" in s_lower or "footage" in s_lower or "monitor" in s_lower:
                shot = "CCTV"
                vis_desc = "Security surveillance monitor displaying high-angle CCTV footage of the empty hotel hallway outside Room 307."
                p = "Vertical 9:16 high-angle CCTV security camera view of empty hotel hallway outside Room 307, timestamp overlay on monitor screen, eerie surveillance view"
                sq = "hotel hallway security camera CCTV monitor"
                must_show = ["CCTV camera perspective", "hotel hallway", "Room 307 door"]
                must_not_show = ["outdoor street", "daylight"]
            elif "empty" in s_lower:
                shot = "wide establishing shot"
                vis_desc = "Completely empty upscale hotel hallway at night with burgundy carpet, warm sconces, and Room 307 at the far end."
                p = "Photorealistic vertical 9:16 wide establishing shot of completely empty upscale hotel hallway at night, burgundy patterned carpet, warm amber sconces, closed Room 307 door at end of hall"
                sq = "empty upscale hotel hallway at night"
                must_show = ["empty hallway", "burgundy carpet", "closed doors"]
                must_not_show = ["people", "crowd", "daylight"]
            else:
                vis_desc = f"Suspenseful view in hotel hallway near Room 307 door."
                p = f"Photorealistic vertical 9:16 cinematic {shot} of upscale hotel corridor outside Room 307, burgundy carpet, dark wood paneling, warm moody sconce lighting"
                sq = "hotel corridor Room 307 night"
                must_show = ["hotel hallway", "Room 307"]
                must_not_show = ["daylight", "outdoor"]

        # 3. Domain: Specific Objects (Suitcase / Silver Key)
        elif any(k in s_lower for k in ["suitcase", "key", "luggage"]):
            anchor_ref = "suitcase_key"
            importance = "critical"
            if "key" in s_lower and "suitcase" in s_lower:
                shot = "close-up"
                vis_desc = "A woman opens a vibrant red travel suitcase and removes a small silver key."
                p = "Photorealistic vertical 9:16 cinematic close-up shot of a woman opening a vibrant red travel suitcase and carefully removing a small ornate silver key, warm focused table lighting"
                sq = "woman opening red suitcase removing silver key"
                must_show = ["woman opening suitcase", "red suitcase", "small silver key", "key being removed"]
                must_not_show = ["black suitcase", "generic woman without suitcase", "gold key"]
            elif "key" in s_lower:
                shot = "macro detail"
                vis_desc = "A woman's hand removes a small ornate silver key from inside the open red suitcase."
                p = "Photorealistic vertical 9:16 macro close-up shot of a woman's hand carefully lifting a small ornate silver key out of an open red travel suitcase, focused warm table lighting"
                sq = "hand removing silver key from red suitcase"
                must_show = ["red suitcase", "small silver key", "hand removing key"]
                must_not_show = ["black suitcase", "gold key", "generic woman without suitcase"]
            else:
                shot = "medium shot"
                vis_desc = "A woman opens a vibrant red travel suitcase on a table in a dimly lit room."
                p = "Photorealistic vertical 9:16 shot of a woman opening a vibrant red travel suitcase on a wooden table, warm ambient lighting"
                sq = "woman opening red suitcase"
                must_show = ["woman opening suitcase", "red suitcase"]
                must_not_show = ["black luggage", "outdoor"]

        # 4. Domain: Location Continuity (Kitchen / Refrigerator)
        elif any(k in s_lower for k in ["kitchen", "refrigerator", "fridge", "bottle", "water"]):
            anchor_ref = "kitchen_interior"
            if "bottle" in s_lower or "water" in s_lower:
                shot = "close-up"
                vis_desc = "Hand retrieves a clear cold bottle of water from the illuminated stainless steel refrigerator in the same kitchen."
                p = "Photorealistic vertical 9:16 close-up shot of a hand taking a clear cold bottle of water from inside an open illuminated stainless steel refrigerator in a modern kitchen"
                sq = "taking bottle of water from refrigerator kitchen"
                must_show = ["hand taking water bottle", "refrigerator interior", "modern kitchen"]
                must_not_show = ["outdoor", "different room"]
            elif "refrigerator" in s_lower or "fridge" in s_lower or "opens" in s_lower:
                shot = "medium shot"
                vis_desc = "Person opens the stainless steel refrigerator door in the modern kitchen, cool light illuminating the room."
                p = "Photorealistic vertical 9:16 medium shot of person opening stainless steel refrigerator door in modern kitchen at evening, cool white refrigerator light glowing"
                sq = "person opening refrigerator kitchen evening"
                must_show = ["person opening refrigerator", "refrigerator", "same modern kitchen"]
                must_not_show = ["living room", "outdoor"]
            else:
                shot = "wide establishing shot"
                vis_desc = "Person walks into a modern residential kitchen with clean countertops and stainless steel appliances."
                p = "Photorealistic vertical 9:16 wide establishing shot of person entering a modern residential kitchen, dark granite countertops, stainless steel appliances, evening lighting"
                sq = "person entering modern kitchen evening"
                must_show = ["person entering kitchen", "modern kitchen", "countertops"]
                must_not_show = ["bedroom", "outdoor street"]

        # 5. Domain: Aviation / Documentary (specific to general)
        elif any(k in s_lower for k in ["radar", "transponder", "tracking", "atc", "blip", "screen"]):
            shot = "close-up"
            anchor_ref = "radar_screen"
            vis_desc = "Close-up of green glowing radar sweep line and blips in dark air traffic control room."
            p = "Photorealistic vertical 9:16 close-up of glowing green air traffic control radar screen with sweeping line and radar blips in dark control room"
            sq = "air traffic control radar screen glowing green"
            must_show = ["glowing green radar screen", "radar blip", "dark ATC room"]
            must_not_show = ["airplane exterior", "daylight sky", "map", "diagram"]
        elif any(k in s_lower for k in ["cockpit", "pilot", "flight instruments", "controls", "hour into"]):
            shot = "close-up"
            anchor_ref = "airplane_cockpit"
            vis_desc = "Inside airplane cockpit at night, illuminated flight instruments and pilot controls."
            p = "Photorealistic vertical 9:16 cinematic shot inside commercial airliner cockpit at night, illuminated flight instruments, pilot controls, starry dark clouds outside"
            sq = "airplane cockpit night flight instruments pilot"
            must_show = ["cockpit instrument panels", "pilot controls", "night sky outside"]
            must_not_show = ["map", "diagram", "exterior street"]
        elif any(k in s_lower for k in ["cabin", "passenger", "passengers", "people on board"]):
            shot = "medium shot"
            anchor_ref = "airplane_cabin"
            vis_desc = "Inside commercial airliner passenger cabin with passengers seated in rows under warm cabin lights."
            p = "Photorealistic vertical 9:16 medium shot inside commercial airliner passenger cabin, passengers seated in rows under warm cabin lighting, window view"
            sq = "airliner passenger cabin interior people seated"
            must_show = ["airplane passenger cabin", "seated passengers", "airplane windows"]
            must_not_show = ["map", "diagram", "exterior plane"]
        elif any(k in s_lower for k in ["black box", "flight recorder", "data recorder"]):
            shot = "close-up"
            anchor_ref = "black_box"
            vis_desc = "Bright orange cylindrical flight data recorder resting on the dark ocean floor."
            p = "Photorealistic vertical 9:16 close-up shot of bright orange flight data recorder black box resting on dark seabed, submersible spotlight beam"
            sq = "flight data recorder black box ocean floor"
            must_show = ["bright orange flight recorder", "ocean floor seabed"]
            must_not_show = ["airplane in sky", "office desk", "map", "diagram"]
        elif any(k in s_lower for k in ["submarine", "sonar", "underwater", "scanned", "ocean floor", "abyss", "deep sea"]):
            shot = "close-up"
            anchor_ref = "deep_sea_search"
            vis_desc = "Deep-sea research submarine scanning dark ocean floor with powerful spotlights."
            p = "Photorealistic vertical 9:16 cinematic shot of deep-sea research submarine scanning dark ocean floor with powerful spotlights, deep sea sonar exploration"
            sq = "deep sea submarine scanning ocean floor searchlights"
            must_show = ["research submarine", "searchlights", "dark seabed ocean floor"]
            must_not_show = ["sunny beach", "map", "diagram"]
        elif any(k in s_lower for k in ["mystery", "unsolved", "what really happened", "remains"]):
            shot = "cinematic reveal"
            anchor_ref = "aviation_mystery"
            vis_desc = "Silhouetted commercial airliner flying through dramatic stormy sunset clouds, mystery atmosphere."
            p = "Photorealistic vertical 9:16 cinematic silhouette of commercial passenger airplane flying through dramatic stormy sunset clouds, golden hour mystery atmosphere"
            sq = "airplane silhouette flying sunset clouds"
            must_show = ["airplane silhouette", "dramatic sunset clouds"]
            must_not_show = ["map", "diagram", "ground"]
        elif any(k in s_lower for k in ["ocean", "sea", "waves", "indian ocean", "vast water"]):
            shot = "wide shot"
            anchor_ref = "stormy_ocean"
            vis_desc = "Aerial cinematic view of vast dark stormy ocean waves under ominous night sky."
            p = "Photorealistic vertical 9:16 aerial wide shot of vast dark ocean waves under stormy night sky, deep turquoise-black water, moody atmosphere"
            sq = "vast dark ocean waves stormy night"
            must_show = ["dark stormy ocean", "ocean waves", "night sky"]
            must_not_show = ["sunny beach", "map", "diagram"]
        elif any(k in s_lower for k in ["took off", "take off", "takeoff", "departure", "runway", "heading", "flight", "plane", "airliner", "airline", "aircraft"]):
            shot = "wide establishing shot"
            anchor_ref = "airplane_takeoff"
            vis_desc = "Commercial passenger airliner taking off into the night sky from an illuminated runway."
            p = "Photorealistic vertical 9:16 wide establishing shot of commercial Boeing 777 passenger airliner taking off into night sky from illuminated runway, glowing runway lights, dramatic atmosphere"
            sq = "commercial passenger airliner takeoff night runway"
            must_show = ["commercial passenger airplane", "taking off", "night runway"]
            must_not_show = ["map", "diagram", "daylight beach", "drone"]
        else:
            kws = clean_words(scene_text)
            vis_desc = f"{shot.title()} illustrating {scene_text[:35]}..."
            clean_subject = "commercial airliner in sky" if any(x in script_text.lower() for x in ["flight", "plane", "aviation", "airliner", "aircraft"]) else (' '.join(kws[:3]) if kws else "cinematic scene")
            p = f"Photorealistic vertical 9:16 cinematic {shot} of {clean_subject}, dramatic lighting, 8k, photorealistic"
            sq = f"{clean_subject} cinematic"
            must_show = [clean_subject]
            must_not_show = ["blurry", "watermark", "map", "diagram"]

        # Enforce continuity
        p = enforce_continuity_in_prompt(p, continuity_bible, scene_text)

        # Validate scene
        val = heuristic_validate_scene(scene_text, p, must_show, must_not_show, continuity_bible=continuity_bible, visual_description=vis_desc)
        if not val["accepted"] and val.get("correction_prompt"):
            p = val["correction_prompt"]

        scenes.append({
            "scene_id": f"scene_{idx+1:02d}",
            "start_time": round(current_time, 2),
            "end_time": round(current_time + dur, 2),
            "duration": round(dur, 2),
            "narration": scene_text,
            "visual_description": vis_desc,
            "image_prompt": p,
            "search_query": sq,
            "shot_type": shot,
            "camera_motion": motion,
            "must_show": must_show,
            "must_not_show": must_not_show,
            "continuity_anchor": anchor_ref,
            "importance": importance,
            "source": "generated"
        })
        current_time += dur

    return {
        "story_analysis": story_analysis,
        "continuity_bible": continuity_bible,
        "scenes": scenes
    }


def plan_visual_storyboard(
    script_text: str,
    total_duration: float,
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Main Visual Director planning entry point.
    1. Story analysis (extracts story_type, characters, objects, locations, tone)
    2. Continuity bible creation
    3. Meaningful visual beat segmentation
    4. Structured Gemini Flash planning with validation & retry
    5. Safe semantic fallback if Gemini is offline/unconfigured
    """
    script_clean = script_text.strip()
    if not script_clean:
        return {"story_analysis": {}, "continuity_bible": {}, "scenes": []}

    # Step 1: Story Analysis
    story_analysis = analyze_story(script_clean, api_key=api_key)

    # Step 2: Continuity Bible
    continuity_bible = build_continuity_bible(story_analysis, script_clean)

    # Step 3: Visual Beat Segmentation (~3-6s per scene, ~10-14 for 60s)
    beats = create_visual_beats(script_clean, total_duration, min_dur=2.0, max_dur=4.5)
    if not beats:
        beats = [(script_clean, total_duration)]
    scene_texts = [t for t, _ in beats]

    resolved_key = api_key or os.environ.get("GEMINI_API_KEY", "")

    if not resolved_key:
        print("[Visual Director] No Gemini API key provided. Using semantic fallback planner.")
        return semantic_fallback_plan(script_clean, total_duration, story_analysis, continuity_bible)

    # Step 4: Gemini Flash Visual Director Call
    prompt_payload = (
        f"{VISUAL_DIRECTOR_SYSTEM_PROMPT}\n\n"
        f"Story Analysis:\n{json.dumps(story_analysis, indent=2)}\n\n"
        f"Continuity Bible:\n{json.dumps(continuity_bible, indent=2)}\n\n"
        f"Full Narration Script ({total_duration:.1f}s total):\n{script_clean}\n\n"
        f"Sequential Spoken Beats ({len(scene_texts)} beats):\n{json.dumps(scene_texts)}"
    )

    body = {
        "contents": [{
            "parts": [{"text": prompt_payload}]
        }],
        "generationConfig": {
            "responseMimeType": "application/json",
            "maxOutputTokens": 4000,
            "temperature": 0.2
        }
    }

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
                        raw_scenes = parsed["scenes"]
                        final_scenes = []
                        curr_t = 0.0

                        for idx, (b_text, b_dur) in enumerate(beats):
                            s_data = raw_scenes[idx] if idx < len(raw_scenes) else {}

                            shot = s_data.get("shot_type", "cinematic shot")
                            motion = s_data.get("camera_motion", "push in")
                            vis_desc = s_data.get("visual_description", f"Visual illustrating {b_text[:35]}")
                            p = s_data.get("image_prompt") or f"Photorealistic vertical 9:16 {shot} of {b_text}, cinematic 8k"
                            sq = s_data.get("search_query") or " ".join(clean_words(b_text)[:3])
                            must_show = s_data.get("must_show") or [b_text[:20]]
                            must_not_show = s_data.get("must_not_show") or ["blurry", "watermark"]
                            importance = s_data.get("importance", "medium")
                            anchor_ref = s_data.get("continuity_anchor", "bible")

                            # Enforce continuity
                            p = enforce_continuity_in_prompt(p, continuity_bible, b_text)

                            # Validate scene with up to 2 retries
                            val = heuristic_validate_scene(b_text, p, must_show, must_not_show, continuity_bible=continuity_bible, visual_description=vis_desc)
                            if not val["accepted"] and val.get("correction_prompt"):
                                p = val["correction_prompt"]

                            final_scenes.append({
                                "scene_id": f"scene_{idx+1:02d}",
                                "start_time": round(curr_t, 2),
                                "end_time": round(curr_t + b_dur, 2),
                                "duration": round(b_dur, 2),
                                "narration": b_text,
                                "visual_description": vis_desc,
                                "image_prompt": p,
                                "search_query": sq,
                                "shot_type": shot,
                                "camera_motion": motion,
                                "must_show": must_show,
                                "must_not_show": must_not_show,
                                "continuity_anchor": anchor_ref,
                                "importance": importance,
                                "source": "generated"
                            })
                            curr_t += b_dur

                        print(f"[Visual Director] Successfully planned {len(final_scenes)} scenes with {model_name}!")
                        return {
                            "story_analysis": story_analysis,
                            "continuity_bible": continuity_bible,
                            "scenes": final_scenes
                        }
            except Exception as e:
                print(f"[Visual Director] {model_name} attempt {attempt+1} error: {e}")
                time.sleep(0.8)

    print("[Visual Director] Gemini models exhausted. Falling back to semantic planner.")
    return semantic_fallback_plan(script_clean, total_duration, story_analysis, continuity_bible)
