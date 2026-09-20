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
from dataclasses import dataclass, field, asdict
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional, Tuple

from engine.beats import create_story_beats, clean_words
from engine.visual_director.story_analyzer import analyze_story
from engine.visual_director.continuity import build_continuity_bible, enforce_continuity_in_prompt
from engine.visual_director.planner import plan_visual_storyboard, semantic_fallback_plan
from engine.visual_director.generator import generate_and_validate_scene, single_visual_attempt
from engine.config import get_gemini_api_key

SESSIONS_DIR = os.path.abspath("outputs/segment_sessions")
os.makedirs(SESSIONS_DIR, exist_ok=True)


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
    media_type: str = "image"  # "image" | "video" | "blank"
    source: str = "generated"   # "generated" | "manual"
    source_tier: str = ""       # "flux" | "flux_failed" | "manual_upload"
    is_custom: bool = False
    validation_score: int = 85
    needs_manual: bool = False
    fail_reason: str = ""
    dirty: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Segment":
        valid_keys = {
            "segment_id", "text", "duration", "order_index", "image_prompt",
            "video_prompt", "visual_description", "shot_type", "camera_motion",
            "must_show", "must_not_show", "image_url", "image_path", "media_type",
            "source", "source_tier", "is_custom", "validation_score", "needs_manual",
            "fail_reason", "dirty"
        }
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)


@dataclass
class StoryboardSession:
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    mode: str = "auto"  # "auto" | "manual"
    script_text: str = ""
    total_duration: float = 0.0
    story_analysis: Dict[str, Any] = field(default_factory=dict)
    continuity_bible: Dict[str, Any] = field(default_factory=dict)
    segments: List[Segment] = field(default_factory=list)
    gemini_calls_used: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "mode": self.mode,
            "script_text": self.script_text,
            "total_duration": round(self.total_duration, 2),
            "story_analysis": self.story_analysis,
            "continuity_bible": self.continuity_bible,
            "segments": [s.to_dict() for s in self.segments],
            "gemini_calls_used": self.gemini_calls_used
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StoryboardSession":
        raw_segs = data.get("segments", [])
        segs = [Segment.from_dict(s) for s in raw_segs]
        return cls(
            session_id=data.get("session_id", uuid.uuid4().hex),
            mode=data.get("mode", "auto"),
            script_text=data.get("script_text", ""),
            total_duration=float(data.get("total_duration", 0.0)),
            story_analysis=data.get("story_analysis", {}),
            continuity_bible=data.get("continuity_bible", {}),
            segments=segs,
            gemini_calls_used=int(data.get("gemini_calls_used", 0))
        )


