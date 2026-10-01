"""
engine/project.py - Project and Scene Data Model, Edit Operations, Media Handling, and Background Generation Pool.
"""

import os
import re
import copy
import json
import uuid
import time
import zipfile
from io import BytesIO
from dataclasses import dataclass, field, asdict
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional, Tuple, Set
from PIL import Image

from engine.beats import create_story_beats
from engine.director import plan_scenes_with_director, compile_prompt, validate_image_with_vision_qa
from engine.flux import generate as generate_flux
from engine.stock_video import fetch_broll_for_scene, CACHE_DIR as STOCK_CACHE_DIR, download_stock_video
from engine.llm import generate_content
from engine.config import get_gemini_api_key

PROJECTS_DIR = os.path.abspath("outputs/projects")
CUSTOM_MEDIA_DIR = os.path.abspath("outputs/custom_scenes")
PREVIEWS_DIR = os.path.abspath("outputs/ai_previews")

os.makedirs(PROJECTS_DIR, exist_ok=True)
os.makedirs(CUSTOM_MEDIA_DIR, exist_ok=True)
os.makedirs(PREVIEWS_DIR, exist_ok=True)
os.makedirs(STOCK_CACHE_DIR, exist_ok=True)

# Background generation worker pool (max 2 workers)
_GEN_EXECUTOR = ThreadPoolExecutor(max_workers=2)
_CANCELLED_PROJECTS = set()


@dataclass
class Scene:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    text: str = ""
    image_prompt: str = ""
    video_prompt: str = ""
    motion: str = "push in"
    status: str = "empty"       # "empty" | "queued" | "generating" | "ready" | "failed" | "manual"
    media_url: str = ""
    media_path: str = ""
    media_type: str = "blank"   # "image" | "video" | "blank"
    source_tier: str = ""       # "flux" | "manual" | "flux_failed"
    fail_reason: Optional[str] = None
    qa_score: Optional[int] = None
    qa_note: Optional[str] = None
    hold_previous: bool = False
    entities: List[str] = field(default_factory=list)
    duration: float = 3.0
    hook_text: Optional[str] = None
    high_impact_words: List[str] = field(default_factory=list)
    broll_keywords: List[str] = field(default_factory=list)
    visual_type: str = "literal"
    visual_priority: str = "medium"
    must_show: List[str] = field(default_factory=list)
    should_avoid: List[str] = field(default_factory=list)
    search_queries: List[str] = field(default_factory=list)
    visual_strategy: str = "pexels"
    continuity_group: str = ""
    shot_scale: str = "medium"
    motion_intensity: str = "medium"
    mood: str = "cinematic"
    selected_query: Optional[str] = None
    selected_reason: Optional[str] = None
    candidate_count: int = 0
    ai_ranking_score: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Compatibility aliases for UI
        d["segment_id"] = self.id
        d["camera_motion"] = self.motion
        d["is_custom"] = (self.status == "manual" or self.source_tier == "manual")
        d["image_url"] = self.media_url
        d["image_path"] = self.media_path
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Scene":
        s_id = data.get("id") or data.get("segment_id") or uuid.uuid4().hex
        motion = data.get("motion") or data.get("camera_motion") or "push in"
        status = data.get("status")
        if not status:
            if data.get("is_custom") or data.get("source_tier") == "manual":
                status = "manual"
            elif data.get("media_url") or data.get("image_url"):
                status = "ready"
            elif data.get("fail_reason"):
                status = "failed"
            else:
                status = "empty"

        media_url = data.get("media_url") or data.get("image_url") or ""
        media_path = data.get("media_path") or data.get("image_path") or ""
        media_type = data.get("media_type")
        if not media_type or media_type == "blank":
            if media_url:
                media_type = "video" if (media_url.endswith(".mp4") or media_url.endswith(".webm")) else "image"
            else:
                media_type = "blank"

        return cls(
            id=s_id,
            text=data.get("text", ""),
            image_prompt=data.get("image_prompt", ""),
            video_prompt=data.get("video_prompt", ""),
            motion=motion,
            status=status,
            media_url=media_url,
            media_path=media_path,
            media_type=media_type,
            source_tier=data.get("source_tier", ""),
            fail_reason=data.get("fail_reason"),
            qa_score=data.get("qa_score"),
            qa_note=data.get("qa_note"),
            hold_previous=bool(data.get("hold_previous", False)),
            entities=data.get("entities", []),
            duration=float(data.get("duration", 3.0)),
            hook_text=data.get("hook_text"),
            high_impact_words=list(data.get("high_impact_words") or []),
            broll_keywords=list(data.get("broll_keywords") or []),
            visual_type=str(data.get("visual_type") or "literal"),
            visual_priority=str(data.get("visual_priority") or "medium"),
            must_show=list(data.get("must_show") or []),
            should_avoid=list(data.get("should_avoid") or []),
            search_queries=list(data.get("search_queries") or []),
            visual_strategy=str(data.get("visual_strategy") or "pexels"),
            continuity_group=str(data.get("continuity_group") or ""),
            shot_scale=str(data.get("shot_scale") or "medium"),
            motion_intensity=str(data.get("motion_intensity") or "medium"),
            mood=str(data.get("mood") or "cinematic"),
            selected_query=data.get("selected_query"),
            selected_reason=data.get("selected_reason"),
            candidate_count=int(data.get("candidate_count", 0)),
            ai_ranking_score=data.get("ai_ranking_score")
        )


@dataclass
class Project:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    script: str = ""
    style_lock: str = ""
    start_mode: str = "auto"    # "auto" | "manual"
    transition_style: str = "crossfade"  # "crossfade" | "zoom-punch" | "none"
    visual_source: str = "video"         # "video" (Pexels) | "flux" (AI art)
    color_filter: str = "none"           # "none" | "viral_punch" | "moody_noir" | "teal_orange" | "warm_film" | "cyberpunk"
    scenes: List[Scene] = field(default_factory=list)
    timeline: Optional[Dict[str, Any]] = None
    total_duration: float = 0.0
    history: List[Dict[str, Any]] = field(default_factory=list)
    future: List[Dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.id,
            "session_id": self.id,  # Compatibility alias
            "script": self.script,
            "script_text": self.script,  # Compatibility alias
            "style_lock": self.style_lock,
            "start_mode": self.start_mode,
            "mode": self.start_mode,  # Compatibility alias
            "transition_style": self.transition_style,
            "visual_source": self.visual_source,
            "color_filter": getattr(self, "color_filter", "none"),
            "scenes": [s.to_dict() for s in self.scenes],
            "segments": [s.to_dict() for s in self.scenes],  # Compatibility alias
            "timeline": self.timeline,
            "total_duration": round(self.total_duration, 2),
            "history": self.history,
            "future": self.future,
            "can_undo": len(self.history) > 0,
            "can_redo": len(self.future) > 0,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Project":
        scenes_data = data.get("scenes") or data.get("segments") or []
        scenes = [Scene.from_dict(s) for s in scenes_data]
        p_id = data.get("id") or data.get("project_id") or data.get("session_id") or uuid.uuid4().hex
        script = data.get("script") or data.get("script_text") or ""
        mode = data.get("start_mode") or data.get("mode") or "auto"
        transition_style = data.get("transition_style", "crossfade")
        visual_source = data.get("visual_source", "video")
        color_filter = data.get("color_filter", "none")

        p = cls(
            id=p_id,
            script=script,
            style_lock=data.get("style_lock", ""),
            start_mode=mode,
            transition_style=transition_style,
            visual_source=visual_source,
            color_filter=color_filter,
            scenes=scenes,
            timeline=data.get("timeline"),
            total_duration=float(data.get("total_duration", 0.0)),
            history=data.get("history", []),
            future=data.get("future", []),
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time()))
        )
        p.recalculate_durations()
        return p

    def recalculate_durations(self) -> None:
        if self.timeline and "scenes" in self.timeline:
            t_map = {s["scene_index"]: s["duration"] for s in self.timeline["scenes"] if "scene_index" in s}
            for idx, sc in enumerate(self.scenes):
                if idx in t_map:
                    sc.duration = t_map[idx]
        self.total_duration = round(sum(s.duration for s in self.scenes), 2)

    def snapshot(self) -> None:
        """Saves current state snapshot for 20-step undo."""
        snap = {
            "script": self.script,
            "style_lock": self.style_lock,
            "visual_source": self.visual_source,
            "color_filter": getattr(self, "color_filter", "none"),
            "scenes": [s.to_dict() for s in self.scenes],
            "total_duration": self.total_duration
        }
        self.history.append(snap)
        if len(self.history) > 20:
            self.history.pop(0)
        self.future.clear()

    def sync_script_from_scenes(self) -> None:
        self.script = " ".join(s.text.strip() for s in self.scenes if s.text.strip())
        self.timeline = None  # Invalidate timeline on text changes
        self.recalculate_durations()
        self.updated_at = time.time()


