import asyncio
import os
import re
import socket
import aiohttp
from typing import List, Dict, Any, Tuple
import edge_tts

# Curated list of high-retention viral voices
VOICES = {
    "en-US-ChristopherNeural": {
        "name": "Christopher (US - Deep & Authoritative / MrBeast style)",
        "gender": "Male",
        "lang": "en-US",
        "vibe": "Storytelling, Facts, Mysteries"
    },
    "en-US-GuyNeural": {
        "name": "Guy (US - Energetic & Fast-Paced)",
        "gender": "Male",
        "lang": "en-US",
        "vibe": "YouTube Viral, Gaming, Quick Tips"
    },
    "en-US-JennyNeural": {
        "name": "Jenny (US - Engaging & Clear)",
        "gender": "Female",
        "lang": "en-US",
        "vibe": "Lifestyle, Psychology, Facts"
    },
    "en-US-AvaNeural": {
        "name": "Ava (US - Modern, Crisp & Professional)",
        "gender": "Female",
        "lang": "en-US",
        "vibe": "Tech, Business, Motivation"
    },
    "en-US-AndrewNeural": {
        "name": "Andrew (US - Cinematic Warm Baritone)",
        "gender": "Male",
        "lang": "en-US",
        "vibe": "Documentary, Deep Quotes, History"
    },
    "en-US-EricNeural": {
        "name": "Eric (US - Dramatic & Intense)",
        "gender": "Male",
        "lang": "en-US",
        "vibe": "Action, Thriller, Conspiracies"
    },
    "en-GB-RyanNeural": {
        "name": "Ryan (UK - Sophisticated British)",
        "gender": "Male",
        "lang": "en-GB",
        "vibe": "Classy Facts, Science, Fiction"
    },
    "en-IN-PrabhatNeural": {
        "name": "Prabhat (Indian English - Dynamic)",
        "gender": "Male",
        "lang": "en-IN",
        "vibe": "India Tech, Finance, Motivation"
    },
    "hi-IN-MadhurNeural": {
        "name": "Madhur (Hindi - Confident & Powerful)",
        "gender": "Male",
        "lang": "hi-IN",
        "vibe": "Hindi Kahaniyan, Facts, Shorts"
    },
    "hi-IN-SwaraNeural": {
        "name": "Swara (Hindi - Melodic & Clear)",
        "gender": "Female",
        "lang": "hi-IN",
        "vibe": "Hindi Motivation, Top 5"
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


async def generate_speech_with_words(
    text: str,
    voice: str = "en-US-ChristopherNeural",
    rate: str = "+10%",
    pitch: str = "+0Hz",
    output_audio_path: str = "output_voice.mp3"
) -> Tuple[str, List[Dict[str, Any]], float]:
    """
    Generates TTS audio file with:
    - IPv4 DNS enforcement (prevents Windows getaddrinfo IPv6 failure)
    - 3-attempt retry with exponential backoff
    - Offline local pyttsx3 fallback if internet is completely down
    """
    clean_text = clean_text_for_tts(text)
    if not clean_text:
        raise ValueError("Script text cannot be empty.")

    if voice not in VOICES:
        voice = "en-US-ChristopherNeural"

    last_error = None
    
    # Try Edge-TTS with IPv4 connector and retries
    for attempt in range(1, 4):
        try:
            # Force IPv4 socket family to bypass buggy Windows IPv6 DNS resolution
            connector = aiohttp.TCPConnector(family=socket.AF_INET)
            comm = edge_tts.Communicate(
                text=clean_text,
                voice=voice,
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

    # If Edge-TTS failed after 3 retries (due to internet / firewall / Microsoft server hiccup):
    print(f"[TTS Fallback] Edge-TTS unreachable ({last_error}). Switching to offline local Windows engine...")
    return generate_offline_fallback_speech(clean_text, output_audio_path)


def get_available_voices() -> Dict[str, Dict[str, str]]:
    return VOICES
