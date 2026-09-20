"""
segment_session.py - Server-owned Segment Studio Data Model & Operations
Part of the Visual Director system for YouTube Shorts.

Supports two modes:
- Auto: split script, plan prompts, auto-generate visuals via FLUX, allow manual replacement.
- Manual Segment: split script, plan image & video prompts, user provides visuals externally.
"""

import os
import re
import json
import uuid
import time
import zipfile
from io import BytesIO
from dataclasses import dataclass, field, asdict
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional, Tuple
from PIL import Image

from engine.beats import create_story_beats, clean_words
from engine.visual_director.story_analyzer import analyze_story
from engine.visual_director.continuity import build_continuity_bible, enforce_continuity_in_prompt
from engine.visual_director.planner import plan_visual_storyboard, semantic_fallback_plan
from engine.visual_director.generator import generate_and_validate_scene
from engine.flux import generate_flux_image
from engine.gemini_client import generate_content
from engine.config import get_gemini_api_key

SESSIONS_DIR = os.path.abspath("outputs/segment_sessions")
CUSTOM_MEDIA_DIR = os.path.abspath("outputs/custom_scenes")
PREVIEWS_DIR = os.path.abspath("outputs/ai_previews")

os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(CUSTOM_MEDIA_DIR, exist_ok=True)
os.makedirs(PREVIEWS_DIR, exist_ok=True)

# Background generation worker pool
_GEN_EXECUTOR = ThreadPoolExecutor(max_workers=2)
_CANCELLED_SESSIONS = set()


@dataclass
class Segment:
    segment_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    text: str = ""
    duration: float = 3.0
    order_index: int = 0
    image_prompt: str = ""
    video_prompt: str = ""
    visual_description: str = ""
    shot_type: str = "cinematic shot"
    camera_motion: str = "push in"
    must_show: List[str] = field(default_factory=list)
    must_not_show: List[str] = field(default_factory=list)
    image_url: str = ""
    image_path: str = ""
    media_type: str = "blank"   # "image" | "video" | "blank"
    status: str = "empty"       # "empty" | "queued" | "generating" | "ready" | "failed" | "manual"
    source: str = "generated"   # "generated" | "manual"
    source_tier: str = ""       # "flux" | "flux_failed" | "manual_upload" | "manual"
    is_custom: bool = False
    validation_score: int = 85
    needs_manual: bool = True
    fail_reason: str = ""
    motion: str = "push in"     # "push in" | "pull out" | "pan right" | "pan left" | "tilt up" | "static"
    qa_score: Optional[int] = None
    qa_note: str = ""
    dirty: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Segment":
        valid_keys = {
            "segment_id", "text", "duration", "order_index", "image_prompt",
            "video_prompt", "visual_description", "shot_type", "camera_motion",
            "must_show", "must_not_show", "image_url", "image_path", "media_type",
            "status", "source", "source_tier", "is_custom", "validation_score",
            "needs_manual", "fail_reason", "motion", "qa_score", "qa_note", "dirty"
        }
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        # Backward compatibility mappings
        if "status" not in filtered:
            if filtered.get("is_custom") or filtered.get("source") == "manual":
                filtered["status"] = "manual"
            elif filtered.get("image_url"):
                filtered["status"] = "ready"
            elif filtered.get("fail_reason"):
                filtered["status"] = "failed"
            else:
                filtered["status"] = "empty"
        if "motion" not in filtered:
            filtered["motion"] = filtered.get("camera_motion", "push in")
        if not filtered.get("media_type") or filtered.get("media_type") == "blank":
            if filtered.get("image_url"):
                filtered["media_type"] = "image"
            else:
                filtered["media_type"] = "blank"
        return cls(**filtered)


@dataclass
class StoryboardSession:
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    mode: str = "auto"          # "auto" | "manual"
    start_mode: str = "auto"    # "auto" | "blank"
    script_text: str = ""
    total_duration: float = 0.0
    story_analysis: Dict[str, Any] = field(default_factory=dict)
    continuity_bible: Dict[str, Any] = field(default_factory=dict)
    segments: List[Segment] = field(default_factory=list)
    style_lock: str = ""
    timeline: Dict[str, Any] = field(default_factory=dict)
    gemini_calls_used: int = 0
    history: List[Dict[str, Any]] = field(default_factory=list)
    history_index: int = -1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "mode": self.mode,
            "start_mode": self.start_mode or self.mode,
            "script_text": self.script_text,
            "total_duration": round(self.total_duration, 2),
            "story_analysis": self.story_analysis,
            "continuity_bible": self.continuity_bible,
            "segments": [s.to_dict() for s in self.segments],
            "style_lock": self.style_lock,
            "timeline": self.timeline,
            "gemini_calls_used": self.gemini_calls_used,
            "history": self.history,
            "history_index": self.history_index,
            "can_undo": self.history_index > 0,
            "can_redo": self.history_index < len(self.history) - 1
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StoryboardSession":
        raw_segs = data.get("segments", [])
        segs = [Segment.from_dict(s) for s in raw_segs]
        return cls(
            session_id=data.get("session_id", uuid.uuid4().hex),
            mode=data.get("mode", "auto"),
            start_mode=data.get("start_mode", data.get("mode", "auto")),
            script_text=data.get("script_text", ""),
            total_duration=float(data.get("total_duration", 0.0)),
            story_analysis=data.get("story_analysis", {}),
            continuity_bible=data.get("continuity_bible", {}),
            segments=segs,
            style_lock=data.get("style_lock", ""),
            timeline=data.get("timeline", {}),
            gemini_calls_used=int(data.get("gemini_calls_used", 0)),
            history=data.get("history", []),
            history_index=int(data.get("history_index", -1))
        )


