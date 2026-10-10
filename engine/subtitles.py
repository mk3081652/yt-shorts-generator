import os
import re
from typing import List, Dict, Any, Optional, Tuple

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
        "font_size": 56,  # 56px on 1080x1920: perfectly legible, strictly fits 1-2 lines within screen
        "primary_color": "&H0000E6FF",  # Electric Yellow
        "secondary_color": "&H00FFFFFF",
        "outline_color": "&H00000000",  # Deep Black razor outline
        "back_color": "&H80000000",
        "bold": 1,
        "outline": 4.0,
        "shadow": 2.0,
        "alignment": 8,    # Top-center anchor: Line 1 stays stable, Line 2 appears directly below
        "margin_v": 1180,  # 61.4% down screen: golden lower-middle third, clear of subjects & UI
        "margin_l": 60,
        "margin_r": 60,
        "uppercase": True,
        "border_style": 1
    },
    "glacier_cyan": {
        "name": "Glacier Cyan",
        "font_name": "Arial Black",
        "font_size": 56,
        "primary_color": "&H00FFF200",  # Ice Cyan
        "secondary_color": "&H00FFFFFF",
        "outline_color": "&H00000000",
        "back_color": "&H80000000",
        "bold": 1,
        "outline": 4.0,
        "shadow": 2.0,
        "alignment": 8,
        "margin_v": 1180,
        "margin_l": 60,
        "margin_r": 60,
        "uppercase": True,
        "border_style": 1
    },
    "neon_lime": {
        "name": "Neon Lime",
        "font_name": "Arial Black",
        "font_size": 56,
        "primary_color": "&H0033FF00",  # Electric Lime
        "secondary_color": "&H00FFFFFF",
        "outline_color": "&H00000000",
        "back_color": "&H80000000",
        "bold": 1,
        "outline": 4.0,
        "shadow": 2.0,
        "alignment": 8,
        "margin_v": 1180,
        "margin_l": 60,
        "margin_r": 60,
        "uppercase": True,
        "border_style": 1
    },
    "sunset_coral": {
        "name": "Sunset Coral",
        "font_name": "Arial Black",
        "font_size": 56,
        "primary_color": "&H004455FF",  # Flame Coral
        "secondary_color": "&H00FFFFFF",
        "outline_color": "&H00000000",
        "back_color": "&H80000000",
        "bold": 1,
        "outline": 4.0,
        "shadow": 2.0,
        "alignment": 8,
        "margin_v": 1180,
        "margin_l": 60,
        "margin_r": 60,
        "uppercase": True,
        "border_style": 1
    },
    "clean": {
        "name": "Cinematic Clean White",
        "font_name": "Arial Black",
        "font_size": 54,
        "primary_color": "&H00FFFFFF",  # Pure White
        "secondary_color": "&H00FFFFFF",
        "outline_color": "&H00000000",
        "back_color": "&H80000000",
        "bold": 1,
        "outline": 3.5,
        "shadow": 2.0,
        "alignment": 8,
        "margin_v": 1180,
        "margin_l": 60,
        "margin_r": 60,
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

def split_chunk_into_one_or_two_lines(chunk: List[Dict[str, Any]]) -> Tuple[List[int], List[int]]:
    """
    Determines which words belong on Line 1 and Line 2.
    Guarantees strictly 1 or 2 lines, fitting comfortably within screen bounds.
    """
    n = len(chunk)
    if n <= 3:
        return list(range(n)), []

    words = [w["word"] for w in chunk]
    best_split = n // 2
    best_diff = 999
    for s in range(1, n):
        len1 = sum(len(w) for w in words[:s]) + (s - 1)
        len2 = sum(len(w) for w in words[s:]) + (n - s - 1)
        penalty = 0
        if len1 > 18:
            penalty += (len1 - 18) * 10
        if len2 > 18:
            penalty += (len2 - 18) * 10
        diff = abs(len1 - len2) + penalty
        if diff < best_diff:
            best_diff = diff
            best_split = s

    return list(range(best_split)), list(range(best_split, n))


def generate_ass_subtitles(
    word_boundaries: List[Dict[str, Any]],
    output_ass_path: str,
    style_name: str = "hyper_yellow",
    max_words_per_segment: int = 4,   # 4-5 words max per 1-2 line phrase
    margin_v: int = None,
    high_impact_words: Optional[List[str]] = None,
    hook_banner: Optional[Dict[str, Any]] = None,
    progressive_typing: bool = True    # Types live word-by-word as narration speaks
) -> str:
    """
    Builds an Advanced SubStation Alpha (.ass) subtitle file.
    Formats captions into clean 1 or 2 lines strictly within screen bounds.
    With progressive_typing=True, words type out live one-by-one as the voiceover speaks,
    highlighting the current active spoken word with theme highlight and clean white for
    previously typed words.
    """
    resolved_style_name = STYLE_ALIASES.get(style_name, style_name)
    style = dict(STYLE_PRESETS.get(resolved_style_name, STYLE_PRESETS["hyper_yellow"]))
    if margin_v is not None:
        style["margin_v"] = margin_v

    play_res_x = 1080
    play_res_y = 1920
    font_size = style.get("font_size", 56)
    border_style = style.get("border_style", 1)
    ass_margin_v = style.get("margin_v", 1180)
    ass_margin_l = style.get("margin_l", 60)
    ass_margin_r = style.get("margin_r", 60)
    ass_alignment = style.get("alignment", 8)
    outline_val = style.get("outline", 4.0)
    shadow_val = style.get("shadow", 2.0)

    ass_header = f"""[Script Info]
Title: Viral YouTube Shorts Subtitles
ScriptType: v4.00+
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.601
PlayResX: {play_res_x}
PlayResY: {play_res_y}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: ViralDefault,{style['font_name']},{font_size},{style['primary_color']},{style['secondary_color']},{style['outline_color']},{style['back_color']},{style['bold']},0,0,0,100,100,1,0,{border_style},{outline_val},{shadow_val},{ass_alignment},{ass_margin_l},{ass_margin_r},{ass_margin_v},1
Style: HookBanner,Arial Black,52,&H00FFFFFF,&H0000E6FF,&H00000000,&H80000000,1,0,0,0,100,100,1,0,3,4.0,2.0,8,60,60,320,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events = []

    if not word_boundaries:
        return output_ass_path

    # Clean words and group into natural 3-5 word phrases
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
        # Split on strong punctuation (. ! ? ; :) or when reaching 4-5 words
        has_sentence_end = any(p in word_text for p in ['.', '!', '?', ';', ':'])
        if len(current_chunk) >= max_words_per_segment or (len(current_chunk) >= 3 and has_sentence_end):
            chunks.append(current_chunk)
            current_chunk = []
            
    if current_chunk:
        chunks.append(current_chunk)

    # Vibrant highlight colors for active word pop per preset
    STYLE_HIGHLIGHTS = {
        "hyper_yellow": "&H0000FFFF",  # Brilliant Electric Yellow
        "glacier_cyan": "&H00FFF200",  # Ice Cyan
        "neon_lime": "&H0033FF00",     # Neon Lime Energy
        "sunset_coral": "&H004455FF",  # Flame Coral
        "clean": "&H0000E6FF"          # High-contrast Gold
    }

    highlight_c = STYLE_HIGHLIGHTS.get(resolved_style_name, "&H0000FFFF")
    base_c = "&H00FFFFFF"

    for chunk_idx, chunk in enumerate(chunks):
        num_words = len(chunk)
        line1_idxs, line2_idxs = split_chunk_into_one_or_two_lines(chunk)

        for active_idx in range(num_words):
            active_word = chunk[active_idx]
            start_t = active_word["start"]
            if active_idx < num_words - 1:
                end_t = max(start_t + 0.04, chunk[active_idx + 1]["start"])
            else:
                end_t = active_word["end"] + 0.18
                if chunk_idx < len(chunks) - 1:
                    end_t = min(end_t, chunks[chunk_idx + 1][0]["start"])

            start_time = format_ass_time(start_t)
            end_time = format_ass_time(end_t)

            # Build Line 1 formatted words
            l1_words = []
            for w_idx in line1_idxs:
                if not progressive_typing or w_idx <= active_idx:
                    w_item = chunk[w_idx]
                    raw_w = w_item["word"]
                    disp_w = raw_w.upper() if style.get("uppercase", True) else raw_w
                    is_hi = is_high_impact_word(raw_w, high_impact_words)

                    if w_idx == active_idx:
                        l1_words.append(f"{{\\c{highlight_c}&}}{disp_w}")
                    else:
                        c = highlight_c if is_hi else base_c
                        l1_words.append(f"{{\\c{c}&}}{disp_w}")

            # Build Line 2 formatted words
            l2_words = []
            if line2_idxs:
                for w_idx in line2_idxs:
                    if not progressive_typing or w_idx <= active_idx:
                        w_item = chunk[w_idx]
                        raw_w = w_item["word"]
                        disp_w = raw_w.upper() if style.get("uppercase", True) else raw_w
                        is_hi = is_high_impact_word(raw_w, high_impact_words)

                        if w_idx == active_idx:
                            l2_words.append(f"{{\\c{highlight_c}&}}{disp_w}")
                        else:
                            c = highlight_c if is_hi else base_c
                            l2_words.append(f"{{\\c{c}&}}{disp_w}")

            # Assemble: strictly 1 or 2 lines
            if l2_words:
                text_content = f"{' '.join(l1_words)}\\N{' '.join(l2_words)}"
            else:
                text_content = ' '.join(l1_words)

            if text_content.strip():
                dialogue_line = f"Dialogue: 0,{start_time},{end_time},ViralDefault,,0,0,0,,{text_content}"
                events.append(dialogue_line)

    # Bold on-screen hook banner overlay for Scene 1 (Layer 1, top pill box)
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
