"""
subtitles.py - Module 2: Dynamic Word-Level Styled Subtitles

Features:
- Whisper word-level timestamps extraction (word_timestamps=True).
- Chunks subtitles into 1 to 3 words maximum per screen event.
- Vertical center-third placement (1080x1920 canvas, Alignment=5).
- Bold uppercase typography (Montserrat Black / Impact, Fontsize ~78).
- Pure white text with thick black outline (BorderStyle=1, Outline=5, Shadow=2).
- Active word karaoke highlighting in bright Electric Yellow (&H0000FFFF&),
  resetting to white once vocalization completes.
"""

import os
import re
import json
import subprocess
from typing import List, Dict, Any, Optional, Tuple

# Colors in ASS are &HAABBGGRR (Alpha, Blue, Green, Red)
COLOR_WHITE = "&H00FFFFFF&"
COLOR_YELLOW = "&H0000FFFF&"  # Electric Yellow: R=FF, G=FF, B=00
COLOR_BLACK = "&H00000000&"   # Deep Black


def format_ass_timestamp(seconds: float) -> str:
    """Format seconds into ASS timestamp: H:MM:SS.cs (centiseconds)."""
    if seconds < 0:
        seconds = 0.0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs >= 100:
        cs = 99
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def extract_word_timestamps(
    audio_path: str,
    script_text: str = "",
    openai_api_key: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Extracts word-level timestamps from audio using:
    1. Local OpenAI Whisper library if installed (word_timestamps=True).
    2. OpenAI Whisper API if key is present.
    3. Zero-RAM deterministic audio duration aligner as resilient fallback.

    Returns:
        List of dicts: [{"word": "TWO", "start": 0.00, "end": 0.28}, ...]
    """
    if not os.path.exists(audio_path):
        return []

    # 1. Attempt local Whisper model
    try:
        import whisper
        model = whisper.load_model("base")
        result = model.transcribe(audio_path, word_timestamps=True)
        words: List[Dict[str, Any]] = []
        for segment in result.get("segments", []):
            for word_obj in segment.get("words", []):
                clean_w = word_obj.get("word", "").strip()
                if clean_w:
                    words.append({
                        "word": clean_w,
                        "start": round(float(word_obj.get("start", 0.0)), 3),
                        "end": round(float(word_obj.get("end", 0.0)), 3)
                    })
        if words:
            return words
    except Exception:
        pass

    # 2. Attempt remote OpenAI Whisper API if key exists
    api_key = openai_api_key or os.environ.get("OPENAI_API_KEY", "").strip()
    if api_key:
        try:
            from engine.whisper_client import transcribe_with_whisper_api
            api_words = transcribe_with_whisper_api(audio_path, api_key=api_key)
            if api_words:
                return api_words
        except Exception:
            pass

    # 3. Deterministic zero-RAM word aligner
    from engine.whisper_client import get_audio_duration
    total_dur = get_audio_duration(audio_path)
    clean_words = [w.strip() for w in script_text.split() if w.strip()]
    if not clean_words:
        clean_words = ["Spoken", "Narration"]

    weights = []
    for w in clean_words:
        weight = 1.0
        if any(p in w for p in [".", "!", "?", "—", "..."]):
            weight += 0.45
        elif any(p in w for p in [",", ";", ":"]):
            weight += 0.25
        weights.append(weight)

    total_weight = sum(weights) or 1.0
    effective_dur = max(1.5, total_dur - 0.15)

    words = []
    cur_t = 0.0
    for i, w in enumerate(clean_words):
        dur = (weights[i] / total_weight) * effective_dur
        start_t = cur_t
        end_t = min(total_dur, cur_t + dur)
        words.append({
            "word": w,
            "start": round(start_t, 3),
            "end": round(end_t, 3)
        })
        cur_t = end_t

    return words


def chunk_words(
    words: List[Dict[str, Any]],
    max_chunk_size: int = 3
) -> List[List[Dict[str, Any]]]:
    """
    Chunks word stream into 1 to 3 words maximum per screen event.
    Splits immediately on punctuation boundaries to preserve syntactic rhythm.
    """
    chunks: List[List[Dict[str, Any]]] = []
    current_chunk: List[Dict[str, Any]] = []

    for item in words:
        raw_word = item.get("word", "").strip()
        if not raw_word:
            continue

        clean_w = re.sub(r'[*_#`~"\'\[\]\(\)]', '', raw_word).strip()
        item_copy = {
            "word": clean_w.upper(),
            "start": item["start"],
            "end": item["end"]
        }
        current_chunk.append(item_copy)

        has_boundary = any(p in clean_w for p in [".", "!", "?", ",", ";", "—", "..."])
        if len(current_chunk) >= max_chunk_size or has_boundary:
            chunks.append(current_chunk)
            current_chunk = []

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def generate_ass_subtitles(
    word_boundaries: List[Dict[str, Any]],
    output_ass_path: str,
    font_name: str = "Montserrat Black",
    font_size: int = 78,
    canvas_w: int = 1080,
    canvas_h: int = 1920
) -> str:
    """
    Generates an Advanced SubStation Alpha (.ass) subtitle file featuring
    active word karaoke highlighting in bright Electric Yellow.

    Specs:
    - 1080x1920 portrait canvas.
    - Locked to vertical center-third (Alignment=5, MarginV=0).
    - Bold uppercase typography (Montserrat Black / Impact).
    - Thick black outline (Outline=5.0, Shadow=2.0, BorderStyle=1).
    - 1 to 3 words per chunk.
    - Active word highlighted in Electric Yellow (&H0000FFFF&).
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_ass_path)), exist_ok=True)

    header = f"""[Script Info]
Title: High-Retention Viral Shorts Subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.601
PlayResX: {canvas_w}
PlayResY: {canvas_h}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: CenterShorts,{font_name},{font_size},{COLOR_WHITE},{COLOR_YELLOW},{COLOR_BLACK},&H90000000,1,0,0,0,100,100,2,0,1,5.0,2.0,5,40,40,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events: List[str] = []
    chunks = chunk_words(word_boundaries, max_chunk_size=3)

    for chunk in chunks:
        num_words = len(chunk)

        # For each word in the chunk, generate an active event interval
        for active_idx in range(num_words):
            active_word = chunk[active_idx]
            start_t = active_word["start"]

            # End time extends to next word's start, or end of active word + small hold
            if active_idx < num_words - 1:
                end_t = max(start_t + 0.05, chunk[active_idx + 1]["start"])
            else:
                end_t = active_word["end"] + 0.12

            start_str = format_ass_timestamp(start_t)
            end_str = format_ass_timestamp(end_t)

            # Build karaoke string: active word in Yellow, other words in White
            line_parts = []
            for w_idx, w_item in enumerate(chunk):
                w_text = w_item["word"]
                if w_idx == active_idx:
                    # Active word in bright Electric Yellow with kinetic pop scale
                    line_parts.append(f"{{\\c{COLOR_YELLOW}\\fscx108\\fscy108}}{w_text}{{\\c{COLOR_WHITE}\\fscx100\\fscy100}}")
                else:
                    # Inactive word in crisp White
                    line_parts.append(f"{{\\c{COLOR_WHITE}}}{w_text}")

            text_content = " ".join(line_parts)
            dialogue_line = f"Dialogue: 0,{start_str},{end_str},CenterShorts,,0,0,0,,{text_content}"
            events.append(dialogue_line)

    full_ass = header + "\n".join(events) + "\n"

    with open(output_ass_path, "w", encoding="utf-8") as f:
        f.write(full_ass)

    return output_ass_path