# ==============================================================================
# PERSISTENCE
# ==============================================================================

def get_project_path(project_id: str) -> str:
    # Security: validate against ^[a-f0-9]{32}$
    if not re.match(r'^[a-f0-9]{32}$', project_id):
        raise ValueError("Invalid project ID format")
    return os.path.join(PROJECTS_DIR, f"{project_id}.json")


def save_project(project: Project) -> None:
    project.updated_at = time.time()
    path = get_project_path(project.id)
    tmp_path = f"{path}.{uuid.uuid4().hex}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(project.to_dict(), f, indent=2)
    os.replace(tmp_path, path)


def load_project(project_id: str) -> Optional[Project]:
    try:
        path = get_project_path(project_id)
        if not os.path.exists(path):
            # Backward compatibility check for segment_sessions
            legacy_path = os.path.join(os.path.abspath("outputs/segment_sessions"), f"{project_id}.json")
            if os.path.exists(legacy_path):
                path = legacy_path
            else:
                return None

        for attempt in range(2):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return Project.from_dict(data)
            except (json.JSONDecodeError, OSError):
                if attempt == 0:
                    time.sleep(0.05)
                    continue
                raise
    except Exception as e:
        print(f"[Project] Load error for {project_id}: {e}")
        return None


# ==============================================================================
# CREATION & BACKGROUND GENERATION
# ==============================================================================

def create_project(
    script: str,
    start: str = "auto",
    manual_delimiter: bool = False,
    visual_source: str = "video",
    api_key: Optional[str] = None
) -> Project:
    """Creates a new Project, runs the Director, and queues generation if mode=auto."""
    p_id = uuid.uuid4().hex
    words = script.strip().split()
    total_dur = max(3.0, round(len(words) / 2.7, 2))

    # 1. Break into verbatim story beats (honoring user scene breaks & markers)
    beats = create_story_beats(script, total_dur)
    if not beats:
        beats = [(script.strip(), total_dur)]

    # Clean narration text for TTS voiceover & project script
    clean_narration = " ".join(t for t, _ in beats).strip() or script.strip()
    words = clean_narration.split()
    total_dur = max(3.0, round(len(words) / 2.7, 2))
    sum_dur = sum(d for _, d in beats)
    if sum_dur > 0:
        beats = [(t, max(1.8, round((d / sum_dur) * total_dur, 2))) for t, d in beats]

    # 2. Plan storyboard with director
    plan_dict, is_basic = plan_scenes_with_director(clean_narration, beats, api_key=api_key)

    scenes = []
    for s_dict in plan_dict.get("scenes", []):
        sc = Scene(
            id=uuid.uuid4().hex,
            text=s_dict.get("text", ""),
            image_prompt=s_dict.get("image_prompt", ""),
            video_prompt=s_dict.get("video_prompt", ""),
            motion=s_dict.get("camera_motion", "push in"),
            status="empty",
            media_type="blank",
            hold_previous=bool(s_dict.get("hold_previous", False)),
            entities=s_dict.get("entities", []),
            duration=float(s_dict.get("duration", 3.0)),
            broll_keywords=list(s_dict.get("broll_keywords") or []),
            visual_type=str(s_dict.get("visual_type") or "literal"),
            visual_priority=str(s_dict.get("visual_priority") or "medium"),
            must_show=list(s_dict.get("must_show") or []),
            should_avoid=list(s_dict.get("should_avoid") or []),
            search_queries=list(s_dict.get("search_queries") or []),
            visual_strategy=str(s_dict.get("visual_strategy") or "pexels"),
            continuity_group=str(s_dict.get("continuity_group") or ""),
            shot_scale=str(s_dict.get("shot_scale") or "medium"),
            motion_intensity=str(s_dict.get("motion_intensity") or "medium"),
            mood=str(s_dict.get("mood") or "cinematic")
        )
        scenes.append(sc)

    # 3. If auto mode, mark scenes as queued and queue generation in background
    if start == "auto":
        for sc in scenes:
            sc.status = "queued"

    project = Project(
        id=p_id,
        script=clean_narration,
        style_lock="",
        start_mode=start,
        visual_source=visual_source,
        scenes=scenes,
        total_duration=total_dur
    )
    save_project(project)

    if start == "auto":
        queue_project_generation(project.id)

    return project


