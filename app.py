import os
import sys
import json
import uuid
import shutil
import logging
from typing import Optional, Dict, List, Any

logger = logging.getLogger("yt_shorts_app")

# Load local .env file if it exists
_env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_file):
    try:
        with open(_env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except Exception:
        pass

from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException

# Enforce UTF-8 console output on Windows to prevent UnicodeEncodeError
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
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
    add_segment,
    delete_segment,
    edit_segment_text,
    edit_segment_prompt,
    replan_dirty_segments,
    upload_segment_media,
    clear_segment_media,
    generate_segment_media,
    generate_missing_media,
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
        except Exception:
            pass
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
    mode: str = "manual"  # "auto" | "manual"
    manual_delimiter: bool = False


class SplitSegmentRequest(BaseModel):
    segment_id: str
    split_at_word_index: int


class MergeSegmentRequest(BaseModel):
    segment_id: str
    direction: str = "next"


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


class SegmentActionRequest(BaseModel):
    segment_id: str


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


@app.post("/api/segments/create")
def api_create_segments(req: CreateSegmentsRequest):
    """Creates a new StoryboardSession in Auto or Manual Segment mode."""
    if not req.script.strip():
        raise HTTPException(status_code=400, detail="Script cannot be empty.")
    try:
        session = create_session(
            script=req.script,
            mode=req.mode,
            manual_delimiter=req.manual_delimiter,
            api_key=os.environ.get("GEMINI_API_KEY", None)
        )
        return session.to_dict()
    except Exception as e:
        log_and_raise_safe(e, "Failed to create segment session", status_code=500)


@app.post("/api/segments/{id}/upload_media")
def api_upload_segment_media(
    id: str,
    file: UploadFile = File(...),
    segment_id: str = Form(...)
):
    """Attaches an uploaded image or video to a segment."""
    allowed_exts = ('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.mp4', '.mov', '.webm')
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_exts:
        raise HTTPException(status_code=400, detail="Unsupported file format. Supported: JPG, PNG, WEBP, MP4, MOV, WEBM.")

    safe_name = f"media_{uuid.uuid4().hex[:8]}{ext}"
    dest_path = os.path.abspath(os.path.join("outputs/ai_previews", safe_name))
    with open(dest_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    media_type = "video" if ext in ('.mp4', '.mov', '.webm') else "image"
    session, err, code = upload_segment_media(id, segment_id, dest_path, media_type)
    if err:
        raise HTTPException(status_code=code, detail=err)
    return session.to_dict()


@app.post("/api/segments/{id}/clear_media")
def api_clear_segment_media(id: str, req: SegmentActionRequest):
    """Clears media for a segment, marking it blank / needs_manual."""
    session, err, code = clear_segment_media(id, req.segment_id)
    if err:
        raise HTTPException(status_code=code, detail=err)
    return session.to_dict()


@app.post("/api/segments/{id}/generate")
def api_generate_segment_media(id: str, req: SegmentActionRequest):
    """Regenerates media for a single segment using FLUX."""
    session, err, code = generate_segment_media(id, req.segment_id, api_key=os.environ.get("GEMINI_API_KEY", None))
    if err:
        raise HTTPException(status_code=code, detail=err)
    return session.to_dict()


@app.post("/api/segments/{id}/generate_missing")
def api_generate_missing_media(id: str):
    """Generates media for all segments missing visuals in parallel."""
    session, err, code = generate_missing_media(id, api_key=os.environ.get("GEMINI_API_KEY", None))
    if err:
        raise HTTPException(status_code=code, detail=err)
    return session.to_dict()


@app.post("/api/segments/{id}/split")
def api_split_segment(id: str, req: SplitSegmentRequest):
    """Splits an existing segment at a specified word index."""
    session, err, code = split_segment(id, req.segment_id, req.split_at_word_index)
    if err:
        raise HTTPException(status_code=code, detail=err)
    return session.to_dict()


@app.post("/api/segments/{id}/merge")
def api_merge_segment(id: str, req: MergeSegmentRequest):
    """Merges a segment with its next or previous neighbor."""
    session, err, code = merge_segment(id, req.segment_id, req.direction)
    if err:
        raise HTTPException(status_code=code, detail=err)
    return session.to_dict()


@app.post("/api/segments/{id}/add")
def api_add_segment(id: str, req: AddSegmentRequest):
    """Inserts a new segment after the specified segment ID."""
    session, err, code = add_segment(id, req.after_segment_id, req.text)
    if err:
        raise HTTPException(status_code=code, detail=err)
    return session.to_dict()


@app.post("/api/segments/{id}/delete")
def api_delete_segment(id: str, req: DeleteSegmentRequest):
    """Removes a segment from the session and shrinks total duration."""
    session, err, code = delete_segment(id, req.segment_id)
    if err:
        raise HTTPException(status_code=code, detail=err)
    return session.to_dict()


@app.post("/api/segments/{id}/edit_text")
def api_edit_segment_text(id: str, req: EditTextRequest):
    """Edits a segment's text with word-level diffing and duration recalculation."""
    session, err, code = edit_segment_text(id, req.segment_id, req.new_text)
    if err:
        raise HTTPException(status_code=code, detail=err)
    return session.to_dict()


@app.post("/api/segments/{id}/edit_prompt")
def api_edit_segment_prompt(id: str, req: EditPromptRequest):
    """Edits a segment's visual generation prompt (image or video)."""
    session, err, code = edit_segment_prompt(id, req.segment_id, req.new_prompt, kind=req.kind)
    if err:
        raise HTTPException(status_code=code, detail=err)
    return session.to_dict()


@app.post("/api/segments/{id}/replan_dirty")
def api_replan_dirty_segments(id: str):
    """Re-runs prompt generation and validation for dirty, non-custom segments."""
    session, err, code = replan_dirty_segments(id, api_key=os.environ.get("GEMINI_API_KEY", None))
    if err:
        raise HTTPException(status_code=code, detail=err)
    return session.to_dict()


@app.get("/api/segments/{id}")
def api_get_segment_session(id: str):
    """Retrieves an existing StoryboardSession by ID."""
    session = load_session(id)
    if not session:
        raise HTTPException(status_code=404, detail="Segment session not found.")
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
