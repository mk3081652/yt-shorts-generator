"""
engine/director.py - The Director: Scene planning, deterministic prompt compiler, and basic-mode fallback.
Translates full script + verbatim beats into a cohesive visual storyboard.
"""

import os
import re
import json
import base64
from typing import Dict, Any, List, Optional, Tuple

from engine.config import (
    get_gemini_api_key,
    is_vision_qa_enabled
)
from engine.llm import generate_content


DIRECTOR_SYSTEM_PROMPT = """You are an elite film director, cinematographer, and visual director storyboarding a vertical (9:16) YouTube Short from its narration.
You receive the full script and a numbered list of beats (the exact spoken lines).

STEP 1, READ THE WHOLE SCRIPT. Decide: genre, tone, era, one-sentence visual style shared by every scene, and up to 5 recurring entities (people, creatures, objects, places). Give each entity a fixed, concrete visual description (age, clothing, colours, materials, distinguishing marks, scale). These descriptions will be copied verbatim into every scene that features the entity.

STEP 2, CINEMATIC VISUAL STORYBOARD. For each beat, answer: "What does the viewer literally SEE while hearing this line?"
The individual scene is the primary source of truth. The overall script/topic only provides context.
CRITICAL RULES:
- SEMANTIC ACCURACY OVER TOPIC KEYWORDS:
  * "The pilot noticed something strange on the instruments display" -> Pilot inside cockpit looking at flight instruments at night. (NEVER generic exterior airplane in clouds!)
  * "The ship entered the storm and was never seen again" -> Ship battling dark stormy ocean waves. (NEVER generic calm ocean without ship!)
  * "Investigators discovered a classified document hidden inside the archive" -> Hands opening classified archive document with red stamps under desk lamp.
  * "At 2:17 AM, the signal suddenly disappeared" -> Control room monitor screen flatlining or blinking red alert.
  * "The company lost 40% of its value in three days" -> Financial stock market charts falling red, busy trading floor screens.
  * "Roman soldiers marched toward the city" -> Roman legionaries marching in armor formation.
  * "She sat alone by the window waiting for an answer" -> Solitary woman sitting by window in moody room looking outside.
- UNIVERSAL VISUAL TYPES (classify each scene):
  * "literal": Concrete object, person, vehicle, or action.
  * "conceptual": Financial trends, economic events, invisible phenomena translated into concrete visuals (charts, screens, activity).
  * "historical": Ancient or period events depicted via representative reenactment footage.
  * "abstract": Emotions or uncertainty translated into physical moments (waiting, empty hallway, silhouette at window).
  * "data": Documents, screens, computer monitors, blueprints, maps, electronic displays.
  * "location": Specific atmospheric environment, landscape, or facility.
  * "person": Specific character, profession, or human reaction.
  * "object": Specific machine, device, artifact, or tool.
- VISUAL PRIORITY:
  * "high": Hook scene (first 3s), major reveal, shocking surprise, key turning point, dramatic climax.
  * "medium": Supporting story beats, essential context, action progression.
  * "low": Bridging sentences, brief commentary, quiet transitions.
- VISUAL STRATEGY:
  * "pexels": Realistic modern real-world footage expected to exist in stock video libraries.
  * "flux": Highly fantastical, hyper-specific historical, surreal, or sci-fi visuals where realistic stock video does not exist.
  * "hold": If narration is continuous commentary and continuing previous visual is stronger than switching to filler.
- SHOT VARIETY & PACING:
  * Vary shot types intentionally: wide / establishing -> medium subject -> close-up detail -> POV -> low-angle -> over-shoulder.
  * Never repeat the exact same framing for 3 consecutive scenes.
- SEARCH QUERIES:
  * Generate 3 to 6 distinct, concrete 2-to-4 word search queries for stock video footage describing LITERAL filmable physical subjects/actions/places.
  * Avoid vague fluff ("mystery", "story", "important", "dramatic") unless paired with a concrete noun ("dramatic storm clouds").
- MUST SHOW & SHOULD AVOID:
  * must_show: 2-3 essential visual elements that MUST be visible.
  * should_avoid: 1-2 generic or misleading visuals that would ruin semantic accuracy.
- CONTINUITY GROUP:
  * Group scenes sharing the same continuous scene setting (e.g. "cockpit_night", "ocean_storm", "archive_room", "trading_floor").

Return JSON only:
{
 "style": "one sentence shared visual style",
 "entities": [{"id":"e1","name":"...","look":"fixed visual description"}],
 "scenes": [{
   "beat": 0,
   "subject": "who/what is in frame",
   "action": "what is happening",
   "setting": "where, time of day",
   "shot": "wide | medium | close-up | macro | low-angle | over-shoulder | POV | aerial",
   "lighting": "short phrase",
   "mood": "tense | urgent | mysterious | energetic | sombre | triumphant",
   "visual_type": "literal | conceptual | historical | abstract | data | location | person | object",
   "visual_priority": "high | medium | low",
   "visual_strategy": "pexels | flux | hold",
   "continuity_group": "string label for scene setting block",
   "shot_scale": "close-up | medium | wide | extreme_close_up | establishing | pov | detail",
   "motion_intensity": "low | medium | high",
   "must_show": ["key element 1", "key element 2"],
   "should_avoid": ["unwanted generic element 1"],
   "search_queries": [
     "concrete query 1",
     "concrete query 2",
     "concrete query 3",
     "concrete query 4"
   ],
   "broll_keywords": ["2-3 word search 1", "search 2", "search 3"],
   "camera_motion": "push in | pull out | pan right | pan left | tilt up | static",
   "video_prompt": "1-2 sentences: camera move + subject motion for image-to-video tools",
   "entities": ["e1"],
   "is_abstract": false,
   "hold_previous": false
 }]
}"""


