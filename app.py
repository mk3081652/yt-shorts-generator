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

from urllib.parse import quote
from fastapi import FastAPI, Request, UploadFile, File, Form, BackgroundTasks, HTTPException

# Enforce UTF-8 console output on Windows to prevent UnicodeEncodeError
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, FileResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict

from engine.tts import get_available_voices, generate_speech_with_words
from engine.subtitles import STYLE_PRESETS
from engine.audio import get_available_bgm
from engine.metadata import get_viral_hooks, get_script_templates, generate_youtube_metadata
from engine.render import render_shorts_video

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
from engine.youtube_uploader import (
    check_auth_status,
    upload_video_to_youtube,
    get_authenticated_service,
    authorize_new_channel,
    list_channels,
    set_active_channel,
    save_channel_credentials,
    remove_channel,
    export_channel_credentials,
    get_active_channel_id,
    ensure_tokens_dir,
    create_web_flow
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
elif bool(os.environ.get("RENDER") or os.environ.get("PORT")):
    allowed_origins = ["*"]
else:
    allowed_origins = [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
        "http://127.0.0.1:3000"
    ]

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
    subtitle_style: str = "hyper_yellow"
    bgm_track: str = "phonk_energetic"
    bgm_volume: float = 0.18
    transition_style: Optional[str] = "crossfade"
    scene_overrides: Optional[Dict[str, str]] = None
    preview_scenes: Optional[List[Dict[str, Any]]] = None
    session_id: Optional[str] = None
    project_id: Optional[str] = None
    custom_audio_path: Optional[str] = None
    tts_provider: Optional[str] = None
    motion_texture: Optional[str] = None
    resolution: Optional[str] = "720p"

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
    angle: Optional[str] = "investigative_mystery"  # "investigative_mystery" | "contrarian_myth" | "forensic_details"


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
    transition_style: Optional[str] = None


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


@app.get("/favicon.ico")
def serve_favicon():
    return FileResponse("static/favicon.ico")


@app.get("/healthz")
@app.get("/health")
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


def synthesize_fallback_script(topic: str, angle: str = "investigative_mystery") -> str:
    """Generates a high-retention 50-60 second viral YouTube Shorts script when AI is unavailable."""
    topic_clean = topic.strip().title()
    templates_by_angle = {
        "investigative_mystery": [
            f"Think you know the real truth about {topic_clean}? What if I told you the official story is completely backward? Deep below the surface, researchers and investigative teams uncovered classified anomalies that historians have argued about for decades. When the final records were examined, the evidence was undeniable. Strange signals were recorded, key witnesses suddenly went silent, and official reports were heavily redacted. What they actually found defies every explanation we were taught in school. The closer you look at the timeline, the clearer it becomes that something massive occurred behind closed doors. The real question isn't whether it happened—the question is: why are they still keeping it quiet? Drop a comment with what you think, and subscribe for more mind-bending revelations.",
            f"This secret about {topic_clean} will completely change how you see the world. Almost nobody knows what actually occurred behind closed doors during the final moments. When independent experts analyzed the recovered data, what they uncovered shocked everyone in the room. Unexplained readings appeared on the monitors, followed by an eerie silence that lasted for days. Decades of research have tried to sweep these facts under the rug, but modern forensic technology has finally cracked the puzzle. The deeper you look into the archives, the more mysterious the entire event becomes. Could this be the biggest cover-up in modern history? Share this with someone who needs to know the truth, and subscribe so you don't miss part two."
        ],
        "contrarian_myth": [
            f"Everything you were told about {topic_clean} is a complete lie. The mainstream consensus says one thing, but primary source archives expose the shocking opposite. When researchers cross-referenced the original field notes, the popular myth collapsed instantly. The people behind the initial narrative had a massive financial incentive to keep the real facts hidden from the public. Look at the data from the initial experiment: the numbers don't match the history books at all. Once you see the deception, you can never unsee it. Did you believe the myth too? Tell me what surprised you most in the comments, and follow for more truth-bombs.",
            f"Stop believing this dangerous myth about {topic_clean}! For generations, textbook history repeated the exact same story without checking the facts. But when investigators tracked down the unedited journals, the whole narrative fell apart. What everyone considers common knowledge is actually based on a mistranslation from over a century ago. The actual discovery was far more dangerous, and officials scrambled to suppress it immediately. The real evidence is right in front of us, yet ninety-nine percent of people still believe the fairy tale. What do you think really happened? Share your thoughts below and subscribe."
        ],
        "forensic_details": [
            f"You won't believe what forensic investigators just uncovered about {topic_clean}. When detectives re-examined the physical evidence with modern spectral analysis, microscopic traces revealed a chilling detail. The timeline documented by officials was off by exactly three hours. Critical communication logs had been wiped clean, but backup telemetry caught the exact sequence of events. Every forensic marker points to an outside intervention that was intentionally covered up. The evidence isn't speculation—it's written right in the digital metadata. What do you think this proof actually means? Let me know in the comments, and follow for more forensic breakdowns."
        ]
    }
    import random
    pool = templates_by_angle.get(angle, templates_by_angle["investigative_mystery"])
    return random.choice(pool)


@app.post("/api/generate_script")
def api_generate_script(req: GenerateScriptRequest):
    """Generates a viral 50-60 second spoken narration script for YouTube Shorts using Gemini or local synthesizer."""
    topic = req.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="Topic cannot be empty.")

    angle = (req.angle or "investigative_mystery").lower()
    angle_instructions = {
        "investigative_mystery": "Editorial Angle: Investigative Mystery. Unearth classified anomalies, unexpected disappearances, or unexplained records. Question official timelines and highlight strange clues.",
        "contrarian_myth": "Editorial Angle: Contrarian Myth-Busting. Challenge conventional wisdom, shatter widely accepted myths, and expose what mainstream consensus gets completely wrong.",
        "forensic_details": "Editorial Angle: Forensic Telemetry & Evidence. Focus on micro-clues, recovered technical telemetry, timeline inconsistencies, and forensic records."
    }
    angle_instruction = angle_instructions.get(angle, angle_instructions["investigative_mystery"])

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    clean_text = None
    model_used = None

    if api_key:
        prompt = f"""You are an elite, viral YouTube Shorts narrative specialist.
Write a full-length, high-retention 50-60 second spoken voiceover script about: "{topic}".

{angle_instruction}

STRICT HIGH-RETENTION & LOW-SWIPE RULES (Algorithmic Virality):
1. PATTERN-INTERRUPT HOOK (First 1.5 seconds): The first sentence MUST be an irresistible, forbidden-secret or curiosity-gap statement that forces the viewer's thumb to halt immediately. No introductions, no greetings, no throat-clearing.
2. Fast-paced, intriguing storytelling with genuine surprises, drama, or twists every 5-8 seconds.
3. Cadence variation: Keep sentence lengths varied between 1.8s and 3.2s per phrase (roughly 5 to 10 words per phrase) for rapid visual transitions without monotone pacing.
4. Total word count MUST be between 130 and 150 words (aiming for exactly 50 to 58 seconds of speech, staying safely under the 60-second YouTube Shorts limit).
5. Pacing: Break the story into 4 distinct beats:
   - Beat 1 (0-10s): The shocking hook and the setup.
   - Beat 2 (10-30s): The rising intrigue and strange clues or discoveries.
   - Beat 3 (30-48s): The climactic revelation or unexpected twist.
   - Beat 4 (48-56s): SEAMLESS INFINITY LOOP! The final sentence MUST grammatically connect directly back into the opening hook sentence of Beat 1, creating an endless loop so viewers re-watch without realizing it ended (boosting retention above 100%).
   - STRICT BAN: DO NOT SAY "Subscribe for more", "Follow for more", or "Leave a comment" anywhere in the script! It triggers viewers to swipe away instantly.
6. OUTPUT SPOKEN NARRATION WORDS ONLY!
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
                thinking_level=None,
                max_output_tokens=4000,
                json_mode=False,
                api_key=api_key
            )
            if text:
                clean_text = text.strip()
                clean_text = re.sub(r'\*\*\[.*?\]\*\*', '', clean_text)
                clean_text = re.sub(r'\[.*?\]', '', clean_text)
                clean_text = re.sub(r'^(?:Voiceover|Narrator|Script|Hook):\s*', '', clean_text, flags=re.IGNORECASE)
                clean_text = re.sub(r'^["\']|["\']$', '', clean_text)
                clean_text = sanitize_spoken_script(clean_text)
                model_used = model
        except Exception as e:
            logger.warning(f"Gemini script generation failed, falling back to local synthesizer: {e}")

    if not clean_text:
        clean_text = synthesize_fallback_script(topic, angle=angle)
        model_used = "viral_synthesizer"

    return {"topic": topic, "script": clean_text, "model": model_used, "angle": angle}


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
    proj, err, code = edit_project_meta(
        id,
        scene_id=req.segment_id,
        motion=req.motion,
        style_lock=req.style_lock,
        transition_style=req.transition_style
    )
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
    try:
        file_bytes = await file.read()
        proj, err, code = upload_project_media(id, segment_id, file_bytes, file.filename or "media.jpg")
        if err:
            raise HTTPException(status_code=code, detail=err)
        return proj.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Upload Error] Project {id}, Scene {segment_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to process media upload: {str(e)}")


@app.post("/api/projects/{id}/upload_bulk")
async def api_project_upload_bulk(
    id: str,
    files: List[UploadFile] = File(...)
):
    validate_session_id(id)
    try:
        files_data = []
        for f in files:
            data = await f.read()
            files_data.append((f.filename or "media.jpg", data))
        proj, results, err, code = upload_project_bulk(id, files_data)
        if err:
            raise HTTPException(status_code=code, detail=err)
        return {"project": proj.to_dict(), "session": proj.to_dict(), "results": results}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Bulk Upload Error] Project {id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to process bulk upload: {str(e)}")


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
        project = create_project(
            script=cleaned,
            start="auto",
            manual_delimiter=req.manual_delimiter,
            api_key=os.environ.get("GEMINI_API_KEY", None)
        )
        return project.to_dict()
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
            session_id=req.session_id,
            transition_style=getattr(req, "transition_style", "crossfade"),
            custom_audio_path=getattr(req, "custom_audio_path", None),
            tts_provider=getattr(req, "tts_provider", None),
            motion_texture=getattr(req, "motion_texture", None),
            resolution=getattr(req, "resolution", "720p") or "720p"
        )
        script_for_meta = req.script or ""
        if not script_for_meta.strip() and req.project_id:
            try:
                proj = load_project(req.project_id)
                if proj and getattr(proj, "script", None):
                    script_for_meta = proj.script
            except Exception:
                pass
        metadata = generate_youtube_metadata(script_for_meta)

        # Generate high-CTR viral thumbnail for download/preview
        thumb_path = os.path.abspath(f"outputs/thumb_{job_id}.jpg")
        thumb_url = None
        try:
            from engine.thumbnail import generate_viral_thumbnail
            generate_viral_thumbnail(
                title=metadata.get("title", "Mystery Short"),
                script=script_for_meta,
                video_path=os.path.abspath(f"outputs/{os.path.basename(res['video_url'])}"),
                output_path=thumb_path
            )
            thumb_url = f"/outputs/{os.path.basename(thumb_path)}"
        except Exception as e:
            logger.warning(f"Render task thumbnail error: {e}")

        cur = load_job(job_id) or {}
        cur.update({
            "status": "completed",
            "progress": 100,
            "message": "Complete! Video generated.",
            "video_url": res["video_url"],
            "thumbnail_url": thumb_url,
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


@app.get("/api/job/{job_id}")
@app.get("/api/status/{job_id}")
async def get_status(job_id: str):
    """Poll rendering progress."""
    job = load_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


class LoopScriptRequest(BaseModel):
    script: str
    api_key: Optional[str] = None


@app.post("/api/script/loop")
def api_loop_script(req: LoopScriptRequest):
    """
    Refines an existing script so the final sentence connects seamlessly back into the opening line,
    creating an infinite replay loop that drives retention >100%.
    """
    raw = (req.script or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Script cannot be empty.")

    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', raw) if s.strip()]
    if not sentences:
        return {"success": True, "script": raw}

    first_sentence = sentences[0]
    api_key = req.api_key or os.environ.get("GEMINI_API_KEY")

    prompt = f"""You are an elite YouTube Shorts script editor specialized in 100%+ retention through Seamless Infinity Loops.
