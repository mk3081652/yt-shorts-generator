import asyncio
import os
import re
import socket
import json
import urllib.request
import urllib.error
import aiohttp
from typing import List, Dict, Any, Tuple, Optional
import edge_tts

from engine.config import (
    get_openai_api_key,
    get_elevenlabs_api_key,
    get_elevenlabs_voice_id,
    get_tts_provider
)
from engine.whisper_client import align_words_for_audio

# Curated list of high-retention viral voices (100% Free, Studio Broadcast Quality, Zero Humming)
VOICES = {
    # 💼 Motivational & Finance Topics (Deep, commanding, ElevenLabs-grade authority)
    "en-US-BrianMultilingualNeural": {
        "name": "Brian (Motivational & Finance - Deep 1% Mindset)",
        "gender": "Male",
        "lang": "en-US",
        "vibe": "Deep, commanding, wealth building, alpha power",
        "default_speed": 0.90,
        "recommended_pace": "0.90x (Commanding & Resonant)"
    },
    "en-US-AndrewMultilingualNeural": {
        "name": "Andrew (Motivational & Finance - Charismatic Wealth Mentor)",
        "gender": "Male",
        "lang": "en-US",
        "vibe": "High-status, engaging, financial wisdom, confident",
        "default_speed": 0.92,
        "recommended_pace": "0.92x (Smooth & Engaging)"
    },
    # 🔍 Mysterious Events & Unsolved Enigmas (Dark, chilling, investigative)
    "en-GB-RyanNeural": {
        "name": "Ryan (Mysterious Events - Dark True Crime & British Suspense)",
        "gender": "Male",
        "lang": "en-GB",
        "vibe": "Chilling, investigative, solemn, documentary grit",
        "default_speed": 0.88,
        "recommended_pace": "0.88x (Dark & Gripping)"
    },
    "en-US-GuyNeural": {
        "name": "Guy (Mysterious Events - Cinematic Mystery & Unsolved Files)",
        "gender": "Male",
        "lang": "en-US",
        "vibe": "Atmospheric, deep American narrator, dark revelations",
        "default_speed": 0.88,
        "recommended_pace": "0.88x (Cinematic Suspense)"
    },
    # 🚀 Viral Storytelling (High-retention, punchy facts)
    "en-US-ChristopherNeural": {
        "name": "Christopher (Viral Storytelling - High-CTR Facts & Hooks)",
        "gender": "Male",
        "lang": "en-US",
        "vibe": "Fast-paced, punchy, curiosity-driven",
        "default_speed": 1.00,
        "recommended_pace": "1.00x (Standard Punchy)"
    }
}