def queue_project_generation(project_id: str) -> None:
    """Queues generation (Pexels b-roll or FLUX) for all empty/queued scenes in background."""
    project = load_project(project_id)
    if not project:
        return

    _CANCELLED_PROJECTS.discard(project_id)

    for sc in project.scenes:
        if sc.status in ("empty", "failed") and sc.status != "manual":
            sc.status = "queued"

    save_project(project)

    def _worker(pid: str):
        proj = load_project(pid)
        if not proj:
            return

        used_video_ids: Set[str] = set()
        for s in proj.scenes:
            if s.media_path and s.media_type == "video":
                base = os.path.basename(s.media_path)
                match = re.search(r'_(\d+)\.mp4$', base)
                if match:
                    used_video_ids.add(match.group(1))

        for sc in proj.scenes:
            if pid in _CANCELLED_PROJECTS:
                break
            if sc.status != "queued" or sc.status == "manual":
                continue

            sc.status = "generating"
            save_project(proj)

            # 0. Check hold_previous / hold strategy
            curr_idx = next((i for i, s in enumerate(proj.scenes) if s.id == sc.id), 0)
            if curr_idx > 0 and (sc.hold_previous or getattr(sc, "visual_strategy", "") == "hold"):
                prev_ready = next((p for p in reversed(proj.scenes[:curr_idx]) if p.status in ("ready", "manual") and p.media_path and os.path.exists(p.media_path)), None)
                if prev_ready:
                    sc.media_url = prev_ready.media_url
                    sc.media_path = prev_ready.media_path
                    sc.media_type = prev_ready.media_type
                    sc.source_tier = prev_ready.source_tier
                    sc.selected_reason = f"Reused visual from scene {prev_ready.id[:6]} for story continuity"
                    sc.status = "ready"
                    sc.fail_reason = None
                    save_project(proj)
                    continue

            visual_src = getattr(proj, "visual_source", "video")
            strat = getattr(sc, "visual_strategy", "pexels")
            media_assigned = False

            # 1. If visual_source is video (or hybrid) and scene strategy allows pexels, try Pexels b-roll
            if visual_src in ("video", "hybrid") and strat != "flux":
                try:
                    broll = fetch_broll_for_scene(
                        scene_id=sc.id,
                        scene_text=sc.text,
                        image_prompt=sc.image_prompt,
                        video_prompt=sc.video_prompt,
                        subject=getattr(sc, "subject", ""),
                        action=getattr(sc, "action", ""),
                        setting=getattr(sc, "setting", ""),
                        shot=getattr(sc, "shot_scale", "") or getattr(sc, "motion", ""),
                        mood=getattr(sc, "mood", "cinematic"),
                        visual_type=getattr(sc, "visual_type", "literal"),
                        visual_priority=getattr(sc, "visual_priority", "medium"),
                        must_show=getattr(sc, "must_show", []),
                        should_avoid=getattr(sc, "should_avoid", []),
                        search_queries=getattr(sc, "search_queries", []),
                        broll_keywords=getattr(sc, "broll_keywords", []),
                        continuity_group=getattr(sc, "continuity_group", ""),
                        topic=proj.script[:120],
                        used_video_ids=used_video_ids
                    )
                    if broll and broll.get("media_path") and os.path.exists(broll["media_path"]):
                        fname = os.path.basename(broll["media_path"])
                        sc.media_url = f"/outputs/stock_videos/{fname}"
                        sc.media_path = broll["media_path"]
                        sc.media_type = "video"
                        sc.source_tier = "pexels"
                        sc.fail_reason = None
                        sc.selected_query = broll.get("query")
                        sc.selected_reason = broll.get("reason")
                        sc.candidate_count = broll.get("candidate_count", 1)
                        sc.ai_ranking_score = broll.get("ai_score")
                        sc.status = "ready"
                        media_assigned = True
                        if broll.get("video_id"):
                            used_video_ids.add(str(broll["video_id"]))
                except Exception as broll_err:
                    print(f"[StockVideo] Worker error for scene {sc.id}: {broll_err}")

            # 2. If not assigned (or if visual_source is flux / strategy flux), generate via FLUX
            if not media_assigned:
                out_name = f"{pid}_{sc.id}.jpg"
                out_path = os.path.join(PREVIEWS_DIR, out_name)

                ok, reason = generate_flux(sc.image_prompt, out_path)

                if pid in _CANCELLED_PROJECTS:
                    break

                if ok and os.path.exists(out_path):
                    sc.status = "ready"
                    sc.media_url = f"/outputs/ai_previews/{out_name}"
                    sc.media_path = out_path
                    sc.media_type = "image"
                    sc.source_tier = "flux"
                    sc.fail_reason = None

                    # Optional Vision QA
                    score, note = validate_image_with_vision_qa(out_path, sc.text)
                    if score is not None:
                        sc.qa_score = score
                        sc.qa_note = note
                else:
                    sc.status = "failed"
                    sc.source_tier = "flux_failed"
                    sc.fail_reason = reason

            save_project(proj)

    _GEN_EXECUTOR.submit(_worker, project_id)


# ==============================================================================
# SCENE EDIT OPERATIONS
# ==============================================================================

def edit_scene_text(project_id: str, scene_id: str, new_text: str) -> Tuple[Optional[Project], Optional[str], int]:
    project = load_project(project_id)
    if not project:
        return None, "Project not found", 404

    target = next((s for s in project.scenes if s.id == scene_id), None)
    if not target:
        return None, "Scene not found", 404

    project.snapshot()
    target.text = new_text.strip()
    project.sync_script_from_scenes()
    save_project(project)
    return project, None, 200


def edit_scene_prompt(project_id: str, scene_id: str, new_prompt: str, kind: str = "image") -> Tuple[Optional[Project], Optional[str], int]:
    project = load_project(project_id)
    if not project:
        return None, "Project not found", 404

    target = next((s for s in project.scenes if s.id == scene_id), None)
    if not target:
        return None, "Scene not found", 404

    project.snapshot()
    if kind == "video":
        target.video_prompt = new_prompt.strip()
    else:
        target.image_prompt = new_prompt.strip()

    save_project(project)
    return project, None, 200


def edit_scene_duration(
    project_id: str,
    scene_id: str,
    new_duration: float
) -> Tuple[Optional[Project], Optional[str], int]:
    """Updates an individual scene duration, syncs timeline timestamps and total duration."""
    project = load_project(project_id)
    if not project:
        return None, "Project not found", 404

    target = next((s for s in project.scenes if s.id == scene_id), None)
    if not target:
        return None, "Scene not found", 404

    dur = max(0.5, round(float(new_duration), 2))
    project.snapshot()
    target.duration = dur

    # Update timeline scenes if present
    if project.timeline and "scenes" in project.timeline:
        cur_t = 0.0
        for s_info in project.timeline["scenes"]:
            sc_ref = next((s for s in project.scenes if s.id == s_info.get("scene_id")), None)
            d = sc_ref.duration if sc_ref else float(s_info.get("duration", 3.0))
            s_info["start"] = round(cur_t, 2)
            s_info["end"] = round(cur_t + d, 2)
            s_info["duration"] = round(d, 2)
            cur_t += d
        project.timeline["total_duration"] = round(cur_t, 2)

    project.total_duration = round(sum(s.duration for s in project.scenes), 2)
    save_project(project)
    return project, None, 200


def assign_stock_video_to_scene(
    project_id: str,
    scene_id: str,
    video_id: str,
    download_url: str
) -> Tuple[Optional[Project], Optional[str], int]:
    """Downloads a chosen stock video from Pexels and assigns it directly to the target scene."""
    project = load_project(project_id)
    if not project:
        return None, "Project not found", 404

    target = next((s for s in project.scenes if s.id == scene_id), None)
    if not target:
        return None, "Scene not found", 404

    out_name = f"pexels_{video_id}_{uuid.uuid4().hex[:6]}.mp4"
    out_path = os.path.join(STOCK_CACHE_DIR, out_name)

    downloaded = download_stock_video(download_url, out_path)
    if not downloaded or not os.path.exists(downloaded):
        return None, "Failed to download stock video from Pexels", 500

    project.snapshot()
    target.media_path = downloaded
    target.media_url = f"/outputs/stock_videos/{out_name}"
    target.media_type = "video"
    target.status = "ready"
    target.source_tier = "manual"
    target.selected_reason = f"Manually assigned Pexels video (ID {video_id})"
    target.fail_reason = None

    save_project(project)
    return project, None, 200


