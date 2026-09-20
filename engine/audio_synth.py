import os
import wave
import struct
import math
import numpy as np

def generate_lofi_track(filename: str, duration: float = 30.0, sr: int = 44100):
    """Generate a warm, relaxing lo-fi hip-hop beat with jazz chords and vinyl crackle."""
    t = np.linspace(0, duration, int(sr * duration), False)
    audio = np.zeros_like(t)
    
    # 80 BPM -> beat is 0.75s, bar is 3.0s
    bar_len = 3.0
    
    # Jazz chords (freqs in Hz)
    # Cmaj7: C3(130.8), E3(164.8), G3(196.0), B3(246.9)
    # Am7:   A2(110.0), C3(130.8), E3(164.8), G3(196.0)
    # Dm7:   D3(146.8), F3(174.6), A3(220.0), C4(261.6)
    # G7:    G2(98.0),  B2(123.5), D3(146.8), F3(174.6)
    chords = [
        [130.8, 164.8, 196.0, 246.9],
        [110.0, 130.8, 164.8, 196.0],
        [146.8, 174.6, 220.0, 261.6],
        [98.0,  123.5, 146.8, 174.6]
    ]
    
    # Render chords with soft decay (Rhodes-like warmth)
    for i, chord in enumerate(chords):
        chord_start = i * bar_len
        while chord_start < duration:
            mask = (t >= chord_start) & (t < chord_start + bar_len)
            t_rel = t[mask] - chord_start
            decay = np.exp(-t_rel * 1.2) * (1 - np.exp(-t_rel * 50))
            chord_signal = np.zeros_like(t_rel)
            for freq in chord:
                # Fundamental + soft harmonics
                chord_signal += np.sin(2 * np.pi * freq * t_rel) * 0.4
                chord_signal += np.sin(2 * np.pi * freq * 2 * t_rel) * 0.15
                chord_signal += np.sin(2 * np.pi * freq * 3 * t_rel) * 0.05
            audio[mask] += chord_signal * decay * 0.25
            chord_start += bar_len * len(chords)
            
    # Add gentle kick & snare groove (80 BPM)
    beat_time = 0.75
    num_beats = int(duration / beat_time)
    for b in range(num_beats):
        bt = b * beat_time
        # Kick on beat 0 and 2.5
        if b % 4 == 0 or (b % 4 == 2 and b % 2 == 0):
            mask = (t >= bt) & (t < bt + 0.3)
            t_k = t[mask] - bt
            kick = np.sin(2 * np.pi * (100 * np.exp(-t_k * 25) + 40) * t_k) * np.exp(-t_k * 12)
            audio[mask] += kick * 0.35
        # Soft snare on beat 2
        if b % 2 == 1:
            mask = (t >= bt) & (t < bt + 0.25)
            t_s = t[mask] - bt
            noise = np.random.uniform(-0.15, 0.15, size=len(t_s)) * np.exp(-t_s * 15)
            audio[mask] += noise * 0.3
            
    # Vinyl crackle texture
    crackle = np.random.normal(0, 0.012, size=len(t))
    cmask = np.random.rand(len(t)) > 0.9985
    crackle[cmask] += np.random.uniform(0.05, 0.12, size=np.sum(cmask))
    audio += crackle

    # Normalize & save
    audio = np.clip(audio, -0.95, 0.95)
    int_audio = (audio * 32767).astype(np.int16)
    
    os.makedirs(os.path.dirname(os.path.abspath(filename)), exist_ok=True)
    with wave.open(filename, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(int_audio.tobytes())


def generate_phonk_track(filename: str, duration: float = 30.0, sr: int = 44100):
    """Generate high-energy phonk / viral workout beat with 808 sub bass and fast tempo."""
    t = np.linspace(0, duration, int(sr * duration), False)
    audio = np.zeros_like(t)
    
    # 135 BPM -> beat is 0.444s
    beat_time = 60.0 / 135.0
    
    # Aggressive cowbell melody frequencies (F# minor Phonk scale)
    notes = [370.0, 440.0, 493.9, 554.4, 493.9, 440.0, 370.0, 330.0]
    num_notes = int(duration / (beat_time / 2))
    
    for n in range(num_notes):
        nt = n * (beat_time / 2)
        freq = notes[n % len(notes)]
        mask = (t >= nt) & (t < nt + 0.2)
        t_c = t[mask] - nt
        # Cowbell metallic envelope
        cowbell = (np.sin(2 * np.pi * freq * t_c) + 0.6 * np.sin(2 * np.pi * (freq * 1.5) * t_c)) * np.exp(-t_c * 18)
        audio[mask] += cowbell * 0.22
        
    # Deep 808 Sub-Bass
    num_bars = int(duration / (beat_time * 4))
    for b in range(num_bars):
        bt = b * beat_time * 4
        mask = (t >= bt) & (t < bt + beat_time * 3.8)
        t_b = t[mask] - bt
        bass = np.sin(2 * np.pi * 46.2 * t_b) * 0.4 # 46.2 Hz (F#1)
        # Slight distortion for phonk bite
        bass = np.tanh(bass * 1.8) * 0.35
        audio[mask] += bass

    # Punchy Kick & Claps
    for b in range(int(duration / beat_time)):
        bt = b * beat_time
        # Kick on every beat
        mask = (t >= bt) & (t < bt + 0.18)
        t_k = t[mask] - bt
        kick = np.sin(2 * np.pi * (140 * np.exp(-t_k * 35) + 48) * t_k) * np.exp(-t_k * 16)
        audio[mask] += kick * 0.4
        
        # Snare/Clap on 2 and 4
        if b % 2 == 1:
            mask = (t >= bt) & (t < bt + 0.15)
            t_s = t[mask] - bt
            clap = np.random.uniform(-0.25, 0.25, size=len(t_s)) * np.exp(-t_s * 25)
            audio[mask] += clap * 0.35

    audio = np.clip(audio, -0.95, 0.95)
    int_audio = (audio * 32767).astype(np.int16)
    os.makedirs(os.path.dirname(os.path.abspath(filename)), exist_ok=True)
    with wave.open(filename, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(int_audio.tobytes())


def generate_mystery_track(filename: str, duration: float = 30.0, sr: int = 44100):
    """Generate dark, atmospheric suspense drone with tension strings and eerie sub rumble."""
    t = np.linspace(0, duration, int(sr * duration), False)
    # Low drone with beating dissonance (55Hz and 58Hz)
    drone = 0.3 * np.sin(2 * np.pi * 55.0 * t) + 0.25 * np.sin(2 * np.pi * 58.2 * t)
    # Slow tension swell
    swell = 0.15 * np.sin(2 * np.pi * 0.1 * t) * np.sin(2 * np.pi * 220.0 * t)
    # Ticking clock
    ticking = np.zeros_like(t)
    for s in range(int(duration)):
        mask = (t >= s) & (t < s + 0.03)
        t_tick = t[mask] - s
        ticking[mask] = np.sin(2 * np.pi * 1800 * t_tick) * np.exp(-t_tick * 100) * 0.18
        
    audio = drone + swell + ticking
    audio = np.clip(audio, -0.95, 0.95)
    int_audio = (audio * 32767).astype(np.int16)
    os.makedirs(os.path.dirname(os.path.abspath(filename)), exist_ok=True)
    with wave.open(filename, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(int_audio.tobytes())


def generate_epic_track(filename: str, duration: float = 30.0, sr: int = 44100):
    """Generate cinematic motivational build-up with rhythmic bass and grand harmonies."""
    t = np.linspace(0, duration, int(sr * duration), False)
    audio = np.zeros_like(t)
    
    # 120 BPM -> beat is 0.5s
    beat_time = 0.5
    
    # Taiko drum hit every beat
    for b in range(int(duration / beat_time)):
        bt = b * beat_time
        mask = (t >= bt) & (t < bt + 0.4)
        t_d = t[mask] - bt
        drum = np.sin(2 * np.pi * (80 * np.exp(-t_d * 20) + 35) * t_d) * np.exp(-t_d * 8)
        audio[mask] += drum * 0.38
        
    # Dramatic cinematic chords (D minor)
    # D3(146.8), F3(174.6), A3(220.0) -> Bb3(233.1) -> C4(261.6)
    chord_seq = [
        [73.4, 146.8, 174.6, 220.0],
        [58.3, 116.5, 174.6, 233.1],
        [65.4, 130.8, 196.0, 261.6],
        [73.4, 146.8, 174.6, 220.0]
    ]
    bar_len = 2.0
    for i, chord in enumerate(chord_seq):
        st = i * bar_len
        while st < duration:
            mask = (t >= st) & (t < st + bar_len)
            t_c = t[mask] - st
            env = np.sin(np.pi * (t_c / bar_len)) # smooth swell
            sig = np.zeros_like(t_c)
            for f in chord:
                sig += np.sin(2 * np.pi * f * t_c) * 0.2
                sig += np.sin(2 * np.pi * f * 2 * t_c) * 0.08
            audio[mask] += sig * env
            st += bar_len * len(chord_seq)
            
    audio = np.clip(audio, -0.95, 0.95)
    int_audio = (audio * 32767).astype(np.int16)
    os.makedirs(os.path.dirname(os.path.abspath(filename)), exist_ok=True)
    with wave.open(filename, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(int_audio.tobytes())
