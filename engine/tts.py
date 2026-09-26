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

# Curated list of high-retention viral voices (4 Kokoro Local AI voices + 1 Christopher Neural voice)
VOICES = {
    # Local Zero-Cost Neural Voices (Kokoro TTS)
    "kokoro:am_adam": {
        "name": "Kokoro Adam (Motivational Authority - Local AI)",
        "gender": "Male",
        "lang": "en-US",
        "vibe": "Deep, Commanding, 1% Mindset"
    },
    "kokoro:am_onyx": {
        "name": "Kokoro Onyx (Motivational Resonant - Local AI)",
        "gender": "Male",
        "lang": "en-US",
        "vibe": "Gritty, Powerful, Discipline"
    },
    "kokoro:am_michael": {
        "name": "Kokoro Michael (True-Crime Mystery - Local AI)",
        "gender": "Male",
        "lang": "en-US",
        "vibe": "Investigative, Chilling, Unsolved"
    },
    "kokoro:bm_george": {
        "name": "Kokoro George (British Suspense - Local AI)",
        "gender": "Male",
        "lang": "en-GB",
        "vibe": "Atmospheric, Classy, Historical"
    },
    # Ultra-Fast Built-in Neural Voice (Free & Instant)
    "en-US-ChristopherNeural": {
        "name": "Christopher (US - Deep & Authoritative / MrBeast style)",
        "gender": "Male",
        "lang": "en-US",
        "vibe": "Storytelling, Facts, Mysteries"
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


async def generate_speech_with_words(
    text: str,
    voice: str = "en-US-ChristopherNeural",
    rate: str = "+10%",
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

    # 0. Kokoro Local AI Route (Zero Cloud Cost)
    if req_provider == "kokoro" or voice.startswith("kokoro:"):
        try:
            import tts_engine
            kokoro_voice = voice.replace("kokoro:", "")
            channel = "mystery" if any(k in kokoro_voice for k in ("george", "michael")) else "motivational"
            voice_type = "alternative" if any(k in kokoro_voice for k in ("onyx", "george")) else "primary"

            # Parse speed from rate string (e.g. "+10%", "-5%", "+0%")
            speed_val = 1.0
            if rate:
                m = re.search(r'([+-]?\d+)', str(rate))
                if m:
                    pct = float(m.group(1))
                    speed_val = max(0.6, min(1.8, 1.0 + (pct / 100.0)))

            engine = tts_engine.KokoroTTSEngine.get_instance()
            out_p, dur = engine.synthesize(
                text=clean_text,
                output_path=output_audio_path,
                voice=kokoro_voice,
                channel=channel,
                voice_type=voice_type,
                speed_override=speed_val
            )
            if os.path.exists(output_audio_path) and os.path.getsize(output_audio_path) > 1000:
                from subtitles import extract_word_timestamps
                words = extract_word_timestamps(output_audio_path, script_text=clean_text)
                return output_audio_path, words, dur
        except Exception as e:
            print(f"[TTS] Kokoro synthesis warning: {e}. Falling back to cloud/offline TTS...")


    # 1. ElevenLabs Premium Route
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

    # 2. OpenAI TTS-HD Route
    if req_provider in ("openai", "elevenlabs") or voice.startswith("openai:"):
        oa_key = get_openai_api_key()
        if oa_key:
            oa_voice = voice.replace("openai:", "") if voice.startswith("openai:") else "onyx"
            ok = generate_openai_speech(clean_text, oa_voice, output_audio_path, api_key=oa_key)
            if ok and os.path.exists(output_audio_path):
                words, dur = align_words_for_audio(output_audio_path, clean_text, api_key=oa_key)
                return output_audio_path, words, dur
            print("[TTS] OpenAI TTS synthesis failed, falling back to Edge-TTS...")

    # 3. Edge-TTS Route (Fast, zero-cost, native WordBoundaries)
    edge_voice = voice
    if edge_voice.startswith("openai:") or edge_voice.startswith("elevenlabs:") or (edge_voice not in VOICES and "Neural" not in edge_voice):
        edge_voice = "en-US-ChristopherNeural"

    last_error = None
    
    # Try Edge-TTS with IPv4 connector and retries
    for attempt in range(1, 4):
        try:
            connector = aiohttp.TCPConnector(family=socket.AF_INET)
            comm = edge_tts.Communicate(
                text=clean_text,
                voice=edge_voice,
                rate=rate,
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