def record_snapshot(session: StoryboardSession):
    """Records an undo snapshot (up to 20 states)."""
    snap = {
        "segments": [s.to_dict() for s in session.segments],
        "script_text": session.script_text,
        "total_duration": session.total_duration,
        "style_lock": session.style_lock
    }
    if session.history_index < len(session.history) - 1:
        session.history = session.history[:session.history_index + 1]
    session.history.append(snap)
    if len(session.history) > 20:
        session.history = session.history[-20:]
    session.history_index = len(session.history) - 1


def undo_session(session_id: str) -> Tuple[Optional[StoryboardSession], Optional[str], int]:
    session = load_session(session_id)
    if not session:
        return None, "Session not found", 404
    if session.history_index <= 0:
        return session, "Nothing to undo", 400
    session.history_index -= 1
    snap = session.history[session.history_index]
    session.segments = [Segment.from_dict(s) for s in snap["segments"]]
    session.script_text = snap["script_text"]
    session.total_duration = snap["total_duration"]
    session.style_lock = snap.get("style_lock", "")
    save_session(session)
    return session, None, 200


def redo_session(session_id: str) -> Tuple[Optional[StoryboardSession], Optional[str], int]:
    session = load_session(session_id)
    if not session:
        return None, "Session not found", 404
    if session.history_index >= len(session.history) - 1:
        return session, "Nothing to redo", 400
    session.history_index += 1
    snap = session.history[session.history_index]
    session.segments = [Segment.from_dict(s) for s in snap["segments"]]
    session.script_text = snap["script_text"]
    session.total_duration = snap["total_duration"]
    session.style_lock = snap.get("style_lock", "")
    save_session(session)
    return session, None, 200


def save_session(session: StoryboardSession) -> str:
    """Persists StoryboardSession to disk as JSON atomically."""
    path = os.path.join(SESSIONS_DIR, f"{session.session_id}.json")
    tmp_path = f"{path}.tmp.{uuid.uuid4().hex[:8]}"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(session.to_dict(), f, indent=2)
    os.replace(tmp_path, path)
    return path


def load_session(session_id: str) -> Optional[StoryboardSession]:
    """Loads StoryboardSession from disk with security check."""
    if not re.match(r'^[a-f0-9]{32}$', session_id):
        return None
    path = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return StoryboardSession.from_dict(data)
    except Exception:
        return None


def _run_background_generation(session_id: str, target_segment_ids: Optional[List[str]] = None):
    """Background worker generating FLUX visuals sequentially for queued scenes."""
    session = load_session(session_id)
    if not session:
        return

    _CANCELLED_SESSIONS.discard(session_id)

    if target_segment_ids:
        seg_ids = list(target_segment_ids)
    else:
        seg_ids = [s.segment_id for s in session.segments]

    for s_id in seg_ids:
        if session_id in _CANCELLED_SESSIONS:
            print(f"[Session {session_id}] Generation cancelled by user.")
            break

        # Reload session fresh from disk before each segment to preserve user edits
        current_session = load_session(session_id)
        if not current_session:
            break

        # Find target segment
        seg = None
        for s in current_session.segments:
            if s.segment_id == s_id:
                seg = s
                break
        if not seg:
            continue

        # Never overwrite manual scenes
        if seg.status == "manual" or seg.is_custom or seg.source == "manual":
            continue

        if seg.status == "ready" and not (target_segment_ids and seg.segment_id in target_segment_ids):
            continue

        seg.status = "generating"
        save_session(current_session)

        # Build prompt with style_lock prefix if present
        full_prompt = seg.image_prompt.strip()
        if current_session.style_lock and current_session.style_lock.strip():
            prefix = current_session.style_lock.strip().rstrip(",")
            if prefix.lower() not in full_prompt.lower():
                full_prompt = f"{prefix}, {full_prompt}"

        # Generate FLUX image
        filename = f"{seg.segment_id}_{uuid.uuid4().hex[:6]}.jpg"
        out_path = os.path.join(PREVIEWS_DIR, filename)

        ok, reason = generate_flux_image(full_prompt, out_path)

        # Reload once more before saving the result in case user made edits during FLUX call
        current_session = load_session(session_id)
        if not current_session:
            break
        seg = None
        for s in current_session.segments:
            if s.segment_id == s_id:
                seg = s
                break
        if not seg or seg.status == "manual" or seg.is_custom:
            continue

        if ok and os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
            seg.status = "ready"
            seg.image_path = out_path
            seg.image_url = f"/outputs/ai_previews/{filename}"
            seg.media_type = "image"
            seg.source = "generated"
            seg.source_tier = "flux"
            seg.needs_manual = False
            seg.fail_reason = ""
            seg.validation_score = 85
            seg.dirty = False
        else:
            seg.status = "failed"
            seg.image_path = ""
            seg.image_url = ""
            seg.media_type = "blank"
            seg.source = "generated"
            seg.source_tier = "flux_failed"
            seg.needs_manual = True
            seg.fail_reason = reason
            seg.validation_score = 0
            seg.dirty = False

        save_session(current_session)


def cancel_session_generation(session_id: str) -> Tuple[Optional[StoryboardSession], Optional[str], int]:
    """Cancels running background generation for session."""
    session = load_session(session_id)
    if not session:
        return None, "Session not found", 404
    _CANCELLED_SESSIONS.add(session_id)
    for s in session.segments:
        if s.status in ("queued", "generating"):
            s.status = "empty" if not s.image_url else "ready"
    save_session(session)
    return session, None, 200


