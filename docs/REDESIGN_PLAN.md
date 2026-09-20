# REDESIGN PLAN — yt-shorts-generator (Fast Scene Editor & Visual Storyboard)

## Executive Summary
This document outlines the end-to-end implementation plan for upgrading `yt-shorts-generator` to the unified Fast Scene Editor on branch `redesign/scene-editor`. Step 2 becomes a single, high-performance editor with two entry points (**⚡ Auto** and **✂️ Manual Segment**). The codebase is cleaned of legacy Wikimedia, Google Flow, and duplicate engines.

---

## Non-Regression & Quality Gates
Every phase will be committed individually (`One commit per phase`). After each phase:
1. `pytest tests` passes.
2. `python -c "import app"` succeeds.
3. Server boots cleanly (`python -m uvicorn app:app --port 8000`).
4. `GET /` and `GET /api/config` return HTTP 200.

---

## Phase Breakdown

### Phase 1: Foundation (Config, Gemini 3.8 Flash, FLUX, Planner Fallback)
- **Goals**:
  - Centralize config in `engine/config.py`.
  - Standardize Gemini client in `engine/gemini_client.py` using `gemini-3.8-flash` (fallbacks: `gemini-3.7-flash,gemini-flash-latest`), header authentication (`x-goog-api-key`), `thinkingLevel` ("low" / "medium", never "minimal"), generous token limits, and backoff.
  - Consolidate FLUX generation in `engine/flux.py` using Cloudflare Workers AI `@cf/black-forest-labs/flux-1-schnell`. Delete legacy Imagen, Pollinations, and dark-canvas generators. Center-cover-crop to 9:16 using Pillow. Add 45s timeout, 15m cooldown on rate limits, and explicit reason returns.
  - Update `requirements.txt` to include `Pillow`.
  - Fix planner schema (`video_prompt`, `image_prompt`) and semantic fallback when no ontology matches.
  - Fix missing `import json` in `app.py`.
  - Add `.env.example` and `scripts/live_check.py`.
- **Files Touched**:
  - `engine/config.py`
  - `engine/gemini_client.py`
  - `engine/flux.py`
  - `engine/visual_director/planner.py`
  - `engine/visual_director/story_analyzer.py`
  - `engine/visual_director/validator.py`
  - `app.py`
  - `requirements.txt`
  - `.env.example`
  - `scripts/live_check.py`
- **Risks**: Gemini 400 error if thinkingConfig is rejected (handled by retrying without it). Cloudflare 429 handled by cooldown and clear status return.

### Phase 2: Session Model & API (Single Source of Truth)
- **Goals**:
  - Enhance `StoryboardSession` and `Segment` in `engine/visual_director/segment_session.py`.
  - Add segment fields: `status` (`empty | queued | generating | ready | failed | manual`), `video_prompt`, `media_type` (`image | video | ""`), `needs_manual`, `fail_reason`, `source_tier`, `motion`, `qa_score`, `qa_note`.
  - Add session fields: `start_mode`, `style_lock`, `timeline`, and 20-step undo/redo history.
  - Implement endpoints: `create`, `get`, `edit_text`, `edit_prompt`, `edit_meta`, `split`, `merge`, `move_boundary`, `add`, `delete`, `upload_media` (magic byte validation with Pillow/ffprobe), `upload_bulk` (file list or .zip with zip-slip/zip-bomb protection), `clear_media`, `generate`, `generate_missing`, `cancel`, `suggest_prompts`, `undo`, `redo`, `export_prompts`.
  - Synchronize `session.script_text = " ".join(seg.text)` after all text-affecting mutations.
  - Security hardening: UUID4 / 32-hex validation for `session_id`, `os.path.basename` sanitation, 7-day session cleanup on boot.
  - Remove deprecated routes: `/api/prepare_scenes`, `/api/refresh_scene_image`, `/api/upload_batch_images`, `/api/upload_background`.
- **Files Touched**:
  - `engine/visual_director/segment_session.py`
  - `app.py`
- **Risks**: File upload validation breaking valid uploads (mitigated by supporting webm, mp4, mov, jpg, png, webp).

