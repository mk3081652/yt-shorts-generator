import os
import io
import zipfile
import pytest
from PIL import Image
from unittest.mock import patch, MagicMock

from engine.project import (
    Scene,
    Project,
    create_project,
    load_project,
    save_project,
    edit_scene_text,
    edit_scene_prompt,
    edit_meta,
    split_scene,
    merge_scene,
    move_boundary,
    add_scene,
    delete_scene,
    upload_media,
    upload_bulk,
    clear_media,
    generate_scene_media,
    suggest_prompts,
    export_prompts,
    undo_project,
    redo_project,
    get_project_path,
    validate_media_bytes,
    queue_project_generation
)


@pytest.fixture
def mock_director():
    with patch("engine.project.plan_scenes_with_director") as mock_dir:
        mock_dir.return_value = ({
            "scenes": [
                {
                    "scene_index": 1,
                    "text": "The Roman Empire was built on conquest and law.",
                    "image_prompt": "Cinematic shot of ancient Roman forum with towering marble columns",
                    "video_prompt": "Slow pan over ancient Roman forum",
                    "camera_motion": "push in",
                    "duration": 4.0,
                    "entities": ["Roman Empire", "forum"],
                    "hold_previous": False
                },
                {
                    "scene_index": 2,
                    "text": "Legions marched across three continents defending the frontier.",
                    "image_prompt": "Cinematic shot of Roman legion marching along stone road under stormy skies",
                    "video_prompt": "Tracking shot of marching Roman soldiers",
                    "camera_motion": "pan right",
                    "duration": 4.5,
                    "entities": ["Legions", "soldiers"],
                    "hold_previous": False
                }
            ],
            "style_lock": "Cinematic 35mm film"
        }, False)
        yield mock_dir


@pytest.fixture
def mock_flux():
    with patch("engine.project.generate_flux") as mock_f:
        mock_f.return_value = (True, None)
        yield mock_f