def edit_meta(
    project_id: str,
    scene_id: Optional[str] = None,
    motion: Optional[str] = None,
    hold_previous: Optional[bool] = None,
    style_lock: Optional[str] = None,
    transition_style: Optional[str] = None,
    visual_source: Optional[str] = None
) -> Tuple[Optional[Project], Optional[str], int]:
    project = load_project(project_id)
    if not project:
        return None, "Project not found", 404

    project.snapshot()

    if style_lock is not None:
        project.style_lock = style_lock.strip()

    if transition_style is not None:
        project.transition_style = transition_style.strip()

    if visual_source is not None:
        project.visual_source = visual_source.strip()

    if scene_id:
        target = next((s for s in project.scenes if s.id == scene_id), None)
        if target:
            if motion is not None:
                target.motion = motion
            if hold_previous is not None:
                target.hold_previous = hold_previous

    save_project(project)
    return project, None, 200


def split_scene(project_id: str, scene_id: str, split_at_word_index: int) -> Tuple[Optional[Project], Optional[str], int]:
    project = load_project(project_id)
    if not project:
        return None, "Project not found", 404

    idx = next((i for i, s in enumerate(project.scenes) if s.id == scene_id), -1)
    if idx == -1:
        return None, "Scene not found", 404

    target = project.scenes[idx]
    words = target.text.strip().split()
    if split_at_word_index <= 0 or split_at_word_index >= len(words):
        return None, "Invalid split position", 400

    project.snapshot()

    text1 = " ".join(words[:split_at_word_index])
    text2 = " ".join(words[split_at_word_index:])
    ratio = len(words[:split_at_word_index]) / float(len(words))
    dur1 = max(1.5, round(target.duration * ratio, 2))
    dur2 = max(1.5, round(target.duration * (1.0 - ratio), 2))

    target.text = text1
    target.duration = dur1

    new_scene = Scene(
        id=uuid.uuid4().hex,
        text=text2,
        duration=dur2,
        image_prompt=target.image_prompt,
        video_prompt=target.video_prompt,
        motion=target.motion,
        status="empty",
        media_type="blank"
    )
    project.scenes.insert(idx + 1, new_scene)
    project.sync_script_from_scenes()
    save_project(project)
    return project, None, 200


def merge_scene(project_id: str, scene_id: str, direction: str = "next") -> Tuple[Optional[Project], Optional[str], int]:
    project = load_project(project_id)
    if not project:
        return None, "Project not found", 404

    idx = next((i for i, s in enumerate(project.scenes) if s.id == scene_id), -1)
    if idx == -1:
        return None, "Scene not found", 404

    target_idx = idx + 1 if direction == "next" else idx - 1
    if target_idx < 0 or target_idx >= len(project.scenes):
        return None, "No scene to merge with in that direction", 400

    project.snapshot()

    first_idx, second_idx = (idx, target_idx) if direction == "next" else (target_idx, idx)
    s1 = project.scenes[first_idx]
    s2 = project.scenes[second_idx]

    s1.text = f"{s1.text.strip()} {s2.text.strip()}".strip()
    s1.duration = round(s1.duration + s2.duration, 2)
    # If s1 was empty but s2 had media, preserve s2's media
    if (not s1.media_url or s1.status == "empty") and s2.media_url:
        s1.media_url = s2.media_url
        s1.media_path = s2.media_path
        s1.media_type = s2.media_type
        s1.status = s2.status
        s1.source_tier = s2.source_tier

    project.scenes.pop(second_idx)
    project.sync_script_from_scenes()
    save_project(project)
    return project, None, 200


def move_boundary(project_id: str, scene_id: str, direction: str = "left", words: int = 1) -> Tuple[Optional[Project], Optional[str], int]:
    project = load_project(project_id)
    if not project:
        return None, "Project not found", 404

    idx = next((i for i, s in enumerate(project.scenes) if s.id == scene_id), -1)
    if idx == -1:
        return None, "Scene not found", 404

    if direction == "left":
        if idx == 0:
            return None, "First scene cannot shift words left", 400
        left_scene = project.scenes[idx - 1]
        curr_scene = project.scenes[idx]
        curr_words = curr_scene.text.strip().split()
        if len(curr_words) <= words:
            return None, "Scene must have words remaining", 400
        project.snapshot()
        moved = curr_words[:words]
        curr_scene.text = " ".join(curr_words[words:])
        left_scene.text = f"{left_scene.text.strip()} {' '.join(moved)}".strip()
    else:
        if idx >= len(project.scenes) - 1:
            return None, "Last scene cannot shift words right", 400
        curr_scene = project.scenes[idx]
        right_scene = project.scenes[idx + 1]
        curr_words = curr_scene.text.strip().split()
        if len(curr_words) <= words:
            return None, "Scene must have words remaining", 400
        project.snapshot()
        moved = curr_words[-words:]
        curr_scene.text = " ".join(curr_words[:-words])
        right_scene.text = f"{' '.join(moved)} {right_scene.text.strip()}".strip()

    project.sync_script_from_scenes()
    save_project(project)
    return project, None, 200


def add_scene(project_id: str, after_scene_id: str, text: str) -> Tuple[Optional[Project], Optional[str], int]:
    project = load_project(project_id)
    if not project:
        return None, "Project not found", 404

    idx = next((i for i, s in enumerate(project.scenes) if s.id == after_scene_id), len(project.scenes) - 1)

    project.snapshot()
    words = text.strip().split()
    dur = max(2.0, round(len(words) / 2.7, 2))

    new_scene = Scene(
        id=uuid.uuid4().hex,
        text=text.strip(),
        duration=dur,
        image_prompt=text.strip(),
        video_prompt=f"Cinematic motion on {text[:60]}",
        status="empty",
        media_type="blank"
    )
    project.scenes.insert(idx + 1, new_scene)
    project.sync_script_from_scenes()
    save_project(project)
    return project, None, 200


def delete_scene(project_id: str, scene_id: str) -> Tuple[Optional[Project], Optional[str], int]:
    project = load_project(project_id)
    if not project:
        return None, "Project not found", 404

    if len(project.scenes) <= 1:
        return None, "Cannot delete the only scene", 400

    project.snapshot()
    project.scenes = [s for s in project.scenes if s.id != scene_id]
    project.sync_script_from_scenes()
    save_project(project)
    return project, None, 200


# ==============================================================================
# MEDIA UPLOADS & BULK ZIP
# ==============================================================================

VALID_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
VALID_VIDEO_EXTS = {".mp4", ".mov", ".webm"}


def validate_media_bytes(data: bytes, filename: str) -> Tuple[bool, str, str]:
    """Validates magic bytes and file size. Returns (ok, media_type, error)."""
    ext = os.path.splitext(filename.lower())[1]

    # Image validation
    if ext in VALID_IMAGE_EXTS:
        if len(data) > 25 * 1024 * 1024:
            return False, "", "Image exceeds 25MB limit"
        try:
            img = Image.open(BytesIO(data))
            img.verify()
            return True, "image", ""
        except Exception:
            return False, "", "Corrupted or invalid image file"

    # Video validation
    elif ext in VALID_VIDEO_EXTS:
        if len(data) > 80 * 1024 * 1024:
            return False, "", "Video exceeds 80MB limit"
        # Magic bytes check for mp4/mov/webm
        if len(data) >= 8:
            header = data[:32]
            if b"ftyp" in header or header.startswith(b"\x1a\x45\xdf\xa3") or b"moov" in header or b"mdat" in header:
                return True, "video", ""
        return False, "", "Invalid video container magic bytes"

    return False, "", f"Unsupported file type: {ext}"