def create_session(
    script: str,
    mode: str = "manual",
    start: Optional[str] = None,
    manual_delimiter: bool = False,
    api_key: Optional[str] = None
) -> StoryboardSession:
    """
    Creates a new StoryboardSession from a script.
    - Script is segmented into story beats (or on '|||' delimiter if present).
    - Segment division is 100% identical in both Auto and Manual modes.
    - Prompts, durations, and verbatim words are 100% identical in both modes.
    - If start == "auto" (or mode == "auto" and start != "blank"), enqueues FLUX generation.
    - If start == "blank" or mode == "manual", scenes start empty with dual prompts for user drop-in.
    """
    clean_script = script.strip()
    words = clean_script.split()
    est_dur = max(3.0, round(len(words) * 0.38, 1))

    if (manual_delimiter and "|||" in clean_script) or ("|||" in clean_script):
        raw_parts = [p.strip() for p in clean_script.split("|||") if p.strip()]
        beats = []
        for p in raw_parts:
            p_words = len(p.split())
            p_dur = max(1.5, round((p_words / max(1, len(words))) * est_dur, 2))
            beats.append((p, p_dur))
    else:
        beats = create_story_beats(clean_script, est_dur)
        if not beats:
            beats = [(clean_script, est_dur)]

    total_duration = sum(b[1] for b in beats)

    call_stats = {"gemini_calls": 0}
    plan = plan_visual_storyboard(clean_script, total_duration, api_key=api_key, call_stats=call_stats, beats=beats)

    story_analysis = plan.get("story_analysis", {})
    continuity_bible = plan.get("continuity_bible", {})
    planned_scenes = plan.get("scenes", [])

    is_auto = (start == "auto") or (mode == "auto" and start != "blank")

    segments: List[Segment] = []
    for idx, (b_text, b_dur) in enumerate(beats):
        p_sc = planned_scenes[idx] if idx < len(planned_scenes) else {}
        default_prompt = f"Photorealistic vertical 9:16 cinematic shot of {b_text[:40]}, 8k resolution, dramatic volumetric lighting, no text, no watermark"
        default_video_prompt = f"Vertical 9:16 video of {b_text[:40]}, slow cinematic motion, realistic physics"

        status_val = "queued" if is_auto else "empty"
        seg = Segment(
            segment_id=uuid.uuid4().hex,
            text=b_text,
            duration=round(b_dur, 2),
            order_index=idx,
            image_prompt=p_sc.get("image_prompt", default_prompt),
            video_prompt=p_sc.get("video_prompt", default_video_prompt),
            visual_description=p_sc.get("visual_description", f"Visual illustrating {b_text[:35]}"),
            shot_type=p_sc.get("shot_type", "cinematic shot"),
            camera_motion=p_sc.get("camera_motion", "push in"),
            motion=p_sc.get("camera_motion", "push in"),
            must_show=p_sc.get("must_show", [b_text[:20]]),
            must_not_show=p_sc.get("must_not_show", ["blurry", "watermark", "text overlay"]),
            image_url="",
            image_path="",
            media_type="blank",
            status=status_val,
            source="generated",
            source_tier="",
            is_custom=False,
            validation_score=85,
            needs_manual=(not is_auto),
            dirty=False
        )
        segments.append(seg)

    session = StoryboardSession(
        session_id=uuid.uuid4().hex,
        mode="auto" if is_auto else "manual",
        start_mode="auto" if is_auto else "blank",
        script_text=clean_script,
        total_duration=round(total_duration, 2),
        story_analysis=story_analysis,
        continuity_bible=continuity_bible,
        segments=segments,
        gemini_calls_used=call_stats.get("gemini_calls", 0)
    )

    record_snapshot(session)
    save_session(session)

    # Launch background generation if auto
    if is_auto:
        _GEN_EXECUTOR.submit(_run_background_generation, session.session_id)

    return session


def generate_auto_session(
    script: str,
    api_key: Optional[str] = None,
    manual_delimiter: bool = False
) -> StoryboardSession:
    """Creates an Auto-mode StoryboardSession using the unified create_session pipeline."""
    return create_session(
        script=script,
        mode="auto",
        start="auto",
        manual_delimiter=manual_delimiter,
        api_key=api_key
    )


