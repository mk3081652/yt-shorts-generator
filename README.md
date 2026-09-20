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

---

## 🎬 Step 2: Visual Storyboard Modes

Step 2 provides a fast scene editor with two dedicated workflows:

1. **⚡ Auto Mode**:
   - The script is automatically split into visual beats.
   - Gemini analyzes the story and writes targeted 9:16 image prompts.
   - Cloudflare FLUX.1-schnell generates vertical visual scenes.
   - You can replace or re-roll any scene image individually or drop your own media.

2. **✂️ Manual Segment Mode**:
   - The script is segmented scene-by-scene with both an **Image Prompt** and a **Video Prompt** per scene.
   - The user edits narration and prompts, copies prompts for external AI generation tools, and drops in generated images or videos (`.mp4`, `.mov`, `.webp`, `.jpg`, `.png`).
   - Nothing is auto-generated in this mode, giving you complete creative control.

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