DEFAULT_SHARED_STYLE = "Cinematic film still, 35mm photography, natural dramatic lighting, highly detailed"
DEFAULT_CAMERA_MOTIONS = ["push in", "pull out", "pan right", "pan left", "tilt up", "static"]
DEFAULT_SHOTS = ["wide", "medium", "close-up", "macro", "low-angle", "over-shoulder", "POV", "aerial"]


def compile_prompt(
    scene_data: Dict[str, Any],
    entities_map: Dict[str, str],
    shared_style: str,
    style_lock: str = ""
) -> str:
    """
    Deterministic Prompt Compiler (pure function):
    {style_lock}. {style}. {shot} shot of {subject} {action}, {setting}. {each entity.look, copied verbatim}. {lighting}. Vertical 9:16, subject centered, no text, no watermark.

    Rules:
    - Keep under about 60 words: trim setting and lighting first, NEVER entity looks.
    - Positive exclusions clause at the end.
    - style_lock is applied dynamically at compile time.
    """
    shot = scene_data.get("shot", "medium").strip() or "medium"
    subject = scene_data.get("subject", "").strip()
    action = scene_data.get("action", "").strip()
    setting = scene_data.get("setting", "").strip()
    lighting = scene_data.get("lighting", "").strip()

    # Gather entity looks verbatim
    entity_ids = scene_data.get("entities", [])
    entity_looks_list = []
    if isinstance(entity_ids, list):
        for eid in entity_ids:
            if eid in entities_map and entities_map[eid].strip():
                entity_looks_list.append(entities_map[eid].strip())
    entity_looks_clause = ". ".join(entity_looks_list)

    # Core action clause
    if subject and action:
        core = f"{shot} shot of {subject} {action}"
    elif subject:
        core = f"{shot} shot of {subject}"
    else:
        core = f"{shot} shot"

    suffix = "Vertical 9:16, subject centered, no text, no watermark."

    def build_candidate(include_setting: bool, include_lighting: bool) -> str:
        parts = []
        if style_lock.strip():
            parts.append(style_lock.strip().rstrip("."))
        if shared_style.strip():
            parts.append(shared_style.strip().rstrip("."))

        scene_part = core
        if include_setting and setting:
            scene_part = f"{scene_part}, {setting.rstrip('.')}"
        parts.append(scene_part)

        if entity_looks_clause:
            parts.append(entity_looks_clause.rstrip("."))

        if include_lighting and lighting:
            parts.append(lighting.strip().rstrip("."))

        parts.append(suffix)
        return ". ".join(p for p in parts if p)

    # 1. Full prompt
    candidate = build_candidate(include_setting=True, include_lighting=True)
    if len(candidate.split()) <= 65:
        return candidate

    # 2. Trim lighting
    candidate = build_candidate(include_setting=True, include_lighting=False)
    if len(candidate.split()) <= 65:
        return candidate

    # 3. Trim setting (never trim entity looks!)
    candidate = build_candidate(include_setting=False, include_lighting=False)
    return candidate