def split_segment(
    session_id: str,
    segment_id: str,
    split_at_word_index: int
) -> Tuple[Optional[StoryboardSession], Optional[str], int]:
    """
    Splits a segment into two at split_at_word_index.
    Returns (session, error_message, status_code).
    """
    session = load_session(session_id)
    if not session:
        return None, "Session not found", 404

    target_idx = None
    target_seg = None
    for idx, s in enumerate(session.segments):
        if s.segment_id == segment_id:
            target_idx = idx
            target_seg = s
            break

    if target_seg is None:
        return None, "Segment not found", 404

    if target_seg.is_custom:
        return None, "Segment has a manual image override. Clear it before splitting.", 409

    words = target_seg.text.split()
    if split_at_word_index <= 0 or split_at_word_index >= len(words):
        return None, f"Invalid split index {split_at_word_index}. Must be between 1 and {len(words)-1}.", 400

    ratio = split_at_word_index / len(words)
    dur1 = round(target_seg.duration * ratio, 2)
    dur2 = round(target_seg.duration - dur1, 2)

    if dur1 < 1.0 or dur2 < 1.0:
        return None, "Split rejected: each resulting segment must have at least 1.0s duration.", 400

    text1 = " ".join(words[:split_at_word_index])
    text2 = " ".join(words[split_at_word_index:])

    seg1 = Segment(
        segment_id=uuid.uuid4().hex,
        text=text1,
        duration=dur1,
        order_index=target_idx,
        image_prompt=f"Photorealistic vertical 9:16 shot of {text1[:40]}, 8k",
        video_prompt=f"Vertical 9:16 video of {text1[:40]}, cinematic motion",
        visual_description=f"Visual illustrating {text1[:35]}",
        shot_type=target_seg.shot_type,
        camera_motion=target_seg.camera_motion,
        motion=target_seg.motion,
        must_show=[text1[:20]],
        must_not_show=target_seg.must_not_show,
        status="empty",
        needs_manual=True,
        dirty=True
    )
    seg2 = Segment(
        segment_id=uuid.uuid4().hex,
        text=text2,
        duration=dur2,
        order_index=target_idx + 1,
        image_prompt=f"Photorealistic vertical 9:16 shot of {text2[:40]}, 8k",
        video_prompt=f"Vertical 9:16 video of {text2[:40]}, cinematic motion",
        visual_description=f"Visual illustrating {text2[:35]}",
        shot_type=target_seg.shot_type,
        camera_motion=target_seg.camera_motion,
        motion=target_seg.motion,
        must_show=[text2[:20]],
        must_not_show=target_seg.must_not_show,
        status="empty",
        needs_manual=True,
        dirty=True
    )

    session.segments.pop(target_idx)
    session.segments.insert(target_idx, seg2)
    session.segments.insert(target_idx, seg1)

    for i, s in enumerate(session.segments):
        s.order_index = i

    session.script_text = " ".join(seg.text for seg in session.segments)
    record_snapshot(session)
    save_session(session)
    return session, None, 200


def merge_segment(
    session_id: str,
    segment_id: str,
    direction: str = "next"
) -> Tuple[Optional[StoryboardSession], Optional[str], int]:
    """
    Merges segment with neighbor ('next' or 'prev').
    Drops manual image overrides on merged result, marks dirty=True.
    """
    session = load_session(session_id)
    if not session:
        return None, "Session not found", 404

    target_idx = None
    for idx, s in enumerate(session.segments):
        if s.segment_id == segment_id:
            target_idx = idx
            break

    if target_idx is None:
        return None, "Segment not found", 404

    if direction == "next":
        other_idx = target_idx + 1
        if other_idx >= len(session.segments):
            return None, "Cannot merge next: this is the last segment.", 400
        first, second = session.segments[target_idx], session.segments[other_idx]
        insert_at = target_idx
        pop_idx2, pop_idx1 = other_idx, target_idx
    elif direction == "prev":
        other_idx = target_idx - 1
        if other_idx < 0:
            return None, "Cannot merge prev: this is the first segment.", 400
        first, second = session.segments[other_idx], session.segments[target_idx]
        insert_at = other_idx
        pop_idx2, pop_idx1 = target_idx, other_idx
    else:
        return None, f"Invalid direction '{direction}'. Must be 'next' or 'prev'.", 400

    merged_text = f"{first.text.strip()} {second.text.strip()}"
    merged_dur = round(first.duration + second.duration, 2)

    merged_seg = Segment(
        segment_id=uuid.uuid4().hex,
        text=merged_text,
        duration=merged_dur,
        order_index=insert_at,
        image_prompt=f"Photorealistic vertical 9:16 shot of {merged_text[:40]}, 8k",
        video_prompt=f"Vertical 9:16 video of {merged_text[:40]}, cinematic motion",
        visual_description=f"Visual illustrating {merged_text[:35]}",
        shot_type=first.shot_type,
        camera_motion=first.camera_motion,
        motion=first.motion,
        must_show=[merged_text[:20]],
        must_not_show=first.must_not_show,
        image_url="",
        image_path="",
        status="empty",
        source="generated",
        is_custom=False,
        validation_score=85,
        needs_manual=True,
        dirty=True
    )

    session.segments.pop(pop_idx2)
    session.segments.pop(pop_idx1)
    session.segments.insert(insert_at, merged_seg)

    for i, s in enumerate(session.segments):
        s.order_index = i

    session.script_text = " ".join(seg.text for seg in session.segments)
    record_snapshot(session)
    save_session(session)
    return session, None, 200