def upload_media(project_id: str, scene_id: str, file_bytes: bytes, filename: str) -> Tuple[Optional[Project], Optional[str], int]:
    project = load_project(project_id)
    if not project:
        return None, "Project not found", 404

    target = next((s for s in project.scenes if s.id == scene_id), None)
    if not target:
        return None, "Scene not found", 404

    ok, m_type, err = validate_media_bytes(file_bytes, filename)
    if not ok:
        return None, err, 400

    project.snapshot()

    safe_name = os.path.basename(filename)

    if m_type == "image":
        out_filename = f"{project_id}_{scene_id}_{uuid.uuid4().hex[:8]}.jpg"
        out_path = os.path.join(CUSTOM_MEDIA_DIR, out_filename)

        try:
            # Downscale and crop to 9:16 if needed
            img = Image.open(BytesIO(file_bytes))

            # Handle RGBA / transparency before saving as JPEG
            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                img = img.convert("RGBA")
                bg = Image.new("RGB", img.size, (0, 0, 0))
                bg.paste(img, mask=img.split()[3])
                img = bg
            elif img.mode != "RGB":
                img = img.convert("RGB")

            w, h = img.size
            target_ratio = 9.0 / 16.0
            current_ratio = w / float(h)

            if abs(current_ratio - target_ratio) > 0.01:
                if current_ratio > target_ratio:
                    new_w = int(h * target_ratio)
                    offset = (w - new_w) // 2
                    img = img.crop((offset, 0, offset + new_w, h))
                else:
                    new_h = int(w / target_ratio)
                    offset = (h - new_h) // 2
                    img = img.crop((0, offset, w, offset + new_h))

            if img.size != (1080, 1920):
                img = img.resize((1080, 1920), Image.Resampling.BILINEAR)
            img.save(out_path, "JPEG", quality=90, optimize=True)
            del img
        except Exception as img_err:
            return None, f"Image processing failed: {str(img_err)}", 400
    else:
        ext = os.path.splitext(safe_name.lower())[1] or ".mp4"
        out_filename = f"{project_id}_{scene_id}_{uuid.uuid4().hex[:8]}{ext}"
        out_path = os.path.join(CUSTOM_MEDIA_DIR, out_filename)
        # Video file saved directly
        with open(out_path, "wb") as f:
            f.write(file_bytes)

    # LOCKED: Manual scene
    target.media_url = f"/outputs/custom_scenes/{out_filename}"
    target.media_path = out_path
    target.media_type = m_type
    target.status = "manual"
    target.source_tier = "manual"
    target.fail_reason = None

    save_project(project)
    return project, None, 200


def upload_bulk(project_id: str, files_data: List[Tuple[str, bytes]]) -> Tuple[Optional[Project], List[Dict[str, Any]], Optional[str], int]:
    """Bulk uploads media files or a .zip archive, mapping sequentially or by number in filename."""
    project = load_project(project_id)
    if not project:
        return None, [], "Project not found", 404

    extracted_files: List[Tuple[str, bytes]] = []

    for fname, data in files_data:
        safe_fname = os.path.basename(fname)
        if safe_fname.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(BytesIO(data)) as zf:
                    total_uncompressed = sum(info.file_size for info in zf.infolist())
                    if total_uncompressed > 200 * 1024 * 1024:
                        return None, [], "Zip archive exceeds 200MB uncompressed limit", 400

                    for z_info in zf.infolist():
                        if z_info.is_dir():
                            continue
                        # Prevent zip slip
                        z_norm = os.path.normpath(z_info.filename)
                        if z_norm.startswith("..") or os.path.isabs(z_norm):
                            continue
                        z_base = os.path.basename(z_norm)
                        ext = os.path.splitext(z_base.lower())[1]
                        if ext in VALID_IMAGE_EXTS or ext in VALID_VIDEO_EXTS:
                            extracted_files.append((z_base, zf.read(z_info.filename)))
            except Exception as e:
                return None, [], f"Invalid zip file: {e}", 400
        else:
            extracted_files.append((safe_fname, data))

    if not extracted_files:
        return None, [], "No valid media files found", 400

    project.snapshot()
    results = []

    # Map files by number in filename or sequential into empty scenes
    for fname, fbytes in extracted_files:
        # Check if number in filename corresponds to 1-based scene index (e.g. scene_2.jpg -> index 1)
        num_match = re.search(r'(\d+)', fname)
        assigned_scene = None
        if num_match:
            try:
                num = int(num_match.group(1)) - 1
                if 0 <= num < len(project.scenes) and project.scenes[num].status != "manual":
                    assigned_scene = project.scenes[num]
            except Exception:
                pass

        if not assigned_scene:
            # Pick first non-manual scene without media
            assigned_scene = next((s for s in project.scenes if (s.status == "empty" or not s.media_url) and s.status != "manual"), None)

        if not assigned_scene:
            results.append({"filename": fname, "status": "skipped", "reason": "No available scene"})
            continue

        ok, m_type, err = validate_media_bytes(fbytes, fname)
        if not ok:
            results.append({"filename": fname, "status": "failed", "reason": err})
            continue

        if m_type == "image":
            out_fname = f"{project_id}_{assigned_scene.id}_{uuid.uuid4().hex[:6]}.jpg"
            out_path = os.path.join(CUSTOM_MEDIA_DIR, out_fname)
            img = Image.open(BytesIO(fbytes))

            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                img = img.convert("RGBA")
                bg = Image.new("RGB", img.size, (0, 0, 0))
                bg.paste(img, mask=img.split()[3])
                img = bg
            elif img.mode != "RGB":
                img = img.convert("RGB")

            # Crop to 9:16
            w, h = img.size
            target_ratio = 9.0 / 16.0
            current_ratio = w / float(h)
            if abs(current_ratio - target_ratio) > 0.01:
                if current_ratio > target_ratio:
                    new_w = int(h * target_ratio)
                    offset = (w - new_w) // 2
                    img = img.crop((offset, 0, offset + new_w, h))
                else:
                    new_h = int(w / target_ratio)
                    offset = (h - new_h) // 2
                    img = img.crop((0, offset, w, offset + new_h))

            if img.size != (1080, 1920):
                img = img.resize((1080, 1920), Image.Resampling.LANCZOS)
            img.save(out_path, "JPEG", quality=92)
        else:
            ext = os.path.splitext(fname.lower())[1] or ".mp4"
            out_fname = f"{project_id}_{assigned_scene.id}_{uuid.uuid4().hex[:6]}{ext}"
            out_path = os.path.join(CUSTOM_MEDIA_DIR, out_fname)
            with open(out_path, "wb") as f:
                f.write(fbytes)

        assigned_scene.media_url = f"/outputs/custom_scenes/{out_fname}"
        assigned_scene.media_path = out_path
        assigned_scene.media_type = m_type
        assigned_scene.status = "manual"
        assigned_scene.source_tier = "manual"
        assigned_scene.fail_reason = None
        scene_index = next((i for i, s in enumerate(project.scenes) if s.id == assigned_scene.id), 0)
        results.append({
            "filename": fname,
            "scene_id": assigned_scene.id,
            "scene_index": scene_index + 1,  # 1-based for display
            "media_url": assigned_scene.media_url,
            "media_type": m_type,
            "status": "success"
        })

    save_project(project)
    return project, results, None, 200


