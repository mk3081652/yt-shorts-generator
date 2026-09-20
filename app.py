import os
import sys
import shutil
import uuid

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

from typing import Optional, Dict, List, Any
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException

# Enforce UTF-8 console output on Windows to prevent UnicodeEncodeError
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from engine.tts import get_available_voices, generate_speech_with_words
from engine.subtitles import STYLE_PRESETS
from engine.backgrounds import get_available_backgrounds, get_target_cut_duration
from engine.audio import get_available_bgm
from engine.metadata import get_viral_hooks, get_script_templates, generate_youtube_metadata
from engine.compositor import render_shorts_video
from engine.smart_visuals import (
    prepare_scenes_data,
    search_targeted_scene_image,
    find_primary_wikipedia_topic
)

app = FastAPI(title="Viral YouTube Shorts Creator Tool")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
os.makedirs("assets/backgrounds", exist_ok=True)
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
    except Exception:
        pass

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
    script: str
    voice: str = "en-US-ChristopherNeural"
    voice_rate: str = "+10%"
    subtitle_style: str = "mrbeast"
    bg_choice: str = "ai_gemini"
    bgm_track: str = "phonk_energetic"
    bgm_volume: float = 0.18
    scene_overrides: Optional[Dict[str, str]] = None
    preview_scenes: Optional[List[Dict[str, Any]]] = None

class PrepareScenesRequest(BaseModel):
    script: str
    voice_rate: str = "+10%"
    bg_choice: str = "ai_gemini"
    scene_overrides: Optional[Dict[str, str]] = None

class RefreshSceneRequest(BaseModel):
    script: str
    scene_id: int
    scene_text: str
    exclude_urls: List[str] = []
    bg_choice: Optional[str] = "smart_fast"

class VoicePreviewRequest(BaseModel):
    text: str = "Welcome to the ultimate YouTube Shorts Creator!"
    voice: str = "en-US-ChristopherNeural"
    voice_rate: str = "+10%"

class MetadataRequest(BaseModel):
    script: str

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
        "backgrounds": get_available_backgrounds(),
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

