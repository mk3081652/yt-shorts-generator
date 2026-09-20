import os
import sys
import re
import time
import json
import uuid
import shutil
import logging
from typing import Optional, Dict, List, Any

logger = logging.getLogger("yt_shorts_app")

import engine.config

from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException

# Enforce UTF-8 console output on Windows to prevent UnicodeEncodeError
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict

from engine.tts import get_available_voices, generate_speech_with_words
from engine.subtitles import STYLE_PRESETS
from engine.audio import get_available_bgm
from engine.metadata import get_viral_hooks, get_script_templates, generate_youtube_metadata
from engine.render import render_shorts_video
from engine.visual_director.segment_session import (
    create_session,
    generate_auto_session,
    split_segment,
    merge_segment,
    move_boundary,
    add_segment,
    delete_segment,
    edit_segment_text,
    edit_segment_prompt,
    edit_segment_meta,
    replan_dirty_segments,
    upload_segment_media,
    upload_bulk_media,
    clear_segment_media,
    generate_segment_media,
    generate_missing_media,
    suggest_prompts,
    export_prompts,
    undo_session,
    redo_session,
    cancel_session_generation,
    prepare_voice_timeline,
    load_session
)

from engine.project import (
    create_project,
    load_project,
    save_project,
    edit_scene_text,
    edit_scene_prompt,
    edit_meta as edit_project_meta,
    split_scene,
    merge_scene,
    move_boundary as move_project_boundary,
    add_scene,
    delete_scene,
    upload_media as upload_project_media,
    upload_bulk as upload_project_bulk,
    clear_media as clear_project_media,
    generate_scene_media,
    generate_missing_media as generate_project_missing_media,
    cancel_generation as cancel_project_generation,
    suggest_prompts as suggest_project_prompts,
    export_prompts as export_project_prompts,
    undo_project,
    redo_project,
    Project,
    Scene
)
from engine.timeline import prepare_voice_timeline as prepare_project_voice_timeline


app = FastAPI(title="Viral YouTube Shorts Creator Tool")


def log_and_raise_safe(e: Exception, user_message: str, status_code: int = 500):
    """Logs full exception and traceback server-side, returning only generic message to client."""
    logger.error(f"[Server Error] {user_message}: {e}", exc_info=True)
    raise HTTPException(status_code=status_code, detail=user_message)


# Explicit CORS allowlist
allowed_origins_env = os.environ.get("ALLOWED_ORIGINS", "").strip()
if allowed_origins_env:
    allowed_origins = [orig.strip() for orig in allowed_origins_env.split(",") if orig.strip()]
