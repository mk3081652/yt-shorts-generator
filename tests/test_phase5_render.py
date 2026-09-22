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


def test_subtitles_emphasis_and_hook_banner(tmp_path):
    from engine.subtitles import is_high_impact_word, generate_ass_subtitles

    assert is_high_impact_word("300") is True
    assert is_high_impact_word("$50M") is True
    assert is_high_impact_word("SHOCKED") is True
    assert is_high_impact_word("THE") is False  # Filtered stop word
    assert is_high_impact_word("custom_keyword", scene_keywords=["custom_keyword"]) is True

    ass_out = str(tmp_path / "test_subs.ass")
    words = [
        {"word": "UNBELIEVABLE", "start": 0.0, "end": 0.5},
        {"word": "fact", "start": 0.5, "end": 0.9},
        {"word": "about", "start": 0.9, "end": 1.2},
        {"word": "100%", "start": 1.2, "end": 1.6}
    ]

    hook_banner = {"text": "WAIT FOR IT!", "start": 0.0, "end": 2.5}
    res_path = generate_ass_subtitles(
        word_boundaries=words,
        output_ass_path=ass_out,
        style_name="hyper_yellow",
        high_impact_words=["fact"],
        hook_banner=hook_banner
    )
    assert os.path.exists(res_path)
    with open(res_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Check HookBanner style & dialogue
    assert "Style: HookBanner" in content
    assert "Dialogue: 1,0:00:00.00,0:00:02.50,HookBanner" in content
    assert "WAIT FOR IT!" in content

    # Check per-word accent formatting & scale
    assert "\\fscx120\\fscy120" in content
    assert "UNBELIEVABLE" in content


def test_motion_variety_and_hook(tmp_path):
    from engine.motion import create_ken_burns_motion_clip, MOTION_MAP

    test_img = str(tmp_path / "motion_test.jpg")
    create_test_image(test_img, 1080, 1920)

    # Test all canonical motion types map properly
    assert MOTION_MAP["zoom_in"] == 0
    assert MOTION_MAP["zoom_out"] == 1
    assert MOTION_MAP["pan_right"] == 2
    assert MOTION_MAP["pan_left"] == 3
    assert MOTION_MAP["static"] == 5

    out_clip = str(tmp_path / "out_hook.mp4")
    with patch("subprocess.run") as mock_sub:
        def fake_ffmpeg(cmd, *args, **kwargs):
            out_file = cmd[-1]
            os.makedirs(os.path.dirname(os.path.abspath(out_file)), exist_ok=True)
            with open(out_file, "wb") as f:
                f.write(b"fake_video")
            res = MagicMock()
            res.returncode = 0
            return res
        mock_sub.side_effect = fake_ffmpeg

        # Test hook punch zoom
        ok = create_ken_burns_motion_clip(
            image_path=test_img,
            duration=2.0,
            output_path=out_clip,
            motion="zoom_in",
            is_hook=True
        )
        assert ok is True
        # Check that punchier zoom expression was passed in ffmpeg args
        called_cmd = mock_sub.call_args[0][0]
        cmd_str = " ".join(called_cmd)
        assert "min(zoom+0.0032,1.30)" in cmd_str


def test_sfx_library_and_track(tmp_path):
    from engine.audio import get_available_sfx, get_random_sfx, build_sfx_track

    sfxs = get_available_sfx()
    assert len(sfxs) >= 4  # We created 4 wav SFX files
    assert any("whoosh" in s for s in sfxs)

    sfx1 = get_random_sfx(0)
    sfx2 = get_random_sfx(1)
    assert sfx1 is not None
    assert sfx2 is not None

    out_track = str(tmp_path / "sfx_mix.wav")
    with patch("subprocess.run") as mock_sub:
        def fake_ffmpeg(cmd, *args, **kwargs):
            out_file = cmd[-1]
            os.makedirs(os.path.dirname(os.path.abspath(out_file)), exist_ok=True)
            with open(out_file, "wb") as f:
                f.write(b"RIFFfakeaudio")
            res = MagicMock()
            res.returncode = 0
            return res
        mock_sub.side_effect = fake_ffmpeg

        track = build_sfx_track(
            cut_points=[2.5, 5.0],
            output_path=out_track,
            total_duration=8.0
        )
        assert track is not None
        assert os.path.exists(track)


def test_render_broll_xfade_transition(tmp_path):
    scenes = [
        {"duration": 3.0, "media_path": "fake1.jpg", "media_type": "image", "motion": "zoom_in"},
        {"duration": 3.0, "media_path": "fake2.jpg", "media_type": "image", "motion": "pan_right"}
    ]
    out_broll = str(tmp_path / "broll_test.mp4")

    with patch("engine.render.render_scene_clip") as mock_clip, \
         patch("subprocess.run") as mock_sub:
        def fake_clip(media_path, media_type, motion, duration, out_path, temp_dir, idx, is_hook=False):
            with open(out_path, "wb") as f:
                f.write(b"fake_clip")
            return True
        mock_clip.side_effect = fake_clip

        def fake_ffmpeg(cmd, *args, **kwargs):
            out_file = cmd[-1]
            os.makedirs(os.path.dirname(os.path.abspath(out_file)), exist_ok=True)
            with open(out_file, "wb") as f:
                f.write(b"fake_xfade_broll")
            res = MagicMock()
            res.returncode = 0
            return res
        mock_sub.side_effect = fake_ffmpeg

        ok = render_broll_clips(
            scenes=scenes,
            output_path=out_broll,
            temp_dir=str(tmp_path),
            transition_style="crossfade"
        )
        assert ok is True
        assert os.path.exists(out_broll)
        called_cmd = mock_sub.call_args[0][0]
        cmd_str = " ".join(called_cmd)
        assert "xfade" in cmd_str
        assert "transition=fade" in cmd_str


def test_project_transition_style_and_edit_meta(tmp_path):
    from engine.project import Project, edit_meta, save_project, load_project

    proj = Project(
        id="b" * 32,
        script="Short script testing transitions.",
        transition_style="crossfade"
    )
    d = proj.to_dict()
    assert d["transition_style"] == "crossfade"

    proj2 = Project.from_dict(d)
    assert proj2.transition_style == "crossfade"

    with patch("engine.project.PROJECTS_DIR", str(tmp_path)):
        save_project(proj)
        p_loaded, err, code = edit_meta(proj.id, transition_style="zoom-punch")
        assert err is None
        assert code == 200
        assert p_loaded.transition_style == "zoom-punch"


def test_ypp_metadata_compliance():
    from engine.metadata import _generate_metadata_nlp_fallback, generate_youtube_metadata

    meta = _generate_metadata_nlp_fallback("The mystery of Flight 370 continues to baffle scientists.")
    assert meta["altered_or_synthetic_content"] is True
    assert "YouTube Partner Program (YPP) Disclosure" in meta["compliance_notes"]
    assert "Created with AI assistance for visual storytelling." in meta["description"]

    # Test with generate_youtube_metadata
    with patch("engine.llm.generate_content", return_value=(None, None)):
        meta2 = generate_youtube_metadata("Ancient ruins discovered under Antarctic ice shelf.")
        assert meta2["altered_or_synthetic_content"] is True
        assert "YouTube Partner Program (YPP) Disclosure" in meta2["compliance_notes"]
        assert "Created with AI assistance for visual storytelling." in meta2["description"]


def test_human_voiceover_override(tmp_path):
    custom_audio = tmp_path / "custom_voice.mp3"
    custom_audio.write_bytes(b"ID3humanvoiceover")

    words = [
        {"word": "This", "start": 0.0, "end": 0.5},
        {"word": "is", "start": 0.5, "end": 0.9},
        {"word": "human", "start": 0.9, "end": 1.4},
        {"word": "voiceover.", "start": 1.4, "end": 2.0}
    ]

    with patch("engine.render.generate_speech_with_words", new_callable=AsyncMock) as mock_tts, \
         patch("engine.render.align_words_for_audio", return_value=(words, 2.0)) as mock_align, \
         patch("engine.render.generate_ass_subtitles") as mock_ass, \
         patch("engine.render.render_broll_clips") as mock_broll, \
         patch("subprocess.run") as mock_run:

        def fake_ffmpeg(cmd, *args, **kwargs):
            out_file = cmd[-1]
            os.makedirs(os.path.dirname(os.path.abspath(out_file)), exist_ok=True)
            with open(out_file, "wb") as f:
                f.write(b"fake_video")
            res = MagicMock()
            res.returncode = 0
            return res
        mock_run.side_effect = fake_ffmpeg

        res = render_shorts_video(
            script_text="This is human voiceover.",
            custom_audio_path=str(custom_audio)
        )

        assert res["success"] is True
        # Ensure automated TTS was skipped entirely
        mock_tts.assert_not_called()
        # Ensure word alignment was called on the custom audio file
        mock_align.assert_called_once()


def test_whisper_client_zero_ram_fallback(tmp_path):
    from engine.whisper_client import align_audio_fallback, align_words_for_audio

    script = "The clock struck midnight in the old tower"
    audio_dummy = tmp_path / "dummy.mp3"
    audio_dummy.write_bytes(b"dummy")

    with patch("engine.whisper_client.get_audio_duration", return_value=4.0):
        aligned, dur = align_audio_fallback(str(audio_dummy), script_text=script)

        assert len(aligned) == 8
        assert aligned[0]["word"] == "The"
        assert aligned[-1]["word"] == "tower"
        assert aligned[0]["start"] == 0.0
        assert aligned[-1]["end"] <= 4.0
        assert dur == 4.0

    # With no API key, align_words_for_audio must fall back to zero-ram aligner without crashing
    with patch.dict(os.environ, {"OPENAI_API_KEY": ""}), \
         patch("engine.whisper_client.get_audio_duration", return_value=4.0):
        words, dur2 = align_words_for_audio(str(audio_dummy), script_text=script)
        assert len(words) == 8
        assert words[-1]["end"] <= 4.0
        assert dur2 == 4.0


def test_storage_manager(tmp_path):
    from engine.storage import save_or_upload_file

    fake_video = tmp_path / "test_out.mp4"
    fake_video.write_bytes(b"videodata")

    # Local fallback
    res_local = save_or_upload_file(str(fake_video))
    assert res_local["provider"] == "local"
    assert res_local["is_remote"] is False
    assert res_local["url"].startswith("/outputs/")

    # Non-existent file error handling
    res_missing = save_or_upload_file(str(tmp_path / "does_not_exist.mp4"))
    assert res_missing["error"] == "File does not exist"


def test_sidechain_ducking_and_film_grain(tmp_path):
    dummy_voice = tmp_path / "voice.mp3"
    dummy_voice.write_bytes(b"dummyvoice")

    words = [
        {"word": "Ducking", "start": 0.0, "end": 1.0},
        {"word": "test.", "start": 1.0, "end": 2.0}
    ]

    with patch("engine.render.generate_speech_with_words", new_callable=AsyncMock) as mock_tts, \
         patch("engine.render.generate_ass_subtitles"), \
         patch("engine.render.render_broll_clips"), \
         patch("subprocess.run") as mock_run:

        mock_tts.return_value = (str(dummy_voice), words, 2.0)

        captured_cmd = []
        def fake_ffmpeg(cmd, *args, **kwargs):
            nonlocal captured_cmd
            captured_cmd = list(cmd)
            out_file = cmd[-1]
            os.makedirs(os.path.dirname(os.path.abspath(out_file)), exist_ok=True)
            with open(out_file, "wb") as f:
                f.write(b"ducked_video")
            res = MagicMock()
            res.returncode = 0
            return res
        mock_run.side_effect = fake_ffmpeg

        res = render_shorts_video(
            script_text="Ducking test.",
            motion_texture="film_grain"
        )

        assert res["success"] is True
        cmd_str = " ".join(captured_cmd)

        # Verify sidechain ducking filter is present
        assert "sidechaincompress=threshold=0.08:ratio=5:attack=50:release=350" in cmd_str
        # Verify 35mm film grain is present
        assert "noise=alls=8:allf=t+u" in cmd_str


