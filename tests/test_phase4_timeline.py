import os
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

from app import app
from engine.project import Project, Scene, create_project, load_project, save_project
from engine.timeline import align, prepare_voice_timeline


@pytest.fixture
def mock_director():
    with patch("engine.project.plan_scenes_with_director") as mock_dir:
        mock_dir.return_value = ({
            "scenes": [
                {
                    "scene_index": 1,
                    "text": "The Roman Empire was built on conquest.",
                    "image_prompt": "Roman forum",
                    "camera_motion": "push in",
                    "duration": 3.0,
                    "entities": ["Roman Empire"],
                    "hold_previous": False
                },
                {
                    "scene_index": 2,
                    "text": "Legions marched across three continents.",
                    "image_prompt": "Roman legion",
                    "camera_motion": "pan right",
                    "duration": 3.0,
                    "entities": ["Legions"],
                    "hold_previous": False
                }
            ],
            "style_lock": ""
        }, False)
        yield mock_dir


def test_align_empty_and_fallback():
    # Empty scenes
    assert align([], [], 10.0) == []

    # Fallback without words
    scenes = [
        Scene(id="s1", text="Scene one", duration=3.5),
        Scene(id="s2", text="Scene two", duration=4.0)
    ]
    aligned = align(scenes, [], 0.0)
    assert len(aligned) == 2
    assert aligned[0]["start"] == 0.0
    assert aligned[0]["end"] == 3.5
    assert aligned[0]["duration"] == 3.5
    assert aligned[1]["start"] == 3.5
    assert aligned[1]["end"] == 7.5
    assert aligned[1]["duration"] == 4.0


def test_align_with_tts_words():
    scenes = [
        Scene(id="s1", text="The Roman Empire was built on conquest.", duration=3.0),
        Scene(id="s2", text="Legions marched across three continents.", duration=3.0)
    ]
    # 7 words in scene 1, 5 words in scene 2 = 12 words total
    words = [
        {"word": "The", "start": 0.0, "end": 0.3},
        {"word": "Roman", "start": 0.3, "end": 0.7},
        {"word": "Empire", "start": 0.7, "end": 1.2},
        {"word": "was", "start": 1.2, "end": 1.4},
        {"word": "built", "start": 1.4, "end": 1.8},
        {"word": "on", "start": 1.8, "end": 2.0},
        {"word": "conquest.", "start": 2.0, "end": 2.6},
        {"word": "Legions", "start": 2.8, "end": 3.3},
        {"word": "marched", "start": 3.3, "end": 3.8},
        {"word": "across", "start": 3.8, "end": 4.2},
        {"word": "three", "start": 4.2, "end": 4.5},
        {"word": "continents.", "start": 4.5, "end": 5.2}
    ]
    total_duration = 5.2

    aligned = align(scenes, words, total_duration)
    assert len(aligned) == 2
    assert aligned[0]["start"] == 0.0
    assert aligned[0]["end"] == 2.6
    assert aligned[0]["duration"] == 2.6
    assert aligned[1]["start"] == 2.6
    assert aligned[1]["end"] == 5.2
    assert aligned[1]["duration"] == 2.6


@pytest.mark.anyio
async def test_prepare_voice_timeline_and_caching(mock_director, tmp_path):
    script = "The Roman Empire was built on conquest. Legions marched across three continents."
    proj = create_project(script, start="manual")

    dummy_audio = tmp_path / "dummy.mp3"
    dummy_audio.write_bytes(b"ID3dummy")

    words = [
        {"word": "The", "start": 0.0, "end": 0.3},
        {"word": "Roman", "start": 0.3, "end": 0.7},
        {"word": "Empire", "start": 0.7, "end": 1.2},
        {"word": "was", "start": 1.2, "end": 1.4},
        {"word": "built", "start": 1.4, "end": 1.8},
        {"word": "on", "start": 1.8, "end": 2.0},
        {"word": "conquest.", "start": 2.0, "end": 2.6},
        {"word": "Legions", "start": 2.8, "end": 3.3},
        {"word": "marched", "start": 3.3, "end": 3.8},
        {"word": "across", "start": 3.8, "end": 4.2},
        {"word": "three", "start": 4.2, "end": 4.5},
        {"word": "continents.", "start": 4.5, "end": 5.2}
    ]

    with patch("engine.tts.generate_speech_with_words", new_callable=AsyncMock) as mock_tts:
        mock_tts.return_value = (str(dummy_audio), words, 5.2)

        # First call: runs TTS
        updated, err, code = await prepare_voice_timeline(proj.id)
        assert code == 200
        assert updated.timeline is not None
        assert updated.total_duration == 5.2
        assert mock_tts.call_count == 1

        # Second call with same parameters: uses cache
        cached, err, code = await prepare_voice_timeline(proj.id)
        assert code == 200
        assert mock_tts.call_count == 1  # No additional TTS call

        # Call with different voice: cache invalidated, runs TTS again
        updated2, err, code = await prepare_voice_timeline(proj.id, voice="en-GB-SoniaNeural")
        assert code == 200
        assert mock_tts.call_count == 2


def test_prepare_voice_api_endpoint(mock_director, tmp_path):
    client = TestClient(app)
    script = "The Roman Empire was built on conquest. Legions marched across three continents."
    proj = create_project(script, start="manual")

    dummy_audio = tmp_path / "dummy_api.mp3"
    dummy_audio.write_bytes(b"ID3dummy")

    words = [
        {"word": "The", "start": 0.0, "end": 0.3},
        {"word": "Roman", "start": 0.3, "end": 2.5},
        {"word": "continents.", "start": 2.5, "end": 5.0}
    ]

    with patch("engine.tts.generate_speech_with_words", new_callable=AsyncMock) as mock_tts:
        mock_tts.return_value = (str(dummy_audio), words, 5.0)

        resp = client.post(f"/api/projects/{proj.id}/prepare_voice", json={
            "voice": "en-US-ChristopherNeural",
            "rate": "+10%"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "timeline" in data
        assert data["timeline"]["total_duration"] == 5.0
        assert len(data["timeline"]["scenes"]) == 2