def save_session(session: StoryboardSession) -> str:
    """Persists StoryboardSession to disk as JSON."""
    path = os.path.join(SESSIONS_DIR, f"{session.session_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(session.to_dict(), f, indent=2)
    return path


def load_session(session_id: str) -> Optional[StoryboardSession]:
    """Loads StoryboardSession from disk."""
    path = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return StoryboardSession.from_dict(data)
    except Exception:
        return None


def create_session(
    script: str,
    mode: str = "manual",
    manual_delimiter: bool = False,
    api_key: Optional[str] = None
) -> StoryboardSession:
    """
    Creates a new StoryboardSession from a script.
    - Script is segmented into story beats (or on '|||' delimiter if present).
    - Segment division is 100% identical in both Auto and Manual modes.
    - Prompts, durations, and verbatim words are 100% identical in both modes.
    - If mode == "auto", generates FLUX visuals for each scene in parallel.
    - If mode == "manual", scenes start blank for user drop-in.
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

    segments: List[Segment] = []
    for idx, (b_text, b_dur) in enumerate(beats):
        p_sc = planned_scenes[idx] if idx < len(planned_scenes) else {}
        default_prompt = f"Photorealistic vertical 9:16 cinematic shot of {b_text[:40]}, 8k resolution, dramatic volumetric lighting, no text, no watermark"
        default_video_prompt = f"Vertical 9:16 video of {b_text[:40]}, slow cinematic motion, realistic physics"
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
            must_show=p_sc.get("must_show", [b_text[:20]]),
            must_not_show=p_sc.get("must_not_show", ["blurry", "watermark", "text overlay"]),
            image_url="",
            image_path="",
            media_type="blank",
            source="manual" if mode == "manual" else "generated",
            source_tier="",
            is_custom=False,
            validation_score=85,
            needs_manual=(mode == "manual"),
            dirty=False
        )
        segments.append(seg)

    # If mode == "auto", generate FLUX visuals for each scene in parallel
    if mode == "auto":
        output_dir = os.path.abspath("outputs/ai_previews")
        os.makedirs(output_dir, exist_ok=True)

        def _gen_worker(seg: Segment) -> Segment:
            sc_obj = {
                "scene_id": f"scene_{seg.order_index+1:02d}",
                "narration": seg.text,
                "duration": seg.duration,
                "order_index": seg.order_index,
                "image_prompt": seg.image_prompt,
                "video_prompt": seg.video_prompt,
                "visual_description": seg.visual_description,
                "shot_type": seg.shot_type,
                "camera_motion": seg.camera_motion,
                "must_show": seg.must_show,
                "must_not_show": seg.must_not_show,
                "search_query": " ".join(clean_words(seg.text)[:3])
            }
            res = generate_and_validate_scene(
                scene=sc_obj,
                output_dir=output_dir,
                continuity_bible=continuity_bible,
                api_key=api_key,
                generation_mode="flux",
                call_stats=call_stats
            )
            has_image = bool(res.get("image_path") and os.path.exists(res.get("image_path")))
            seg.image_url = res.get("image_url", "")
            seg.image_path = res.get("image_path", "")
            seg.media_type = "image" if has_image else "blank"
            seg.source = res.get("source", "generated")
            seg.source_tier = res.get("source_tier", "flux")
            seg.validation_score = res.get("validation_score", 0 if not has_image else 85)
            seg.needs_manual = not has_image
            seg.fail_reason = res.get("fail_reason", "")
            return seg

        with ThreadPoolExecutor(max_workers=2) as executor:
            segments = list(executor.map(_gen_worker, segments))

    session = StoryboardSession(
        session_id=uuid.uuid4().hex,
        mode=mode,
        script_text=clean_script,
        total_duration=round(total_duration, 2),
        story_analysis=story_analysis,
        continuity_bible=continuity_bible,
        segments=segments,
        gemini_calls_used=call_stats.get("gemini_calls", 0)
    )
    save_session(session)
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
        manual_delimiter=manual_delimiter,
        api_key=api_key
    )


def split_segment(
    session_id: str,
    segment_id: str,
    split_at_word_index: int
) -> Tuple[Optional[StoryboardSession], Optional[str], int]:
    """
    Splits a segment into two at split_at_word_index (word ratio).
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
        must_show=[text1[:20]],
        must_not_show=target_seg.must_not_show,
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
        must_show=[text2[:20]],
        must_not_show=target_seg.must_not_show,
        dirty=True
    )

    session.segments.pop(target_idx)
    session.segments.insert(target_idx, seg2)
    session.segments.insert(target_idx, seg1)

    for i, s in enumerate(session.segments):
        s.order_index = i

    session.script_text = " ".join(seg.text for seg in session.segments)
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
        must_show=[merged_text[:20]],
        must_not_show=first.must_not_show,
        image_url="",
        image_path="",
        source="generated",
        is_custom=False,
        validation_score=85,
        dirty=True
    )

    session.segments.pop(pop_idx2)
    session.segments.pop(pop_idx1)
    session.segments.insert(insert_at, merged_seg)

    for i, s in enumerate(session.segments):
        s.order_index = i

    session.script_text = " ".join(seg.text for seg in session.segments)
    save_session(session)
    return session, None, 200


def add_segment(
    session_id: str,
    after_segment_id: str,
    text: str
) -> Tuple[Optional[StoryboardSession], Optional[str], int]:
    """
    Inserts a new segment after after_segment_id.
    Estimates duration from word count and EXTENDS total_duration.
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
        must_show=[clean_text[:20]],
        must_not_show=["blurry", "watermark"],
        dirty=True
    )

    session.segments.insert(target_idx + 1, new_seg)
    session.total_duration = round(session.total_duration + est_dur, 2)

    for i, s in enumerate(session.segments):
        s.order_index = i

    session.script_text = " ".join(seg.text for seg in session.segments)
    save_session(session)
    return session, None, 200


def delete_segment(
    session_id: str,
    segment_id: str
) -> Tuple[Optional[StoryboardSession], Optional[str], int]:
    """
    Removes a segment and SHRINKS total_duration by its duration.
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
    save_session(session)
    return session, None, 200