def basic_mode_plan(beats: List[Tuple[str, float]], style_lock: str = "") -> Dict[str, Any]:
    """
    Basic Mode Fallback:
    Used when no GEMINI_API_KEY is available or when Gemini call fails.
    Uses the narration line itself as the subject. No keyword hijacking, no ontology.
    """
    shared_style = DEFAULT_SHARED_STYLE
    scenes = []
    shots_cycle = ["wide", "medium", "close-up", "low-angle", "POV", "over-shoulder"]
    motions_cycle = ["push in", "pull out", "pan right", "tilt up", "push in", "static"]

    for idx, (text, dur) in enumerate(beats):
        shot = shots_cycle[idx % len(shots_cycle)]
        motion = motions_cycle[idx % len(motions_cycle)]
        cleaned_text = re.sub(r'[\r\n\t]+', ' ', text).strip()
        words = [w for w in re.sub(r'[^a-zA-Z0-9\s]', ' ', cleaned_text).split() if len(w) > 2]
        fallback_query = " ".join(words[:3]) if words else "cinematic atmospheric scene"

        scene_dict = {
            "beat": idx,
            "subject": cleaned_text,
            "action": "",
            "setting": "",
            "shot": shot,
            "lighting": "dramatic cinematic lighting",
            "mood": "tense" if idx == 0 else "cinematic",
            "visual_type": "literal",
            "visual_priority": "high" if idx == 0 else ("medium" if idx < len(beats) - 1 else "high"),
            "visual_strategy": "pexels",
            "continuity_group": f"group_{idx // 3}",
            "shot_scale": shot,
            "motion_intensity": "medium",
            "must_show": [fallback_query],
            "should_avoid": [],
            "search_queries": [fallback_query, f"{fallback_query} cinematic", f"{fallback_query} vertical"],
            "broll_keywords": [fallback_query, f"{fallback_query} cinematic", f"{fallback_query} vertical"],
            "entities": [],
            "camera_motion": motion,
            "video_prompt": f"{motion.capitalize()} camera movement framing {cleaned_text[:80]}",
            "is_abstract": False,
            "hold_previous": False
        }

        image_prompt = compile_prompt(scene_dict, {}, shared_style, style_lock=style_lock)
        scene_dict["image_prompt"] = image_prompt
        scene_dict["duration"] = dur
        scene_dict["text"] = text
        scenes.append(scene_dict)

    return {
        "style": shared_style,
        "entities": [],
        "scenes": scenes,
        "is_basic_mode": True
    }


