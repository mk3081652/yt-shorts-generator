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

# Modern, eye-catching, simple viral subtitle presets
# Colors in ASS are &HAABBGGRR (Hex: Alpha, Blue, Green, Red)
STYLE_PRESETS = {
    "hyper_yellow": {
        "name": "Hyper Yellow",
        "font_name": "Arial Black",
        "font_size": 17, # Crisp ~68px on 1080x1920
        "primary_color": "&H0000E6FF", # High-contrast Electric Yellow (R:FF G:E6 B:00)
        "secondary_color": "&H00FFFFFF",
        "outline_color": "&H00000000", # Deep Black razor outline
        "back_color": "&HA0000000",
        "bold": 1,
        "outline": 3.2,
        "shadow": 2.0,
        "alignment": 2, # bottom-center
        "margin_v": 490, # Golden Shorts reading zone
        "uppercase": True,
        "border_style": 1
    },
    "glacier_cyan": {
        "name": "Glacier Cyan",
        "font_name": "Arial Black",
        "font_size": 17,
        "primary_color": "&H00FFF200", # Vivid Ice Cyan (R:00 G:F2 B:FF)
        "secondary_color": "&H00FFFFFF",
        "outline_color": "&H00000000",
        "back_color": "&HA0000000",
        "bold": 1,
        "outline": 3.2,
        "shadow": 2.0,
        "alignment": 2,
        "margin_v": 490,
        "uppercase": True,
        "border_style": 1
    },
    "neon_lime": {
        "name": "Neon Lime",
        "font_name": "Arial Black",
        "font_size": 17,
        "primary_color": "&H0033FF00", # Vivid Electric Lime (R:00 G:FF B:33)
        "secondary_color": "&H00FFFFFF",
        "outline_color": "&H00000000",
        "back_color": "&HA0000000",
        "bold": 1,
        "outline": 3.2,
        "shadow": 2.0,
        "alignment": 2,
        "margin_v": 490,
        "uppercase": True,
        "border_style": 1
    },
    "sunset_coral": {
        "name": "Sunset Coral",
        "font_name": "Arial Black",
        "font_size": 17,
        "primary_color": "&H004455FF", # Trendy Warm Coral / Flame (R:FF G:55 B:44)
        "secondary_color": "&H00FFFFFF",
        "outline_color": "&H00000000",
        "back_color": "&HA0000000",
        "bold": 1,
        "outline": 3.2,
        "shadow": 2.0,
        "alignment": 2,
        "margin_v": 490,
        "uppercase": True,
        "border_style": 1
    },
    "clean": {
        "name": "Cinematic Clean White",
        "font_name": "Arial",
        "font_size": 16, # Clean ~64px on 1080x1920
        "primary_color": "&H00FFFFFF", # Pure Crisp White
        "secondary_color": "&H00FFFFFF",
        "outline_color": "&H80111111", # Soft translucent outline
        "back_color": "&H90000000",
        "bold": 1,
        "outline": 2.2,
        "shadow": 1.5,
        "alignment": 2,
        "margin_v": 490,
        "uppercase": False,
        "border_style": 1
    }
}

# Backward compatibility alias map
STYLE_ALIASES = {
    "viral_pop": "hyper_yellow",
    "mrbeast": "hyper_yellow",
    "neon_pulse": "glacier_cyan",
    "cyberpunk": "glacier_cyan",
    "hormozi": "neon_lime",
    "tok_hype": "sunset_coral",
    "editorial_box": "clean"
}

def clean_word_text(w: str) -> str:
    """Strip markdown asterisks, brackets, quotes, etc."""
    cleaned = re.sub(r'[*_#`~\[\]\(\)\{\}\<\>"]', '', w).strip()
    return cleaned

def generate_ass_subtitles(
    word_boundaries: List[Dict[str, Any]],
    output_ass_path: str,
    style_name: str = "hyper_yellow",
    max_words_per_segment: int = 2,
    margin_v: int = None
) -> str:
    """
    Builds an Advanced SubStation Alpha (.ass) subtitle file.
    Groups words into punchy 1-2 word segments with eye-catching, modern, simple kinetic styling.
    """
    resolved_style_name = STYLE_ALIASES.get(style_name, style_name)
    style = dict(STYLE_PRESETS.get(resolved_style_name, STYLE_PRESETS["hyper_yellow"]))
    if margin_v is not None:
        style["margin_v"] = margin_v
    
    play_res_x = 1080
    play_res_y = 1920
    font_size = style["font_size"] * 4 # ~64-68px on 1080x1920
    border_style = style.get("border_style", 1)

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
Style: ViralDefault,{style['font_name']},{font_size},{style['primary_color']},{style['secondary_color']},{style['outline_color']},{style['back_color']},{style['bold']},0,0,0,100,100,2,0,{border_style},{style['outline'] * 2},{style['shadow'] * 2},{style['alignment']},40,40,{style['margin_v']},1

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

        primary_c = style['primary_color']
        text_content = ' '.join(words_text)

        # Eye-catching, modern, simple micro-pop bounce (snappy 65ms scale pop)
        if resolved_style_name == "clean":
            formatted_text = f"{{\\fscx106\\fscy106\\t(0,60,\\fscx100\\fscy100)\\c{primary_c}&}}{text_content}"
        else:
            formatted_text = f"{{\\fscx112\\fscy112\\t(0,65,\\fscx100\\fscy100)\\c{primary_c}&}}{text_content}"

        dialogue_line = f"Dialogue: 0,{start_time},{end_time},ViralDefault,,0,0,0,,{formatted_text}"
        events.append(dialogue_line)

    full_ass_content = ass_header + "\n".join(events) + "\n"

    os.makedirs(os.path.dirname(os.path.abspath(output_ass_path)), exist_ok=True)
    with open(output_ass_path, "w", encoding="utf-8") as f:
        f.write(full_ass_content)

    return output_ass_path