def clean_text_for_tts(text: str) -> str:
    """Clean markdown, emojis, asterisks and extra whitespace for natural TTS pronunciation."""
    cleaned = re.sub(r'[*_#`~]', '', text)
    cleaned = re.sub(r'\[.*?\]', '', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def generate_offline_fallback_speech(
    clean_text: str,
    output_audio_path: str
) -> Tuple[str, List[Dict[str, Any]], float]:
    """
    Offline local Windows TTS fallback (zero internet required) using pyttsx3.
    """
    import pyttsx3
    import wave
    
    os.makedirs(os.path.dirname(os.path.abspath(output_audio_path)), exist_ok=True)
    wav_path = output_audio_path.replace('.mp3', '.wav')
    
    engine = pyttsx3.init()
    engine.setProperty('rate', 165)
    engine.save_to_file(clean_text, wav_path)
    engine.runAndWait()
    
    # Measure audio duration from generated wav file
    total_duration = 5.0
    try:
        with wave.open(wav_path, 'rb') as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            total_duration = frames / float(rate)
    except Exception:
        total_duration = max(3.0, len(clean_text.split()) * 0.38)
        
    # Convert wav to mp3 if needed or keep path
    words = clean_text.split()
    word_boundaries = []
    if words:
        time_per_word = total_duration / len(words)
        for i, w in enumerate(words):
            start_t = i * time_per_word
            end_t = (i + 1) * time_per_word
            word_boundaries.append({
                "word": w,
                "start": start_t,
                "end": end_t
            })
            
    return wav_path, word_boundaries, total_duration


def generate_elevenlabs_speech(
    clean_text: str,
    voice_id: str,
    output_audio_path: str,
    api_key: Optional[str] = None
) -> bool:
    """
    Synthesizes expressive neural speech via ElevenLabs API.
    Voice settings tailored for high-retention storytelling (stability 0.40).
    """
    key = api_key or get_elevenlabs_api_key()
    if not key:
        return False

    v_id = voice_id or get_elevenlabs_voice_id()
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{v_id}"
    payload = {
        "text": clean_text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.40,
            "similarity_boost": 0.80,
            "style": 0.35,
            "use_speaker_boost": True
        }
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "xi-api-key": key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read()
            if len(content) > 1000:
                os.makedirs(os.path.dirname(os.path.abspath(output_audio_path)), exist_ok=True)
                with open(output_audio_path, "wb") as f:
                    f.write(content)
                return True
    except Exception as e:
        print(f"[TTS] ElevenLabs synthesis failed: {e}")

    return False


def generate_openai_speech(
    clean_text: str,
    voice_name: str,
    output_audio_path: str,
    api_key: Optional[str] = None,
    model: str = "tts-1-hd"
) -> bool:
    """
    Synthesizes expressive neural speech via OpenAI TTS-HD.
    """
    key = api_key or get_openai_api_key()
    if not key:
        return False

    url = "https://api.openai.com/v1/audio/speech"
    valid_voices = {"alloy", "echo", "fable", "onyx", "nova", "shimmer"}
    safe_voice = voice_name.lower().replace("openai:", "")
    if safe_voice not in valid_voices:
        safe_voice = "onyx"

    payload = {
        "model": model,
        "input": clean_text,
        "voice": safe_voice,
        "response_format": "mp3",
        "speed": 1.04
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read()
            if len(content) > 1000:
                os.makedirs(os.path.dirname(os.path.abspath(output_audio_path)), exist_ok=True)
                with open(output_audio_path, "wb") as f:
                    f.write(content)
                return True
    except Exception as e:
        print(f"[TTS] OpenAI TTS-HD synthesis failed: {e}")

    return False


def resolve_voice_speeds(voice: str, rate: Any) -> Tuple[float, str]:
    """
    Resolves speed for voices into Edge-TTS rate string (e.g. '-10%', '-15%', '+0%') and float multiplier.
    Provides calibrated natural baselines for each voice:
    - Brian: 0.90 (-10%) deep commanding authority for wealth/motivation
    - Andrew: 0.92 (-8%) charismatic engaging finance mentor
    - Ryan: 0.88 (-12%) dark, chilling true-crime suspense
    - Guy: 0.88 (-12%) atmospheric cinematic mystery narrator
    - Christopher: 1.00 (+0%) viral high-CTR storytelling
    """
    v = (voice or "").lower()
    if "brian" in v:
        base_speed = 0.90
    elif "andrew" in v:
        base_speed = 0.92
    elif "ryan" in v:
        base_speed = 0.88
    elif "guy" in v:
        base_speed = 0.88
    elif "adam" in v or "onyx" in v:
        base_speed = 0.90
    elif "michael" in v or "george" in v:
        base_speed = 0.88
    else:
        base_speed = 1.00

    if not rate or str(rate).strip() in ("", "default"):
        kokoro_spd = base_speed
        edge_pct = int(round((base_speed - 1.0) * 100))
    else:
        s = str(rate).strip().lower().rstrip("x")
        # Direct float e.g. "0.85", "0.75", "0.90", "1.00"
        try:
            val = float(s)
            kokoro_spd = max(0.65, min(1.35, val))
            edge_pct = int(round((val - 1.0) * 100))
        except ValueError:
            m = re.search(r'([+-]?\d+(?:\.\d+)?)%', s)
            if m:
                pct = float(m.group(1))
                if pct == 0:
                    kokoro_spd = base_speed
                    edge_pct = int(round((base_speed - 1.0) * 100))
                else:
                    kokoro_spd = max(0.65, min(1.35, round(base_speed * (1.0 + pct / 100.0), 2)))
                    edge_pct = int(round(pct))
            else:
                kokoro_spd = base_speed
                edge_pct = int(round((base_speed - 1.0) * 100))

    edge_rate = f"{edge_pct:+d}%"
    return kokoro_spd, edge_rate


async def generate_speech_with_words(
    text: str,
    voice: str = "en-US-ChristopherNeural",
    rate: str = "+0%",
    pitch: str = "+0Hz",
    output_audio_path: str = "output_voice.mp3",
    provider: Optional[str] = None
) -> Tuple[str, List[Dict[str, Any]], float]:
    """
    Generates TTS audio file with multi-tier provider routing:
    1. ElevenLabs API (if configured or requested)
    2. OpenAI TTS-HD (if configured or requested)
    3. Edge-TTS (Free, fast neural with WordBoundaries)
    4. Offline pyttsx3 fallback
    """
    clean_text = clean_text_for_tts(text)
    if not clean_text:
        raise ValueError("Script text cannot be empty.")

    req_provider = (provider or get_tts_provider()).lower()
    kokoro_speed, edge_rate_str = resolve_voice_speeds(voice, rate)

    # Map any legacy voice names to clean studio neural voices
    if voice.startswith("kokoro:") or "kokoro" in voice.lower():
        v_sub = voice.replace("kokoro:", "").lower()
        if "adam" in v_sub or "onyx" in v_sub:
            voice = "en-US-BrianMultilingualNeural"
        elif "michael" in v_sub:
            voice = "en-US-GuyNeural"
        elif "george" in v_sub:
            voice = "en-GB-RyanNeural"
        else:
            voice = "en-US-ChristopherNeural"

    # 1. ElevenLabs Premium Route (if configured)
    if req_provider == "elevenlabs" or voice.startswith("elevenlabs:"):
        el_key = get_elevenlabs_api_key()
        if el_key:
            v_id = voice.replace("elevenlabs:", "") if voice.startswith("elevenlabs:") else get_elevenlabs_voice_id()
            if v_id in ("adam", ""):
                v_id = "pNInz6obpgDQGcFmaJgB"
            elif v_id == "rachel":
                v_id = "21m00Tcm4TlvDq8ikWAM"
            ok = generate_elevenlabs_speech(clean_text, v_id, output_audio_path, api_key=el_key)
            if ok and os.path.exists(output_audio_path):
                words, dur = align_words_for_audio(output_audio_path, clean_text)
                return output_audio_path, words, dur
            print("[TTS] ElevenLabs synthesis failed, falling back to next provider...")

    # 2. OpenAI TTS-HD Route (if configured)
    if req_provider in ("openai", "elevenlabs") or voice.startswith("openai:"):
        oa_key = get_openai_api_key()
        if oa_key:
            oa_voice = voice.replace("openai:", "") if voice.startswith("openai:") else "onyx"
            ok = generate_openai_speech(clean_text, oa_voice, output_audio_path, api_key=oa_key)
            if ok and os.path.exists(output_audio_path):
                words, dur = align_words_for_audio(output_audio_path, clean_text, api_key=oa_key)
                return output_audio_path, words, dur
            print("[TTS] OpenAI TTS synthesis failed, falling back to Edge-TTS...")

    # 3. Studio Neural Edge-TTS Route (100% Free, Zero Humming, Native WordBoundaries)
    edge_voice = voice
    if edge_voice.startswith("openai:") or edge_voice.startswith("elevenlabs:") or (edge_voice not in VOICES and "Neural" not in edge_voice):
        if "brian" in edge_voice.lower() or "adam" in edge_voice.lower() or "onyx" in edge_voice.lower():
            edge_voice = "en-US-BrianMultilingualNeural"
        elif "andrew" in edge_voice.lower():
            edge_voice = "en-US-AndrewMultilingualNeural"
        elif "ryan" in edge_voice.lower() or "george" in edge_voice.lower():
            edge_voice = "en-GB-RyanNeural"
        elif "guy" in edge_voice.lower() or "michael" in edge_voice.lower():
            edge_voice = "en-US-GuyNeural"
        else:
            edge_voice = "en-US-ChristopherNeural"

    last_error = None
    
    # Try Edge-TTS with IPv4 connector and retries
    for attempt in range(1, 4):
        try:
            connector = aiohttp.TCPConnector(family=socket.AF_INET)
            comm = edge_tts.Communicate(
                text=clean_text,
                voice=edge_voice,
                rate=edge_rate_str,
                pitch=pitch,
                boundary="WordBoundary",
                connector=connector,
                connect_timeout=12,
                receive_timeout=45
            )

            word_boundaries = []
            audio_chunks = bytearray()

            async for chunk in comm.stream():
                chunk_type = chunk.get("type")
                if chunk_type == "audio":
                    audio_chunks.extend(chunk.get("data", b""))
                elif chunk_type == "WordBoundary":
                    offset_sec = chunk["offset"] / 10_000_000.0
                    duration_sec = chunk["duration"] / 10_000_000.0
                    word_text = chunk.get("text", "").strip()
                    if word_text:
                        word_boundaries.append({
                            "word": word_text,
                            "start": offset_sec,
                            "end": offset_sec + duration_sec
                        })

            if audio_chunks:
                os.makedirs(os.path.dirname(os.path.abspath(output_audio_path)), exist_ok=True)
                with open(output_audio_path, "wb") as f:
                    f.write(audio_chunks)

                total_duration = 0.0
                if word_boundaries:
                    total_duration = word_boundaries[-1]["end"] + 0.35
                else:
                    total_duration = max(2.0, len(clean_text.split()) * 0.35)

                return output_audio_path, word_boundaries, total_duration

        except Exception as e:
            last_error = e
            print(f"[TTS Retry] Attempt {attempt} failed ({e}). Retrying in {attempt * 1.5}s...")
            await asyncio.sleep(attempt * 1.5)

    # 4. Local offline pyttsx3 fallback
    print(f"[TTS Fallback] Edge-TTS unreachable ({last_error}). Switching to offline local Windows engine...")
    return generate_offline_fallback_speech(clean_text, output_audio_path)


def get_available_voices() -> Dict[str, Dict[str, str]]:
    return VOICES
