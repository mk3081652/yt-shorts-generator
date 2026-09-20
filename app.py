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
from pydantic import BaseModel

from engine.tts import get_available_voices, generate_speech_with_words
from engine.subtitles import STYLE_PRESETS
from engine.audio import get_available_bgm
from engine.metadata import get_viral_hooks, get_script_templates, generate_youtube_metadata
from engine.compositor import render_shorts_video
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
    bg_choice: Optional[str] = None  # Ignored, for backward compatibility


class VoicePreviewRequest(BaseModel):
    text: str = "Welcome to the ultimate YouTube Shorts Creator!"
    voice: str = "en-US-ChristopherNeural"
    voice_rate: str = "+10%"


class MetadataRequest(BaseModel):
    script: str


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


@app.post("/api/auto/generate")
def api_auto_generate(req: AutoGenerateRequest):
    """Auto mode: splits script, plans prompts with Gemini, generates images with FLUX."""
    if not req.script.strip():
        raise HTTPException(status_code=400, detail="Script cannot be empty.")
    try:
        session = generate_auto_session(
            script=req.script,
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
    """Cleans up sessions and previews older than 7 days."""
    cutoff = time.time() - (7 * 86400)
    for folder in ("outputs/segment_sessions", "outputs/ai_previews", "outputs/custom_scenes"):
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
    if not req.script.strip():
        raise HTTPException(status_code=400, detail="Script cannot be empty.")
    try:
        session = create_session(
            script=req.script,
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