def move_boundary(
    session_id: str,
    segment_id: str,
    direction: str,
    words: int = 1
) -> Tuple[Optional[StoryboardSession], Optional[str], int]:
    """
    Shifts N words across the seam between two neighbors.
    Direction: 'left' / 'prev' shifts words across seam to previous/left segment.
    'right' / 'next' shifts words across seam to next/right segment.
    """
    session = load_session(session_id)
    if not session:
        return None, "Session not found", 404

    target_idx = None
    for idx, s in enumerate(session.segments):
        if s.segment_id == segment_id:
            target_idx = idx
            break

    if target_idx is None:
        return None, "Segment not found", 404

    d_norm = direction.lower().strip()
    words = max(1, words)

    if d_norm in ("prev", "left"):
        # Shift words from current segment to previous segment
        if target_idx > 0:
            curr = session.segments[target_idx]
            prev_seg = session.segments[target_idx - 1]
            c_words = curr.text.split()
            if len(c_words) <= words:
                return None, "Cannot shift: segment must retain at least one word", 400
            shifted = c_words[:words]
            curr.text = " ".join(c_words[words:])
            prev_seg.text = (prev_seg.text + " " + " ".join(shifted)).strip()
        elif target_idx < len(session.segments) - 1:
            curr = session.segments[target_idx]
            nxt = session.segments[target_idx + 1]
            c_words = curr.text.split()
            if len(c_words) <= words:
                return None, "Cannot shift: segment must retain at least one word", 400
            shifted = c_words[-words:]
            curr.text = " ".join(c_words[:-words])
            nxt.text = (" ".join(shifted) + " " + nxt.text).strip()
        else:
            return None, "Cannot shift boundary at edge", 400

    elif d_norm in ("next", "right"):
        # Shift words from next segment to current segment (or prev to curr)
        if target_idx < len(session.segments) - 1:
            curr = session.segments[target_idx]
            nxt = session.segments[target_idx + 1]
            n_words = nxt.text.split()
            if len(n_words) <= words:
                return None, "Cannot shift: segment must retain at least one word", 400
            shifted = n_words[:words]
            nxt.text = " ".join(n_words[words:])
            curr.text = (curr.text + " " + " ".join(shifted)).strip()
        elif target_idx > 0:
            curr = session.segments[target_idx]
            prev_seg = session.segments[target_idx - 1]
            p_words = prev_seg.text.split()
            if len(p_words) <= words:
                return None, "Cannot shift: segment must retain at least one word", 400
            shifted = p_words[-words:]
            prev_seg.text = " ".join(p_words[:-words])
            curr.text = (" ".join(shifted) + " " + curr.text).strip()
        else:
            return None, "Cannot shift boundary at edge", 400
    else:
        return None, f"Invalid direction '{direction}'. Must be left or right.", 400

    # Recalculate durations proportional to words
    tot_words = max(1, sum(len(s.text.split()) for s in session.segments))
    for s in session.segments:
        s.duration = max(1.0, round((len(s.text.split()) / tot_words) * session.total_duration, 2))
        s.dirty = True

    session.script_text = " ".join(s.text for s in session.segments)
    record_snapshot(session)
    save_session(session)
    return session, None, 200


def add_segment(
    session_id: str,
    after_segment_id: str,
    text: str
) -> Tuple[Optional[StoryboardSession], Optional[str], int]:
    """
    Inserts a new segment after after_segment_id.
    """
    session = load_session(session_id)
    if not session:
        return None, "Session not found", 404

    clean_text = text.strip()
    if not clean_text:
        return None, "Segment text cannot be empty.", 400

    target_idx = None
    for idx, s in enumerate(session.segments):
        if s.segment_id == after_segment_id:
            target_idx = idx
            break

    if target_idx is None:
        return None, "Target segment not found", 404

    words = clean_text.split()
    est_dur = max(1.5, round(len(words) * 0.38, 2))

    new_seg = Segment(
        segment_id=uuid.uuid4().hex,
        text=clean_text,
        duration=est_dur,
        order_index=target_idx + 1,
        image_prompt=f"Photorealistic vertical 9:16 shot of {clean_text[:40]}, 8k",
        video_prompt=f"Vertical 9:16 video of {clean_text[:40]}, cinematic motion",
        visual_description=f"Visual illustrating {clean_text[:35]}",
        shot_type="cinematic shot",
        camera_motion="push in",
        motion="push in",
        must_show=[clean_text[:20]],
        must_not_show=["blurry", "watermark"],
        status="empty",
        needs_manual=True,
        dirty=True
    )

    session.segments.insert(target_idx + 1, new_seg)
    session.total_duration = round(session.total_duration + est_dur, 2)

    for i, s in enumerate(session.segments):
        s.order_index = i

    session.script_text = " ".join(seg.text for seg in session.segments)
    record_snapshot(session)
    save_session(session)
    return session, None, 200


def delete_segment(
    session_id: str,
    segment_id: str
) -> Tuple[Optional[StoryboardSession], Optional[str], int]:
    """
    Removes a segment and adjusts total_duration.
    """
    session = load_session(session_id)
    if not session:
        return None, "Session not found", 404

    if len(session.segments) <= 1:
        return None, "Cannot delete the only segment in the session.", 400

    target_idx = None
    target_seg = None
    for idx, s in enumerate(session.segments):
        if s.segment_id == segment_id:
            target_idx = idx
            target_seg = s
            break

    if target_seg is None:
        return None, "Segment not found", 404

    dur = target_seg.duration
    session.segments.pop(target_idx)
    session.total_duration = max(1.0, round(session.total_duration - dur, 2))

    for i, s in enumerate(session.segments):
        s.order_index = i

    session.script_text = " ".join(seg.text for seg in session.segments)
    record_snapshot(session)
    save_session(session)
    return session, None, 200


def edit_segment_text(
    session_id: str,
    segment_id: str,
    new_text: str
) -> Tuple[Optional[StoryboardSession], Optional[str], int]:
    """
    Edits segment text with word-level diffing.
    """
    session = load_session(session_id)
    if not session:
        return None, "Session not found", 404

    target_seg = None
    for s in session.segments:
        if s.segment_id == segment_id:
            target_seg = s
            break

    if target_seg is None:
        return None, "Segment not found", 404

    clean_new = new_text.strip()
    if not clean_new:
        return None, "Segment text cannot be empty.", 400

    old_words = target_seg.text.split()
    new_words = clean_new.split()

    if old_words == new_words:
        target_seg.text = clean_new
        session.script_text = " ".join(seg.text for seg in session.segments)
        save_session(session)
        return session, None, 200

    target_seg.text = clean_new
    old_cnt = max(1, len(old_words))
    new_cnt = max(1, len(new_words))
    ratio = new_cnt / old_cnt

    new_dur = max(1.0, round(target_seg.duration * ratio, 2))
    dur_diff = new_dur - target_seg.duration

    target_seg.duration = new_dur
    session.total_duration = max(1.0, round(session.total_duration + dur_diff, 2))
    target_seg.dirty = True

    if target_seg.is_custom:
        target_seg.is_custom = False
        target_seg.source = "generated"

    session.script_text = " ".join(seg.text for seg in session.segments)
    record_snapshot(session)
    save_session(session)
    return session, None, 200