Here is the creator's current script:
\"\"\"{raw}\"\"\"

The opening hook is:
\"{first_sentence}\"

TASK:
1. Keep the story, facts, and voice intact.
2. Remove any "Subscribe for more", "Follow for more", or generic sign-offs.
3. Rewrite ONLY the final sentence/clause so that it syntactically and logically connects directly back into the opening hook: \"{first_sentence}\".
4. When the video restarts, the listener should not notice the boundary because the last sentence bridges seamlessly into the first sentence.
5. Total length must be 130 to 150 words.
6. Return ONLY the spoken voiceover script text with no labels, no quotation marks, and no commentary.
"""
    try:
        from engine.gemini_client import generate_content
        looped_text, _ = generate_content(prompt, thinking_level="low", max_output_tokens=3000, json_mode=False, api_key=api_key, timeout=8)
        if looped_text and len(looped_text.strip().split()) >= 20:
            clean = sanitize_spoken_script(looped_text)
            return {"success": True, "script": clean, "first_sentence": first_sentence}
    except Exception as e:
        logger.warning(f"Script looping error: {e}")

    # Fallback rule-based loop bridge
    filtered = [s for s in sentences if not any(w in s.lower() for w in ["subscribe", "follow", "like this video", "comment below"])]
    if filtered:
        bridge = "And that is the exact reason why..."
        looped = " ".join(filtered) + " " + bridge
        return {"success": True, "script": sanitize_spoken_script(looped), "first_sentence": first_sentence}

    return {"success": True, "script": raw, "first_sentence": first_sentence}


class YouTubePublishRequest(BaseModel):
    script: str = ""
    title: Optional[str] = None
    topic: Optional[str] = None
    privacy_status: str = "unlisted"  # "public", "unlisted", "private"
    channel_id: Optional[str] = None
    voice: str = "en-US-ChristopherNeural"
    voice_rate: str = "+10%"
    subtitle_style: str = "hyper_yellow"
    bgm_track: str = "mystery_suspense"
    bgm_volume: float = 0.18
    project_id: Optional[str] = None
    rapid_pacing: bool = True
    category_id: str = "27"
    enable_sfx: bool = True
    enable_progress_bar: bool = True
    resolution: Optional[str] = "720p"


def run_youtube_publish_task(job_id: str, req: YouTubePublishRequest):
    def update_progress(msg: str, pct: int):
        cur = load_job(job_id) or {}
        cur.update({"status": "processing", "message": msg, "progress": pct})
        save_job(job_id, cur)

    try:
        logger.info(f"[YouTube Publish] Starting job {job_id} with requested privacy_status='{req.privacy_status}' and channel_id='{req.channel_id}'")
        update_progress("Analyzing script and generating viral metadata...", 5)
        raw_script = (req.script or "").strip()
        if not raw_script and req.project_id:
            try:
                p = load_project(req.project_id)
                if p and p.script:
                    raw_script = p.script
            except Exception:
                pass

        if not raw_script and req.topic:
            raw_script = req.topic.strip()

        # Sanitize pasted text
        clean_script = sanitize_spoken_script(raw_script)

        # If user only passed a short topic/headline (< 20 words), generate a full 50-60s script with AI
        if clean_script and len(clean_script.split()) < 20:
            update_progress("Expanding topic into a 60-second high-retention script with Infinity Loop...", 10)
            try:
                from engine.gemini_client import generate_content as gemini_gen
                prompt = (
                    f"Write a full 50-58 second spoken voiceover script (130-150 words) about: {clean_script}. "
                    "Start with an irresistible 2-second curiosity hook. Fast-paced, intriguing, no markdown, verbatim spoken words only. "
                    "The final sentence MUST bridge seamlessly into the first sentence creating an infinite replay loop. "
                    "Never say 'subscribe' or 'follow'."
                )
                ai_text, _ = gemini_gen(prompt, thinking_level="low", timeout=12)
                if ai_text and len(ai_text.split()) >= 20:
                    clean_script = sanitize_spoken_script(ai_text)
            except Exception as e:
                logger.warning(f"AI script expansion skipped: {e}")

        if not clean_script:
            raise ValueError("Script or topic cannot be empty.")

        # Generate high-CTR Title, Description, and Tags
        update_progress("Crafting SEO Title, Description, and YPP Tags...", 15)
        metadata = generate_youtube_metadata(clean_script)
        if req.title and req.title.strip():
            metadata["title"] = req.title.strip()

        # Storyboard / Scene Planning
        update_progress("Planning dynamic multi-focal storyboard...", 25)
        proj = None
        if req.project_id:
            proj = load_project(req.project_id)
        if not proj:
            proj = create_project(
                script=clean_script,
                start="auto",
                api_key=os.environ.get("GEMINI_API_KEY", None)
            )

        # Wait for scene media generation if auto mode queued scenes (up to 20s, or skip if rate-limited)
        update_progress("Synthesizing scene visuals...", 35)
        from engine.flux import is_rate_limited
        start_wait = time.time()
        while time.time() - start_wait < 20:
            if is_rate_limited():
                break
            p_check = load_project(proj.id)
            if not p_check:
                break
            pending = [s for s in p_check.scenes if s.status in ("queued", "generating")]
            if not pending:
                proj = p_check
                break
            time.sleep(1.0)

        # Render vertical video (720p Turbo default or 1080p)
        target_res = getattr(req, "resolution", "720p") or "720p"
        update_progress(f"Turbo rendering {target_res} Short with camera motion, SFX, & subtitles...", 50)
        res = render_shorts_video(
            script_text=clean_script,
            voice=req.voice,
            voice_rate=req.voice_rate,
            subtitle_style=req.subtitle_style,
            bgm_track=req.bgm_track,
            bgm_volume=req.bgm_volume,
            progress_callback=update_progress,
            project_id=proj.id,
            rapid_pacing=req.rapid_pacing,
            transition_style="crossfade",
            enable_sfx=getattr(req, "enable_sfx", True),
            enable_progress_bar=getattr(req, "enable_progress_bar", True),
            resolution=target_res,
            hook_text=f"⚠️ {metadata.get('title', '').split('#')[0].strip().upper()[:40]}" if metadata.get('title') else None
        )

        final_video_file = os.path.abspath(f"outputs/{os.path.basename(res['video_url'])}")

        # Synthesize High-CTR Viral Thumbnail
        thumb_path = os.path.abspath(f"outputs/thumb_{job_id}.jpg")
        thumb_url = None
        try:
            from engine.thumbnail import generate_viral_thumbnail
            first_scene_img = None
            if proj and proj.scenes:
                for sc in proj.scenes:
                    sc_img = getattr(sc, "image_path", None) or getattr(sc, "media_path", None)
                    if sc_img and os.path.exists(sc_img):
                        first_scene_img = sc_img
                        break
            generate_viral_thumbnail(
                title=metadata.get("title", "Mystery Short"),
                script=clean_script,
                video_path=final_video_file,
                base_image_path=first_scene_img,
                output_path=thumb_path
            )
            thumb_url = f"/outputs/{os.path.basename(thumb_path)}"
        except Exception as e:
            logger.warning(f"Viral thumbnail synthesis notice: {e}")
            thumb_path = None

        # Check YouTube Auth and Publish
        update_progress("Checking YouTube API connection...", 75)
        auth = check_auth_status(channel_id=req.channel_id)

        if auth.get("authenticated"):
            update_progress("Uploading video and viral thumbnail to YouTube...", 80)
            upload_result = upload_video_to_youtube(
                video_path=final_video_file,
                title=metadata.get("title", "Mystery Short #Shorts"),
                description=metadata.get("description", ""),
                tags=metadata.get("tags", []),
                privacy_status=req.privacy_status,
                category_id=req.category_id,
                channel_id=req.channel_id,
                thumbnail_path=thumb_path,
                progress_callback=update_progress
            )

            if upload_result.get("success"):
                cur = load_job(job_id) or {}
                cur.update({
                    "status": "completed",
                    "progress": 100,
                    "message": "Published directly to YouTube with Viral Thumbnail! 🎉",
                    "video_url": res["video_url"],
                    "thumbnail_url": thumb_url,
                    "duration": res["duration"],
                    "metadata": metadata,
                    "youtube_published": True,
                    "video_id": upload_result.get("video_id"),
                    "youtube_url": upload_result.get("youtube_url"),
                    "watch_url": upload_result.get("watch_url"),
                    "privacy_status": req.privacy_status,
                    "actual_privacy_status": upload_result.get("actual_privacy_status", req.privacy_status),
                    "channel_id": upload_result.get("channel_id"),
                    "channel_title": upload_result.get("channel_title") or auth.get("channel_title")
                })
                save_job(job_id, cur)
                return
            else:
                cur = load_job(job_id) or {}
                cur.update({
                    "status": "completed",
                    "progress": 100,
                    "message": f"Video rendered! YouTube upload note: {upload_result.get('error')}",
                    "video_url": res["video_url"],
                    "thumbnail_url": thumb_url,
                    "duration": res["duration"],
                    "metadata": metadata,
                    "youtube_published": False,
                    "youtube_error": upload_result.get("error")
                })
                save_job(job_id, cur)
                return
        else:
            # Video rendered successfully! Provide instructions for YouTube OAuth
            cur = load_job(job_id) or {}
            cur.update({
                "status": "completed",
                "progress": 100,
                "message": "Video generated! Connect your YouTube account with client_secrets.json to auto-publish.",
                "video_url": res["video_url"],
                "duration": res["duration"],
                "metadata": metadata,
                "youtube_published": False,
                "youtube_auth_needed": True,
                "youtube_auth_message": auth.get("message", "Place client_secrets.json in project root and authorize.")
            })
            save_job(job_id, cur)

    except Exception as e:
        logger.error(f"YouTube publish task failed for job {job_id}: {e}", exc_info=True)
        cur = load_job(job_id) or {}
        cur.update({
            "status": "error",
            "progress": 0,
            "message": str(e)
        })
        save_job(job_id, cur)


class ChannelSelectRequest(BaseModel):
    channel_id: str


class ChannelImportRequest(BaseModel):
    token_json: Any


@app.get("/api/youtube/channels")
def api_youtube_get_channels():
    """Lists all connected YouTube channels and the active channel."""
    channels = list_channels()
    active_id = get_active_channel_id()
    return {
        "channels": channels,
        "active_channel_id": active_id,
        "total": len(channels)
    }


@app.post("/api/youtube/channels/select")
def api_youtube_select_channel(req: ChannelSelectRequest):
    """Sets the designated channel as active."""
    success = set_active_channel(req.channel_id)
    if not success:
        raise HTTPException(status_code=404, detail="Channel not found.")
    return {"success": True, "active_channel_id": req.channel_id}


@app.post("/api/youtube/channels/import")
def api_youtube_import_token(req: ChannelImportRequest):
    """Imports credentials JSON to connect a new channel."""
    try:
        token_data = req.token_json
        if isinstance(token_data, str):
            token_data = json.loads(token_data)
        saved = save_channel_credentials(token_data)
        return {"success": True, "channel": saved}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to import credentials: {str(e)}")


@app.post("/api/youtube/channels/upload_token")
async def api_youtube_upload_token_file(file: UploadFile = File(...)):
    """Uploads a token.json file to connect a channel."""
    try:
        content = await file.read()
        text = content.decode("utf-8")
        data = json.loads(text)
        saved = save_channel_credentials(data)
        return {"success": True, "channel": saved}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to process token file: {str(e)}")


@app.get("/api/youtube/channels/{channel_id}/export")
def api_youtube_export_channel(channel_id: str):
    """Exports credentials JSON for a specific channel."""
    creds = export_channel_credentials(channel_id)
    if not creds:
        raise HTTPException(status_code=404, detail="Credentials not found for channel.")
    return JSONResponse(content=creds)


@app.get("/api/youtube/channels/{channel_id}/download")
def api_youtube_download_channel_token(channel_id: str):
    """Downloads token credentials as a JSON file."""
    t_dir = ensure_tokens_dir()
    path = os.path.join(t_dir, f"{channel_id}.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Channel credentials file not found.")
    return FileResponse(
        path=path,
        media_type="application/json",
        filename=f"token_{channel_id}.json"
    )


@app.delete("/api/youtube/channels/{channel_id}")
def api_youtube_remove_channel(channel_id: str):
    """Removes a connected channel."""
    removed = remove_channel(channel_id)
    return {"success": removed, "channels": list_channels(), "active_channel_id": get_active_channel_id()}


@app.get("/api/youtube/auth_status")
def api_youtube_auth_status(channel_id: Optional[str] = None):
    """Checks whether YouTube OAuth credentials are valid and ready."""
    return check_auth_status(channel_id=channel_id)


@app.post("/api/youtube/authorize")
def api_youtube_authorize():
    """Forces OAuth consent flow with Google Account picker to link a new channel."""
    try:
        info = authorize_new_channel()
        return {
            "authenticated": True,
            "channel_title": info.get("channel_title"),
            "channel_id": info.get("channel_id"),
            "channel": info
        }
    except Exception as e:
        err_str = str(e)
        return {
            "authenticated": False,
            "error": err_str,
            "is_headless": ("headless" in err_str.lower() or "browser" in err_str.lower()),
            "guidance": "If running on Render or remote server, use 'Upload token.json' or 'Paste JSON' in the UI."
        }


def _get_oauth_redirect_uri(request: Request) -> str:
    """Builds redirect URI matching incoming protocol & host (supports reverse proxies)."""
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.headers.get("host", request.url.netloc))
    return f"{proto}://{host}/api/youtube/oauth2callback"


@app.get("/api/youtube/oauth/url")
def api_youtube_oauth_url(request: Request):
    """Returns Google OAuth authorization URL for web redirect."""
    redirect_uri = _get_oauth_redirect_uri(request)
    try:
        flow = create_web_flow(redirect_uri=redirect_uri)
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            prompt="select_account consent",
            include_granted_scopes="true"
        )
        return {"success": True, "auth_url": auth_url, "redirect_uri": redirect_uri}
    except Exception as e:
        logger.error(f"Failed to create OAuth URL: {e}")
        return {"success": False, "error": str(e), "redirect_uri": redirect_uri}


@app.get("/api/youtube/oauth/login")
def api_youtube_oauth_login(request: Request):
    """Directly redirects browser to Google Account selection & consent screen."""
    redirect_uri = _get_oauth_redirect_uri(request)
    try:
        flow = create_web_flow(redirect_uri=redirect_uri)
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            prompt="select_account consent",
            include_granted_scopes="true"
        )
        resp = RedirectResponse(url=auth_url)
        if flow.code_verifier:
            resp.set_cookie("oauth_code_verifier", flow.code_verifier, max_age=600, httponly=True, samesite="lax")
        return resp
    except Exception as e:
        logger.error(f"OAuth login redirect error: {e}")
        return RedirectResponse(url=f"/?oauth_error={quote(str(e))}")


@app.get("/api/youtube/oauth2callback")
def api_youtube_oauth2callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None
):
    """Receives authorization response from Google and completes channel connection."""
    if error:
        logger.warning(f"OAuth callback received error from Google: {error}")
        return RedirectResponse(url=f"/?oauth_error={quote(error)}")

    if not code:
        return RedirectResponse(url="/?oauth_error=No+authorization+code+received+from+Google")

    redirect_uri = _get_oauth_redirect_uri(request)
    try:
        os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
        flow = create_web_flow(redirect_uri=redirect_uri)
        verifier = request.cookies.get("oauth_code_verifier")
        if verifier:
            flow.code_verifier = verifier
        flow.fetch_token(code=code)
        creds = flow.credentials
        saved = save_channel_credentials(json.loads(creds.to_json()))
        channel_name = saved.get("channel_title", "YouTube Channel")
        logger.info(f"[OAuth Callback] Successfully connected channel '{channel_name}' via web redirect!")
        resp = RedirectResponse(url=f"/?connected={quote(channel_name)}")
        resp.delete_cookie("oauth_code_verifier")
        return resp
    except Exception as e:
        logger.error(f"Failed to process OAuth callback: {e}", exc_info=True)
        return RedirectResponse(url=f"/?oauth_error={quote(str(e))}")


@app.post("/api/youtube/publish")
async def api_youtube_publish(req: YouTubePublishRequest, background_tasks: BackgroundTasks):
    """1-Click Paste & Publish to YouTube."""
    raw_script = (req.script or "").strip()
    if not raw_script and not req.topic and not req.project_id:
        raise HTTPException(status_code=400, detail="Please provide a script or topic to publish.")

    job_id = str(uuid.uuid4())[:8]
    save_job(job_id, {
        "status": "queued",
        "progress": 5,
        "message": "Starting 1-Click YouTube publishing workflow...",
        "video_url": None,
        "youtube_url": None,
        "metadata": None
    })

    background_tasks.add_task(run_youtube_publish_task, job_id, req)
    return {"job_id": job_id, "status": "queued"}



if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)

