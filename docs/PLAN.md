# Refactoring Plan: Director Editor (`yt-shorts-generator`)

## 1. Objective
Refactor `yt-shorts-generator` into a streamlined, clean, production-ready application that turns a script into a vertical (9:16) YouTube Short whose visuals match the narration, operating in two modes (AI and Manual) within **one unified editor**.

---

## 2. Target Architecture

```
app.py                 FastAPI routes only (thin layer)
engine/
  config.py            Single .env loader, typed getters read at call time
  llm.py               Gemini 3.8 Flash client (text-in/JSON-out, thinkingConfig, header-based auth)
  beats.py             STOP_WORDS, clean_words, create_story_beats (verbatim word-preserving)
  director.py          Script -> scene plan (one call) + deterministic prompt compiler + basic mode
  flux.py              The ONLY image generator (Cloudflare Workers AI FLUX-1-schnell)
  project.py           Project/Scene model, edit ops, persistence, undo/redo, background pool (2 workers)
  timeline.py          Align scenes to TTS word timestamps
  render.py            Per-scene clips (Ken Burns, video crop, blank) + concat + mux
  tts.py               (UNTOUCHED) Edge TTS voice actor
  subtitles.py         (UNTOUCHED) ASS subtitle presets
  audio.py             (UNTOUCHED) BGM mixing & volume
  audio_synth.py       (UNTOUCHED) Sound effects
  metadata.py          (UNTOUCHED) YouTube title, description, tags
static/js/
  api.js               REST API fetch client
  state.js             Reactive project state & event bus
  card.js              Single scene card renderer (XSS-safe textContent)
  editor.js            Storyboard container, split-modal, toolbar, shortcuts
  main.js              App bootstrap & step coordination (ES modules)
static/css/style.css   Pruned stylesheet (dead CSS removed)
scripts/live_check.py  Verification script for Gemini and Flux live calls
tests/                 Unit & regression test suite (mocked, no network)
```

### Delete List
- `engine/smart_visuals.py`
- `engine/gemini_visuals.py`
- `engine/backgrounds.py`
- `engine/visual_director/` (`story_analyzer.py`, `continuity.py`, `planner.py`, `validator.py`, `generator.py`, `prompts.py`, `segment_session.py`)
- Root `test_visual_director.py`
- 4 pacing presets
- Custom-video background upload & batch image upload (`/api/upload_background`, `/api/upload_batch_images`, `/api/prepare_scenes`, `/api/refresh_scene_image`)
- `bg_choice` references
- Google Flow UI/references, Imagen, Pollinations, dark-canvas fake images
- Keyword ontology & heuristic text validator
- "API calls" counter in UI
- Duplicate .env loaders and duplicate stdout/IPv4 hacks

---

## 3. Implementation Phases & Gate Criteria

### Phase 1: Foundation
- **Files**: `engine/config.py`, `engine/llm.py`, `engine/flux.py`, `app.py` (`/healthz`, json persistence fix), `requirements.txt` (add `Pillow`), `.env.example`, `scripts/live_check.py`.
- **Scope**:
  - `config.py`: typed getters read at call time.
  - `llm.py`: Gemini client with header-based auth (`x-goog-api-key`), `thinkingConfig` ("low", never "minimal"), model fallbacks, `_post()` helper for testing.
  - `flux.py`: Cloudflare Workers AI FLUX with retry, cooldown timestamp on 429, Pillow center-cover 9:16 crop, no secondary fallback.
  - Verify no API keys committed to git.
- **Gate**: `pytest tests`, `python -c "import app"`, server boots, `GET /` and `GET /healthz` return 200.

### Phase 2: The Director
- **Files**: `engine/director.py`, `engine/beats.py`.
- **Scope**:
  - Full script + numbered beats sent to Gemini in one structured call using the generic director system prompt.
  - Deterministic Prompt Compiler: `{style_lock}. {style}. {shot} shot of {subject} {action}, {setting}. {entities}. {lighting}. Vertical 9:16, subject centered, no text, no watermark.` (under ~60 words).
  - Basic Mode fallback: `"{style default} {shot} shot of {narration line}"`.
  - Vision QA (optional when `VISION_QA=1`).
  - `hold_previous` flag support for abstract/continuous lines.
- **Gate**: `pytest tests`, `python -c "import app"`, server boots, `GET /` and `GET /healthz` return 200.