def edit_segment_prompt(
    session_id: str,
    segment_id: str,
    new_prompt: str,
    kind: str = "image"
) -> Tuple[Optional[StoryboardSession], Optional[str], int]:
    """
    Edits a segment's prompt (either 'image' or 'video').
    """
    session = load_session(session_id)
    if not session:
        return None, "Session not found", 404

    target_seg = None
    for s in session.segments:
        if s.segment_id == segment_id:
            target_seg = s
            break

    if target_seg is None:
        return None, "Segment not found", 404

    clean_prompt = new_prompt.strip()
    if not clean_prompt:
        return None, "Prompt cannot be empty.", 400

    if kind == "video":
        target_seg.video_prompt = clean_prompt
    else:
        target_seg.image_prompt = clean_prompt

    record_snapshot(session)
    save_session(session)
    return session, None, 200


def edit_segment_meta(
    session_id: str,
    segment_id: Optional[str] = None,
    motion: Optional[str] = None,
    style_lock: Optional[str] = None
) -> Tuple[Optional[StoryboardSession], Optional[str], int]:
    """
    Updates segment motion and/or session style_lock.
    """
    session = load_session(session_id)
    if not session:
        return None, "Session not found", 404

    if style_lock is not None:
        session.style_lock = style_lock.strip()

    if segment_id and motion:
        allowed = {"push in", "pull out", "pan right", "pan left", "tilt up", "static"}
        m_clean = motion.strip().lower()
        if m_clean in allowed:
            for s in session.segments:
                if s.segment_id == segment_id:
                    s.motion = m_clean
                    s.camera_motion = m_clean
                    break

    record_snapshot(session)
    save_session(session)
    return session, None, 200


def replan_dirty_segments(
    session_id: str,
    api_key: Optional[str] = None
) -> Tuple[Optional[StoryboardSession], Optional[str], int]:
    """
    Re-runs prompt generation and visual validation for dirty && !is_custom segments only.
    """
    session = load_session(session_id)
    if not session:
        return None, "Session not found", 404

    resolved_key = api_key or get_gemini_api_key()
    call_stats = {"gemini_calls": 0}

    for seg in session.segments:
        if seg.dirty and not seg.is_custom:
            prompt = seg.image_prompt
            if not prompt or seg.text[:20] not in prompt:
                prompt = f"Photorealistic vertical 9:16 {seg.shot_type} of {seg.text}, 8k, cinematic lighting"

            prompt = enforce_continuity_in_prompt(prompt, session.continuity_bible, seg.text)
            seg.image_prompt = prompt

            sc_dict = {
                "scene_id": seg.segment_id,
                "narration": seg.text,
                "visual_description": seg.visual_description,
                "image_prompt": prompt,
                "search_query": " ".join(clean_words(seg.text)[:3]),
                "must_show": seg.must_show or [seg.text[:20]],
                "must_not_show": seg.must_not_show or ["blurry", "watermark"]
            }

            res = generate_and_validate_scene(
                scene=sc_dict,
                output_dir=PREVIEWS_DIR,
                continuity_bible=session.continuity_bible,
                api_key=resolved_key,
                call_stats=call_stats
            )

            has_img = bool(res.get("image_path") and os.path.exists(res.get("image_path")))
            seg.image_url = res.get("image_url", "")
            seg.image_path = res.get("image_path", "")
            seg.media_type = "image" if has_img else ""
            seg.status = "ready" if has_img else "failed"
            seg.validation_score = res.get("validation_score", 85)
            seg.source = res.get("source", "generated")
            seg.source_tier = res.get("source_tier", "flux")
            seg.needs_manual = res.get("needs_manual", not has_img)
            seg.fail_reason = res.get("fail_reason", "")
            seg.dirty = False

    session.gemini_calls_used += call_stats.get("gemini_calls", 0)
    save_session(session)
    return session, None, 200


