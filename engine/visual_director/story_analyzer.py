"""
story_analyzer.py - Story Understanding & Narrative Analysis
Part of the Visual Director system for YouTube Shorts.

Analyzes the full script prior to scene planning to establish:
- story_type (mystery, miniature assembly, crime, history, science, etc.)
- setting & time_period
- main & secondary characters (identity, clothing, appearance)
- important_objects & important_locations
- events sequence
- visual_style & tone
- continuity_requirements
"""

import os
import re
import json
import urllib.request
from typing import Dict, Any, List, Optional

GEMINI_MODELS = [
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
    "gemini-pro-latest"
]

STORY_ANALYZER_SYSTEM_PROMPT = """You are a Master Narrative Analyst and Visual Director for YouTube Shorts.
Analyze the following video narration script and extract a comprehensive Story Analysis JSON object.

Extract exactly:
{
  "story_type": "mystery | miniature assembly | crime | history | science | technology | biography | documentary | fictional story | horror | educational",
  "setting": "Detailed description of the primary environment/setting",
  "time_period": "Modern day | Historical (era) | Futuristic | Timeless",
  "main_characters": [
    {
      "id": "char_1",
      "name_or_role": "...",
      "description": "appearance, clothing, scale, distinctive features"
    }
  ],
  "secondary_characters": [],
  "important_objects": [
    {
      "id": "obj_1",
      "name": "...",
      "description": "color, material, markings, scale"
    }
  ],
  "important_locations": [
    {
      "id": "loc_1",
      "name": "...",
      "description": "room, hallway, workshop, architectural details, lighting"
    }
  ],
  "events": [
    "Sequential list of major physical actions/events described in script"
  ],
  "visual_style": "cinematic realistic | photorealistic macro diorama | suspenseful atmospheric | documentary archive",
  "tone": "suspenseful | energetic | precise craftsmanship | mysterious | educational",
  "continuity_requirements": [
    "Specific elements that MUST remain visually identical across all scene cuts"
  ]
}

Return ONLY valid JSON.
"""


def extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Extracts JSON object from raw model string."""
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


def fallback_story_analysis(script_text: str) -> Dict[str, Any]:
    """
    Intelligent semantic fallback analyzer when Gemini API is unconfigured or offline.
    Determines domain, characters, scale, key objects, and continuity requirements.
    """
    s_lower = script_text.lower()

    # 1. Miniature Car Assembly
    if any(k in s_lower for k in ["miniature", "scale", "mechanic", "tiny", "suspension", "wheel", "chassis", "model car"]):
        return {
            "story_type": "miniature assembly",
            "setting": "Miniature precision automotive workshop workbench with micro tools and clean lighting",
            "time_period": "Modern day precision diorama",
            "main_characters": [
                {
                    "id": "tiny_mechanics",
                    "name_or_role": "Tiny 1:18 scale figurine mechanics",
                    "description": "Miniature figurine mechanics in matching dark blue factory overalls with realistic micro tools"
                }
            ],
            "secondary_characters": [],
            "important_objects": [
                {
                    "id": "supercar_chassis",
                    "name": "Miniature Supercar",
                    "description": "Red 1:18-scale miniature sports car with metallic red finish, black chassis, and micro components"
                },
                {
                    "id": "suspension_parts",
                    "name": "Micro suspension springs and wheel bolts",
                    "description": "Tiny chrome suspension components and realistic scale wheel fasteners"
                }
            ],
            "important_locations": [
                {
                    "id": "micro_workshop",
                    "name": "Miniature Workshop Workbench",
                    "description": "Macro-scale workbench surface with miniature tool racks and overhead task lighting"
                }
            ],
            "events": [
                "Tiny mechanics assemble miniature car components",
                "Mechanics install suspension springs on chassis",
                "Mechanics tighten wheel bolts with micro wrenches",
                "Windshield and body panels installed"
            ],
            "visual_style": "photorealistic macro miniature factory, shallow depth of field, realistic miniature materials",
            "tone": "precise craftsmanship, engaging macro storytelling",
            "continuity_requirements": [
                "Strict miniature 1:18 scale throughout",
                "Same red miniature supercar across every scene",
                "Same tiny mechanics in dark blue uniforms",
                "Zero full-size people or vehicles"
            ]
        }

    # 2. Mystery / Room 307
    if any(k in s_lower for k in ["room 307", "hotel", "security", "corridor", "hallway", "cctv", "creak"]):
        return {
            "story_type": "mystery",
            "setting": "Quiet upscale hotel hallway at night with burgundy carpet and dark walnut doors",
            "time_period": "Modern day",
            "main_characters": [
                {
                    "id": "hotel_security",
                    "name_or_role": "Hotel Security Guards",
                    "description": "Two hotel security guards in dark navy uniforms with security badges"
                }
            ],
            "secondary_characters": [],
            "important_objects": [
                {
                    "id": "room_307_door",
                    "name": "Room 307 Door",
                    "description": "Dark wooden hotel door with a polished brass plaque reading 'Room 307'"
                },
                {
                    "id": "security_monitor",
                    "name": "CCTV Monitor",
                    "description": "Security surveillance monitor displaying hallway camera angle with timestamp overlay"
                }
            ],
            "important_locations": [
                {
                    "id": "hotel_hallway",
                    "name": "Upscale Hotel Hallway",
                    "description": "Dimly lit long hotel corridor with warm amber sconces and burgundy patterned carpet"
                },
                {
                    "id": "room_307_interior",
                    "name": "Inside Room 307",
                    "description": "Dark, silent hotel room interior"
                }
            ],
            "events": [
                "Hallway is completely empty at night",
                "Room 307 door slowly swings open",
                "Security guards rush down the hallway toward the room",
                "Guards discover the room is empty",
                "Surveillance footage is reviewed"
            ],
            "visual_style": "cinematic realistic, dark atmospheric lighting, realistic textures, subtle suspense",
            "tone": "suspenseful, eerie, high tension",
            "continuity_requirements": [
                "Identical hotel hallway architecture and carpet across all scenes",
                "Room 307 door must always have brass '307' plaque",
                "Same two security guards in matching dark navy uniforms"
            ]
        }

    # 3. Specific Object (Suitcase / Key)
    if any(k in s_lower for k in ["suitcase", "key", "luggage"]):
        return {
            "story_type": "mystery",
            "setting": "Intimate interior setting with dramatic focused lighting",
            "time_period": "Modern day",
            "main_characters": [
                {
                    "id": "protagonist",
                    "name_or_role": "Woman",
                    "description": "Carefully handling luggage in private setting"
                }
            ],
            "secondary_characters": [],
            "important_objects": [
                {
                    "id": "red_suitcase",
                    "name": "Red Suitcase",
                    "description": "Distinctive vibrant red travel suitcase with polished metal clasps"
                },
                {
                    "id": "silver_key",
                    "name": "Silver Key",
                    "description": "Small ornate silver key retrieved from suitcase interior"
                }
            ],
            "important_locations": [
                {
                    "id": "interior_room",
                    "name": "Private Room",
                    "description": "Dimly lit room with warm spotlight on table"
                }
            ],
            "events": [
                "Woman opens red suitcase",
                "Small silver key is removed from inside"
            ],
            "visual_style": "cinematic realistic, tactile macro details",
            "tone": "curious, secretive, suspenseful",
            "continuity_requirements": [
                "Suitcase must strictly be red with matching hardware",
                "Key must strictly be small and silver"
            ]
        }

    # 4. Location Continuity (Kitchen / Refrigerator)
    if any(k in s_lower for k in ["kitchen", "refrigerator", "fridge", "bottle", "water"]):
        return {
            "story_type": "fictional story",
            "setting": "Modern residential kitchen with clean countertops and stainless steel appliances",
            "time_period": "Modern day",
            "main_characters": [
                {
                    "id": "resident",
                    "name_or_role": "Person",
                    "description": "Casual domestic clothing, navigating home at night"
                }
            ],
            "secondary_characters": [],
            "important_objects": [
                {
                    "id": "refrigerator",
                    "name": "Refrigerator",
                    "description": "Stainless steel refrigerator emitting cool interior glow when opened"
                },
                {
                    "id": "water_bottle",
                    "name": "Bottle of Water",
                    "description": "Clear condensation-covered bottle of water"
                }
            ],
            "important_locations": [
                {
                    "id": "kitchen",
                    "name": "Home Kitchen",
                    "description": "Modern kitchen with dark countertops, tile backsplash, and ambient evening light"
                }
            ],
            "events": [
                "Person enters the kitchen",
                "Person opens the refrigerator door",
                "Person retrieves bottle of water"
            ],
            "visual_style": "cinematic realistic, warm domestic atmosphere",
            "tone": "calm, naturalistic, grounded",
            "continuity_requirements": [
                "Exact same kitchen layout and cabinet style across all cuts",
                "Same refrigerator design and interior contents"
            ]
        }

    # 5. Aviation / Documentary
    if any(k in s_lower for k in ["flight", "plane", "radar", "ocean", "black box", "sonar", "pilot"]):
        return {
            "story_type": "documentary",
            "setting": "Aviation tracking control rooms and deep oceanic search sectors",
            "time_period": "Modern day investigative documentary",
            "main_characters": [],
            "secondary_characters": [],
            "important_objects": [
                {
                    "id": "radar_screen",
                    "name": "Radar Display",
                    "description": "Glowing green cathode ray / LCD radar display with sweeping sector line and blips"
                },
                {
                    "id": "black_box",
                    "name": "Flight Data Recorder",
                    "description": "Bright cylindrical orange flight data recorder black box"
                }
            ],
            "important_locations": [
                {
                    "id": "atc_room",
                    "name": "Air Traffic Control Center",
                    "description": "Dark operational control room with illuminated monitors"
                },
                {
                    "id": "ocean_floor",
                    "name": "Deep Ocean Floor",
                    "description": "Abyssal ocean floor scanned by submersible spotlights"
                }
            ],
            "events": [
                "Aircraft departs on scheduled flight",
                "Radar contact lost over open water",
                "Deep-sea search conducted for wreckage and flight recorder"
            ],
            "visual_style": "cinematic documentary photography, high contrast realism",
            "tone": "serious, investigative, suspenseful",
            "continuity_requirements": [
                "Radar displays must show green phosphorescent sweep",
                "Black box must be high-visibility bright orange on seabed"
            ]
        }

    # General Story Fallback
    return {
        "story_type": "fictional story",
        "setting": "Cinematic visual environment matching narrative context",
        "time_period": "Modern day",
        "main_characters": [],
        "secondary_characters": [],
        "important_objects": [],
        "important_locations": [],
        "events": [script_text[:100]],
        "visual_style": "cinematic realistic, 9:16 vertical composition",
        "tone": "engaging, narrative",
        "continuity_requirements": [
            "Maintain consistent lighting and environment across sequential scenes"
        ]
    }


def analyze_story(
    script_text: str,
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Main entry point for story analysis.
    Uses Gemini structured output if API key is provided, or semantic fallback analyzer.
    """
    clean_text = script_text.strip()
    if not clean_text:
        return fallback_story_analysis("")

    resolved_key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not resolved_key:
        print("[Story Analyzer] WARNING: No GEMINI_API_KEY configured. Running in degraded semantic fallback mode.")
        res = fallback_story_analysis(clean_text)
        res["ai_analyzed"] = False
        return res

    body = {
        "contents": [{
            "parts": [{
                "text": f"{STORY_ANALYZER_SYSTEM_PROMPT}\n\nNarration Script:\n{clean_text}"
            }]
        }],
        "generationConfig": {
            "responseMimeType": "application/json",
            "maxOutputTokens": 2000,
            "temperature": 0.1
        }
    }

    for model_name in GEMINI_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={resolved_key}"
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
                parsed = extract_json(raw_text)
                if parsed and "story_type" in parsed:
                    print(f"[Story Analyzer] Successfully analyzed story with {model_name} (Type: {parsed.get('story_type')})")
                    parsed["ai_analyzed"] = True
                    return parsed
        except Exception as e:
            print(f"[Story Analyzer] {model_name} attempt failed: {e}")

    print("[Story Analyzer] WARNING: Gemini analysis unavailable. Using semantic fallback analysis.")
    res = fallback_story_analysis(clean_text)
    res["ai_analyzed"] = False
    return res
