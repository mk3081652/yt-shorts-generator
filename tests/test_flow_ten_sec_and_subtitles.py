"""
tests/test_flow_ten_sec_and_subtitles.py - Validation for Google Flow 10s alignment and progressive live typing captions.
"""

import pytest
import os
import shutil
import tempfile
from engine.beats import split_into_ten_sec_beats
from engine.director import build_google_flow_prompt
from engine.project import create_project, align_project_to_flow_ten_sec, Scene
from engine.subtitles import generate_ass_subtitles


def test_split_into_ten_sec_beats_verbatim_preservation():
    script = (
        "For centuries, historians claimed the Great Sphinx of Giza was carved for Pharaoh Khafre. "
        "However, in nineteen eighty-nine, an independent seismic radar survey revealed something remarkable: "
        "a massive artificial subterranean chamber hidden precisely forty feet below the paws! "
        "Geological water erosion patterns suggest it was built during torrential rains twelve thousand years ago."
    )
    beats = split_into_ten_sec_beats(script, target_clip_dur=10.0)
    assert len(beats) >= 2

    # Verify 100% verbatim reconstruction
    # beats is List[Tuple[str, float]]
    reconstructed = " ".join(b[0] for b in beats)
    assert script.split() == reconstructed.split()

    for text, dur in beats:
        assert dur == 10.0
        assert len(text.strip()) > 0


def test_build_google_flow_prompt():
    prompt = build_google_flow_prompt(
        narration_text="a massive artificial subterranean chamber hidden precisely forty feet below the paws!",
        scene_keywords="Sphinx underground chamber ancient radar discovery",
        motion_hint="slow cinematic push in"
    )
    assert "9:16" in prompt
    assert "photorealistic" in prompt.lower()
    assert "no subtitles" in prompt.lower()
    assert len(prompt) > 20


def test_project_flow_ten_sec_alignment():
    script = (
        "In 1971, a man identified only as D. B. Cooper boarded Northwest Orient Airlines Flight 305 in Portland. "
        "Mid-flight, he handed the flight attendant a handwritten note claiming he possessed a bomb inside his briefcase. "
        "He demanded two hundred thousand dollars in negotiable cash and four parachutes upon landing in Seattle. "
        "After releasing thirty-six passengers, he ordered the Boeing 727 back into the air toward Reno. "
        "Somewhere over southwestern Washington, through freezing rain and zero visibility, Cooper strapped the money to his waist, "
        "lowered the aft stairway, and jumped into the abyss. He was never found."
    )
    # Create project with flow_ten_sec=True
    proj = create_project(script, flow_ten_sec=True)
    assert len(proj.scenes) >= 3

    for s in proj.scenes:
        assert s.google_flow_prompt is not None
        assert len(s.google_flow_prompt) > 10

    # Also test align_project_to_flow_ten_sec
    aligned_proj, err, code = align_project_to_flow_ten_sec(proj.id)
    assert err is None
    assert aligned_proj is not None
    assert len(aligned_proj.scenes) >= 3
    for s in aligned_proj.scenes:
        assert s.google_flow_prompt is not None


def test_progressive_typewriter_subtitles():
    words = [
        {"word": "For", "start": 0.0, "end": 0.3},
        {"word": "centuries,", "start": 0.3, "end": 0.8},
        {"word": "historians", "start": 0.8, "end": 1.4},
        {"word": "claimed", "start": 1.4, "end": 1.8},
        {"word": "the", "start": 1.8, "end": 2.0},
        {"word": "truth.", "start": 2.0, "end": 2.5},
        {"word": "Now", "start": 2.6, "end": 2.9},
        {"word": "radar", "start": 2.9, "end": 3.3},
        {"word": "reveals", "start": 3.3, "end": 3.8},
        {"word": "the", "start": 3.8, "end": 4.0},
        {"word": "secret.", "start": 4.0, "end": 4.5},
    ]

    with tempfile.NamedTemporaryFile(suffix=".ass", delete=False) as tf:
        ass_path = tf.name

    try:
        generate_ass_subtitles(
            word_boundaries=words,
            output_ass_path=ass_path,
            style_name="hyper_yellow",
            max_words_per_segment=5,
            progressive_typing=True
        )

        assert os.path.exists(ass_path)
        with open(ass_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "[Events]" in content
        assert "Dialogue:" in content
        # Progressive typing formats with highlight tags
        assert "\\c&H" in content
    finally:
        if os.path.exists(ass_path):
            os.remove(ass_path)
