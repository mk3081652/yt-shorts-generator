# ⚡ Viral YouTube Shorts Creator Studio (100% Free)

A self-hosted, high-velocity desktop web application designed to turn any script into complete, professional, eye-catching, viral YouTube Shorts to monetize your YouTube channel fast.

---

## 🌟 Key Features

1. **100% Free & Unlimited AI Voiceover**:
   - Powered by Edge-TTS (Microsoft Neural Voice Models: Christopher, Guy, Jenny, Ava, Andrew, Prabhat, etc.).
   - Zero API keys, zero subscriptions, zero usage caps.
   - Millisecond-accurate word boundary timestamps for synchronized subtitle animation.

2. **Viral Subtitle Engine (MrBeast & Alex Hormozi Styles)**:
   - Rapid 1-2 word animated popping captions.
   - Dynamic colors: MrBeast Yellow (`#FFE600`), Hormozi Neon Green (`#00FF66`), Cyberpunk Cyan (`#00F2FE`), and Clean Aesthetic White.
   - Thick black outlines & drop shadows rendered via hardware-accelerated ASS subtitles in FFmpeg.

3. **High-Retention Backgrounds & B-Roll**:
   - Built-in dynamic procedural motion loops (Cyberpunk Tunnel, Cosmic Galaxy, Luxury Gold, Dark Mystery, Matrix Code).
   - Drag-and-drop custom MP4/MOV video upload.
   - Ready for viral gameplay loops (Minecraft, GTA stunts, Satisfying sand).
   - Optional free Pexels/Pixabay API stock video keyword search.

4. **Royalty-Free Background Music (BGM) with Auto-Ducking**:
   - Curated tracks for every mood: Epic Cinematic, Phonk Energetic, Mystery Suspense, and Lo-Fi Chill.
   - Auto audio ducking: Music volume ducks smoothly behind voiceover so speech remains crystal clear.

5. **YouTube Monetization & SEO Kit**:
   - High-CTR Title generator with emojis and viral hooks.
   - Complete YouTube description with hashtags (`#shorts`, `#viral`, `#facts`).
   - One-click copy for Shorts feed tags.

6. **Instant Web Studio & In-Browser Player**:
   - Real-time voice audition before rendering.
   - 9:16 vertical smartphone preview player.
   - One-click download of 1080x1920 HD MP4.

---

## 🚀 Quick Start (Windows)

Simply double click `start.bat` or run:

```bash
cd C:\Users\mk308\.gemini\antigravity\scratch\yt-shorts-generator
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Then open your browser to **[http://localhost:8000](http://localhost:8000)**.

### 🔑 Environment Configuration (`.env`)

Copy `.env.example` to `.env` or set environment variables:

```bash
cp .env.example .env
```

Key environment variables:
- `GEMINI_API_KEY`: Get a free key from **[Google AI Studio](https://aistudio.google.com/apikey)**. Powers the Visual Director AI for intelligent scene-by-scene beat splitting and cinematic 9:16 prompt generation.
- `CLOUDFLARE_ACCOUNT_ID` & `CLOUDFLARE_API_TOKEN`: Optional. Powers FLUX.1-schnell image generation in ⚡ Auto mode via Cloudflare Workers AI.

> [!NOTE]
> **Graceful Fallbacks**:
> - Without `GEMINI_API_KEY`, the app runs in a deterministic semantic fallback mode, maintaining continuity anchors and shot variety.
> - Without Cloudflare FLUX credentials, scenes default to blank canvas clips with Ken Burns subtle motion, allowing quick manual image/video drops.

### 🔍 Live API & Model Verification

Verify your Gemini and Cloudflare FLUX connections with one command:

```bash
python scripts/live_check.py
```

---

## 🎬 Step 2: Fast Scene Editor (Auto & Manual Segment)

Step 2 provides a unified, ultra-responsive scene editor with two dedicated workflows:

1. **⚡ Auto Mode**:
   - The script is split scene-by-scene into visual story beats.
   - Gemini writes exact, targeted 9:16 visual prompts per scene with character/location continuity.
   - Cloudflare Workers AI FLUX.1-schnell generates high-resolution vertical visuals.
   - Individual scene re-rolling, prompt suggestions (3 variations via Gemini), and manual overrides.

2. **✂️ Manual Segment Mode**:
   - The script is segmented scene-by-scene with dual prompts: an **Image Prompt** and a **Video Prompt** per scene.
   - The user edits narration and prompts, copies prompts with one click for external tools (Midjourney, Runway, Kling, Pika), and drops in generated media (`.mp4`, `.mov`, `.webp`, `.jpg`, `.png`).
   - Nothing is auto-generated in this mode, giving you complete creative control.

### 🛠️ Editor Power Tools:
- **🎨 Style-Lock**: Define an aesthetic style (e.g. `cinematic film grain, 35mm photograph, moody lighting`) that is automatically prepended to every prompt.
- **↩️ 20-Step Undo/Redo**: Full undo/redo history via toolbar buttons or `Ctrl+Z` / `Ctrl+Y` (`Cmd+Z` / `Cmd+Shift+Z`).
- **✂️ Interactive Word-Split**: Click any word chip in a scene sentence to split the scene at that exact word boundary.
- **◀ / ▶ Seam Shifting**: Shift single words left or right across scene boundaries with instant timeline recalculation.
- **📦 Bulk Drop Zone**: Drag-and-drop multiple images/videos or a `.zip` archive to automatically assign media to scenes sequentially.
- **📋 Clipboard Paste**: Focus any scene card and press `Ctrl+V` (`Cmd+V`) to paste an image or video directly from your clipboard.
- **🎙️ Voice-First Timeline**: When moving to Step 3, TTS audio and exact word boundary timestamps are generated and cached, aligning scene durations to exact speech timing.
- **🚀 Sequential Low-RAM Rendering**: Scene clips (image Ken Burns, video loops, black canvas) are rendered sequentially to maintain a strict < 512MB RAM ceiling.

---

## 💡 How to Make Viral Shorts to Monetize Fast

1. **Load a Template or Paste a Script**:
   - Keep scripts between **60 and 110 words** (~20 to 45 seconds). YouTube's algorithm rewards Shorts with >100% average view duration (loops).
2. **Hook the Viewer in the First 3 Seconds**:
   - Use the **🪝 Add Viral Hook** dropdown to start with high curiosity ("Stop scrolling right now!", "Nobody talks about this...").
3. **Select High-Energy Voice & Subtitles**:
   - Choose **Christopher (US)** or **Guy (US)** with `+10%` or `+15%` pacing.
   - Select **MrBeast** or **Hormozi** subtitles.
4. **Hit Generate**:
   - Within 15-25 seconds, your 1080x1920 MP4 is ready.
5. **Upload to YouTube**:
   - Copy the generated Title, Description & Tags with one click and paste directly into YouTube Studio!
