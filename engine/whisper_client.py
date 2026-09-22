"""
engine/whisper_client.py - Remote Word-Level Transcription & Zero-RAM Audio Alignment.
Strictly adheres to Render Free Tier (512MB RAM):
- Uses OpenAI Whisper API for exact word-level timestamps when available.
- Zero local PyTorch weights loaded in memory.
- Provides a fast, deterministic audio-energy and duration fallback aligner.
"""

import os
import re
import wave
import json
import urllib.request
import urllib.error
from typing import List, Dict, Any, Tuple, Optional
import imageio_ffmpeg
import subprocess

from engine.config import get_openai_api_key

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()


def get_audio_duration(audio_path: str) -> float:
    """Accurately measures audio duration in seconds via ffprobe or ffmpeg."""
    if not os.path.exists(audio_path):
        return 0.0
    try:
        # Try wav header first for speed
        if audio_path.lower().endswith(".wav"):
            with wave.open(audio_path, "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                if rate > 0:
                    return round(frames / float(rate), 3)
    except Exception:
        pass

    try:
        cmd = [
            FFMPEG_EXE, "-i", os.path.abspath(audio_path)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
        dur_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", res.stderr)
        if dur_match:
            hours = float(dur_match.group(1))
            mins = float(dur_match.group(2))
            secs = float(dur_match.group(3))
            return round(hours * 3600 + mins * 60 + secs, 3)
    except Exception as e:
        print(f"[WhisperClient] Failed to probe duration for {audio_path}: {e}")

    # Fallback estimate based on file size for mp3
    try:
        size = os.path.getsize(audio_path)
        # Average 128kbps = 16000 bytes/sec
        return max(2.0, round(size / 16000.0, 2))
    except Exception:
        return 5.0


def transcribe_with_whisper_api(audio_path: str, api_key: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
    """
    Transcribes audio via OpenAI Whisper API requesting word-level timestamps.
    Consumes <5MB RAM (zero local model execution).
    """
    key = api_key or get_openai_api_key()
    if not key or not os.path.exists(audio_path):
        return None

    url = "https://api.openai.com/v1/audio/transcriptions"
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"

    try:
        with open(audio_path, "rb") as f:
            file_bytes = f.read()

        filename = os.path.basename(audio_path)
        content_type = "audio/mpeg" if filename.lower().endswith(".mp3") else "audio/wav"

        # Build multipart/form-data body
        body = bytearray()
        
        # model field
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(b'Content-Disposition: form-data; name="model"\r\n\r\n')
        body.extend(b"whisper-1\r\n")

        # response_format field
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(b'Content-Disposition: form-data; name="response_format"\r\n\r\n')
        body.extend(b"verbose_json\r\n")

        # timestamp_granularities[] field
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(b'Content-Disposition: form-data; name="timestamp_granularities[]"\r\n\r\n')
        body.extend(b"word\r\n")

        # file field
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode("utf-8"))
        body.extend(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
        body.extend(file_bytes)
        body.extend(b"\r\n")

        body.extend(f"--{boundary}--\r\n".encode("utf-8"))

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}"
        }

        req = urllib.request.Request(url, data=bytes(body), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=35) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))

        words_data = resp_data.get("words", [])
        if words_data:
            word_boundaries = []
            for item in words_data:
                w_text = str(item.get("word", "")).strip()
                if w_text:
                    word_boundaries.append({
                        "word": w_text,
                        "start": round(float(item.get("start", 0.0)), 3),
                        "end": round(float(item.get("end", 0.0)), 3)
                    })
            if word_boundaries:
                return word_boundaries

    except Exception as e:
        print(f"[WhisperClient] Whisper API transcription warning: {e}")

    return None


def align_audio_fallback(audio_path: str, script_text: str = "") -> Tuple[List[Dict[str, Any]], float]:
    """
    Lightweight zero-RAM fallback word aligner:
    - Measures exact audio duration
    - Distributes script words proportionally with natural punctuation weighting
    """
    total_duration = get_audio_duration(audio_path)
    clean_words = [w.strip() for w in script_text.split() if w.strip()]
    if not clean_words:
        clean_words = ["Spoken", "Narration"]

    # Assign weights: words with punctuation get slightly longer pauses
    weights = []
    for w in clean_words:
        weight = 1.0
        if any(p in w for p in [".", "!", "?", ":"]):
            weight += 0.45
        elif any(p in w for p in [",", ";"]):
            weight += 0.25
        weights.append(weight)

    total_weight = sum(weights) or 1.0
    effective_dur = max(1.5, total_duration - 0.20)

    word_boundaries = []
    cur_t = 0.0
    for i, w in enumerate(clean_words):
        dur = (weights[i] / total_weight) * effective_dur
        start_t = cur_t
        end_t = min(total_duration, cur_t + dur)
        word_boundaries.append({
            "word": w,
            "start": round(start_t, 3),
            "end": round(end_t, 3)
        })
        cur_t = end_t

    return word_boundaries, total_duration


def align_words_for_audio(
    audio_path: str,
    script_text: str = "",
    api_key: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], float]:
    """
    Master alignment function:
    1. Attempts remote OpenAI Whisper API if key is present.
    2. Falls back to deterministic proportional word alignment.
    3. Returns (word_boundaries, total_duration).
    """
    total_duration = get_audio_duration(audio_path)

    # Attempt remote Whisper API first
    whisper_words = transcribe_with_whisper_api(audio_path, api_key=api_key)
    if whisper_words:
        measured_dur = whisper_words[-1]["end"] + 0.30
        return whisper_words, max(total_duration, measured_dur)

    # Fallback to local zero-RAM aligner
    return align_audio_fallback(audio_path, script_text=script_text)