else:
    allowed_origins = [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
        "http://127.0.0.1:3000"
    ]
    if bool(os.environ.get("RENDER") or os.environ.get("PORT")):
        print("[WARNING] ALLOWED_ORIGINS is not set in production. Defaulting to localhost. Set ALLOWED_ORIGINS to your production domain.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_no_cache_headers(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# Mount static and output folders
os.makedirs("static", exist_ok=True)
os.makedirs("outputs", exist_ok=True)
os.makedirs("outputs/projects", exist_ok=True)
os.makedirs("outputs/custom_scenes", exist_ok=True)
os.makedirs("outputs/ai_previews", exist_ok=True)
os.makedirs("assets/bgm", exist_ok=True)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/outputs", StaticFiles(directory="outputs"), name="outputs")
app.mount("/assets", StaticFiles(directory="assets"), name="assets")

# Global job status dictionary with disk persistence
JOBS = {}
JOBS_DIR = os.path.abspath("outputs/jobs")
os.makedirs(JOBS_DIR, exist_ok=True)


def save_job(job_id: str, data: dict):
    JOBS[job_id] = data
    try:
        j_path = os.path.join(JOBS_DIR, f"{job_id}.json")
        with open(j_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception as e:
        logger.error(f"Failed to save job {job_id}: {e}")


def load_job(job_id: str) -> Optional[dict]:
    if job_id in JOBS:
        return JOBS[job_id]
    j_path = os.path.join(JOBS_DIR, f"{job_id}.json")
    if os.path.exists(j_path):
        try:
            with open(j_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                JOBS[job_id] = data
                return data
        except Exception as e:
            logger.error(f"Failed to load job {job_id}: {e}")
    return None


class RenderRequest(BaseModel):
    script: str = ""
    voice: str = "en-US-ChristopherNeural"
    voice_rate: str = "+10%"
    subtitle_style: str = "mrbeast"
    bgm_track: str = "phonk_energetic"
    bgm_volume: float = 0.18
    scene_overrides: Optional[Dict[str, str]] = None
    preview_scenes: Optional[List[Dict[str, Any]]] = None
    session_id: Optional[str] = None
    project_id: Optional[str] = None

    model_config = ConfigDict(extra="allow")


class CreateProjectRequest(BaseModel):
    script: str
    start: Optional[str] = "auto"
    manual_delimiter: bool = False


class VoicePreviewRequest(BaseModel):
    text: str = "Welcome to the ultimate YouTube Shorts Creator!"
    voice: str = "en-US-ChristopherNeural"
    voice_rate: str = "+10%"


class MetadataRequest(BaseModel):
    script: str


class GenerateScriptRequest(BaseModel):
    topic: str


def sanitize_spoken_script(text: str) -> str:
    """Removes accidental prompt wrappers or markdown meta-instructions pasted into script box."""
    if not text:
        return text
    s = text.strip()
    # Strip patterns like: "For the ... video, use this ... prompt:\s*(**Image prompt:** >)?"
    s = re.sub(r'^For the .*? video,?\s*(?:use this .*? prompt:?)?\s*', '', s, flags=re.IGNORECASE)
    # Strip "**Image prompt:** >" or "Image prompt:"
    s = re.sub(r'^\*{0,2}Image prompt:\*{0,2}\s*>?\s*', '', s, flags=re.IGNORECASE)
    # Strip leading markdown blockquotes "> "
    s = re.sub(r'^>\s*', '', s)
    return s.strip() or text.strip()


class AutoGenerateRequest(BaseModel):
    script: str
    manual_delimiter: bool = False


class CreateSegmentsRequest(BaseModel):
    script: str
    mode: Optional[str] = "auto"
    start: Optional[str] = None
    manual_delimiter: bool = False


class SplitSegmentRequest(BaseModel):
    segment_id: str
    split_at_word_index: int


class MergeSegmentRequest(BaseModel):
    segment_id: str
    direction: str = "next"


class MoveBoundaryRequest(BaseModel):
    segment_id: str
    direction: str = "left"
    words: int = 1


class AddSegmentRequest(BaseModel):
    after_segment_id: str
    text: str


class DeleteSegmentRequest(BaseModel):
    segment_id: str


class EditTextRequest(BaseModel):
    segment_id: str
    new_text: str


class EditPromptRequest(BaseModel):
    segment_id: str
    new_prompt: str
    kind: str = "image"  # "image" | "video"


class EditMetaRequest(BaseModel):
    segment_id: Optional[str] = None
    motion: Optional[str] = None
    style_lock: Optional[str] = None


class SuggestPromptsRequest(BaseModel):
    segment_id: str


class SegmentActionRequest(BaseModel):
    segment_id: str


class PrepareVoiceRequest(BaseModel):
    voice: Optional[str] = "en-US-ChristopherNeural"
    rate: Optional[str] = "+10%"


@app.get("/", response_class=HTMLResponse)
def serve_home():
    with open("templates/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/healthz")
def healthz():
    """Health check endpoint for container orchestrators and monitoring."""
    return {"status": "ok"}


@app.get("/api/config")
def get_config():
    """Returns available options for the studio UI."""
    return {
        "voices": get_available_voices(),
        "subtitle_styles": {
            k: {"name": v["name"], "font": v["font_name"]}
            for k, v in STYLE_PRESETS.items()
        },
        "bgm_tracks": get_available_bgm(),
        "hooks": get_viral_hooks(),
        "templates": get_script_templates(),
        "ai_planner_configured": bool(os.environ.get("GEMINI_API_KEY", "").strip())
    }


@app.post("/api/preview_voice")
async def preview_voice(req: VoicePreviewRequest):
    """Generates a quick audio preview for the selected voice."""
    preview_id = str(uuid.uuid4())[:8]
    output_path = f"outputs/preview_{preview_id}.mp3"

    sample_text = req.text[:120] if req.text.strip() else "Welcome to viral YouTube Shorts Creator!"
    await generate_speech_with_words(
        text=sample_text,
        voice=req.voice,
        rate=req.voice_rate,
        output_audio_path=output_path
    )

    return {
        "audio_url": f"/outputs/preview_{preview_id}.mp3"
    }


@app.post("/api/generate_script")
def api_generate_script(req: GenerateScriptRequest):
    """Generates a viral 30-45 second spoken narration script for YouTube Shorts using Gemini."""
    topic = req.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="Topic cannot be empty.")

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=500, detail="Gemini API key is not configured on server.")

    prompt = f"""You are a master viral YouTube Shorts scriptwriter.
Write a high-retention 60-90 word spoken voiceover script about: "{topic}".

STRICT RULES:
1. The first sentence MUST be an irresistible 3-second hook that immediately stops viewers from scrolling.
2. Fast-paced, intriguing storytelling with surprising facts, mystery, or drama.
3. Total word count MUST be between 60 and 90 words (about 30 to 45 seconds of speech).
4. OUTPUT SPOKEN NARRATION WORDS ONLY!
   - DO NOT include scene directions or camera angles.
   - DO NOT include bracketed sound effects or notes like [Dramatic pause], [Cut to plane].
   - DO NOT include prompt instructions or image descriptions.
   - DO NOT include labels like "Voiceover:", "Narrator:", "Hook:", "Image prompt:".
   - Return ONLY the exact words the voice actor will speak aloud.
"""
    try:
        from engine.gemini_client import generate_content
        text, model = generate_content(
            prompt,
            thinking_level="low",
            max_output_tokens=1000,
            json_mode=False,
            api_key=api_key
        )
        if not text:
            raise HTTPException(status_code=500, detail="Gemini failed to generate script.")

        # Clean any accidental prefixes or quotes
        clean_text = text.strip()
        clean_text = re.sub(r'^(?:Voiceover|Narrator|Script|Hook):\s*', '', clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(r'^["\']|["\']$', '', clean_text)
        clean_text = re.sub(r'\[.*?\]', '', clean_text)  # remove bracketed directions
        clean_text = sanitize_spoken_script(clean_text)

        return {"topic": topic, "script": clean_text, "model": model}
    except HTTPException:
        raise
    except Exception as e:
        log_and_raise_safe(e, "Failed to generate script with Gemini", status_code=500)


@app.post("/api/projects")
def api_create_project(req: CreateProjectRequest):
    """Creates a new Project, runs the Director, and queues generation if mode=auto."""
    cleaned = sanitize_spoken_script(req.script)
    if not cleaned:
        raise HTTPException(status_code=400, detail="Script cannot be empty.")
    try:
        proj = create_project(
            script=cleaned,
            start=req.start or "auto",
            manual_delimiter=req.manual_delimiter,
            api_key=os.environ.get("GEMINI_API_KEY", None)
        )
        return proj.to_dict()
    except Exception as e:
        log_and_raise_safe(e, "Failed to create project", status_code=500)


@app.get("/api/projects/{id}")
def api_get_project(id: str):
    """Retrieves an existing Project by ID."""
    validate_session_id(id)
    proj = load_project(id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found.")
    return proj.to_dict()


@app.post("/api/projects/{id}/edit_text")
def api_project_edit_text(id: str, req: EditTextRequest):
    validate_session_id(id)
    proj, err, code = edit_scene_text(id, req.segment_id, req.new_text)
    if err:
        raise HTTPException(status_code=code, detail=err)
    return proj.to_dict()


@app.post("/api/projects/{id}/edit_prompt")
def api_project_edit_prompt(id: str, req: EditPromptRequest):
    validate_session_id(id)
    proj, err, code = edit_scene_prompt(id, req.segment_id, req.new_prompt, kind=req.kind)
    if err:
        raise HTTPException(status_code=code, detail=err)
    return proj.to_dict()


@app.post("/api/projects/{id}/edit_meta")
def api_project_edit_meta(id: str, req: EditMetaRequest):
    validate_session_id(id)
    proj, err, code = edit_project_meta(id, scene_id=req.segment_id, motion=req.motion, style_lock=req.style_lock)
    if err:
        raise HTTPException(status_code=code, detail=err)
    return proj.to_dict()


@app.post("/api/projects/{id}/split")
def api_project_split(id: str, req: SplitSegmentRequest):
    validate_session_id(id)
    proj, err, code = split_scene(id, req.segment_id, req.split_at_word_index)
    if err:
        raise HTTPException(status_code=code, detail=err)
    return proj.to_dict()


@app.post("/api/projects/{id}/merge")
def api_project_merge(id: str, req: MergeSegmentRequest):
    validate_session_id(id)
    proj, err, code = merge_scene(id, req.segment_id, req.direction)
    if err:
        raise HTTPException(status_code=code, detail=err)
    return proj.to_dict()


@app.post("/api/projects/{id}/move_boundary")
def api_project_move_boundary(id: str, req: MoveBoundaryRequest):
    validate_session_id(id)
    proj, err, code = move_project_boundary(id, req.segment_id, req.direction, req.words)
    if err:
        raise HTTPException(status_code=code, detail=err)
    return proj.to_dict()


@app.post("/api/projects/{id}/add")
def api_project_add(id: str, req: AddSegmentRequest):
    validate_session_id(id)
    proj, err, code = add_scene(id, req.after_segment_id, req.text)
    if err:
        raise HTTPException(status_code=code, detail=err)
    return proj.to_dict()


@app.post("/api/projects/{id}/delete")
def api_project_delete(id: str, req: DeleteSegmentRequest):
    validate_session_id(id)
    proj, err, code = delete_scene(id, req.segment_id)
    if err:
        raise HTTPException(status_code=code, detail=err)
    return proj.to_dict()


@app.post("/api/projects/{id}/upload_media")
async def api_project_upload_media(
    id: str,
    file: UploadFile = File(...),
    segment_id: str = Form(...)
):
    validate_session_id(id)
    file_bytes = await file.read()
    proj, err, code = upload_project_media(id, segment_id, file_bytes, file.filename)
    if err:
        raise HTTPException(status_code=code, detail=err)
    return proj.to_dict()


@app.post("/api/projects/{id}/upload_bulk")
async def api_project_upload_bulk(
    id: str,
    files: List[UploadFile] = File(...)
):
    validate_session_id(id)
    files_data = []
    for f in files:
        data = await f.read()
        files_data.append((f.filename, data))
    proj, results, err, code = upload_project_bulk(id, files_data)
    if err:
        raise HTTPException(status_code=code, detail=err)
    return {"project": proj.to_dict(), "session": proj.to_dict(), "results": results}


@app.post("/api/projects/{id}/clear_media")
def api_project_clear_media(id: str, req: SegmentActionRequest):
    validate_session_id(id)
    proj, err, code = clear_project_media(id, req.segment_id)
    if err:
        raise HTTPException(status_code=code, detail=err)
    return proj.to_dict()


@app.post("/api/projects/{id}/generate")
def api_project_generate(id: str, req: SegmentActionRequest):
    validate_session_id(id)
    proj, err, code = generate_scene_media(id, req.segment_id, api_key=os.environ.get("GEMINI_API_KEY", None))
    if err:
        raise HTTPException(status_code=code, detail=err)
    return proj.to_dict()


@app.post("/api/projects/{id}/generate_missing")
def api_project_generate_missing(id: str):
    validate_session_id(id)
    proj, err, code = generate_project_missing_media(id, api_key=os.environ.get("GEMINI_API_KEY", None))
    if err:
        raise HTTPException(status_code=code, detail=err)
    return proj.to_dict()


@app.post("/api/projects/{id}/cancel")
def api_project_cancel(id: str):
    validate_session_id(id)
    proj, err, code = cancel_project_generation(id)
    if err:
        raise HTTPException(status_code=code, detail=err)
    return proj.to_dict()


@app.post("/api/projects/{id}/suggest_prompts")
def api_project_suggest_prompts(id: str, req: SuggestPromptsRequest):
    validate_session_id(id)
    prompts, err, code = suggest_project_prompts(id, req.segment_id, api_key=os.environ.get("GEMINI_API_KEY", None))
    if err:
        raise HTTPException(status_code=code, detail=err)
    return {"segment_id": req.segment_id, "prompts": prompts}


@app.get("/api/projects/{id}/export_prompts")
def api_project_export_prompts(id: str):
    validate_session_id(id)
    text, err, code = export_project_prompts(id)
    if err:
        raise HTTPException(status_code=code, detail=err)
    return PlainTextResponse(text)


@app.post("/api/projects/{id}/undo")
def api_project_undo(id: str):
    validate_session_id(id)
    proj, err, code = undo_project(id)
    if err:
        raise HTTPException(status_code=code, detail=err)
    return proj.to_dict()


@app.post("/api/projects/{id}/redo")
def api_project_redo(id: str):
    validate_session_id(id)
    proj, err, code = redo_project(id)
    if err:
        raise HTTPException(status_code=code, detail=err)
    return proj.to_dict()


@app.post("/api/projects/{id}/prepare_voice")
async def api_project_prepare_voice(id: str, req: Optional[PrepareVoiceRequest] = None):
    validate_session_id(id)
    v = req.voice if req and req.voice else "en-US-ChristopherNeural"
    r = req.rate if req and req.rate else "+10%"
    proj, err, code = await prepare_project_voice_timeline(id, voice=v, rate=r)
    if err:
        raise HTTPException(status_code=code, detail=err)
    return proj.to_dict()



@app.post("/api/auto/generate")
def api_auto_generate(req: AutoGenerateRequest):
    """Auto mode: splits script, plans prompts with Gemini, generates images with FLUX."""
    cleaned = sanitize_spoken_script(req.script)
    if not cleaned:
        raise HTTPException(status_code=400, detail="Script cannot be empty.")
    try:
        session = generate_auto_session(
            script=cleaned,
            manual_delimiter=req.manual_delimiter,
            api_key=os.environ.get("GEMINI_API_KEY", None)
        )
        return session.to_dict()
    except Exception as e:
        log_and_raise_safe(e, "Failed to auto-generate scenes", status_code=500)


def validate_session_id(session_id: str) -> str:
    """Security check to prevent directory traversal and invalid IDs."""
    if not re.match(r'^[a-f0-9]{32}$', session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID format.")
    return session_id


@app.on_event("startup")
def startup_cleanup():
    """Cleans up projects, sessions and previews older than 7 days."""
    cutoff = time.time() - (7 * 86400)
    for folder in ("outputs/projects", "outputs/segment_sessions", "outputs/ai_previews", "outputs/custom_scenes"):
        p = os.path.abspath(folder)
        if os.path.exists(p):
            for fname in os.listdir(p):
                fpath = os.path.join(p, fname)
                try:
                    if os.path.isfile(fpath) and os.path.getmtime(fpath) < cutoff:
                        os.remove(fpath)
                except Exception:
                    pass


@app.post("/api/segments/create")
def api_create_segments(req: CreateSegmentsRequest):
    """Creates a new StoryboardSession in Auto or Manual Segment mode."""
    cleaned = sanitize_spoken_script(req.script)
    if not cleaned:
        raise HTTPException(status_code=400, detail="Script cannot be empty.")
    try:
        session = create_session(
            script=cleaned,
            mode=req.mode or "auto",
            start=req.start,
            manual_delimiter=req.manual_delimiter,
            api_key=os.environ.get("GEMINI_API_KEY", None)
        )
        return session.to_dict()
    except Exception as e:
        log_and_raise_safe(e, "Failed to create segment session", status_code=500)


@app.get("/api/segments/{id}")
def api_get_segment_session(id: str):
    """Retrieves an existing StoryboardSession by ID."""
    validate_session_id(id)
    session = load_session(id)
    if not session:
        raise HTTPException(status_code=404, detail="Segment session not found.")
    return session.to_dict()


@app.post("/api/segments/{id}/upload_media")
async def api_upload_segment_media(
    id: str,
    file: UploadFile = File(...),
    segment_id: str = Form(...)
):
    """Attaches an uploaded image or video to a segment with magic byte validation."""
    validate_session_id(id)
    file_bytes = await file.read()
    session, err, code = upload_segment_media(id, segment_id, file_bytes, file.filename)
    if err:
        raise HTTPException(status_code=code, detail=err)
    return session.to_dict()


@app.post("/api/segments/{id}/upload_bulk")
async def api_upload_bulk(
    id: str,
    files: List[UploadFile] = File(...)
):
    """Bulk uploads media or .zip archive to assign sequentially to empty scenes."""
    validate_session_id(id)
    files_data = []
    for f in files:
        data = await f.read()
        files_data.append((f.filename, data))
    session, results, err, code = upload_bulk_media(id, files_data)
    if err:
        raise HTTPException(status_code=code, detail=err)
    return {"session": session.to_dict(), "results": results}


@app.post("/api/segments/{id}/clear_media")
def api_clear_segment_media(id: str, req: SegmentActionRequest):
    """Clears media for a segment, marking it blank / needs_manual."""
    validate_session_id(id)
    session, err, code = clear_segment_media(id, req.segment_id)
    if err:
        raise HTTPException(status_code=code, detail=err)
    return session.to_dict()


@app.post("/api/segments/{id}/generate")
def api_generate_segment_media(id: str, req: SegmentActionRequest):
    """Regenerates media for a single segment using FLUX."""
    validate_session_id(id)
    session, err, code = generate_segment_media(id, req.segment_id, api_key=os.environ.get("GEMINI_API_KEY", None))
    if err:
        raise HTTPException(status_code=code, detail=err)
    return session.to_dict()


@app.post("/api/segments/{id}/generate_missing")
def api_generate_missing_media(id: str):
    """Generates media for all segments missing visuals in parallel."""
    validate_session_id(id)
    session, err, code = generate_missing_media(id, api_key=os.environ.get("GEMINI_API_KEY", None))
    if err:
        raise HTTPException(status_code=code, detail=err)
    return session.to_dict()


@app.post("/api/segments/{id}/cancel")
def api_cancel_generation(id: str):
    """Cancels running generation for session."""
    validate_session_id(id)
    session, err, code = cancel_session_generation(id)
    if err:
        raise HTTPException(status_code=code, detail=err)
    return session.to_dict()


@app.post("/api/segments/{id}/split")
def api_split_segment(id: str, req: SplitSegmentRequest):
    """Splits an existing segment at a specified word index."""
    validate_session_id(id)
    session, err, code = split_segment(id, req.segment_id, req.split_at_word_index)
    if err:
        raise HTTPException(status_code=code, detail=err)
    return session.to_dict()


@app.post("/api/segments/{id}/merge")
def api_merge_segment(id: str, req: MergeSegmentRequest):
    """Merges a segment with its next or previous neighbor."""
    validate_session_id(id)
    session, err, code = merge_segment(id, req.segment_id, req.direction)
    if err:
        raise HTTPException(status_code=code, detail=err)
    return session.to_dict()


@app.post("/api/segments/{id}/move_boundary")
def api_move_boundary(id: str, req: MoveBoundaryRequest):
    """Shifts words across the seam between two neighboring scenes."""
    validate_session_id(id)
    session, err, code = move_boundary(id, req.segment_id, req.direction, req.words)
    if err:
        raise HTTPException(status_code=code, detail=err)
    return session.to_dict()


@app.post("/api/segments/{id}/add")
def api_add_segment(id: str, req: AddSegmentRequest):
    """Inserts a new segment after the specified segment ID."""
    validate_session_id(id)
    session, err, code = add_segment(id, req.after_segment_id, req.text)
    if err:
        raise HTTPException(status_code=code, detail=err)
    return session.to_dict()


@app.post("/api/segments/{id}/delete")
def api_delete_segment(id: str, req: DeleteSegmentRequest):
    """Removes a segment from the session and shrinks total duration."""
    validate_session_id(id)
    session, err, code = delete_segment(id, req.segment_id)
    if err:
        raise HTTPException(status_code=code, detail=err)
    return session.to_dict()


@app.post("/api/segments/{id}/edit_text")
def api_edit_segment_text(id: str, req: EditTextRequest):
    """Edits a segment's text with word-level diffing and duration recalculation."""
    validate_session_id(id)
    session, err, code = edit_segment_text(id, req.segment_id, req.new_text)
    if err:
        raise HTTPException(status_code=code, detail=err)
    return session.to_dict()


@app.post("/api/segments/{id}/edit_prompt")
def api_edit_segment_prompt(id: str, req: EditPromptRequest):
    """Edits a segment's visual generation prompt (image or video)."""
    validate_session_id(id)
    session, err, code = edit_segment_prompt(id, req.segment_id, req.new_prompt, kind=req.kind)
    if err:
        raise HTTPException(status_code=code, detail=err)
    return session.to_dict()


@app.post("/api/segments/{id}/edit_meta")
def api_edit_meta(id: str, req: EditMetaRequest):
    """Edits a segment's motion and/or session style_lock."""
    validate_session_id(id)
    session, err, code = edit_segment_meta(id, req.segment_id, motion=req.motion, style_lock=req.style_lock)
    if err:
        raise HTTPException(status_code=code, detail=err)
    return session.to_dict()


@app.post("/api/segments/{id}/suggest_prompts")
def api_suggest_prompts(id: str, req: SuggestPromptsRequest):
    """Suggests 3 alternative image prompts for a scene."""
    validate_session_id(id)
    prompts, err, code = suggest_prompts(id, req.segment_id, api_key=os.environ.get("GEMINI_API_KEY", None))
    if err:
        raise HTTPException(status_code=code, detail=err)
    return {"segment_id": req.segment_id, "prompts": prompts}


@app.post("/api/segments/{id}/undo")
def api_undo(id: str):
    """Reverts to the previous snapshot state."""
    validate_session_id(id)
    session, err, code = undo_session(id)
    if err:
        raise HTTPException(status_code=code, detail=err)
    return session.to_dict()


@app.post("/api/segments/{id}/redo")
def api_redo(id: str):
    """Restores the next snapshot state."""
    validate_session_id(id)
    session, err, code = redo_session(id)
    if err:
        raise HTTPException(status_code=code, detail=err)
    return session.to_dict()


@app.get("/api/segments/{id}/export_prompts")
def api_export_prompts(id: str):
    """Exports numbered list of image prompts formatted for external tools."""
    validate_session_id(id)
    text, err, code = export_prompts(id)
    if err:
        raise HTTPException(status_code=code, detail=err)
    return PlainTextResponse(text)


@app.post("/api/segments/{id}/replan_dirty")
def api_replan_dirty_segments(id: str):
    """Re-runs prompt generation and validation for dirty, non-custom segments."""
    validate_session_id(id)
    session, err, code = replan_dirty_segments(id, api_key=os.environ.get("GEMINI_API_KEY", None))
    if err:
        raise HTTPException(status_code=code, detail=err)
    return session.to_dict()


@app.post("/api/segments/{id}/prepare_voice")
async def api_prepare_voice(id: str, req: Optional[PrepareVoiceRequest] = None):
    """Generates TTS audio and aligns scene durations to exact word boundaries."""
    validate_session_id(id)
    v = req.voice if req and req.voice else "en-US-ChristopherNeural"
    r = req.rate if req and req.rate else "+10%"
    session, err, code = await prepare_voice_timeline(id, voice=v, rate=r)
    if err:
        raise HTTPException(status_code=code, detail=err)
    return session.to_dict()


@app.post("/api/generate_metadata")
def get_metadata(req: MetadataRequest):
    """Generates YouTube Shorts Title, Description & Tags."""
    meta = generate_youtube_metadata(req.script)
    return meta


def run_render_task(job_id: str, req: RenderRequest):
    def update_progress(msg: str, pct: int):
        cur = load_job(job_id) or {}
        cur.update({"status": "processing", "message": msg, "progress": pct})
        save_job(job_id, cur)

    try:
        res = render_shorts_video(
            script_text=req.script,
            voice=req.voice,
            voice_rate=req.voice_rate,
            subtitle_style=req.subtitle_style,
            bgm_track=req.bgm_track,
            bgm_volume=req.bgm_volume,
            progress_callback=update_progress,
            scene_overrides=req.scene_overrides,
            preview_scenes=req.preview_scenes,
            project_id=req.project_id,
            session_id=req.session_id
        )
        metadata = generate_youtube_metadata(req.script)
        cur = load_job(job_id) or {}
        cur.update({
            "status": "completed",
            "progress": 100,
            "message": "Complete! Video generated.",
            "video_url": res["video_url"],
            "duration": res["duration"],
            "metadata": metadata
        })
        save_job(job_id, cur)
    except Exception as e:
        logger.error(f"Render failed for job {job_id}: {e}", exc_info=True)
        cur = load_job(job_id) or {}
        cur.update({
            "status": "error",
            "progress": 0,
            "message": str(e)
        })
        save_job(job_id, cur)


@app.post("/api/generate_short")
async def generate_short(req: RenderRequest, background_tasks: BackgroundTasks):
    """Starts video generation in background and returns job ID."""
    if req.script:
        req.script = sanitize_spoken_script(req.script)
    script_to_check = req.script.strip()
    if not script_to_check and req.session_id:
        sess = load_session(req.session_id)
        if sess and sess.script_text.strip():
            script_to_check = sess.script_text.strip()

    if not script_to_check:
        raise HTTPException(status_code=400, detail="Script text cannot be empty.")

    job_id = str(uuid.uuid4())[:8]
    save_job(job_id, {
        "status": "queued",
        "progress": 5,
        "message": "Initializing generation queue...",
        "video_url": None,
        "metadata": None
    })

    background_tasks.add_task(run_render_task, job_id, req)
    return {"job_id": job_id}


@app.get("/api/status/{job_id}")
async def get_status(job_id: str):
    """Poll rendering progress."""
    job = load_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