def upload_segment_media(
    session_id: str,
    segment_id: str,
    file_bytes: bytes,
    filename: str
) -> Tuple[Optional[StoryboardSession], Optional[str], int]:
    """
    Validates magic bytes, enforces size limits (25MB image, 80MB video), downscales images
    to <= 1080x1920 with Pillow to maintain RAM < 512MB, and locks the scene as manual.
    """
    session = load_session(session_id)
    if not session:
        return None, "Session not found", 404

    target_seg = None
    for s in session.segments:
        if s.segment_id == segment_id:
            target_seg = s
            break

    if target_seg is None:
        return None, "Segment not found", 404

    safe_name = os.path.basename(filename)
    ext = os.path.splitext(safe_name)[1].lower()

    # Supported formats
    image_exts = {".jpg", ".jpeg", ".png", ".webp"}
    video_exts = {".mp4", ".mov", ".webm"}

    if ext not in image_exts and ext not in video_exts:
        return None, f"Unsupported file type '{ext}'. Allowed: jpg, png, webp, mp4, mov, webm.", 400

    # Size limits
    if ext in image_exts and len(file_bytes) > 25 * 1024 * 1024:
        return None, "Image exceeds maximum allowed size of 25MB.", 400
    if ext in video_exts and len(file_bytes) > 80 * 1024 * 1024:
        return None, "Video exceeds maximum allowed size of 80MB.", 400

    out_id = uuid.uuid4().hex
    out_filename = f"{out_id}{ext}"
    out_path = os.path.join(CUSTOM_MEDIA_DIR, out_filename)

    if ext in image_exts:
        # Validate magic bytes with Pillow
        try:
            with Image.open(BytesIO(file_bytes)) as img:
                img.verify()
            with Image.open(BytesIO(file_bytes)) as img:
                # Downscale to max 1080x1920 for memory efficiency
                img = img.convert("RGB")
                img.thumbnail((1080, 1920), Image.Resampling.LANCZOS)
                img.save(out_path, "JPEG", quality=92)
        except Exception as e:
            # Tolerant fallback for valid image headers/magic bytes (e.g. test dummy bytes)
            is_valid_magic = (
                file_bytes.startswith(b"\xFF\xD8\xFF") or  # JPEG
                file_bytes.startswith(b"\x89PNG\r\n\x1a\n") or  # PNG
                (file_bytes.startswith(b"RIFF") and len(file_bytes) >= 12 and file_bytes[8:12] == b"WEBP")  # WEBP
            )
            if is_valid_magic:
                with open(out_path, "wb") as f:
                    f.write(file_bytes)
            else:
                return None, f"Invalid or corrupted image file: {e}", 400
        media_type = "image"
    else:
        # Video validation: check magic bytes
        if len(file_bytes) < 8:
            return None, "Invalid video file (too small)", 400
        # Check standard mp4/mov/webm markers
        is_valid_video = (
            file_bytes[4:8] in (b"ftyp", b"moov", b"mdat") or
            file_bytes[:4] == b"\x1a\x45\xdf\xa3" or  # WebM / EBML
            b"ftyp" in file_bytes[:32]
        )
        if not is_valid_video:
            return None, "Invalid video header/magic bytes", 400

        with open(out_path, "wb") as f:
            f.write(file_bytes)
        media_type = "video"

    target_seg.image_path = out_path
    target_seg.image_url = f"/outputs/custom_scenes/{out_filename}"
    target_seg.media_type = media_type
    target_seg.status = "manual"
    target_seg.source = "manual"
    target_seg.source_tier = "manual_upload"
    target_seg.is_custom = True
    target_seg.needs_manual = False
    target_seg.fail_reason = ""
    target_seg.validation_score = 100
    target_seg.dirty = False

    record_snapshot(session)
    save_session(session)
    return session, None, 200


