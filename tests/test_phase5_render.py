import os
import io
import pytest
from PIL import Image
from unittest.mock import patch, MagicMock, AsyncMock

from engine.project import Project, Scene, create_project
from engine.render import (
    preprocess_image_for_motion,
    render_scene_clip,
    render_broll_clips,
    render_shorts_video
)


def create_test_image(path: str, width: int = 1080, height: int = 1920):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    img = Image.new("RGB", (width, height), color=(100, 150, 200))
    img.save(path, "JPEG")
    return path


def test_preprocess_image_downscale(tmp_path):
    # Oversized 4000x3000 image
    large_img = tmp_path / "huge.jpg"
    create_test_image(str(large_img), 4000, 3000)

    scaled_path = preprocess_image_for_motion(str(large_img), str(tmp_path), 0)
    assert os.path.exists(scaled_path)

    with Image.open(scaled_path) as im:
        w, h = im.size
        assert w <= 1080
        assert h <= 1920


def test_preprocess_image_preserves_within_bounds(tmp_path):
    small_img = tmp_path / "normal.jpg"
    create_test_image(str(small_img), 800, 1200)

    result_path = preprocess_image_for_motion(str(small_img), str(tmp_path), 0)
    assert result_path == str(small_img)


def test_render_scene_clip_fallback_to_blank(tmp_path):
    # Non-existent media should cleanly fall back to blank clip
    out_clip = tmp_path / "blank_out.mp4"
    with patch("engine.render.make_blank_clip") as mock_blank:
        # Simulate make_blank_clip creating the file
        def fake_blank(dur, out):
            with open(out, "wb") as f:
                f.write(b"fake_mp4_data")
            return True
        mock_blank.side_effect = fake_blank

        ok = render_scene_clip(
            media_path="non_existent.jpg",
            media_type="image",
            motion="push in",
            duration=2.5,
            out_path=str(out_clip),
            temp_dir=str(tmp_path),
            idx=0
        )
        assert ok is True
        assert os.path.exists(str(out_clip))
        mock_blank.assert_called_once()


def test_render_shorts_video_smoke(tmp_path):
    # Setup test project
    proj = Project(
        id="a" * 32,
        script="The Roman Empire was built on conquest.",
        scenes=[
            Scene(id="s1", text="The Roman Empire was built on conquest.", duration=3.0, status="ready", media_type="blank")
        ]
    )

    dummy_voice = tmp_path / "voice.mp3"
    dummy_voice.write_bytes(b"ID3dummyvoice")

    words = [
        {"word": "The", "start": 0.0, "end": 0.3},
        {"word": "Roman", "start": 0.3, "end": 0.8},
        {"word": "Empire", "start": 0.8, "end": 1.4},
        {"word": "was", "start": 1.4, "end": 1.7},
        {"word": "built", "start": 1.7, "end": 2.2},
        {"word": "on", "start": 2.2, "end": 2.5},
        {"word": "conquest.", "start": 2.5, "end": 3.0}
    ]

    with patch("engine.render.load_project", return_value=proj), \
         patch("engine.render.generate_speech_with_words", new_callable=AsyncMock) as mock_tts, \
         patch("engine.render.generate_ass_subtitles") as mock_ass, \
         patch("engine.render.render_broll_clips") as mock_broll, \
         patch("subprocess.run") as mock_run:

        mock_tts.return_value = (str(dummy_voice), words, 3.0)

        # Mock subprocess.run for final composition to create output file
        def fake_ffmpeg(cmd, *args, **kwargs):
            out_file = cmd[-1]
            os.makedirs(os.path.dirname(os.path.abspath(out_file)), exist_ok=True)
            with open(out_file, "wb") as f:
                f.write(b"fake_final_video")
            res = MagicMock()
            res.returncode = 0
            return res

        mock_run.side_effect = fake_ffmpeg

        res = render_shorts_video(
            script_text=proj.script,
            project_id=proj.id
        )

        assert res["success"] is True
        assert "short_" in res["video_url"]
        assert res["duration"] == 3.35
        assert res["word_count"] == 7
        assert mock_ass.called
        assert mock_broll.called
