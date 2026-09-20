"""
continuity.py - Continuity Bible & Visual Anchor Management
Part of the Visual Director module for YouTube Shorts.

Establishes and preserves visual anchors across scenes:
- Characters: identity, clothing, age, appearance, scale
- Locations: architectural setting, textures, lighting
- Objects: color, material, markings, scale
- Style: visual style, aspect ratio (always 9:16)
"""

from typing import Dict, Any, Optional, List


class ContinuityAnchor:
    """Legacy compatibility wrapper for continuity data."""

    def __init__(
        self,
        location: str = "",
        characters: str = "",
        clothing: str = "",
        important_objects: str = "",
        architecture: str = "",
        lighting: str = "",
        color_palette: str = "",
        visual_style: str = "photorealistic 8k, cinematic lighting"
    ):
        self.location = location
        self.characters = characters
        self.clothing = clothing
        self.important_objects = important_objects
        self.architecture = architecture
        self.lighting = lighting
        self.color_palette = color_palette
        self.visual_style = visual_style

    def to_dict(self) -> Dict[str, str]:
        return {
            "location": self.location,
            "characters": self.characters,
            "clothing": self.clothing,
            "important_objects": self.important_objects,
            "architecture": self.architecture,
            "lighting": self.lighting,
            "color_palette": self.color_palette,
            "visual_style": self.visual_style
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "ContinuityAnchor":
        if not data or not isinstance(data, dict):
            return cls()
        return cls(
            location=str(data.get("location", "")),
            characters=str(data.get("characters", "")),
            clothing=str(data.get("clothing", "")),
            important_objects=str(data.get("important_objects", "")),
            architecture=str(data.get("architecture", "")),
            lighting=str(data.get("lighting", "")),
            color_palette=str(data.get("color_palette", "")),
            visual_style=str(data.get("visual_style", "photorealistic 8k, cinematic lighting"))
        )


def build_continuity_bible(
    story_analysis: Optional[Dict[str, Any]] = None,
    script_text: str = ""
) -> Dict[str, Any]:
    """
    Constructs the formal Continuity Bible from story analysis or script text.
    Schema:
    {
      "characters": [{"id": "...", "description": "..."}],
      "locations": [{"id": "...", "description": "..."}],
      "objects": [{"id": "...", "description": "..."}],
      "style": {"visual_style": "...", "aspect_ratio": "9:16"}
    }
    """
    if story_analysis and isinstance(story_analysis, dict):
        chars = []
        for c in story_analysis.get("main_characters", []):
            if isinstance(c, dict):
                chars.append({
                    "id": c.get("id", "char"),
                    "description": f"{c.get('name_or_role', '')}: {c.get('description', '')}".strip(": ")
                })
            elif isinstance(c, str):
                chars.append({"id": "char", "description": c})

        locs = []
        for l in story_analysis.get("important_locations", []):
            if isinstance(l, dict):
                locs.append({
                    "id": l.get("id", "loc"),
                    "description": f"{l.get('name', '')}: {l.get('description', '')}".strip(": ")
                })
            elif isinstance(l, str):
                locs.append({"id": "loc", "description": l})

        objs = []
        for o in story_analysis.get("important_objects", []):
            if isinstance(o, dict):
                objs.append({
                    "id": o.get("id", "obj"),
                    "description": f"{o.get('name', '')}: {o.get('description', '')}".strip(": ")
                })
            elif isinstance(o, str):
                objs.append({"id": "obj", "description": o})

        v_style = story_analysis.get("visual_style", "cinematic realistic")

        return {
            "characters": chars,
            "locations": locs,
            "objects": objs,
            "style": {
                "visual_style": v_style,
                "aspect_ratio": "9:16"
            }
        }

    # Fallback directly from script keywords
    s_lower = script_text.lower()
    if any(k in s_lower for k in ["miniature", "scale", "mechanic", "tiny", "chassis", "suspension", "model car"]):
        return {
            "characters": [
                {"id": "tiny_mechanics", "description": "tiny 1:18 scale figurine mechanics in matching dark blue workshop overalls"}
            ],
            "locations": [
                {"id": "micro_workshop", "description": "miniature automotive factory workbench, macro clean lighting"}
            ],
            "objects": [
                {"id": "miniature_supercar", "description": "same red 1:18-scale miniature supercar with metallic red body and black chassis"},
                {"id": "micro_tools", "description": "realistic micro wrenches, tweezers, and miniature installation tools"}
            ],
            "style": {
                "visual_style": "photorealistic macro miniature factory, shallow depth of field, realistic miniature materials",
                "aspect_ratio": "9:16"
            }
        }
    elif any(k in s_lower for k in ["room 307", "hotel", "security", "guard", "corridor", "hallway"]):
        return {
            "characters": [
                {"id": "guards", "description": "two hotel security guards in dark navy uniforms with identification badges"}
            ],
            "locations": [
                {"id": "hotel_hallway", "description": "upscale hotel corridor at night, burgundy patterned carpet, warm amber sconces"}
            ],
            "objects": [
                {"id": "room_307_door", "description": "dark wooden hotel door with brass plaque reading 'Room 307'"}
            ],
            "style": {
                "visual_style": "cinematic realistic, dark atmospheric lighting, subtle suspense",
                "aspect_ratio": "9:16"
            }
        }
    elif any(k in s_lower for k in ["suitcase", "key"]):
        return {
            "characters": [
                {"id": "woman", "description": "woman in private room handling luggage"}
            ],
            "locations": [
                {"id": "room", "description": "quiet private room with focused warm spotlight"}
            ],
            "objects": [
                {"id": "red_suitcase", "description": "vibrant red travel suitcase with silver metal hardware"},
                {"id": "silver_key", "description": "small silver key"}
            ],
            "style": {
                "visual_style": "cinematic realistic, tactile macro details",
                "aspect_ratio": "9:16"
            }
        }
    elif any(k in s_lower for k in ["kitchen", "refrigerator", "water"]):
        return {
            "characters": [
                {"id": "resident", "description": "person in domestic indoor attire"}
            ],
            "locations": [
                {"id": "kitchen", "description": "same modern residential kitchen with clean countertops and stainless appliances"}
            ],
            "objects": [
                {"id": "refrigerator", "description": "stainless steel refrigerator with illuminated interior"},
                {"id": "water_bottle", "description": "clear bottle of water with water droplets"}
            ],
            "style": {
                "visual_style": "cinematic realistic, naturalistic domestic lighting",
                "aspect_ratio": "9:16"
            }
        }

    return {
        "characters": [],
        "locations": [{"id": "environment", "description": "cinematic story environment"}],
        "objects": [],
        "style": {
            "visual_style": "photorealistic 8k, cinematic lighting",
            "aspect_ratio": "9:16"
        }
    }


def build_fallback_continuity_anchor(script_text: str) -> ContinuityAnchor:
    """Maintains backward compatibility for components expecting ContinuityAnchor."""
    bible = build_continuity_bible(script_text=script_text)
    loc_desc = bible["locations"][0]["description"] if bible["locations"] else "Cinematic story environment"
    char_desc = bible["characters"][0]["description"] if bible["characters"] else "Story subjects"
    obj_desc = ", ".join(o["description"] for o in bible["objects"]) if bible["objects"] else "Key story items"
    v_style = bible["style"]["visual_style"]

    return ContinuityAnchor(
        location=loc_desc,
        characters=char_desc,
        clothing=char_desc,
        important_objects=obj_desc,
        architecture=loc_desc,
        lighting="Dramatic atmospheric lighting",
        color_palette="Harmonious cinematic palette",
        visual_style=v_style
    )


def enforce_continuity_in_prompt(
    base_prompt: str,
    bible_or_anchor: Any,
    scene_text: str
) -> str:
    """
    Injects critical continuity details into the scene's image prompt.
    Ensures:
    - 9:16 vertical framing prefix
    - Exact car model/color/scale (1:18 scale, tiny mechanics, dark blue uniforms)
    - Exact door / room number (dark wooden door with brass plaque 'Room 307')
    - Exact object details (red suitcase, small silver key, same kitchen/refrigerator)
    """
    p = base_prompt.strip()
    s_lower = scene_text.lower()

    # Ensure 9:16 vertical composition
    if "vertical" not in p.lower() and "9:16" not in p:
        p = f"Vertical 9:16 cinematic shot, {p}"

    # Extract bible data if dict or anchor
    bible = bible_or_anchor if isinstance(bible_or_anchor, dict) else (
        bible_or_anchor.to_dict() if hasattr(bible_or_anchor, "to_dict") else {}
    )

    # 1. Miniature Car Assembly
    if any(k in s_lower for k in ["miniature", "scale", "mechanic", "tiny", "suspension", "wheel", "chassis", "bolt", "windshield"]):
        if "1:18" not in p and "1:24" not in p and "miniature" not in p.lower():
            p = f"{p}, strict 1:18 miniature scale diorama, tiny figurine mechanics in matching dark blue factory uniforms"
        if "red" not in p.lower() and any(k in s_lower for k in ["car", "supercar", "vehicle", "chassis"]):
            p = f"{p}, red miniature supercar chassis"
        if "tilt-shift" not in p.lower() and "macro" not in p.lower():
            p = f"{p}, macro tilt-shift lens, realistic micro tools"

    # 2. Mystery / Room 307
    if any(k in s_lower for k in ["room 307", "hotel", "security", "guard", "corridor", "hallway", "door"]):
        if "307" not in p and any(k in s_lower for k in ["door", "room"]):
            p = f"{p}, dark wooden hotel door with brass plaque reading 'Room 307'"
        if "guard" in s_lower and "navy" not in p.lower():
            p = f"{p}, two hotel security guards in matching dark navy uniforms"
        if "corridor" in s_lower or "hallway" in s_lower:
            p = f"{p}, same upscale hotel hallway with burgundy patterned carpet"

    # 3. Suitcase / Key
    if any(k in s_lower for k in ["suitcase", "key", "luggage"]):
        if "suitcase" in s_lower and "red" not in p.lower():
            p = f"{p}, vibrant red travel suitcase with metal clasps"
        if "key" in s_lower and "silver" not in p.lower():
            p = f"{p}, small silver key"

    # 4. Kitchen / Refrigerator
    if any(k in s_lower for k in ["kitchen", "refrigerator", "fridge", "water"]):
        if "kitchen" in s_lower:
            p = f"{p}, same modern kitchen with clean countertops"
        if "refrigerator" in s_lower or "fridge" in s_lower:
            p = f"{p}, stainless steel refrigerator with cool interior illumination"

    return p