def clear_media(project_id: str, scene_id: str) -> Tuple[Optional[Project], Optional[str], int]:
    project = load_project(project_id)
    if not project:
        return None, "Project not found", 404

    target = next((s for s in project.scenes if s.id == scene_id), None)
    if not target:
        return None, "Scene not found", 404

    project.snapshot()
    target.media_url = ""
    target.media_path = ""
    target.media_type = "blank"
    target.status = "empty"
    target.source_tier = ""
    target.fail_reason = None
    target.qa_score = None
    target.qa_note = None

    save_project(project)
    return project, None, 200


def generate_scene_media(project_id: str, scene_id: str, api_key: Optional[str] = None) -> Tuple[Optional[Project], Optional[str], int]:
    """Generates media for a single scene via Stock Video (Pexels) or FLUX. Fails if scene is manual (LOCKED)."""
    project = load_project(project_id)
    if not project:
        return None, "Project not found", 404

    target = next((s for s in project.scenes if s.id == scene_id), None)
    if not target:
        return None, "Scene not found", 404

    if target.status == "manual":
        return None, "Scene is locked as manual", 400

    target.status = "generating"
    save_project(project)

    # 0. Check hold_previous / hold strategy
    curr_idx = next((i for i, s in enumerate(project.scenes) if s.id == target.id), 0)
    if curr_idx > 0 and (target.hold_previous or getattr(target, "visual_strategy", "") == "hold"):
        prev_ready = next((p for p in reversed(project.scenes[:curr_idx]) if p.status in ("ready", "manual") and p.media_path and os.path.exists(p.media_path)), None)
        if prev_ready:
            target.media_url = prev_ready.media_url
            target.media_path = prev_ready.media_path
            target.media_type = prev_ready.media_type
            target.source_tier = prev_ready.source_tier
            target.selected_reason = f"Reused visual from scene {prev_ready.id[:6]} for story continuity"
            target.status = "ready"
            target.fail_reason = None
            save_project(project)
            return project, None, 200

    visual_src = getattr(project, "visual_source", "video")
    strat = getattr(target, "visual_strategy", "pexels")
    media_assigned = False

    if visual_src in ("video", "hybrid") and strat != "flux":
        try:
            used_video_ids: Set[str] = set()
            for s in project.scenes:
                if s.id != target.id and s.media_path and s.media_type == "video":
                    base = os.path.basename(s.media_path)
                    match = re.search(r'_(\d+)\.mp4$', base)
                    if match:
                        used_video_ids.add(match.group(1))

            # Regeneration support: if target already has an existing video, exclude it to force variation!
            if target.media_path and target.media_type == "video":
                base = os.path.basename(target.media_path)
                match = re.search(r'_(\d+)\.mp4$', base)
                if match:
                    used_video_ids.add(match.group(1))

            broll = fetch_broll_for_scene(
                scene_id=target.id,
                scene_text=target.text,
                image_prompt=target.image_prompt,
                video_prompt=target.video_prompt,
                subject=getattr(target, "subject", ""),
                action=getattr(target, "action", ""),
                setting=getattr(target, "setting", ""),
                shot=getattr(target, "shot_scale", "") or getattr(target, "motion", ""),
                mood=getattr(target, "mood", "cinematic"),
                visual_type=getattr(target, "visual_type", "literal"),
                visual_priority=getattr(target, "visual_priority", "medium"),
                must_show=getattr(target, "must_show", []),
                should_avoid=getattr(target, "should_avoid", []),
                search_queries=getattr(target, "search_queries", []),
                broll_keywords=getattr(target, "broll_keywords", []),
                continuity_group=getattr(target, "continuity_group", ""),
                topic=project.script[:120],
                used_video_ids=used_video_ids,
                api_key=api_key
            )
            if broll and broll.get("media_path") and os.path.exists(broll["media_path"]):
                fname = os.path.basename(broll["media_path"])
                target.status = "ready"
                target.media_url = f"/outputs/stock_videos/{fname}"
                target.media_path = broll["media_path"]
                target.media_type = "video"
                target.source_tier = "pexels"
                target.fail_reason = None
                target.selected_query = broll.get("query")
                target.selected_reason = broll.get("reason")
                target.candidate_count = broll.get("candidate_count", 1)
                target.ai_ranking_score = broll.get("ai_score")
                media_assigned = True
        except Exception as broll_err:
            print(f"[StockVideo] Single scene error for {target.id}: {broll_err}")

    if not media_assigned:
        out_name = f"{project_id}_{target.id}.jpg"
        out_path = os.path.join(PREVIEWS_DIR, out_name)

        ok, reason = generate_flux(target.image_prompt, out_path, force=True)

        if ok and os.path.exists(out_path):
            target.status = "ready"
            target.media_url = f"/outputs/ai_previews/{out_name}"
            target.media_path = out_path
            target.media_type = "image"
            target.source_tier = "flux"
            target.fail_reason = None
        else:
            target.status = "failed"
            target.source_tier = "flux_failed"
            target.fail_reason = reason

    save_project(project)
    return project, None, 200


def generate_missing_media(project_id: str, api_key: Optional[str] = None) -> Tuple[Optional[Project], Optional[str], int]:
    """Queues generation for all blank, non-manual scenes."""
    project = load_project(project_id)
    if not project:
        return None, "Project not found", 404

    queue_project_generation(project_id)
    return load_project(project_id), None, 200


def cancel_generation(project_id: str) -> Tuple[Optional[Project], Optional[str], int]:
    _CANCELLED_PROJECTS.add(project_id)
    project = load_project(project_id)
    if project:
        for s in project.scenes:
            if s.status in ("queued", "generating") and s.status != "manual":
                s.status = "empty"
        save_project(project)
    return project, None, 200


def suggest_prompts(project_id: str, scene_id: str, api_key: Optional[str] = None) -> Tuple[List[str], Optional[str], int]:
    """Generates 3 alternative image prompts for a scene using Gemini."""
    project = load_project(project_id)
    if not project:
        return [], "Project not found", 404

    target = next((s for s in project.scenes if s.id == scene_id), None)
    if not target:
        return [], "Scene not found", 404

    resolved_key = api_key or get_gemini_api_key()
    if not resolved_key:
        return [], "Gemini API key not configured", 500

    prompt = f"""Given this spoken narration line:
"{target.text}"

Suggest 3 alternative, highly cinematic 9:16 visual prompts that accurately portray this moment.
Return JSON only:
{{
  "prompts": [
    "prompt 1...",
    "prompt 2...",
    "prompt 3..."
  ]
}}"""

    text, _ = generate_content(prompt, thinking_level="low", max_output_tokens=1000, json_mode=True, api_key=resolved_key)
    if not text:
        return [], "Failed to get suggestions from Gemini", 500

    try:
        data = json.loads(text)
        return data.get("prompts", []), None, 200
    except Exception:
        return [], "Invalid response from Gemini", 500


def export_prompts(project_id: str) -> Tuple[str, Optional[str], int]:
    """Exports numbered list of scene narration + image prompts formatted for external AI tools."""
    project = load_project(project_id)
    if not project:
        return "", "Project not found", 404

    lines = []
    prefix = f"[{project.style_lock.strip()}] " if project.style_lock.strip() else ""
    for idx, sc in enumerate(project.scenes):
        p_text = sc.image_prompt.strip()
        narration = (sc.text or "").strip()
        header = f"── Scene #{idx + 1}  ({sc.duration}s) ──"
        block = [header]
        if narration:
            block.append(f"Narration : {narration}")
        block.append(f"Prompt    : {prefix}{p_text}")
        lines.append("\n".join(block))

    return "\n\n".join(lines), None, 200