def plan_scenes_with_director(
    script: str,
    beats: List[Tuple[str, float]],
    api_key: Optional[str] = None,
    style_lock: str = ""
) -> Tuple[Dict[str, Any], bool]:
    """
    Executes the Director pipeline:
    1. Formats the full script and numbered beats.
    2. Calls Gemini 3.8 Flash with DIRECTOR_SYSTEM_PROMPT.
    3. Validates coverage of all beat indices [0 .. len(beats)-1].
    4. On invalid output, retries once with the specific error.
    5. Falls back to basic_mode_plan on total failure.

    Returns:
        (plan_dict, is_basic_mode)
    """
    resolved_key = api_key or get_gemini_api_key()
    if not resolved_key:
        print("[Director] No GEMINI_API_KEY found, using basic mode.")
        return basic_mode_plan(beats, style_lock=style_lock), True

    beats_formatted = "\n".join(f"[{i}] {text}" for i, (text, _) in enumerate(beats))
    user_prompt = f"""FULL SCRIPT:
\"\"\"{script.strip()}\"\"\"

NUMBERED BEATS:
{beats_formatted}

Plan the storyboard following the system instructions. Return valid JSON only."""

    contents = [
        {"role": "user", "parts": [{"text": f"{DIRECTOR_SYSTEM_PROMPT}\n\n{user_prompt}"}]}
    ]

    for attempt in range(2):
        raw_text, used_model = generate_content(
            prompt_or_contents=contents,
            thinking_level="low",
            max_output_tokens=8000,
            json_mode=True,
            api_key=resolved_key
        )

        if not raw_text:
            print(f"[Director] Attempt {attempt+1} returned empty response.")
            continue

        try:
            # Parse JSON
            # Strip potential markdown formatting if returned
            clean_json = raw_text.strip()
            if clean_json.startswith("```"):
                clean_json = re.sub(r'^```(?:json)?\s*', '', clean_json)
                clean_json = re.sub(r'\s*```$', '', clean_json)
            data = json.loads(clean_json)

            shared_style = data.get("style", "").strip() or DEFAULT_SHARED_STYLE
            entities = data.get("entities", [])
            entities_map = {}
            if isinstance(entities, list):
                for e in entities:
                    if isinstance(e, dict) and "id" in e and "look" in e:
                        entities_map[e["id"]] = e["look"]

            scenes_raw = data.get("scenes", [])
            if not isinstance(scenes_raw, list):
                raise ValueError("Key 'scenes' must be a list")

            # Map scenes by beat index
            scenes_by_beat: Dict[int, Dict[str, Any]] = {}
            for s in scenes_raw:
                if isinstance(s, dict) and "beat" in s:
                    try:
                        b_idx = int(s["beat"])
                        scenes_by_beat[b_idx] = s
                    except (ValueError, TypeError):
                        pass

            # Validate coverage
            missing_beats = [i for i in range(len(beats)) if i not in scenes_by_beat]
            if missing_beats:
                raise ValueError(f"Plan missing beats: {missing_beats}")

            # Compile final scene list in exact beat order
            final_scenes = []
            for i, (text, dur) in enumerate(beats):
                s = scenes_by_beat[i]
                img_prompt = compile_prompt(s, entities_map, shared_style, style_lock=style_lock)
                s["image_prompt"] = img_prompt
                s["duration"] = dur
                s["text"] = text  # Preserved 100% verbatim
                if not s.get("camera_motion"):
                    s["camera_motion"] = "push in"
                if not s.get("video_prompt"):
                    s["video_prompt"] = f"{s.get('camera_motion', 'push in').capitalize()} camera movement on {s.get('subject', text)[:80]}"

                # Parse and normalize extended visual fields
                v_type = str(s.get("visual_type") or "literal").lower()
                valid_types = {"literal", "conceptual", "historical", "abstract", "data", "location", "person", "object"}
                s["visual_type"] = v_type if v_type in valid_types else "literal"

                v_prio = str(s.get("visual_priority") or ("high" if i == 0 else "medium")).lower()
                valid_prios = {"high", "medium", "low"}
                s["visual_priority"] = v_prio if v_prio in valid_prios else ("high" if i == 0 else "medium")

                v_strat = str(s.get("visual_strategy") or "pexels").lower()
                valid_strats = {"pexels", "flux", "hold"}
                s["visual_strategy"] = v_strat if v_strat in valid_strats else "pexels"

                s["continuity_group"] = str(s.get("continuity_group") or f"group_{i // 3}").strip()
                s["shot_scale"] = str(s.get("shot_scale") or s.get("shot") or "medium").strip()
                s["motion_intensity"] = str(s.get("motion_intensity") or "medium").strip()
                s["mood"] = str(s.get("mood") or "cinematic").strip()

                # must_show list
                m_show = s.get("must_show")
                if not isinstance(m_show, list) or not m_show:
                    m_show = []
                    if s.get("subject"):
                        m_show.append(s["subject"].strip()[:40])
                    if s.get("setting"):
                        m_show.append(s["setting"].strip()[:40])
                s["must_show"] = [str(x).strip() for x in m_show if str(x).strip()]

                # should_avoid list
                s_avoid = s.get("should_avoid")
                if not isinstance(s_avoid, list):
                    s_avoid = []
                s["should_avoid"] = [str(x).strip() for x in s_avoid if str(x).strip()]

                # search_queries list (3-6 queries)
                queries = s.get("search_queries")
                if not isinstance(queries, list) or not queries:
                    queries = s.get("broll_keywords") or []
                if not isinstance(queries, list) or not queries:
                    queries = []
                    sub = s.get("subject", "").strip()
                    act = s.get("action", "").strip()
                    setg = s.get("setting", "").strip()
                    if sub and setg:
                        queries.append(f"{sub} {setg}"[:35])
                    if sub and act:
                        queries.append(f"{sub} {act}"[:35])
                    if sub:
                        queries.append(sub[:30])
                    if setg:
                        queries.append(setg[:30])
                clean_queries = [str(q).strip() for q in queries if str(q).strip()]
                s["search_queries"] = clean_queries
                s["broll_keywords"] = clean_queries[:3]

                final_scenes.append(s)

            return {
                "style": shared_style,
                "entities": entities,
                "scenes": final_scenes,
                "is_basic_mode": False
            }, False

        except Exception as e:
            print(f"[Director] Attempt {attempt+1} validation error: {e}")
            if attempt == 0:
                # Retry once with specific error
                contents.append({"role": "model", "parts": [{"text": raw_text}]})
                contents.append({"role": "user", "parts": [{
                    "text": f"Error: {e}. Please correct your output and return the complete JSON with all {len(beats)} beats [0..{len(beats)-1}]."
                }]})

    print("[Director] Director call failed after retry, falling back to basic mode.")
    return basic_mode_plan(beats, style_lock=style_lock), True


