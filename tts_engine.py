"""
tts_engine.py - Module 0: Local Kokoro TTS Engine

Local, zero-cost, high-speed neural TTS using Kokoro KPipeline.
Features:
- Singleton pattern maintaining in-memory American ('a') and British ('b') pipelines.
- Channel-specific voice configurations with automatic +10% viral speed adjustment.
- Punctuation preservation ('...', '—', etc.) to trigger natural dramatic breath pauses.
- 24kHz master WAV audio export.
- Self-contained fallback synth for testing and environments without kokoro installed.
"""

import os
import re
import wave
import struct
import logging
import hashlib
import shutil
import subprocess
from typing import Dict, Any, Tuple, Optional, List, Callable

logger = logging.getLogger("kokoro_tts_engine")

# ---------------------------------------------------------------------------
# Channel & Voice Configurations with +10% Speed Pacing
# ---------------------------------------------------------------------------
# Motivational: high authority, deep, commanding (+10% -> 1.15)
# Mystery: true-crime, atmospheric suspense, documentary (+10% -> 0.99 / 0.97)
CHANNEL_CONFIG = {
    "motivational": {
        "channel_name": "Motivational Channel",
        "primary": {
            "voice": "am_adam",
            "lang_code": "a",
            "base_speed": 1.05,
            "speed": 1.15,  # Automatic +10% pacing boost
            "description": "Deep, commanding, high authority"
        },
        "alternative": {
            "voice": "am_onyx",
            "lang_code": "a",
            "base_speed": 1.05,
            "speed": 1.15,  # Automatic +10% pacing boost
            "description": "Resonant, powerful, gritty"
        }
    },
    "mystery": {
        "channel_name": "Mystery Channel",
        "primary": {
            "voice": "am_michael",
            "lang_code": "a",
            "base_speed": 0.90,
            "speed": 0.99,  # Automatic +10% pacing boost (0.90 * 1.10 = 0.99)
            "description": "Deep, documentary, true-crime tone"
        },
        "alternative": {
            "voice": "bm_george",
            "lang_code": "b",
            "base_speed": 0.88,
            "speed": 0.97,  # Automatic +10% pacing boost (0.88 * 1.10 ≈ 0.97)
            "description": "Gritty British narrator, atmospheric suspense"
        }
    }
}


def normalize_text_for_kokoro(text: str) -> str:
    """
    Cleans spoken text while strictly preserving punctuation ('...', '—', ',', '!', '?')
    to allow Kokoro to generate natural, dramatic breath pauses and suspense pacing.
    Removes markdown formatting, brackets, stage directions, and extraneous whitespace.
    """
    if not text:
        return ""

    cleaned = text.strip()

    # Strip bracketed directions: [Dramatic pause], (whispering), [music swells]
    cleaned = re.sub(r'\[.*?\]', '', cleaned)
    cleaned = re.sub(r'\(.*?\)', '', cleaned)

    # Strip markdown headers, asterisks, bold/italics, quotes
    cleaned = re.sub(r'[*_#`~]', '', cleaned)
    cleaned = re.sub(r'[""\'\']', '', cleaned)

    # Convert varied dashes to standard em dash '—' with proper breathing space
    cleaned = re.sub(r'\s*--\s*', ' — ', cleaned)
    cleaned = re.sub(r'\s*–\s*', ' — ', cleaned)
    cleaned = re.sub(r'\s*—\s*', ' — ', cleaned)

    # Standardize ellipsis to exactly three dots '...' with space after
    cleaned = re.sub(r'\.{2,}', '... ', cleaned)

    # Clean multiple spaces while preserving newlines for phrase boundaries
    cleaned = re.sub(r'[ \t]+', ' ', cleaned)
    cleaned = re.sub(r'\s+([.,!?;:—])', r'\1', cleaned)
    cleaned = cleaned.strip()

    return cleaned