def undo_project(project_id: str) -> Tuple[Optional[Project], Optional[str], int]:
    project = load_project(project_id)
    if not project or not project.history:
        return None, "No state to undo", 400

    # Save current state into future
    current_snap = {
        "script": project.script,
        "style_lock": project.style_lock,
        "visual_source": project.visual_source,
        "color_filter": getattr(project, "color_filter", "none"),
        "scenes": [s.to_dict() for s in project.scenes],
        "total_duration": project.total_duration
    }
    project.future.append(current_snap)

    prev_snap = project.history.pop()
    project.script = prev_snap["script"]
    project.style_lock = prev_snap["style_lock"]
    project.visual_source = prev_snap.get("visual_source", getattr(project, "visual_source", "video"))
    project.color_filter = prev_snap.get("color_filter", "none")
    project.scenes = [Scene.from_dict(s) for s in prev_snap["scenes"]]
    project.total_duration = prev_snap["total_duration"]
    save_project(project)
    return project, None, 200


def redo_project(project_id: str) -> Tuple[Optional[Project], Optional[str], int]:
    project = load_project(project_id)
    if not project or not project.future:
        return None, "No state to redo", 400

    current_snap = {
        "script": project.script,
        "style_lock": project.style_lock,
        "visual_source": project.visual_source,
        "color_filter": getattr(project, "color_filter", "none"),
        "scenes": [s.to_dict() for s in project.scenes],
        "total_duration": project.total_duration
    }
    project.history.append(current_snap)

    next_snap = project.future.pop()
    project.script = next_snap["script"]
    project.style_lock = next_snap["style_lock"]
    project.visual_source = next_snap.get("visual_source", getattr(project, "visual_source", "video"))
    project.color_filter = next_snap.get("color_filter", "none")
    project.scenes = [Scene.from_dict(s) for s in next_snap["scenes"]]
    project.total_duration = next_snap["total_duration"]
    save_project(project)
    return project, None, 200


# ==============================================================================
# CAPCUT TIMELINE PRO SUITE: AUTO-SYNC, MAGNETIC RAZOR, SMART MATCH, COLOR LUTS
# ==============================================================================

def auto_sync_timeline(
    project_id: str,
    mode: str = "voice_lock",
    max_cut_dur: float = 2.8
) -> Tuple[Optional[Project], Optional[str], int]:
    """
    Auto-syncs visual scenes with spoken voiceover narration to ensure seamless alignment:
    - mode="voice_lock": Snaps each scene's duration precisely to its spoken audio timestamp,
      preventing stretched visuals or premature cutoffs.
    - mode="rapid_cuts": Also auto-splits long scenes (> max_cut_dur) into dynamic sub-cuts at
      natural word/pause boundaries to prevent viewer boredom drop-offs.
    - mode="motion_sync": Calibrates motion parameters (e.g. hook snap zooms, steady pushes)
      so images feel active throughout the line.
    """
    project = load_project(project_id)
    if not project:
        return None, "Project not found", 404

    # 1. Ensure timeline alignment is present
    if not project.timeline or not project.timeline.get("scenes"):
        cur_t = 0.0
        aligned = []
        for idx, sc in enumerate(project.scenes):
            w_count = max(1, len(sc.text.strip().split()))
            dur = max(1.2, round(w_count / 2.7, 2))
            sc.duration = dur
            aligned.append({
                "scene_id": sc.id,
                "scene_index": idx,
                "start": round(cur_t, 2),
                "end": round(cur_t + dur, 2),
                "duration": dur,
                "text": sc.text
            })
            cur_t += dur
        project.timeline = project.timeline or {}
        project.timeline["scenes"] = aligned
        project.timeline["total_duration"] = round(cur_t, 2)
        project.total_duration = round(cur_t, 2)

    project.snapshot()
    tl_scenes = project.timeline.get("scenes", [])
    tl_map = {s.get("scene_id", f"idx_{s.get('scene_index')}"): s for s in tl_scenes}
    idx_map = {s.get("scene_index"): s for s in tl_scenes if "scene_index" in s}

    # Lock durations to voiceover
    for idx, sc in enumerate(project.scenes):
        matched = tl_map.get(sc.id) or idx_map.get(idx)
        if matched and "duration" in matched:
            sc.duration = max(0.8, round(float(matched["duration"]), 2))

    # Rapid cuts auto-splitting if requested
    if mode in ("rapid_cuts", "retention_boost"):
        new_scenes = []
        for idx, sc in enumerate(project.scenes):
            dur = sc.duration
            words = sc.text.strip().split()
            if dur > max_cut_dur and len(words) >= 6:
                # Find midpoint or punctuation pause
                half_words = len(words) // 2
                split_idx = half_words
                for w_i, w in enumerate(words):
                    if (w.endswith(",") or w.endswith(";") or w.endswith("—") or w.lower() in ("and", "but", "so")) and 2 <= w_i <= len(words) - 3:
                        split_idx = w_i + 1
                        break

                text_a = " ".join(words[:split_idx]).strip()
                text_b = " ".join(words[split_idx:]).strip()
                dur_a = max(1.0, round(dur * (split_idx / len(words)), 2))
                dur_b = max(1.0, round(dur - dur_a, 2))

                sc.text = text_a
                sc.duration = dur_a
                sc.motion = "snap_zoom_hard" if idx == 0 else "zoom_in"
                new_scenes.append(sc)

                # Clone for second half
                sc_b = copy.deepcopy(sc)
                sc_b.id = uuid.uuid4().hex
                sc_b.text = text_b
                sc_b.duration = dur_b
                sc_b.motion = "pan_right"
                new_scenes.append(sc_b)
            else:
                if idx == 0:
                    sc.motion = "snap_zoom_hard"
                new_scenes.append(sc)

        project.scenes = new_scenes

    # Recalculate timeline cumulative timestamps
    cur_t = 0.0
    new_tl_scenes = []
    for idx, sc in enumerate(project.scenes):
        d = sc.duration
        new_tl_scenes.append({
            "scene_id": sc.id,
            "scene_index": idx,
            "start": round(cur_t, 2),
            "end": round(cur_t + d, 2),
            "duration": round(d, 2),
            "text": sc.text
        })
        cur_t += d

    project.timeline["scenes"] = new_tl_scenes
    project.timeline["total_duration"] = round(cur_t, 2)
    project.total_duration = round(cur_t, 2)

    save_project(project)
    return project, None, 200


