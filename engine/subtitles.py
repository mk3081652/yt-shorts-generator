import os
import re
from typing import List, Dict, Any

def format_ass_time(seconds: float) -> str:
    """Format seconds into ASS timestamp: H:MM:SS.cs (centiseconds)"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs >= 100:
        cs = 99
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

# Viral style presets
# Colors in ASS are &HAABBGGRR (Hex: Alpha, Blue, Green, Red)
STYLE_PRESETS = {
    "mrbeast": {
        "name": "MrBeast Viral Yellow",
        "font_name": "Arial Black",
        "font_size": 22,
        "primary_color": "&H0000E6FF", # Bright Punchy Yellow (R:FF G:E6 B:00)
        "secondary_color": "&H00FFFFFF", # White accent
        "outline_color": "&H00000000", # Deep Black
        "back_color": "&H80000000",
        "bold": 1,
        "outline": 5,
        "shadow": 3,
        "alignment": 2, # bottom-center
        "margin_v": 320, # Just above bottom UI overlay
        "uppercase": True
    },
    "hormozi": {
        "name": "Alex Hormozi Neon Green",
        "font_name": "Impact",
        "font_size": 24,
        "primary_color": "&H0033FF00", # Vivid Neon Green (R:00 G:FF B:33)
        "secondary_color": "&H0000FFFF", # Bright Yellow accent
        "outline_color": "&H00000000",
        "back_color": "&HA0000000",
        "bold": 1,
        "outline": 5,
        "shadow": 3,
        "alignment": 2,
        "margin_v": 320, # Just above bottom UI overlay
        "uppercase": True
    },
    "cyberpunk": {
        "name": "Cyberpunk Neon Cyan",
        "font_name": "Arial Black",
        "font_size": 22,
        "primary_color": "&H00FFFF00", # Electric Cyan (R:00 G:FF B:FF)
        "secondary_color": "&H00D400FF", # Magenta accent
        "outline_color": "&H00000000",
        "back_color": "&H60000000",
        "bold": 1,
        "outline": 4.5,
        "shadow": 3,
        "alignment": 2,
        "margin_v": 320, # Just above bottom UI overlay
        "uppercase": True
    },
    "clean": {
        "name": "Cinematic Clean White",
        "font_name": "Arial",
        "font_size": 20,
        "primary_color": "&H00FFFFFF", # Pure White
        "secondary_color": "&H0000E6FF",
        "outline_color": "&H00111111",
        "back_color": "&H90000000",
        "bold": 1,
        "outline": 3.5,
        "shadow": 2,
        "alignment": 2,
        "margin_v": 320, # Just above bottom UI overlay
        "uppercase": False
    }
}

def clean_word_text(w: str) -> str:
    """Strip markdown asterisks, brackets, quotes, etc."""
    cleaned = re.sub(r'[*_#`~\[\]\(\)\{\}\<\>"]', '', w).strip()
    return cleaned

def generate_ass_subtitles(
    word_boundaries: List[Dict[str, Any]],
    output_ass_path: str,
    style_name: str = "mrbeast",
    max_words_per_segment: int = 2,
    margin_v: int = None
) -> str:
    """
    Builds an Advanced SubStation Alpha (.ass) subtitle file.
    Groups words into punchy 1-3 word segments with high-contrast formatting.
    """
    style = dict(STYLE_PRESETS.get(style_name, STYLE_PRESETS["mrbeast"]))
    if margin_v is not None:
        style["margin_v"] = margin_v
    
    play_res_x = 1080
    play_res_y = 1920
    font_size = style["font_size"] * 4 # ~88px for 1080x1920

    ass_header = f"""[Script Info]
Title: Viral YouTube Shorts Subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.601
PlayResX: {play_res_x}
PlayResY: {play_res_y}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: ViralDefault,{style['font_name']},{font_size},{style['primary_color']},{style['secondary_color']},{style['outline_color']},{style['back_color']},{style['bold']},0,0,0,100,100,2,0,1,{style['outline'] * 2},{style['shadow'] * 2},{style['alignment']},40,40,{style['margin_v']},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events = []
    
    if not word_boundaries:
        return output_ass_path

    # Clean words and group into 1-2 punchy words
    clean_items = []
    for item in word_boundaries:
        cw = clean_word_text(item["word"])
        if cw:
            clean_items.append({
                "word": cw,
                "start": item["start"],
                "end": item["end"]
            })

    if not clean_items:
        return output_ass_path

    chunks = []
    current_chunk = []
    
    for item in clean_items:
        current_chunk.append(item)
        word_text = item["word"]
        has_punctuation = any(p in word_text for p in ['.', '!', '?', ',', ';', ':'])
        if len(current_chunk) >= max_words_per_segment or has_punctuation:
            chunks.append(current_chunk)
            current_chunk = []
            
    if current_chunk:
        chunks.append(current_chunk)

    for chunk in chunks:
        start_time = format_ass_time(chunk[0]["start"])
        end_time = format_ass_time(chunk[-1]["end"] + 0.08)
        
        words_text = [w["word"] for w in chunk]
        if style.get("uppercase", True):
            words_text = [w.upper() for w in words_text]

        # PROPER ASS STYLE OVERRIDE TAGS WITH CURLY BRACES!
        # If multiple words, highlight the last punch word in secondary accent color
        if len(words_text) > 1 and style_name in ["mrbeast", "hormozi"]:
            primary_c = style['primary_color']
            accent_c = style['secondary_color']
            # {\\c&H0000E6FF&}FIRST {\\c&H00FFFFFF&}SECOND
            formatted_text = f"{{\\c{primary_c}&}}{words_text[0]} {{\\c{accent_c}&}}{' '.join(words_text[1:])}"
        else:
            primary_c = style['primary_color']
            formatted_text = f"{{\\c{primary_c}&}}{' '.join(words_text)}"

        dialogue_line = f"Dialogue: 0,{start_time},{end_time},ViralDefault,,0,0,0,,{formatted_text}"
        events.append(dialogue_line)

    full_ass_content = ass_header + "\n".join(events) + "\n"

    os.makedirs(os.path.dirname(os.path.abspath(output_ass_path)), exist_ok=True)
    with open(output_ass_path, "w", encoding="utf-8") as f:
        f.write(full_ass_content)

    return output_ass_path