class KokoroTTSEngine:
    """
    Singleton manager for local Kokoro TTS pipelines.
    Maintains resident American ('a') and British ('b') pipelines in memory.
    """
    _instance: Optional["KokoroTTSEngine"] = None
    _pipelines: Dict[str, Any] = {}

    def __new__(cls) -> "KokoroTTSEngine":
        if cls._instance is None:
            cls._instance = super(KokoroTTSEngine, cls).__new__(cls)
            cls._instance._pipelines = {}
        return cls._instance

    @classmethod
    def get_instance(cls) -> "KokoroTTSEngine":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_pipeline(self, lang_code: str = "a") -> Any:
        """
        Retrieves or initializes the resident KPipeline for the given lang_code ('a' or 'b').
        Uses resident singleton instances to avoid reload overhead on subsequent requests.
        """
        lang = lang_code.lower()
        if lang not in ("a", "b"):
            lang = "a"

        if lang in self._pipelines:
            return self._pipelines[lang]

        try:
            from kokoro import KPipeline
            logger.info(f"[KokoroTTS] Initializing local KPipeline for lang_code='{lang}'...")
            pipeline = KPipeline(lang_code=lang, repo_id='hexgrad/Kokoro-82M')
            self._pipelines[lang] = pipeline
            return pipeline
        except ImportError:
            logger.warning("[KokoroTTS] 'kokoro' package not installed. Running in fallback mode.")
            return None
        except Exception as e:
            logger.error(f"[KokoroTTS] Failed to initialize KPipeline('{lang}'): {e}")
            return None

    def synthesize(
        self,
        text: str,
        output_path: str,
        voice: Optional[str] = None,
        channel: str = "motivational",
        voice_type: str = "primary",
        speed_override: Optional[float] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> Tuple[str, float]:
        """
        Synthesizes speech using Kokoro TTS and writes a clean 24kHz WAV or MP3 file.
        Features disk caching and torch inference optimizations for fast generation.

        Args:
            text: Spoken narration script.
            output_path: Target .wav or .mp3 filepath.
            voice: Direct voice name ('am_adam', 'am_onyx', 'am_michael', 'bm_george').
            channel: 'motivational' or 'mystery' (used if voice not directly specified).
            voice_type: 'primary' or 'alternative'.
            speed_override: Custom speed multiplier (defaults to channel-configured pace).
            progress_callback: Optional callback for incremental progress reporting.

        Returns:
            Tuple of (output_path, duration_in_seconds).
        """
        import imageio_ffmpeg

        norm_text = normalize_text_for_kokoro(text)
        if not norm_text:
            raise ValueError("Input text cannot be empty.")

        # Determine voice and language code
        resolved_voice = "am_adam"
        resolved_lang = "a"
        resolved_speed = 1.15

        if voice:
            v_lower = voice.lower().replace("kokoro:", "").strip()
            if "george" in v_lower:
                resolved_voice = "bm_george"
                resolved_lang = "b"
                resolved_speed = 0.97
            elif "michael" in v_lower:
                resolved_voice = "am_michael"
                resolved_lang = "a"
                resolved_speed = 0.99
            elif "onyx" in v_lower:
                resolved_voice = "am_onyx"
                resolved_lang = "a"
                resolved_speed = 1.15
            elif "adam" in v_lower:
                resolved_voice = "am_adam"
                resolved_lang = "a"
                resolved_speed = 1.15
            else:
                channel_key = channel.lower() if channel.lower() in CHANNEL_CONFIG else "motivational"
                voice_key = voice_type.lower() if voice_type.lower() in ("primary", "alternative") else "primary"
                cfg = CHANNEL_CONFIG[channel_key][voice_key]
                resolved_voice = cfg["voice"]
                resolved_lang = cfg["lang_code"]
                resolved_speed = cfg["speed"]
        else:
            channel_key = channel.lower() if channel.lower() in CHANNEL_CONFIG else "motivational"
            voice_key = voice_type.lower() if voice_type.lower() in ("primary", "alternative") else "primary"
            cfg = CHANNEL_CONFIG[channel_key][voice_key]
            resolved_voice = cfg["voice"]
            resolved_lang = cfg["lang_code"]
            resolved_speed = cfg["speed"]

        speed = speed_override if speed_override is not None else resolved_speed

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

        # 1. Fast Cache Check: Master WAV cached audio
        cache_dir = os.path.abspath("outputs/cache/tts")
        os.makedirs(cache_dir, exist_ok=True)
        cache_key = hashlib.sha256(f"{resolved_voice}_{speed:.2f}_{norm_text}".encode("utf-8")).hexdigest()
        cached_wav = os.path.join(cache_dir, f"{cache_key}.wav")

        if os.path.exists(cached_wav) and os.path.getsize(cached_wav) > 1000:
            try:
                with wave.open(cached_wav, "rb") as wf:
                    frames = wf.getnframes()
                    rate = wf.getframerate()
                    dur = round(frames / float(rate), 3)

                if dur > 0.5:
                    if output_path.lower().endswith(".mp3"):
                        cmd = [ffmpeg_exe, "-y", "-i", cached_wav, "-c:a", "libmp3lame", "-b:a", "192k", os.path.abspath(output_path)]
                        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                    else:
                        shutil.copyfile(cached_wav, output_path)

                    logger.info(f"[KokoroTTS Cache Hit] Loaded {dur:.2f}s speech from cache -> {output_path}")
                    if progress_callback:
                        progress_callback(100, "Loaded cached voiceover instantly")
                    return output_path, dur
            except Exception as e:
                logger.warning(f"[KokoroTTS Cache Hit] Cached WAV invalid ({e}), regenerating...")

        # 2. Kokoro Pipeline Inference
        pipeline = self.get_pipeline(resolved_lang)

        if pipeline is not None:
            try:
                import soundfile as sf
                import numpy as np
                import torch

                try:
                    torch.set_num_threads(min(4, os.cpu_count() or 2))
                except Exception:
                    pass

                audio_chunks: List[np.ndarray] = []
                with torch.inference_mode():
                    generator = pipeline(norm_text, voice=resolved_voice, speed=speed)
                    for chunk_idx, (_, _, audio) in enumerate(generator):
                        if audio is not None and len(audio) > 0:
                            audio_chunks.append(audio)
                            if progress_callback:
                                progress_callback(min(90, 20 + chunk_idx * 15), f"Synthesized speech chunk {chunk_idx + 1}...")

                if audio_chunks:
                    full_audio = np.concatenate(audio_chunks)
                    sample_rate = 24000
                    # Write master 24kHz WAV into cache
                    sf.write(cached_wav, full_audio, sample_rate)
                    duration = round(len(full_audio) / float(sample_rate), 3)

                    # Export to requested format
                    if output_path.lower().endswith(".mp3"):
                        cmd = [ffmpeg_exe, "-y", "-i", cached_wav, "-c:a", "libmp3lame", "-b:a", "192k", os.path.abspath(output_path)]
                        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                    else:
                        shutil.copyfile(cached_wav, output_path)

                    logger.info(f"[KokoroTTS] Generated {duration:.2f}s speech with voice '{resolved_voice}' -> {output_path}")
                    return output_path, duration
            except Exception as e:
                logger.error(f"[KokoroTTS] Synthesis failed via Kokoro: {e}. Falling back to natural offline speech.")

        # 3. Fallback synthesizer: Uses local offline pyttsx3 speech (Never synthetic carrier buzz)
        return self._generate_fallback_speech(norm_text, output_path, speed=speed)

    def _generate_fallback_speech(self, text: str, output_path: str, speed: float = 1.0) -> Tuple[str, float]:
        """
        Resilient offline fallback audio generator using local Windows speech (pyttsx3).
        Produces real, intelligible spoken words. Never outputs carrier waves or buzzing tones.
        """
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

        temp_wav = output_path.rsplit(".", 1)[0] + "_fallback_temp.wav"
        try:
            import pyttsx3
            engine = pyttsx3.init()
            rate_val = int(165 * speed)
            engine.setProperty('rate', rate_val)
            engine.save_to_file(text, temp_wav)
            engine.runAndWait()

            dur = 3.0
            if os.path.exists(temp_wav):
                try:
                    with wave.open(temp_wav, "rb") as wf:
                        dur = round(wf.getnframes() / float(wf.getframerate()), 2)
                except Exception:
                    dur = max(2.5, round(len(text.split()) / 2.7, 2))

                if output_path.lower().endswith(".mp3"):
                    cmd = [ffmpeg_exe, "-y", "-i", temp_wav, "-c:a", "libmp3lame", "-b:a", "192k", os.path.abspath(output_path)]
                    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                else:
                    shutil.copyfile(temp_wav, output_path)

                if os.path.exists(temp_wav):
                    try:
                        os.remove(temp_wav)
                    except Exception:
                        pass
                return output_path, dur
        except Exception as e:
            logger.error(f"[KokoroTTS Fallback] pyttsx3 fallback failed: {e}")

        # Emergency silence padding (intelligible empty audio instead of harsh buzz)
        duration = max(2.5, round(len(text.split()) / 2.7, 2))
        cmd = [
            ffmpeg_exe, "-y",
            "-f", "lavfi", "-i", f"anullsrc=r=24000:cl=mono",
            "-t", f"{duration:.2f}",
            "-c:a", "libmp3lame" if output_path.lower().endswith(".mp3") else "pcm_s16le",
            os.path.abspath(output_path)
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return output_path, duration


# Convenience top-level function
def generate_speech(
    text: str,
    output_path: str,
    voice: Optional[str] = None,
    channel: str = "motivational",
    voice_type: str = "primary",
    speed: Optional[float] = None
) -> Tuple[str, float]:
    """Top-level convenience interface for Kokoro TTS generation."""
    engine = KokoroTTSEngine.get_instance()
    return engine.synthesize(
        text=text,
        output_path=output_path,
        voice=voice,
        channel=channel,
        voice_type=voice_type,
        speed_override=speed
    )