def validate_image_with_vision_qa(
    image_path: str,
    narration_text: str,
    api_key: Optional[str] = None
) -> Tuple[Optional[int], Optional[str]]:
    """
    Vision QA (only when VISION_QA=1 and API key is set):
    Evaluates whether the generated image concretely depicts the scene narration.
    Returns (score_0_to_100, note).
    """
    if not is_vision_qa_enabled():
        return None, None

    resolved_key = api_key or get_gemini_api_key()
    if not resolved_key or not os.path.exists(image_path):
        return None, None

    try:
        with open(image_path, "rb") as f:
            img_bytes = f.read()
        b64_data = base64.b64encode(img_bytes).decode("utf-8")

        prompt = f"""Compare this image with the spoken narration line:
Narration: "{narration_text}"

Evaluate how accurately and concretely this image depicts the visual subject, setting, and action described in or implied by the narration.
Return JSON only:
{{
  "score": <0 to 100>,
  "missing": ["<element missing from image>"],
  "note": "<one sentence assessment>"
}}"""

        contents = [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inlineData": {
                            "mimeType": "image/jpeg",
                            "data": b64_data
                        }
                    }
                ]
            }
        ]

        text, _ = generate_content(
            prompt_or_contents=contents,
            thinking_level="low",
            max_output_tokens=1200,
            json_mode=True,
            api_key=resolved_key
        )

        if not text:
            return None, None

        clean_json = text.strip()
        if clean_json.startswith("```"):
            clean_json = re.sub(r'^```(?:json)?\s*', '', clean_json)
            clean_json = re.sub(r'\s*```$', '', clean_json)
        data = json.loads(clean_json)

        score = int(data.get("score", 85))
        note = str(data.get("note", "Accurate visual representation"))
        return score, note
    except Exception as e:
        print(f"[Vision QA] Error: {e}")
        return None, None
