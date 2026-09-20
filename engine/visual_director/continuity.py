"""
continuity.py - Story Continuity Management
Part of the isolated Visual Director module for YouTube Shorts.
Ensures visual anchors (characters, outfits, objects, environments) persist across scene cuts.
"""

from typing import Dict, Any, Optional, List


class ContinuityAnchor:
    """Represents the foundational visual anchors for a story."""

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


def build_fallback_continuity_anchor(script_text: str) -> ContinuityAnchor:
    """Creates a sensible fallback continuity anchor based on script keywords."""
    s_lower = script_text.lower()

    if any(k in s_lower for k in ["miniature", "scale", "mechanics", "tiny", "diecast", "assembly", "model car"]):
        return ContinuityAnchor(
            location="Miniature precision workshop with tiny tool racks and micro workbenches",
            characters="Tiny 1:24 scale figurine mechanics with lifelike facial features",
            clothing="Matching miniature blue workshop overalls with yellow safety accents",
            important_objects="Metallic cherry red miniature sports car chassis, micro chrome suspension springs",
            architecture="Macro-scale workbench, overhead miniature LED strip lighting",
            lighting="Bright focused macro workbench lighting with crisp micro-shadows",
            color_palette="Cherry red, metallic chrome, royal blue, matte charcoal",
            visual_style="Photorealistic 8k tilt-shift macro cinematography, extreme micro detail"
        )
    elif any(k in s_lower for k in ["room 307", "hotel", "security", "corridor", "guards"]):
        return ContinuityAnchor(
            location="Dimly lit luxury hotel corridor with burgundy patterned carpet",
            characters="Two vigilant hotel security guards in matching dark suits",
            clothing="Charcoal black security suits with gold identification badges",
            important_objects="Dark walnut Room 307 door with polished brass numbers '307'",
            architecture="Paneled dark walnut walls with warm brass wall sconces",
            lighting="Moody warm amber sconce lighting casting dramatic long shadows",
            color_palette="Deep burgundy, warm amber, charcoal black, polished brass",
            visual_style="Photorealistic 8k cinematic anamorphic lens, high contrast, suspenseful atmosphere"
        )
    elif any(k in s_lower for k in ["flight", "plane", "radar", "ocean", "black box", "sonar"]):
        return ContinuityAnchor(
            location="Aviation tracking operations and deep ocean search zone",
            characters="Air traffic controllers and naval search crews",
            clothing="Dark navy tactical uniforms and ATC headsets",
            important_objects="Bright glowing green radar sweep, orange flight data recorder",
            architecture="Dim ATC control room and deep ocean floor",
            lighting="High-contrast neon green radar glow and deep-sea submarine spotlights",
            color_palette="Neon green, deep abyss blue, emergency orange, charcoal",
            visual_style="Photorealistic 8k documentary cinematography, sharp realistic textures"
        )
    else:
        return ContinuityAnchor(
            location="Cinematic story environment",
            characters="Story subjects",
            clothing="Era-appropriate consistent attire",
            important_objects="Key story focal items",
            architecture="Realistic environmental details",
            lighting="Cinematic dramatic lighting",
            color_palette="Natural cinematic tones",
            visual_style="Photorealistic 8k, crisp 9:16 vertical framing"
        )


def enforce_continuity_in_prompt(
    base_prompt: str,
    anchor: ContinuityAnchor,
    scene_text: str
) -> str:
    """
    Enriches a scene prompt with vital continuity details if relevant to that scene,
    keeping total prompt length optimal for image generation models (~180-260 chars).
    """
    p = base_prompt.strip()
    s_lower = scene_text.lower()

    # Ensure 9:16 vertical prefix
    if "vertical" not in p.lower() and "9:16" not in p:
        p = f"Vertical 9:16 cinematic shot, {p}"

    # Inject domain-specific anchors if mentioned
    if any(k in s_lower for k in ["miniature", "mechanic", "suspension", "wheel", "engine", "chassis"]):
        if "miniature" not in p.lower() and "tiny" not in p.lower():
            p = f"{p}, miniature 1:24 scale macro shot, tiny figurine mechanics in blue overalls"

    if any(k in s_lower for k in ["room 307", "door", "corridor", "hallway"]):
        if "307" not in p and "corridor" in p.lower():
            p = f"{p}, dark walnut Room 307 door with brass number plate, burgundy carpet"

    return p