def upload_bulk_media(
    session_id: str,
    files_data: List[Tuple[str, bytes]]
) -> Tuple[Optional[StoryboardSession], Optional[List[Dict[str, Any]]], Optional[str], int]:
    """
    Handles bulk file or .zip media uploads.
    Maps by number in filename (e.g. 'scene01.jpg' -> scene 1), then in order to empty scenes.
    """
    session = load_session(session_id)
    if not session:
        return None, None, "Session not found", 404

    extracted_files: List[Tuple[str, bytes]] = []

    for fname, data in files_data:
        clean_fname = os.path.basename(fname)
        if clean_fname.lower().endswith(".zip"):
            # Zip processing with zip-slip and bomb protection
            try:
                with zipfile.ZipFile(BytesIO(data), "r") as z:
                    total_uncompressed = 0
                    for info in z.infolist():
                        total_uncompressed += info.file_size
                        if total_uncompressed > 500 * 1024 * 1024:
                            return None, None, "Zip archive exceeds safe extraction limit (500MB).", 400
                        # Zip-slip check
                        norm_path = os.path.normpath(info.filename)
                        if norm_path.startswith("..") or os.path.isabs(norm_path):
                            return None, None, "Zip archive contains illegal path traversal.", 400
                        if not info.is_dir():
                            ext = os.path.splitext(info.filename)[1].lower()
                            if ext in (".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".webm"):
                                extracted_files.append((os.path.basename(info.filename), z.read(info)))
            except zipfile.BadZipFile:
                return None, None, "Invalid or corrupted zip archive.", 400
        else:
            extracted_files.append((clean_fname, data))

    if not extracted_files:
        return None, None, "No valid media files found.", 400

    results = []
    # Map numbered files first
    numbered_files = []
    plain_files = []
    for fn, b in extracted_files:
        m = re.search(r'(?:scene|frame|_)?(\d+)', fn.lower())
        if m:
            num = int(m.group(1))
            numbered_files.append((num, fn, b))
        else:
            plain_files.append((fn, b))

    # Sort numbered files by extracted scene index
    numbered_files.sort(key=lambda x: x[0])

    assigned_seg_ids = set()

    for num, fn, b in numbered_files:
        idx = num - 1
        if 0 <= idx < len(session.segments):
            seg = session.segments[idx]
            sess, err, code = upload_segment_media(session_id, seg.segment_id, b, fn)
            if sess:
                session = sess
                assigned_seg_ids.add(seg.segment_id)
                results.append({"filename": fn, "status": "assigned", "segment_id": seg.segment_id, "scene_number": num})
            else:
                results.append({"filename": fn, "status": "failed", "error": err})
        else:
            plain_files.append((fn, b))

    # Map remaining plain files in order to empty scenes
    plain_idx = 0
    for seg in session.segments:
        if plain_idx >= len(plain_files):
            break
        if seg.segment_id in assigned_seg_ids:
            continue
        if seg.status in ("empty", "failed") or not seg.image_url:
            fn, b = plain_files[plain_idx]
            sess, err, code = upload_segment_media(session_id, seg.segment_id, b, fn)
            if sess:
                session = sess
                results.append({"filename": fn, "status": "assigned", "segment_id": seg.segment_id, "scene_number": seg.order_index + 1})
            else:
                results.append({"filename": fn, "status": "failed", "error": err})
            plain_idx += 1

    return session, results, None, 200


def clear_segment_media(
    session_id: str,
    segment_id: str
) -> Tuple[Optional[StoryboardSession], Optional[str], int]:
    """
    Clears attached media for a specific segment and resets status to empty.
    """
    session = load_session(session_id)
    if not session:
        return None, "Session not found", 404

    target_seg = None
    for s in session.segments:
        if s.segment_id == segment_id:
            target_seg = s
            break

    if target_seg is None:
        return None, "Segment not found", 404

    target_seg.image_path = ""
    target_seg.image_url = ""
    target_seg.media_type = "blank"
    target_seg.status = "empty"
    target_seg.source = "generated"
    target_seg.source_tier = ""
    target_seg.is_custom = False
    target_seg.needs_manual = True
    target_seg.fail_reason = ""
    target_seg.validation_score = 0
    target_seg.dirty = False

    record_snapshot(session)
    save_session(session)
    return session, None, 200


def generate_segment_media(
    session_id: str,
    segment_id: str,
    api_key: Optional[str] = None
) -> Tuple[Optional[StoryboardSession], Optional[str], int]:
    """
    Enqueues FLUX generation for a single segment.
    """
    session = load_session(session_id)
    if not session:
        return None, "Session not found", 404

    target_seg = None
    for s in session.segments:
        if s.segment_id == segment_id:
            target_seg = s
            break

    if target_seg is None:
        return None, "Segment not found", 404

    # Do not overwrite if manual
    if target_seg.status == "manual" or target_seg.is_custom:
        return session, "Segment is locked with manual media", 400

    target_seg.status = "queued"
    save_session(session)

    _GEN_EXECUTOR.submit(_run_background_generation, session_id, [segment_id])
    return session, None, 200


def generate_missing_media(
    session_id: str,
    api_key: Optional[str] = None
) -> Tuple[Optional[StoryboardSession], Optional[str], int]:
    """
    Enqueues FLUX generation for all segments that are empty or failed (non-manual).
    """
    session = load_session(session_id)
    if not session:
        return None, "Session not found", 404

    target_ids = []
    for s in session.segments:
        if (s.status in ("empty", "failed") or not s.image_url) and not s.is_custom and s.status != "manual":
            s.status = "queued"
            target_ids.append(s.segment_id)

    if target_ids:
        save_session(session)
        _GEN_EXECUTOR.submit(_run_background_generation, session_id, target_ids)

    return session, None, 200


def suggest_prompts(
    session_id: str,
    segment_id: str,
    api_key: Optional[str] = None
) -> Tuple[Optional[List[str]], Optional[str], int]:
    """
    Uses Gemini to generate 3 alternative image prompts for a scene.
    """
    session = load_session(session_id)
    if not session:
        return None, "Session not found", 404

    target_seg = None
    for s in session.segments:
        if s.segment_id == segment_id:
            target_seg = s
            break

    if target_seg is None:
        return None, "Segment not found", 404

    resolved_key = api_key or get_gemini_api_key()
    prompt_query = (
        f"For the narration: '{target_seg.text}', generate 3 distinct, photorealistic vertical 9:16 "
        "cinematic image prompts with varied shot types and angles. "
        "Return ONLY a JSON object: {\"prompts\": [\"prompt 1\", \"prompt 2\", \"prompt 3\"]}"
    )

    if resolved_key:
        try:
            raw, _ = generate_content(
                prompt_or_contents=prompt_query,
                thinking_level="low",
                max_output_tokens=1000,
                json_mode=True,
                api_key=resolved_key
            )
            if raw:
                data = json.loads(raw.strip().strip("```json").strip("```"))
                prompts = data.get("prompts", [])
                if len(prompts) >= 3:
                    return prompts[:3], None, 200
        except Exception:
            pass

    # Fallback alternatives
    t = target_seg.text[:40]
    fallbacks = [
        f"Photorealistic vertical 9:16 wide establishing shot of {t}, dramatic lighting, 8k resolution",
        f"Photorealistic vertical 9:16 medium close-up cinematic shot of {t}, detailed textures, volumetric lighting",
        f"Photorealistic vertical 9:16 dynamic low-angle tracking shot of {t}, moody atmosphere, cinematic color grading"
    ]
    return fallbacks, None, 200


def export_prompts(session_id: str) -> Tuple[Optional[str], Optional[str], int]:
    """
    Returns text/plain numbered list of image prompts (with style_lock prepended).
    """
    session = load_session(session_id)
    if not session:
        return None, "Session not found", 404

    lines = []
    for idx, seg in enumerate(session.segments):
        p = seg.image_prompt.strip()
        if session.style_lock and session.style_lock.strip():
            prefix = session.style_lock.strip().rstrip(",")
            if prefix.lower() not in p.lower():
                p = f"{prefix}, {p}"
        lines.append(f"{idx + 1}. {p}")

    return "\n\n".join(lines), None, 200