def split_scene_at_playhead(
    project_id: str,
    scene_id: str,
    playhead_time: float
) -> Tuple[Optional[Project], Optional[str], int]:
    """
    Splits a scene right where the playhead needle is positioned on the CapCut timeline.
    Splits text words proportionally and divides duration seamlessly.
    """
    project = load_project(project_id)
    if not project:
        return None, "Project not found", 404

    target_idx = next((i for i, s in enumerate(project.scenes) if s.id == scene_id), -1)
    if target_idx == -1:
        return None, "Scene not found", 404

    target = project.scenes[target_idx]
    if target.duration < 1.0:
        return None, "Scene is too short to split (min 1.0s)", 400

    # Calculate cumulative start time of this scene
    scene_start = sum(s.duration for s in project.scenes[:target_idx])
    offset = playhead_time - scene_start

    # Ensure valid offset inside scene
    if offset < 0.4 or offset > (target.duration - 0.4):
        offset = round(target.duration / 2.0, 2)

    words = target.text.strip().split()
    if len(words) < 2:
        return None, "Scene has too few words to split", 400

    ratio = max(0.15, min(0.85, offset / target.duration))
    split_w_idx = max(1, min(len(words) - 1, int(round(len(words) * ratio))))

    text_a = " ".join(words[:split_w_idx]).strip()
    text_b = " ".join(words[split_w_idx:]).strip()
    dur_a = max(0.5, round(offset, 2))
    dur_b = max(0.5, round(target.duration - dur_a, 2))

    project.snapshot()
    target.text = text_a
    target.duration = dur_a

    # Create second scene
    sc_b = copy.deepcopy(target)
    sc_b.id = uuid.uuid4().hex
    sc_b.text = text_b
    sc_b.duration = dur_b
    sc_b.motion = "pan_left" if target.motion != "pan_left" else "pan_right"

    project.scenes.insert(target_idx + 1, sc_b)

    # Re-sync timeline
    cur_t = 0.0
    tl_scenes = []
    for idx, sc in enumerate(project.scenes):
        tl_scenes.append({
            "scene_id": sc.id,
            "scene_index": idx,
            "start": round(cur_t, 2),
            "end": round(cur_t + sc.duration, 2),
            "duration": round(sc.duration, 2),
            "text": sc.text
        })
        cur_t += sc.duration

    if project.timeline:
        project.timeline["scenes"] = tl_scenes
        project.timeline["total_duration"] = round(cur_t, 2)
    project.total_duration = round(cur_t, 2)

    save_project(project)
    return project, None, 200


def smart_match_all_visuals(
    project_id: str,
    force_all: bool = False
) -> Tuple[Optional[Project], Optional[str], int]:
    """
    1-Click AI B-Roll Match: Scans all scenes and auto-assigns relevant vertical HD stock
    videos from Pexels based on spoken keywords. Falls back to generating visuals via AI if needed.
    """
    try:
        project = load_project(project_id)
        if not project:
            return None, "Project not found", 404

        from engine.stock_video import search_pexels_videos, download_stock_video
        from engine.config import get_pexels_api_key

        project.snapshot()
        matched_count = 0
        pexels_key = get_pexels_api_key()

        for sc in project.scenes:
            if not force_all and sc.status == "ready" and sc.media_path and os.path.exists(sc.media_path):
                continue

            queries = sc.search_queries or sc.broll_keywords or []
            query = queries[0] if queries else " ".join(sc.text.split()[:4])
            query = re.sub(r"[^\w\s]", "", query).strip() or "cinematic"

            video_assigned = False
            if pexels_key:
                try:
                    candidates = search_pexels_videos(query, limit=5, orientation="portrait", api_key=pexels_key)
                    if not candidates:
                        # Try broader cinematic keywords
                        fallback_q = "cinematic dark mysterious" if any(w in sc.text.lower() for w in ["vanish", "plane", "disappear", "mystery", "lost"]) else "cinematic vertical footage"
                        candidates = search_pexels_videos(fallback_q, limit=3, orientation="portrait", api_key=pexels_key)

                    if candidates:
                        top = candidates[0]
                        dl_url = top.get("download_url") or top.get("video_url")
                        v_id = top.get("id", uuid.uuid4().hex[:6])
                        if dl_url:
                            out_name = f"pexels_{v_id}_{uuid.uuid4().hex[:6]}.mp4"
                            out_path = os.path.join(STOCK_CACHE_DIR, out_name)
                            downloaded = download_stock_video(dl_url, out_path)
                            if downloaded and os.path.exists(downloaded):
                                sc.media_path = downloaded
                                sc.media_url = f"/outputs/stock_videos/{out_name}"
                                sc.media_type = "video"
                                sc.status = "ready"
                                sc.source_tier = "manual"
                                sc.selected_reason = f"Smart AI Matched for '{query}'"
                                sc.fail_reason = None
                                matched_count += 1
                                video_assigned = True
                except Exception as ex:
                    logger.warning(f"[SmartMatch] Pexels match failed for scene {sc.id}: {ex}")

            # If Pexels video wasn't found or key wasn't provided, and scene still has no visual, fallback to FLUX AI image
            if not video_assigned and (not sc.media_path or not os.path.exists(sc.media_path)):
                try:
                    from engine.flux import generate_image_flux
                    prompt = sc.image_prompt or f"Cinematic 9:16 vertical composition: {sc.text[:120]}"
                    out_name = f"flux_ai_{sc.id[:8]}_{uuid.uuid4().hex[:6]}.jpg"
                    out_path = os.path.abspath(f"outputs/ai_previews/{out_name}")
                    img_path = generate_image_flux(prompt, out_path=out_path)
                    if img_path and os.path.exists(img_path):
                        sc.media_path = img_path
                        sc.media_url = f"/outputs/ai_previews/{out_name}"
                        sc.media_type = "image"
                        sc.status = "ready"
                        sc.source_tier = "flux"
                        sc.selected_reason = f"AI art generated for: {prompt[:40]}..."
                        matched_count += 1
                except Exception as ex:
                    logger.warning(f"[SmartMatch] FLUX fallback failed for scene {sc.id}: {ex}")

        save_project(project)
        return project, None, 200
    except Exception as e:
        logger.error(f"[SmartMatch] Error: {e}", exc_info=True)
        return None, f"Smart match failed: {str(e)}", 500



def apply_color_filter(
    project_id: str,
    color_filter: str
) -> Tuple[Optional[Project], Optional[str], int]:
    """Sets cinematic LUT / color filter for the short video."""
    project = load_project(project_id)
    if not project:
        return None, "Project not found", 404

    project.snapshot()
    project.color_filter = color_filter
    save_project(project)
    return project, None, 200


def reorder_scene(
    project_id: str,
    scene_id: str,
    direction: str
) -> Tuple[Optional[Project], Optional[str], int]:
    """Moves a scene earlier ('left') or later ('right') in the timeline."""
    project = load_project(project_id)
    if not project:
        return None, "Project not found", 404

    idx = next((i for i, s in enumerate(project.scenes) if s.id == scene_id), -1)
    if idx == -1:
        return None, "Scene not found", 404

    if direction == "left" and idx > 0:
        project.snapshot()
        project.scenes[idx - 1], project.scenes[idx] = project.scenes[idx], project.scenes[idx - 1]
    elif direction == "right" and idx < len(project.scenes) - 1:
        project.snapshot()
        project.scenes[idx + 1], project.scenes[idx] = project.scenes[idx], project.scenes[idx + 1]
    else:
        return project, None, 200

    # Re-sync timeline
    cur_t = 0.0
    tl_scenes = []
    for i, sc in enumerate(project.scenes):
        tl_scenes.append({
            "scene_id": sc.id,
            "scene_index": i,
            "start": round(cur_t, 2),
            "end": round(cur_t + sc.duration, 2),
            "duration": round(sc.duration, 2),
            "text": sc.text
        })
        cur_t += sc.duration

    if project.timeline:
        project.timeline["scenes"] = tl_scenes
        project.timeline["total_duration"] = round(cur_t, 2)
    project.total_duration = round(cur_t, 2)

    save_project(project)
    return project, None, 200