@app.post("/api/prepare_scenes")
def prepare_scenes(req: PrepareScenesRequest):
    """
    Analyzes the script and returns all scenes with their assigned
    authentic topic images, timestamps, and text for the visual storyboard.
    """
    script = req.script.strip()
    if not script:
        raise HTTPException(status_code=400, detail="Script cannot be empty.")

    # Calculate estimated duration based on words & speed
    words = script.split()
    speed_mult = 1.10
    if req.voice_rate == "+15%":
        speed_mult = 1.15
    elif req.voice_rate == "+20%":
        speed_mult = 1.20
    elif req.voice_rate == "+0%":
        speed_mult = 1.0

    est_duration = max(3.0, (len(words) / (2.5 * speed_mult)))
    target_cut = get_target_cut_duration(req.bg_choice)

    ai_configured = bool(os.environ.get("GEMINI_API_KEY", "").strip())
    warning = None if ai_configured else (
        "⚠️ GEMINI_API_KEY is not configured on the server. "
        "Visual beats and image prompts are running in degraded fallback mode. "
        "To get accurate AI scene prompts for Google Flow, set GEMINI_API_KEY in your environment."
    )

    try:
        from engine.gemini_visuals import prepare_gemini_scenes_data
        scenes = prepare_gemini_scenes_data(
            script_text=script,
            total_duration=est_duration,
            target_cut_duration=target_cut,
            scene_overrides=req.scene_overrides,
            api_key=os.environ.get("GEMINI_API_KEY", None)
        )
        primary_topic = "Visual Director"

        return {
            "topic": primary_topic,
            "est_duration": round(est_duration, 1),
            "scenes": scenes,
            "ai_planner_configured": ai_configured,
            "warning": warning
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to prepare scenes: {str(e)}")

@app.post("/api/upload_scene_image")
def upload_scene_image(
    file: UploadFile = File(...),
    scene_id: int = Form(...)
):
    """Uploads a manual replacement image for a specific scene (source: manual)."""
    allowed_exts = ('.jpg', '.jpeg', '.png', '.webp', '.bmp')
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_exts:
        raise HTTPException(status_code=400, detail="Invalid image format. Supported: JPG, PNG, WEBP.")

    safe_name = f"scene_{scene_id}_{uuid.uuid4().hex[:6]}{ext}"
    dest_path = os.path.abspath(os.path.join("outputs/custom_scenes", safe_name))
    with open(dest_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {
        "scene_id": scene_id,
        "image_url": f"/outputs/custom_scenes/{safe_name}",
        "local_path": dest_path,
        "filename": file.filename,
        "source": "manual",
        "is_custom": True
    }

@app.post("/api/upload_batch_images")
def upload_batch_images(files: List[UploadFile] = File(...)):
    """Uploads multiple custom images at once to map across scenes (source: manual)."""
    allowed_exts = ('.jpg', '.jpeg', '.png', '.webp', '.bmp')
    saved = []

    for f in files:
        ext = os.path.splitext(f.filename)[1].lower()
        if ext in allowed_exts:
            safe_name = f"custom_{uuid.uuid4().hex[:8]}{ext}"
            dest_path = os.path.abspath(os.path.join("outputs/custom_scenes", safe_name))
            with open(dest_path, "wb") as buffer:
                shutil.copyfileobj(f.file, buffer)
            saved.append({
                "filename": f.filename,
                "image_url": f"/outputs/custom_scenes/{safe_name}",
                "local_path": dest_path,
                "source": "manual",
                "is_custom": True
            })

    return {"uploaded": saved}

@app.post("/api/refresh_scene_image")
def refresh_scene_image(req: RefreshSceneRequest):
    """Finds an alternative unique authentic image or AI re-roll for a single scene using Visual Director."""
    import random
    from engine.visual_director import plan_visual_storyboard, generate_and_validate_scene

    plan = plan_visual_storyboard(req.scene_text, 3.0)
    sc_plan = plan.get("scenes", [{}])[0] if plan.get("scenes") else {}
    ai_p = sc_plan.get("image_prompt", f"Vertical 9:16 cinematic shot of {req.scene_text}, photorealistic 8k")

    seed = random.randint(1000, 999999)
    varied_prompt = f"{ai_p}, alternative cinematic angle, dramatic lighting, variation {seed}"
    
    safe_name = f"refresh_{req.scene_id}_{seed}.jpg"
    dest_path = os.path.abspath(os.path.join("outputs/ai_previews", safe_name))
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

    from engine.visual_director.generator import generate_cloudflare_flux_image, generate_pollinations_image
    ok = generate_cloudflare_flux_image(varied_prompt, dest_path)
    if ok and os.path.exists(dest_path):
        return {
            "found": True,
            "image_url": f"/outputs/ai_previews/{safe_name}",
            "image_title": f"AI FLUX: {ai_p[:35]}...",
            "badge": "AI FLUX",
            "source": "generated"
        }
    
    # Fallback to Pollinations
    import urllib.parse, re
    clean_p = re.sub(r'[^a-zA-Z0-9\s,.-]', '', ai_p)[:180].strip()
    img_url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(clean_p)}?width=1080&height=1920&nologo=true&seed={seed}"
    return {
        "found": True,
        "image_url": img_url,
        "image_title": f"AI: {ai_p[:35]}...",
        "badge": "AI ULTRA",
        "source": "generated"
    }

@app.post("/api/upload_background")
def upload_background(file: UploadFile = File(...)):
    """Allows uploading custom full background video."""
    allowed_exts = ('.mp4', '.mov', '.webm', '.mkv')
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_exts:
        raise HTTPException(status_code=400, detail="Invalid video format.")
    
    safe_name = f"custom_{uuid.uuid4().hex[:6]}{ext}"
    dest_path = os.path.join("assets/backgrounds", safe_name)
    with open(dest_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    return {
        "id": f"file_{safe_name}",
        "name": file.filename,
        "filename": safe_name
    }

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
            bg_choice=req.bg_choice,
            bgm_track=req.bgm_track,
            bgm_volume=req.bgm_volume,
            progress_callback=update_progress,
            scene_overrides=req.scene_overrides,
            preview_scenes=req.preview_scenes
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
    if not req.script.strip():
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