### Phase 3: The Editor UI (Step 2 Redesign)
- **Goals**:
  - Build single responsive scene editor UI in `templates/index.html` and `static/js/app.js`.
  - Add segmented mode switch (`⚡ Auto` vs `✂️ Manual Segment`).
  - Toolbar with scene count, blank count, style-lock input, "Generate missing with Flux", "Copy all prompts", undo/redo, bulk-drop zone, and blank scenes warning banner.
  - Rewritten scene card component with XSS protection (`textContent` / proper escaping):
    - Media slot with thumbnail, video preview, or dark placeholder with status chip.
    - Editable narration textarea (blur saves).
    - [Image | Video] prompt tabs with copy button and 3-alternatives suggestion.
    - Motion dropdown (`push in`, `pull out`, `pan right`, `pan left`, `tilt up`, `static`).
    - Gemini QA chip when score < 80.
    - Actions: Replace, Flux / Retry Flux, Clear, Add, Delete.
  - Interactive click-to-split narration into word chips; seam controls with Merge and boundary shifts (`◀` / `▶`).
  - Fast manual replacement: drag-and-drop onto cards, clipboard paste (Ctrl+V) on focused card, multi-file drop on toolbar.
  - Synchronize Step 1 script with Step 2 edits. Prompt when rendering with blank scenes.
  - Remove all obsolete CSS and HTML for Google Flow and Cut Pacing Card.
- **Files Touched**:
  - `templates/index.html`
  - `static/js/app.js`
  - `static/css/style.css`
- **Risks**: UI regressions on small screen viewports (handled with responsive CSS).

### Phase 4: Voice-First Timeline
- **Goals**:
  - Implement `POST /api/segments/{id}/prepare_voice` using TTS audio and word boundary caching.
  - Implement `align_scenes(segments, words, total)` for exact alignment of scene boundaries with audio.
  - Display estimated times (`~2.4s`) until voice prepared, then exact times.
  - Invalidate cached timeline hash when narration is edited.
- **Files Touched**:
  - `engine/visual_director/segment_session.py`
  - `engine/scene_director.py`
  - `app.py`
  - `static/js/app.js`
- **Risks**: Mismatched TTS word count vs script word count (handled with proportional interpolation in `align_scenes`).

### Phase 5: Sequential Low-RAM Rendering & Compositor
- **Goals**:
  - Update `engine/scene_director.py` to render clips sequentially:
    - Image: Ken Burns effect via `engine/motion.py` according to scene motion choice, or `make_static_clip`.
    - Video: `make_video_scene_clip` (scale/crop to 1080x1920, trim or loop).
    - Blank: `make_blank_clip` (black 1080x1920 via ffmpeg lavfi).
  - Update `engine/compositor.py` to concatenate clips and mux with audio and subtitles.
  - Ensure peak RAM usage stays < 512MB.
  - Remove obsolete `bg_choice` and `file_` branches.
- **Files Touched**:
  - `engine/scene_director.py`
  - `engine/motion.py`
  - `engine/compositor.py`
  - `app.py`
- **Risks**: FFmpeg command failures on edge-case video formats (handled with robust transcoding parameters).

### Phase 6: Automated Test Suite & Dead Code Grep
- **Goals**:
  - Clean up dead code: delete `engine/smart_visuals.py`, `engine/gemini_visuals.py`, `engine/backgrounds.py`.
  - Verify zero occurrences of forbidden strings: `Google Flow`, `Segment Studio`, `bg_choice`, `smart_`, `Imagen`, `Pollinations`, `create_visual_beats`.
  - Comprehensive unit test suite with mocked network calls:
    - Gemini client request structure, thinkingLevel, fallback.
    - Flux failure states, cooldown, center-crop, prompt constraints.
    - Upload media magic bytes, path traversal rejection, bulk upload mapping.
    - Alignment logic for exact and mismatched word tokens.
    - FFmpeg smoke test producing a valid 1080x1920 mp4.
- **Files Touched**:
  - `tests/*`
- **Risks**: Stale test imports referencing deleted modules (remove or rewrite them).

### Phase 7: Documentation & Deployment
- **Goals**:
  - Update `README.md` with new features, architecture, and `scripts/live_check.py` usage.
  - Update `Dockerfile` to adjust directories and ensure it builds and runs smoothly.
  - Final verification report.
- **Files Touched**:
  - `README.md`
  - `Dockerfile`
  - `scripts/live_check.py`
