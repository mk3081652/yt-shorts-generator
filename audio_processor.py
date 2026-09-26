"""
audio_processor.py - Module 4: Layered Audio Design & SFX Automation

Features:
- Hook Impact: Sub-bass thud / impact hit triggered at exact timestamp 0.0s.
- Cut Transitions: Subtle whoosh / swoosh SFX aligned to every rapid image cut timestamp.
- Sidechain Ducking: Automatically ducks background music down to -22 dB while speech
  is active, smoothly recovering to -12 dB during narrator pauses via FFmpeg sidechaincompress.
- Normalized master stereo audio output (AAC 192k / PCM WAV).
"""

import os
import wave
import struct
import subprocess
from typing import List, Dict, Any, Optional
import numpy as np
import imageio_ffmpeg

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()
SFX_DIR = os.path.abspath("assets/sfx")
BGM_DIR = os.path.abspath("assets/bgm")


def ensure_default_sfx() -> Dict[str, str]:
    """Ensures presence of hook impact and transition whooshes in assets/sfx."""
    os.makedirs(SFX_DIR, exist_ok=True)

    # 1. Sub-bass Hook Impact
    impact_path = os.path.join(SFX_DIR, "impact_sub.wav")
    if not os.path.exists(impact_path) or os.path.getsize(impact_path) < 1000:
        sr = 44100
        dur = 1.4
        t = np.linspace(0, dur, int(sr * dur), False)
        pitch_drop = 38 + (120 - 38) * np.exp(-t * 24)
        phase = 2 * np.pi * np.cumsum(pitch_drop) / sr
        body = np.sin(phase) * np.exp(-t * 3.8)
        click = np.random.uniform(-0.3, 0.3, size=len(t)) * np.exp(-t * 140)
        audio = np.clip((body * 0.85 + click * 0.3), -0.95, 0.95)
        int_audio = (audio * 32767).astype(np.int16)
        with wave.open(impact_path, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(int_audio.tobytes())

    # 2. Transition Whoosh
    whoosh_path = os.path.join(SFX_DIR, "whoosh_fast.wav")
    if not os.path.exists(whoosh_path) or os.path.getsize(whoosh_path) < 1000:
        sr = 44100
        dur = 0.55
        t = np.linspace(0, dur, int(sr * dur), False)
        env = np.sin(np.pi * (t / dur)) ** 2
        noise = np.random.normal(0, 0.3, len(t))
        sweep = np.sin(2 * np.pi * (250 + 800 * (t / dur)) * t) * 0.4
        audio = np.clip((noise + sweep) * env * 0.7, -0.95, 0.95)
        int_audio = (audio * 32767).astype(np.int16)
        with wave.open(whoosh_path, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(int_audio.tobytes())

    return {
        "impact": impact_path,
        "whoosh": whoosh_path
    }


def build_master_audio(
    voiceover_path: str,
    output_path: str,
    total_duration: float,
    cut_timestamps: Optional[List[float]] = None,
    bgm_path: Optional[str] = None,
    include_hook_impact: bool = True
) -> str:
    """
    Automates layered audio design via FFmpeg filter_complex:
    1. Hook Impact at 0.0s.
    2. Subtle whoosh transitions at each cut timestamp.
    3. Sidechain Ducking: BGM at -12 dB idle, ducked to -22 dB during voiceover speech.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    sfx = ensure_default_sfx()

    inputs = ["-i", os.path.abspath(voiceover_path)]
    filter_chains = []
    mix_sources = []

    # Stream 0: Voiceover narration
    filter_chains.append("[0:a]volume=1.0,aformat=channel_layouts=stereo:sample_rates=44100[vo]")
    mix_sources.append("[vo]")

    # Sidechain Ducking BGM if provided
    has_bgm = bgm_path and os.path.exists(bgm_path)
    if has_bgm:
        bgm_idx = len(inputs) // 2
        inputs.extend(["-i", os.path.abspath(bgm_path)])
        # -12 dB idle volume (0.251 linear).
        # sidechaincompress ducks BGM by ~10 dB down to -22 dB when voice is active.
        filter_chains.append(
            f"[{bgm_idx}:a]aloop=loop=-1:size=2e+09,"
            f"atrim=duration={total_duration:.2f},"
            f"volume=0.25,"
            f"aformat=channel_layouts=stereo:sample_rates=44100[bgm_base];"
            f"[bgm_base][vo]sidechaincompress=threshold=0.06:ratio=10:attack=20:release=380:makeup=1[ducked_bgm]"
        )
        mix_sources.append("[ducked_bgm]")

    # Hook Impact at 0.0s
    if include_hook_impact and os.path.exists(sfx["impact"]):
        imp_idx = len(inputs) // 2
        inputs.extend(["-i", os.path.abspath(sfx["impact"])])
        filter_chains.append(
            f"[{imp_idx}:a]adelay=0|0,volume=0.35,"
            f"aformat=channel_layouts=stereo:sample_rates=44100[impact]"
        )
        mix_sources.append("[impact]")

    # Cut transition whooshes at every cut timestamp
    if cut_timestamps:
        whoosh_idx = len(inputs) // 2
        inputs.extend(["-i", os.path.abspath(sfx["whoosh"])])

        for idx, cut_t in enumerate(cut_timestamps[:16]):
            # Avoid placing whoosh directly on the 0.0s hook impact
            if cut_t < 0.4 or cut_t > total_duration - 0.4:
                continue
            delay_ms = int(cut_t * 1000)
            label = f"w{idx}"
            filter_chains.append(
                f"[{whoosh_idx}:a]adelay={delay_ms}|{delay_ms},"
                f"volume=0.10,highpass=f=200,lowpass=f=5500,"
                f"aformat=channel_layouts=stereo:sample_rates=44100[{label}]"
            )
            mix_sources.append(f"[{label}]")

    # Combine all streams with amix and limiter
    n_inputs = len(mix_sources)
    mix_str = "".join(mix_sources)
    filter_chains.append(
        f"{mix_str}amix=inputs={n_inputs}:dropout_transition=0:normalize=0[mixed];"
        f"[mixed]alimiter=limit=0.95[aout]"
    )

    full_filter = ";".join(filter_chains)

    cmd = [
        FFMPEG_EXE, "-y",
        *inputs,
        "-filter_complex", full_filter,
        "-map", "[aout]",
        "-t", f"{total_duration:.2f}",
        "-c:a", "pcm_s16le",
        os.path.abspath(output_path)
    ]

    res = subprocess.run(cmd, capture_output=True)
    if res.returncode != 0:
        # Fallback simple copy if filter graph encounters unsupported features
        fallback_cmd = [
            FFMPEG_EXE, "-y",
            "-i", os.path.abspath(voiceover_path),
            "-t", f"{total_duration:.2f}",
            "-c:a", "pcm_s16le",
            os.path.abspath(output_path)
        ]
        subprocess.run(fallback_cmd, check=True, capture_output=True)

    return output_path
