import os
import re
from typing import List, Dict, Any, Optional

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
# alignment: 5 = center-screen (middle-center) — keeps eyes locked in the middle-third
# MarginV for alignment=5: distance from the vertical center (positive = above center)
# On 1920px screen: center=960px. MarginV=-80 places text ~80px BELOW center (lower-middle-third)
STYLE_PRESETS = {
    "hyper_yellow": {
        "name": "Hyper Yellow",
        "font_name": "Arial Black",
        "font_size": 19,  # ~76px on 1080x1920 — large enough to read in 0.5s glance
        "primary_color": "&H0000E6FF",  # Electric Yellow
        "secondary_color": "&H00FFFFFF",
        "outline_color": "&H00000000",  # Deep Black razor outline
        "back_color": "&HA0000000",
        "bold": 1,
        "outline": 3.5,
        "shadow": 2.0,
        "alignment": 5,    # Middle-center — eye-lock zone
        "margin_v": -80,   # Slightly below center = lower-middle-third
        "uppercase": True,
        "border_style": 1
    },
    "glacier_cyan": {
        "name": "Glacier Cyan",
        "font_name": "Arial Black",
        "font_size": 19,
        "primary_color": "&H00FFF200",  # Ice Cyan
        "secondary_color": "&H00FFFFFF",
        "outline_color": "&H00000000",
        "back_color": "&HA0000000",
        "bold": 1,
        "outline": 3.5,
        "shadow": 2.0,
        "alignment": 5,
        "margin_v": -80,
        "uppercase": True,
        "border_style": 1
    },
    "neon_lime": {
        "name": "Neon Lime",
        "font_name": "Arial Black",
        "font_size": 19,
        "primary_color": "&H0033FF00",  # Electric Lime
        "secondary_color": "&H00FFFFFF",
        "outline_color": "&H00000000",
        "back_color": "&HA0000000",
        "bold": 1,
        "outline": 3.5,
        "shadow": 2.0,
        "alignment": 5,
        "margin_v": -80,
        "uppercase": True,
        "border_style": 1
    },
    "sunset_coral": {
        "name": "Sunset Coral",
        "font_name": "Arial Black",
        "font_size": 19,
        "primary_color": "&H004455FF",  # Flame Coral
        "secondary_color": "&H00FFFFFF",
        "outline_color": "&H00000000",
        "back_color": "&HA0000000",
        "bold": 1,
        "outline": 3.5,
        "shadow": 2.0,
        "alignment": 5,
        "margin_v": -80,
        "uppercase": True,
        "border_style": 1
    },
    "clean": {
        "name": "Cinematic Clean White",
        "font_name": "Arial Black",
        "font_size": 18,
        "primary_color": "&H00FFFFFF",  # Pure White
        "secondary_color": "&H00FFFFFF",
        "outline_color": "&H80111111",
        "back_color": "&H90000000",
        "bold": 1,
        "outline": 2.5,
        "shadow": 1.5,
        "alignment": 5,
        "margin_v": -80,
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

STYLE_ACCENTS = {
    "hyper_yellow": "&H00FFFFFF",  # Pure White pop on Yellow
    "glacier_cyan": "&H0033FF00",  # Electric Lime pop on Cyan
    "neon_lime": "&H0000E6FF",     # Electric Yellow pop on Lime
    "sunset_coral": "&H0000E6FF",  # Bright Yellow pop on Coral
    "clean": "&H0000E6FF"          # High-contrast Gold pop on Clean White
}

def clean_word_text(w: str) -> str:
    """Strip markdown asterisks, brackets, quotes, etc."""
    cleaned = re.sub(r'[*_#`~\[\]\(\)\{\}\<\>"]', '', w).strip()
    return cleaned

def is_high_impact_word(word: str, scene_keywords: Optional[List[str]] = None) -> bool:
    r"""
    Identifies words warranting kinetic emphasis:
    - Numbers, percentages, money, quantities (\d+)
    - ALL-CAPS words of 2+ chars (MH370, NEVER, DONT, SHOCKED, TRUTH)
    - Explicit keywords flagged in scene prompt metadata / high_impact_words
    """
    clean = re.sub(r'^[^\w]+|[^\w]+$', '', word)
    if not clean:
        return False

    # 1. Numbers / metrics / stats
    if re.search(r'\d', clean):
        return True

    # 2. ALL-CAPS words
    if len(clean) >= 2 and clean.isupper() and clean.isalpha():
        if clean not in {"A", "AN", "IN", "ON", "AT", "TO", "OF", "IF", "IS", "IT", "AND", "THE"}:
            return True

    # 3. Explicit keywords hook (from scene high_impact_words / prompt metadata)
    if scene_keywords:
        low_clean = clean.lower()
        for kw in scene_keywords:
            if kw and (kw.lower() == low_clean or kw.lower() in low_clean):
                return True

    return False

def generate_ass_subtitles(
    word_boundaries: List[Dict[str, Any]],
    output_ass_path: str,
    style_name: str = "hyper_yellow",
    max_words_per_segment: int = 3,   # 1-3 words per cut for max retention
    margin_v: int = None,
    high_impact_words: Optional[List[str]] = None,
    hook_banner: Optional[Dict[str, Any]] = None
) -> str:
    """
    Builds an Advanced SubStation Alpha (.ass) subtitle file.
    Groups words into punchy 1-3 word segments shown in the middle-third of the
    screen (alignment=5, center-screen). Each word segment pops in with a
    kinetic scale bounce. High-impact words (numbers, ALL-CAPS, keywords)
    get accent color + 120% scale pop for maximum eye-lock retention.
    Optional bold hook banner overlay at top for Scene 1.
    """
    resolved_style_name = STYLE_ALIASES.get(style_name, style_name)
    style = dict(STYLE_PRESETS.get(resolved_style_name, STYLE_PRESETS["hyper_yellow"]))
    if margin_v is not None:
        style["margin_v"] = margin_v

    play_res_x = 1080
    play_res_y = 1920
    font_size = style["font_size"] * 4  # 19*4=76px on 1080x1920
    border_style = style.get("border_style", 1)
    # MarginV in ASS for alignment=5 is measured from bottom (same as alignment=2)
    # But to position at center, we rely on alignment=5 which already centers vertically.
    # MarginV here shifts from the center: positive shifts up, negative shifts down.
    ass_margin_v = max(0, style["margin_v"]) if style["margin_v"] >= 0 else 0

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
Style: ViralDefault,{style['font_name']},{font_size},{style['primary_color']},{style['secondary_color']},{style['outline_color']},{style['back_color']},{style['bold']},0,0,0,100,100,2,0,{border_style},{style['outline'] * 2},{style['shadow'] * 2},{style['alignment']},40,40,{ass_margin_v},1
Style: HookBanner,Arial Black,56,&H00FFFFFF,&H0000E6FF,&H00000000,&HA0000000,1,0,0,0,100,100,2,0,3,4.0,2.0,8,60,60,310,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events = []

    if not word_boundaries:
        return output_ass_path

    # Clean words and group into 1-3 punchy words
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

    # Vibrant highlight colors for active word karaoke pop per preset
    STYLE_HIGHLIGHTS = {
        "hyper_yellow": "&H0000FFFF",  # Brilliant Electric Yellow
        "glacier_cyan": "&H00FFF200",  # Ice Cyan
        "neon_lime": "&H0033FF00",     # Neon Lime Energy
        "sunset_coral": "&H004455FF",  # Flame Coral
        "clean": "&H0000E6FF"          # High-contrast Gold
    }

    highlight_c = STYLE_HIGHLIGHTS.get(resolved_style_name, "&H0000FFFF")
    base_c = "&H00FFFFFF"

    for chunk in chunks:
        num_words = len(chunk)
        for active_idx in range(num_words):
            active_word = chunk[active_idx]
            start_t = active_word["start"]
            if active_idx < num_words - 1:
                end_t = max(start_t + 0.05, chunk[active_idx + 1]["start"])
            else:
                end_t = active_word["end"] + 0.12

            start_time = format_ass_time(start_t)
            end_time = format_ass_time(end_t)

            words_formatted = []
            for w_idx, w_item in enumerate(chunk):
                raw_w = w_item["word"]
                disp_w = raw_w.upper() if style.get("uppercase", True) else raw_w
                is_hi = is_high_impact_word(raw_w, high_impact_words)

                if w_idx == active_idx:
                    # Active spoken word in bright highlight color with kinetic scale bounce
                    if is_hi:
                        words_formatted.append(f"{{\\c{highlight_c}&\\fscx120\\fscy120}}{disp_w}{{\\c{base_c}&\\fscx100\\fscy100}}")
                    else:
                        words_formatted.append(f"{{\\c{highlight_c}&\\fscx110\\fscy110}}{disp_w}{{\\c{base_c}&\\fscx100\\fscy100}}")
                else:
                    # Non-active word in the current chunk
                    if is_hi:
                        words_formatted.append(f"{{\\c{highlight_c}&\\fscx120\\fscy120}}{disp_w}{{\\c{base_c}&\\fscx100\\fscy100}}")
                    else:
                        words_formatted.append(f"{{\\c{base_c}&}}{disp_w}")

            text_content = ' '.join(words_formatted)
            dialogue_line = f"Dialogue: 0,{start_time},{end_time},ViralDefault,,0,0,0,,{text_content}"
            events.append(dialogue_line)

    # Bold on-screen hook banner overlay for Scene 1 (Layer 1, non-interfering top pill box)
    if hook_banner and hook_banner.get("text"):
        hb_text = str(hook_banner["text"]).strip()
        if hb_text:
            hb_start = format_ass_time(float(hook_banner.get("start", 0.0)))
            hb_end = format_ass_time(float(hook_banner.get("end", 2.6)))
            hb_clean = hb_text.upper()
            hook_line = f"Dialogue: 1,{hb_start},{hb_end},HookBanner,,0,0,0,,{{\\fad(150,200)}}{hb_clean}"
            events.insert(0, hook_line)

    full_ass_content = ass_header + "\n".join(events) + "\n"

    os.makedirs(os.path.dirname(os.path.abspath(output_ass_path)), exist_ok=True)
    with open(output_ass_path, "w", encoding="utf-8") as f:
        f.write(full_ass_content)

    return output_ass_path