### Phase 3: Project Model, API & Security
- **Files**: `engine/project.py`, `app.py`.
- **Scope**:
  - `Project` and `Scene` data models with 20-step undo/redo and thread pool (max 2 workers).
  - Clean REST routes under `/api/projects`: create, get, edit_text, edit_prompt, edit_meta, split, merge, move_boundary, add, delete, upload_media (with magic byte validation), upload_bulk (.zip / files), clear_media, generate, generate_missing, cancel, suggest_prompts, undo, redo, export_prompts.
  - Security hardening: project ID regex `^[a-f0-9]{32}$`, `os.path.basename` on uploads, body size caps, CORS allowlist, startup cleanup (>7 days).
- **Gate**: `pytest tests`, `python -c "import app"`, server boots, `GET /` and `GET /healthz` return 200.

### Phase 4: Voice-First Timeline
- **Files**: `engine/timeline.py`, `app.py`.
- **Scope**:
  - `POST /api/projects/{id}/prepare_voice`: Run Edge TTS once, cache audio and word boundaries.
  - Shared `align(scenes, words, total)` aligning scenes to exact spoken word boundaries.
- **Gate**: `pytest tests`, `python -c "import app"`, server boots, `GET /` and `GET /healthz` return 200.

### Phase 5: Render Engine
- **Files**: `engine/render.py`, `app.py`.
- **Scope**:
  - Replace compositor / gemini_visuals / smart_visuals with lightweight, sequential clip rendering:
    - Images: Ken Burns effect based on `camera_motion`.
    - Videos: 9:16 scale/crop/trim/loop.
    - Blanks: 1080x1920 black clip.
    - Concat & mux with subtitles (ASS) and BGM (auto-ducked).
  - Enforce <512MB RAM constraint during render.
- **Gate**: `pytest tests`, `python -c "import app"`, server boots, `GET /` and `GET /healthz` return 200.

### Phase 6: Modern Modular Editor UI
- **Files**: `templates/index.html`, `static/js/api.js`, `static/js/state.js`, `static/js/card.js`, `static/js/editor.js`, `static/js/main.js`, `static/css/style.css`.
- **Scope**:
  - Step 2: Segmented switch (`⚡ Auto | ✂️ Manual Segment`) controlling one unified editor.
  - Modular vanilla ES modules (no bundler).
  - Safe DOM generation via `textContent` and escaped attributes.
  - Fast editing: interactive word split, seam shift (`◀`/`▶`/`🔗 Merge`), clipboard paste, drag-and-drop, keyboard shortcuts (`Ctrl+Z`, `Ctrl+Y`).
  - Prune dead CSS and remove obsolete elements.
- **Gate**: `node -c` on all JS modules, `pytest tests`, server boots, `GET /` and `GET /healthz` return 200.

### Phase 7: Comprehensive Test Suite
- **Files**: `tests/`.
- **Scope**:
  - Complete mock-based test suite covering LLM fallback, prompt compiler golden tests, director retries, Flux failures/cooldowns, project persistence/concurrency, zip uploads, timeline alignment, and smoke render.
  - Delete obsolete test files.
- **Gate**: 100% tests passing in `pytest tests`.

### Phase 8: Documentation, Cleanup & Deployment
- **Files**: `README.md`, `Dockerfile`, `start.bat`.
- **Scope**:
  - Update documentation to reflect the streamlined two-mode single-editor architecture.
  - Ensure Docker build and Windows `start.bat` work reliably.
  - Final grep verification for forbidden strings.
- **Gate**: Final verification checklist and live test instructions.

---

## 4. Risks & Mitigations
1. **Regression of Untouched Modules**:
   - *Risk*: Modifying shared imports could inadvertently break `tts.py`, `audio.py`, `subtitles.py`, or `metadata.py`.
   - *Mitigation*: Strictly leave these files untouched and verify existing tests continue to pass.
2. **Memory Leaks during Render**:
   - *Risk*: MoviePy / ffmpeg can spike RAM above 512MB if full resolution clips are held concurrently.
   - *Mitigation*: Render clips sequentially to disk, downscale image inputs to max 1080x1920 before applying Ken Burns, and run ffmpeg concat demuxer.
3. **API Key Security**:
   - *Risk*: Accidentally committing secrets.
   - *Mitigation*: Enforce `.env` in `.gitignore`, use `.env.example` with empty placeholders, and run grep verification.
