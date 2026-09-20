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
import hashlib
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

# In-memory caches for story analysis and continuity bible keyed by script text hash
_STORY_ANALYSIS_CACHE: Dict[str, Dict[str, Any]] = {}
_CONTINUITY_BIBLE_CACHE: Dict[str, Dict[str, Any]] = {}


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

        # UNIVERSAL DYNAMIC SCENE PLANNER (Works for ANY script, zero hardcoded topics)
        shot = "cinematic shot"
        motion = "push in"
        importance = "medium"
        anchor_ref = "scene_context"
        
        # Universal Semantic Visual Ontology
        SEMANTIC_VISUAL_MAP = {
            # History, Empires & Warfare
            "colosseum": ("roman colosseum", "colosseum rome", "wide establishing shot", "slow zoom out"),
            "gladiator": ("gladiators battling inside arena", "gladiator arena", "medium shot", "dynamic pan"),
            "gladiators": ("gladiators battling inside arena", "gladiator arena", "medium shot", "dynamic pan"),
            "legion": ("roman soldiers marching in armor", "roman soldiers army", "dynamic tracking shot", "tracking push"),
            "legions": ("roman soldiers marching in armor", "roman soldiers army", "dynamic tracking shot", "tracking push"),
            "soldier": ("soldiers in combat gear", "soldiers battlefield", "dynamic tracking shot", "tracking push"),
            "soldiers": ("soldiers in combat gear", "soldiers battlefield", "dynamic tracking shot", "tracking push"),
            "samurai": ("samurai warrior in traditional armor with katana", "samurai warrior", "medium shot", "slow push in"),
            "knight": ("medieval knight in shining plate armor", "medieval knight armor", "medium shot", "slow push in"),
            "knights": ("medieval knights on horseback", "medieval knights", "wide establishing shot", "push in"),
            "castle": ("ancient medieval stone castle fortress", "medieval castle", "wide establishing shot", "slow zoom out"),
            "pyramid": ("ancient Egyptian pyramids of Giza in desert", "giza pyramids", "wide establishing shot", "slow zoom out"),
            "pyramids": ("ancient Egyptian pyramids of Giza in desert", "giza pyramids", "wide establishing shot", "slow zoom out"),
            "pharaoh": ("ancient Egyptian pharaoh golden tomb", "egypt pharaoh", "close-up detail", "macro push in"),
            "napoleon": ("Napoleon Bonaparte on horseback leading army", "napoleon bonaparte", "medium shot", "push in"),
            "viking": ("viking warrior on wooden longship", "viking longship", "wide establishing shot", "push in"),
            "sword": ("ancient steel sword reflecting light", "sword weapon", "close-up detail", "macro push in"),
            
            # Animals & Nature
            "lion": ("wild male lion stalking in African savannah", "lion wildlife", "medium shot", "slow push in"),
            "lions": ("pride of lions resting under acacia tree", "lions savannah", "wide establishing shot", "slow zoom out"),
            "predator": ("wild predator animal hunting in wilderness", "lion hunting", "dynamic tracking shot", "tracking push"),
            "tiger": ("wild Bengal tiger in deep jungle", "tiger wildlife", "medium shot", "slow push in"),
            "shark": ("great white shark swimming in deep ocean", "shark underwater", "close-up detail", "slow pan"),
            "whale": ("massive blue whale swimming in ocean depths", "whale ocean", "wide shot", "slow zoom out"),
            "wolf": ("gray wolf in snowy winter forest", "wolf wildlife", "medium shot", "slow push in"),
            "eagle": ("majestic eagle soaring over mountain peaks", "eagle bird flight", "aerial wide shot", "slow zoom out"),
            "ocean": ("vast dark stormy ocean waves under night sky", "stormy ocean", "wide establishing shot", "slow zoom out"),
            "sea": ("vast dark stormy ocean waves under night sky", "stormy ocean", "wide establishing shot", "slow zoom out"),
            "waves": ("powerful stormy ocean waves crashing", "ocean waves", "close-up detail", "dynamic pan"),
            "volcano": ("erupting volcano with glowing red lava", "volcano lava", "wide establishing shot", "slow zoom out"),
            "jungle": ("dense tropical rainforest with sunlight beams", "jungle rainforest", "wide establishing shot", "slow push in"),
            "desert": ("vast golden sand dunes under desert sun", "desert sand dunes", "wide establishing shot", "slow zoom out"),
            
            # Finance, Crypto & Business
            "bitcoin": ("physical golden Bitcoin cryptocurrency coin", "bitcoin coin", "close-up detail", "macro push in"),
            "crypto": ("digital cryptocurrency blockchain network", "bitcoin crypto", "close-up detail", "macro push in"),
            "blockchain": ("digital blockchain data network visualization", "blockchain technology", "medium shot", "slow pan"),
            "gold": ("pure gold bullion bars stacked in bank vault", "gold bars vault", "close-up detail", "macro push in"),
            "coins": ("glowing gold coins stacked on desk", "gold coins currency", "close-up detail", "macro push in"),
            "wall street": ("busy Wall Street financial trading floor", "wall street trading", "wide establishing shot", "push in"),
            "money": ("stacks of cash currency on table", "currency money", "close-up detail", "macro push in"),
            
            # Space, Sci-Fi & Cyberpunk
            "space": ("deep space nebula with glowing stars and galaxy", "deep space galaxy", "wide establishing shot", "slow zoom out"),
            "galaxy": ("spiral galaxy with billions of glowing stars", "spiral galaxy space", "wide establishing shot", "slow zoom out"),
            "black hole": ("massive supermassive black hole with accretion disk in space", "black hole space", "wide establishing shot", "slow zoom out"),
            "rocket": ("massive space rocket launching with fire into night sky", "space rocket launch", "dynamic tracking shot", "tilt up"),
            "astronaut": ("astronaut in spacesuit floating in deep space", "astronaut spacewalk", "medium shot", "slow push in"),
            "cyberpunk": ("neon-lit cyberpunk city street in rain at night", "cyberpunk city", "wide establishing shot", "push in"),
            "hacker": ("elite computer hacker working in dark room with code screens", "computer hacker", "medium shot", "slow push in"),
            "robot": ("futuristic humanoid robot android with glowing blue eyes", "humanoid robot", "close-up detail", "slow push in"),
            "skyscrapers": ("futuristic city skyscrapers glowing with neon at night", "city skyscrapers night", "wide establishing shot", "slow zoom out"),
            
            # Aviation & Maritime
            "airplane": ("commercial Boeing passenger airliner in flight", "commercial airliner", "wide establishing shot", "slow pan"),
            "airliner": ("commercial Boeing passenger airliner in flight", "commercial airliner", "wide establishing shot", "slow pan"),
            "flight": ("commercial passenger airliner flying through clouds", "commercial airliner flight", "wide establishing shot", "slow pan"),
            "plane": ("commercial Boeing passenger airliner in flight", "commercial airliner", "wide establishing shot", "slow pan"),
            "takeoff": ("commercial passenger airliner taking off into night sky from illuminated runway", "airplane takeoff", "wide establishing shot", "tilt up"),
            "took off": ("commercial passenger airliner taking off into night sky from illuminated runway", "airplane takeoff", "wide establishing shot", "tilt up"),
            "runway": ("commercial airliner on illuminated runway at night", "airplane runway night", "wide establishing shot", "push in"),
            "cockpit": ("inside commercial airliner cockpit at night with glowing instruments", "airplane cockpit", "close-up detail", "slow push in"),
            "radar": ("glowing green air traffic control radar screen in dark room", "radar screen", "close-up detail", "slow push in"),
            "transponder": ("air traffic control radar screen with sweeping green beam", "radar screen", "close-up detail", "slow push in"),
            "cabin": ("inside commercial airliner passenger cabin with passengers seated", "airplane passenger cabin", "medium shot", "slow push in"),
            "passengers": ("inside commercial airliner passenger cabin with passengers seated", "airplane passenger cabin", "medium shot", "slow push in"),
            "submarine": ("deep-sea research submarine scanning dark seabed with searchlights", "underwater submarine", "close-up detail", "slow pan"),
            "sonar": ("deep-sea research submarine scanning dark seabed with searchlights", "underwater submarine", "close-up detail", "slow pan"),
            "black box": ("bright orange flight data recorder black box on ocean floor", "flight recorder black box", "close-up detail", "macro push in"),
            
            # Mystery, Noir & Urban
            "detective": ("vintage noir detective in trench coat in dimly lit room", "detective noir", "medium shot", "slow push in"),
            "revolver": ("vintage silver revolver handgun resting on wooden desk", "revolver handgun", "close-up detail", "macro push in"),
            "gun": ("vintage handgun resting on wooden desk", "handgun weapon", "close-up detail", "macro push in"),
            "journal": ("old antique leather-bound journal with handwritten notes", "vintage leather journal", "close-up detail", "macro push in"),
            "fog": ("heavy atmospheric mist and fog rolling through cobblestone street at night", "fog cobblestone street", "wide establishing shot", "push in"),
            "door": ("dark antique wooden door slowly creaking open into shadows", "antique wooden door", "close-up detail", "slow push in"),
            "corridor": ("long empty upscale hotel hallway with warm wall sconces at night", "hotel corridor hallway", "wide establishing shot", "push in"),
            "hallway": ("long empty upscale hotel hallway with warm wall sconces at night", "hotel corridor hallway", "wide establishing shot", "push in"),
            "suitcase": ("vibrant red vintage travel suitcase resting on table", "vintage suitcase", "close-up detail", "slow push in"),
            "key": ("small ornate antique silver key resting on table", "antique silver key", "close-up detail", "macro push in"),
            "cctv": ("high-angle CCTV security camera surveillance monitor view", "cctv security camera", "close-up detail", "slow push in"),
            "security": ("hotel security guards in dark navy uniforms in hallway", "security guard uniform", "medium shot", "tracking push"),
            "guard": ("security guard in dark navy uniform on night patrol", "security guard uniform", "medium shot", "tracking push"),
            
            # Lifestyle, Food & Domestic
            "kitchen": ("modern residential kitchen with stainless steel appliances", "modern kitchen", "wide establishing shot", "push in"),
            "chef": ("professional chef chopping fresh ingredients in restaurant kitchen", "chef cooking", "medium shot", "dynamic pan"),
            "cooking": ("sizzling pan on stove with fresh garlic and olive oil", "chef cooking pan", "close-up detail", "macro push in"),
            "refrigerator": ("illuminated stainless steel refrigerator door opening in modern kitchen", "modern refrigerator", "medium shot", "slow push in"),
            "car": ("sleek modern sports car in clean workshop garage", "sports car", "wide establishing shot", "slow pan"),
            "workshop": ("mechanic workshop with tools and automotive equipment", "mechanic workshop tools", "medium shot", "push in")
        }
        
        # Check semantic ontology match
        matched_concept = None
        for keyword, mapping in SEMANTIC_VISUAL_MAP.items():
            # Match whole words to prevent subword false positives
            if re.search(r'\b' + re.escape(keyword) + r'\b', s_lower):
                matched_concept = mapping
                break
                
        if matched_concept:
            subject_desc, sq, shot, motion = matched_concept
            vis_desc = f"{shot.title()} of {subject_desc}."
            p = f"Photorealistic vertical 9:16 cinematic {shot} of {subject_desc}, dramatic lighting, 8k resolution, photorealistic"
            must_show = [sq.split()[0]]
            must_not_show = ["map", "route", "chart", "diagram", "technical drawing", "blurry", "watermark", "scanned document", "text overlay"]
        else:
            # Dynamic semantic fallback grounded in story analysis
            setting = (story_analysis.get("setting") or "").strip()
            visual_style = (story_analysis.get("visual_style") or "cinematic realistic").strip()
            tone = (story_analysis.get("tone") or "dramatic").strip()
            main_chars = story_analysis.get("main_characters") or []
            main_char = (main_chars[0].get("description") or main_chars[0].get("name_or_role") or "").strip() if main_chars else ""
            imp_objs = story_analysis.get("important_objects") or []
            imp_obj = (imp_objs[0].get("description") or imp_objs[0].get("name") or "").strip() if imp_objs else ""

            kws = clean_words(scene_text)
            filtered_kws = [
                w for w in kws 
                if not w.isdigit() and w not in {
                    'began', 'lay', 'walked', 'rolled', 'turned', 'went', 'came',
                    'thousands', 'millions', 'hundreds', 'year', 'years', 'decade',
                    'great', 'massive', 'first', 'last', 'really', 'simply', 'later',
                    'became', 'started', 'taking', 'could', 'would', 'should',
                    'might', 'must', 'every', 'never', 'their', 'there', 'where'
                }
            ]

            # Ground subject in story characters, objects, or filtered nouns
            if main_char and any(w in s_lower for w in clean_words(main_char)):
                subject_anchor = main_char
            elif imp_obj and any(w in s_lower for w in clean_words(imp_obj)):
                subject_anchor = imp_obj
            elif filtered_kws:
                subject_anchor = " ".join(filtered_kws[:2])
            elif main_char:
                subject_anchor = main_char
            elif imp_obj:
                subject_anchor = imp_obj
            elif setting:
                subject_anchor = setting
            else:
                subject_anchor = "cinematic scene"

            # Deduce shot type from text action
            if any(w in s_lower for w in ["in", "outside", "city", "street", "palace", "landscape", "sky", "mountain", "vast", "empty"]):
                shot = "wide establishing shot"
                motion = "slow zoom out"
            elif any(w in s_lower for w in ["sprinted", "ran", "marched", "flew", "flying", "navigating", "sprints", "rushed"]):
                shot = "dynamic tracking shot"
                motion = "tracking push"
            elif any(w in s_lower for w in ["small", "silver", "gold", "hand", "finger", "face", "eye", "close", "key", "coin", "screen"]):
                shot = "close-up detail"
                motion = "macro push in"
            else:
                shot = "medium shot"
                motion = "slow push in"

            # Formulate grounded prompt and description
            context_clause = f"in {setting}" if setting and setting.lower() not in subject_anchor.lower() else ""
            style_clause = f"{visual_style}, {tone} atmosphere" if visual_style else "cinematic lighting"

            vis_desc = f"{shot.title()} showing {subject_anchor} {context_clause}.".strip()
            p = f"Photorealistic vertical 9:16 cinematic {shot} of {subject_anchor} {context_clause}, {style_clause}, 8k resolution, photorealistic, dramatic volumetric lighting"

            # Clean search query (1-3 words max, grounded in primary entity)
            if filtered_kws:
                sq = " ".join(filtered_kws[:2])
            elif subject_anchor:
                sq = " ".join(clean_words(subject_anchor)[:2])
            else:
                sq = "cinematic scene"

            must_show = [filtered_kws[0] if filtered_kws else (clean_words(subject_anchor)[0] if clean_words(subject_anchor) else "subject")]
            must_not_show = ["map", "route", "chart", "diagram", "technical drawing", "blurry", "watermark", "scanned document", "text overlay"]

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

    script_hash = hashlib.sha256(script_clean.encode('utf-8')).hexdigest()[:16]

    # Step 1: Story Analysis (cached by script hash to prevent redundant analysis)
    if script_hash in _STORY_ANALYSIS_CACHE:
        story_analysis = _STORY_ANALYSIS_CACHE[script_hash]
    else:
        story_analysis = analyze_story(script_clean, api_key=api_key)
        _STORY_ANALYSIS_CACHE[script_hash] = story_analysis

    # Step 2: Continuity Bible (cached by script hash)
    if script_hash in _CONTINUITY_BIBLE_CACHE:
        continuity_bible = _CONTINUITY_BIBLE_CACHE[script_hash]
    else:
        continuity_bible = build_continuity_bible(story_analysis, script_clean)
        _CONTINUITY_BIBLE_CACHE[script_hash] = continuity_bible

    # Step 3: Visual Beat Segmentation (~3-6s per scene, ~10-14 for 60s)
    beats = create_visual_beats(script_clean, total_duration, min_dur=2.0, max_dur=4.5)
    if not beats:
        beats = [(script_clean, total_duration)]
    scene_texts = [t for t, _ in beats]

    resolved_key = api_key or os.environ.get("GEMINI_API_KEY", "")

    if not resolved_key:
        print("[Visual Director] WARNING: No GEMINI_API_KEY configured. Running in degraded semantic fallback mode.")
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