def create_test_image_bytes(w=500, h=500, fmt="JPEG"):
    img = Image.new("RGB", (w, h), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def test_create_project(mock_director, mock_flux):
    script = "The Roman Empire was built on conquest and law. Legions marched across three continents defending the frontier."
    proj = create_project(script, start="manual")

    assert proj.id is not None
    assert len(proj.scenes) == 2
    assert proj.scenes[0].text == "The Roman Empire was built on conquest and law."
    assert proj.scenes[1].text == "Legions marched across three continents defending the frontier."
    assert proj.start_mode == "manual"
    assert proj.total_duration > 0

    # Verify project was persisted
    loaded = load_project(proj.id)
    assert loaded is not None
    assert loaded.id == proj.id
    assert len(loaded.scenes) == 2


def test_project_id_validation():
    with pytest.raises(ValueError, match="Invalid project ID format"):
        get_project_path("../../etc/passwd")

    with pytest.raises(ValueError, match="Invalid project ID format"):
        get_project_path("invalid-uuid-format")


def test_edit_scene_text_and_prompt(mock_director):
    script = "The Roman Empire was built on conquest and law. Legions marched across three continents defending the frontier."
    proj = create_project(script, start="manual")
    sc_id = proj.scenes[0].id

    # Edit text
    updated, err, code = edit_scene_text(proj.id, sc_id, "The Roman Republic paved the way.")
    assert code == 200
    assert updated.scenes[0].text == "The Roman Republic paved the way."
    assert "The Roman Republic paved the way." in updated.script

    # Edit prompt
    updated, err, code = edit_scene_prompt(proj.id, sc_id, "New cinematic prompt", kind="image")
    assert code == 200
    assert updated.scenes[0].image_prompt == "New cinematic prompt"


def test_split_and_merge_scene(mock_director):
    script = "One two three four five six. Seven eight nine ten."
    proj = create_project(script, start="manual")
    sc_id = proj.scenes[0].id

    # Split first scene at word index 3
    updated, err, code = split_scene(proj.id, sc_id, 3)
    assert code == 200
    assert len(updated.scenes) == 3
    assert updated.scenes[0].text == "The Roman Empire"
    assert updated.scenes[1].text == "was built on conquest and law."

    # Merge first scene with next
    merged, err, code = merge_scene(proj.id, updated.scenes[0].id, direction="next")
    assert code == 200
    assert len(merged.scenes) == 2
    assert merged.scenes[0].text == "The Roman Empire was built on conquest and law."


def test_move_boundary(mock_director):
    script = "The Roman Empire was built on conquest and law. Legions marched across three continents defending the frontier."
    proj = create_project(script, start="manual")
    s2_id = proj.scenes[1].id

    # Move 1 word from scene 2 left to scene 1
    updated, err, code = move_boundary(proj.id, s2_id, direction="left", words=1)
    assert code == 200
    assert updated.scenes[0].text.endswith("Legions")
    assert not updated.scenes[1].text.startswith("Legions")


def test_add_and_delete_scene(mock_director):
    script = "The Roman Empire was built on conquest and law. Legions marched across three continents defending the frontier."
    proj = create_project(script, start="manual")
    s1_id = proj.scenes[0].id

    # Add scene after scene 1
    updated, err, code = add_scene(proj.id, s1_id, "Pax Romana brought centuries of peace.")
    assert code == 200
    assert len(updated.scenes) == 3
    assert updated.scenes[1].text == "Pax Romana brought centuries of peace."

    # Delete newly added scene
    new_id = updated.scenes[1].id
    deleted, err, code = delete_scene(proj.id, new_id)
    assert code == 200
    assert len(deleted.scenes) == 2

    # Cannot delete until 0 scenes
    delete_scene(proj.id, deleted.scenes[0].id)
    _, err, code = delete_scene(proj.id, deleted.scenes[0].id)
    assert code == 400


def test_undo_and_redo(mock_director):
    script = "The Roman Empire was built on conquest and law. Legions marched across three continents defending the frontier."
    proj = create_project(script, start="manual")
    s1_id = proj.scenes[0].id
    orig_text = proj.scenes[0].text

    edit_scene_text(proj.id, s1_id, "A completely modified opening line.")
    curr = load_project(proj.id)
    assert curr.scenes[0].text == "A completely modified opening line."

    # Undo
    undone, err, code = undo_project(proj.id)
    assert code == 200
    assert undone.scenes[0].text == orig_text

    # Redo
    redone, err, code = redo_project(proj.id)
    assert code == 200
    assert redone.scenes[0].text == "A completely modified opening line."


def test_upload_media_validation(mock_director):
    script = "The Roman Empire was built on conquest and law. Legions marched across three continents defending the frontier."
    proj = create_project(script, start="manual")
    s1_id = proj.scenes[0].id

    # 1. Valid image upload
    img_bytes = create_test_image_bytes(800, 600)
    updated, err, code = upload_media(proj.id, s1_id, img_bytes, "test.jpg")
    assert code == 200
    sc = updated.scenes[0]
    assert sc.status == "manual"
    assert sc.source_tier == "manual"
    assert sc.media_type == "image"
    assert os.path.exists(sc.media_path)
    # Check that image was resized to 1080x1920
    with Image.open(sc.media_path) as im:
        assert im.size == (1080, 1920)

    # 2. Corrupted / invalid image
    _, err, code = upload_media(proj.id, s1_id, b"not an image file at all", "fake.png")
    assert code == 400
    assert "Corrupted or invalid" in err

    # 3. Unsupported extension
    _, err, code = upload_media(proj.id, s1_id, b"test", "test.exe")
    assert code == 400
    assert "Unsupported file type" in err


def test_manual_scene_locking(mock_director, mock_flux):
    script = "The Roman Empire was built on conquest and law. Legions marched across three continents defending the frontier."
    proj = create_project(script, start="manual")
    s1_id = proj.scenes[0].id

    # Upload manual media to scene 1
    img_bytes = create_test_image_bytes(800, 600)
    upload_media(proj.id, s1_id, img_bytes, "manual.jpg")

    # Attempt to regenerate scene 1 via generate_scene_media
    _, err, code = generate_scene_media(proj.id, s1_id)
    assert code == 400
    assert "locked as manual" in err

    # Scene 1 media should remain manual and unchanged
    reloaded = load_project(proj.id)
    assert reloaded.scenes[0].status == "manual"
    assert reloaded.scenes[0].source_tier == "manual"


def test_upload_bulk_zip_and_zip_slip(mock_director):
    script = "The Roman Empire was built on conquest and law. Legions marched across three continents defending the frontier."
    proj = create_project(script, start="manual")

    # Create zip with valid images and a zip slip attempt
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as zf:
        zf.writestr("scene_1.jpg", create_test_image_bytes(500, 500))
        zf.writestr("scene_2.jpg", create_test_image_bytes(500, 500))
        zf.writestr("../../../etc/evil.jpg", create_test_image_bytes(500, 500))

    zip_bytes = zip_buf.getvalue()
    updated, results, err, code = upload_bulk(proj.id, [("bulk.zip", zip_bytes)])
    assert code == 200
    assert len(results) >= 2
    # Ensure evil path was not extracted to escape directory
    assert not os.path.exists("etc/evil.jpg")


def test_export_prompts(mock_director):
    script = "The Roman Empire was built on conquest and law. Legions marched across three continents defending the frontier."
    proj = create_project(script, start="manual")
    edit_meta(proj.id, style_lock="Cinematic Historical")

    text, err, code = export_prompts(proj.id)
    assert code == 200
    assert "Scene #1" in text
    assert "[Cinematic Historical]" in text
    assert "Scene #2" in text