def edit_segment_text(
    session_id: str,
    segment_id: str,
    new_text: str
) -> Tuple[Optional[StoryboardSession], Optional[str], int]:
    """
    Edits segment text with word-level diffing:
    - If words identical, update text only without dirty flag or duration change.
    - If words changed, recompute duration proportional to word count (clamped to 1.0s),
      adjust total_duration, set dirty=True, flip is_custom to False if True.
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
    save_session(session)
    return session, None, 200


def replan_dirty_segments(
    session_id: str,
    api_key: Optional[str] = None
) -> Tuple[Optional[StoryboardSession], Optional[str], int]:
    """
    Re-runs prompt generation and visual validation for dirty && !is_custom segments only.
    Reuses existing story_analysis and continuity_bible.
    Increments gemini_calls_used and clears dirty on success.
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
                output_dir="outputs/ai_previews",
                continuity_bible=session.continuity_bible,
                api_key=resolved_key,
                call_stats=call_stats
            )

            has_img = bool(res.get("image_path") and os.path.exists(res.get("image_path")))
            seg.image_url = res.get("image_url", "")
            seg.image_path = res.get("image_path", "")
            seg.media_type = "image" if has_img else "blank"
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
    file_path: str,
    media_type: str = "image"
) -> Tuple[Optional[StoryboardSession], Optional[str], int]:
    """
    Attaches a user-provided image or video to a specific segment.
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

    target_seg.image_path = file_path
    filename = os.path.basename(file_path)
    target_seg.image_url = f"/outputs/ai_previews/{filename}"
    target_seg.media_type = media_type
    target_seg.source = "manual"
    target_seg.source_tier = "manual_upload"
    target_seg.is_custom = True
    target_seg.needs_manual = False
    target_seg.fail_reason = ""
    target_seg.validation_score = 100
    target_seg.dirty = False

    save_session(session)
    return session, None, 200


def clear_segment_media(
    session_id: str,
    segment_id: str
) -> Tuple[Optional[StoryboardSession], Optional[str], int]:
    """
    Clears attached media for a specific segment.
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
    target_seg.source = "manual"
    target_seg.source_tier = ""
    target_seg.is_custom = False
    target_seg.needs_manual = True
    target_seg.fail_reason = ""
    target_seg.validation_score = 0
    target_seg.dirty = False

    save_session(session)
    return session, None, 200


def generate_segment_media(
    session_id: str,
    segment_id: str,
    api_key: Optional[str] = None
) -> Tuple[Optional[StoryboardSession], Optional[str], int]:
    """
    Generates media for a single segment using FLUX.
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

    output_dir = os.path.abspath("outputs/ai_previews")
    os.makedirs(output_dir, exist_ok=True)
    call_stats = {"gemini_calls": 0}

    sc_dict = {
        "scene_id": target_seg.segment_id,
        "narration": target_seg.text,
        "visual_description": target_seg.visual_description,
        "image_prompt": target_seg.image_prompt,
        "search_query": " ".join(clean_words(target_seg.text)[:3]),
        "must_show": target_seg.must_show or [target_seg.text[:20]],
        "must_not_show": target_seg.must_not_show or ["blurry", "watermark"]
    }

    res = generate_and_validate_scene(
        scene=sc_dict,
        output_dir=output_dir,
        continuity_bible=session.continuity_bible,
        api_key=api_key,
        call_stats=call_stats
    )

    has_img = bool(res.get("image_path") and os.path.exists(res.get("image_path")))
    target_seg.image_url = res.get("image_url", "")
    target_seg.image_path = res.get("image_path", "")
    target_seg.media_type = "image" if has_img else "blank"
    target_seg.validation_score = res.get("validation_score", 85)
    target_seg.source = res.get("source", "generated")
    target_seg.source_tier = res.get("source_tier", "flux")
    target_seg.needs_manual = res.get("needs_manual", not has_img)
    target_seg.fail_reason = res.get("fail_reason", "")
    target_seg.dirty = False

    session.gemini_calls_used += call_stats.get("gemini_calls", 0)
    save_session(session)
    return session, None, 200


def generate_missing_media(
    session_id: str,
    api_key: Optional[str] = None
) -> Tuple[Optional[StoryboardSession], Optional[str], int]:
    """
    Generates media for all segments where media is missing or needs_manual=True.
    """
    session = load_session(session_id)
    if not session:
        return None, "Session not found", 404

    missing_segs = [s for s in session.segments if not s.image_path or s.needs_manual]
    if not missing_segs:
        return session, None, 200

    output_dir = os.path.abspath("outputs/ai_previews")
    os.makedirs(output_dir, exist_ok=True)
    call_stats = {"gemini_calls": 0}

    def _worker(seg):
        sc_dict = {
            "scene_id": seg.segment_id,
            "narration": seg.text,
            "visual_description": seg.visual_description,
            "image_prompt": seg.image_prompt,
            "search_query": " ".join(clean_words(seg.text)[:3]),
            "must_show": seg.must_show or [seg.text[:20]],
            "must_not_show": seg.must_not_show or ["blurry", "watermark"]
        }
        res = generate_and_validate_scene(
            scene=sc_dict,
            output_dir=output_dir,
            continuity_bible=session.continuity_bible,
            api_key=api_key,
            call_stats=call_stats
        )
        return seg, res

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(_worker, missing_segs))

    for seg, res in results:
        has_img = bool(res.get("image_path") and os.path.exists(res.get("image_path")))
        seg.image_url = res.get("image_url", "")
        seg.image_path = res.get("image_path", "")
        seg.media_type = "image" if has_img else "blank"
        seg.validation_score = res.get("validation_score", 85)
        seg.source = res.get("source", "generated")
        seg.source_tier = res.get("source_tier", "flux")
        seg.needs_manual = res.get("needs_manual", not has_img)
        seg.fail_reason = res.get("fail_reason", "")
        seg.dirty = False

    session.gemini_calls_used += call_stats.get("gemini_calls", 0)
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

    save_session(session)
    return session, None, 200
