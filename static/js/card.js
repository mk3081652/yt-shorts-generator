/**
 * static/js/card.js - Safe DOM Scene Card Component
 */

import { api } from "./api.js";
import { state } from "./state.js";

const MOTIONS = [
    { value: "push in", label: "Center Push (Zoom In)" },
    { value: "pull out", label: "Reveal Pull (Zoom Out)" },
    { value: "pan right", label: "Pan Right" },
    { value: "pan left", label: "Pan Left" },
    { value: "tilt up", label: "Tilt Up" },
    { value: "static", label: "Static (No Motion)" }
];

export function createSceneCard(scene, index, totalScenes, callbacks = {}) {
    const card = document.createElement("div");
    card.className = "scene-card";
    card.dataset.sceneId = scene.id;
    card.dataset.index = index;

    const isManual = (scene.status === "manual" || scene.source_tier === "manual");
    if (isManual) card.classList.add("scene-manual");
    if (scene.status === "failed") card.classList.add("scene-failed");

    // 1. Header Row
    const header = document.createElement("div");
    header.className = "scene-header";

    const titleGroup = document.createElement("div");
    titleGroup.className = "scene-title-group";

    const title = document.createElement("h4");
    title.textContent = `Scene #${index + 1}`;

    const durBadge = document.createElement("span");
    durBadge.className = "scene-dur-badge";
    durBadge.textContent = `${scene.duration || 3.0}s`;

    titleGroup.appendChild(title);
    titleGroup.appendChild(durBadge);

    const statusGroup = document.createElement("div");
    statusGroup.className = "scene-status-group";

    const statusBadge = document.createElement("span");
    statusBadge.className = `status-pill status-${scene.status || "empty"}`;
    if (isManual) {
        statusBadge.textContent = "🔒 Manual (Locked)";
    } else if (scene.status === "generating") {
        statusBadge.textContent = "⚡ Generating...";
    } else if (scene.status === "queued") {
        statusBadge.textContent = "⏳ Queued";
    } else if (scene.status === "ready") {
        if (scene.source_tier === "pexels" || scene.media_type === "video") {
            statusBadge.textContent = "🎬 Video (Pexels)";
            statusBadge.style.background = "rgba(0, 230, 255, 0.15)";
            statusBadge.style.color = "#00e6ff";
            statusBadge.style.borderColor = "rgba(0, 230, 255, 0.4)";
        } else {
            statusBadge.textContent = "✅ Ready";
        }
    } else if (scene.status === "failed") {
        const isQuota = scene.fail_reason === "flux_quota_exhausted";
        const isRate = scene.fail_reason === "flux_rate_limited";
        const isNotCfg = scene.fail_reason === "flux_not_configured";
        if (isQuota) {
            statusBadge.textContent = "⚠️ Daily Quota";
            statusBadge.title = "Cloudflare free daily 10,000 neurons quota exhausted. Upgrade to Workers Paid or drop media manually.";
        } else if (isRate) {
            statusBadge.textContent = "⚠️ Rate Limit";
            statusBadge.title = "Cloudflare rate limit cooldown in progress. Wait or drop media manually.";
        } else if (isNotCfg) {
            statusBadge.textContent = "⚠️ No API Key";
            statusBadge.title = "Cloudflare credentials not configured in .env.";
        } else {
            statusBadge.textContent = "❌ Failed";
            statusBadge.title = scene.fail_reason || "FLUX generation failed";
        }
    } else {
        statusBadge.textContent = "⚪ Blank";
    }
    statusGroup.appendChild(statusBadge);

    header.appendChild(titleGroup);
    header.appendChild(statusGroup);
    card.appendChild(header);

    // 2. Body Grid: Visual Media Preview (Left) + Text & Prompts (Right)
    const body = document.createElement("div");
    body.className = "scene-body";

    // Media Preview Box
    const mediaBox = document.createElement("div");
    mediaBox.className = "scene-media-box";
    mediaBox.title = "Click to upload media or drop an image/video file here";

    if (scene.media_url || scene.image_url) {
        const url = scene.media_url || scene.image_url;
        if (scene.media_type === "video" || url.endsWith(".mp4") || url.endsWith(".webm")) {
            const video = document.createElement("video");
            video.src = url;
            video.autoplay = true;
            video.loop = true;
            video.muted = true;
            video.playsInline = true;
            video.className = "scene-preview-media";
            mediaBox.appendChild(video);
        } else {
            const img = document.createElement("img");
            img.src = url;
            img.alt = `Scene ${index + 1} Visual`;
            img.className = "scene-preview-media";
            mediaBox.appendChild(img);
        }

        // Media Overlay Actions (Clear, Replace)
        const overlay = document.createElement("div");
        overlay.className = "media-overlay-actions";

        const replaceBtn = document.createElement("button");
        replaceBtn.type = "button";
        replaceBtn.className = "btn-icon-overlay";
        replaceBtn.title = "Replace Media";
        replaceBtn.textContent = "📁";
        replaceBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            fileInput.click();
        });

        const clearBtn = document.createElement("button");
        clearBtn.type = "button";
        clearBtn.className = "btn-icon-overlay btn-danger";
        clearBtn.title = "Clear Media";
        clearBtn.textContent = "✕";
        clearBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            if (callbacks.onClearMedia) callbacks.onClearMedia(scene.id);
        });

        overlay.appendChild(replaceBtn);
        overlay.appendChild(clearBtn);
        mediaBox.appendChild(overlay);
    } else {
        // Blank placeholder
        const placeholder = document.createElement("div");
        placeholder.className = "media-placeholder";

        const pIcon = document.createElement("span");
        pIcon.className = "placeholder-icon";
        pIcon.textContent = scene.status === "generating" ? "⏳" : (scene.status === "failed" ? "⚠️" : "🖼️");

        const pText = document.createElement("span");
        pText.className = "placeholder-text";
        if (scene.status === "generating") {
            pText.textContent = "Generating...";
        } else if (scene.status === "failed") {
            const isQuota = scene.fail_reason === "flux_quota_exhausted";
            const isRate = scene.fail_reason === "flux_rate_limited";
            const isNotCfg = scene.fail_reason === "flux_not_configured";
            if (isQuota) pText.textContent = "Daily Quota Reached (Click/Drop Media)";
            else if (isRate) pText.textContent = "Rate Limited (Click/Drop Media)";
            else if (isNotCfg) pText.textContent = "No API Key (Click/Drop Media)";
            else pText.textContent = "Generation Failed (Click/Drop Media)";
        } else {
            pText.textContent = "Drop Media or Click Upload";
        }

        placeholder.appendChild(pIcon);
        placeholder.appendChild(pText);
        mediaBox.appendChild(placeholder);
    }

    // Hidden file input for uploading
    const fileInput = document.createElement("input");
    fileInput.type = "file";
    fileInput.accept = "image/*,video/*";
    fileInput.style.display = "none";
    fileInput.addEventListener("change", (e) => {
        const file = e.target.files && e.target.files[0];
        if (file && callbacks.onUploadMedia) {
            callbacks.onUploadMedia(scene.id, file);
        }
    });
    mediaBox.appendChild(fileInput);

    mediaBox.addEventListener("click", () => {
        fileInput.click();
    });

    // Drag-and-drop onto scene card
    mediaBox.addEventListener("dragover", (e) => {
        e.preventDefault();
        e.stopPropagation();
        mediaBox.classList.add("drag-hover");
    });
    mediaBox.addEventListener("dragleave", (e) => {
        e.preventDefault();
        e.stopPropagation();
        mediaBox.classList.remove("drag-hover");
    });
    mediaBox.addEventListener("drop", (e) => {
        e.preventDefault();
        e.stopPropagation();
        mediaBox.classList.remove("drag-hover");
        const file = e.dataTransfer.files && e.dataTransfer.files[0];
        if (file && callbacks.onUploadMedia) {
            callbacks.onUploadMedia(scene.id, file);
        }
    });

    body.appendChild(mediaBox);

    // Text & Prompt Editor (Right)
    const contentBox = document.createElement("div");
    contentBox.className = "scene-content-box";

    // Spoken Narration
    const narrationGroup = document.createElement("div");
    narrationGroup.className = "field-group";

    const narrationHeader = document.createElement("div");
    narrationHeader.className = "field-header-row";

    const narrationLabel = document.createElement("label");
    narrationLabel.className = "field-label";
    narrationLabel.textContent = "🎙️ Spoken Narration:";

    const listenBtn = document.createElement("button");
    listenBtn.type = "button";
    listenBtn.className = "btn-text-action btn-listen-narration";
    listenBtn.style.color = "#00e6ff";
    listenBtn.style.borderColor = "rgba(0, 230, 255, 0.4)";
    listenBtn.textContent = "🔊 Listen Narration";
    listenBtn.title = "Audition neural voice reading this scene";

    listenBtn.addEventListener("click", async () => {
        const text = narrationArea.value.trim();
        if (!text) {
            alert("Please enter spoken narration text first!");
            return;
        }

        if (listenBtn.dataset.playing === "true") {
            if (window._sceneAudioPlayer) {
                window._sceneAudioPlayer.pause();
                window._sceneAudioPlayer = null;
            }
            listenBtn.dataset.playing = "false";
            listenBtn.textContent = "🔊 Listen Narration";
            return;
        }

        // Stop any active audition
        if (window._sceneAudioPlayer) {
            window._sceneAudioPlayer.pause();
            window._sceneAudioPlayer = null;
        }
        document.querySelectorAll(".btn-listen-narration").forEach(b => {
            b.dataset.playing = "false";
            b.textContent = "🔊 Listen Narration";
        });

        listenBtn.dataset.playing = "true";
        listenBtn.textContent = "⏳ Speaking...";

        try {
            const voice = document.getElementById("voiceSelect")?.value || "en-US-ChristopherNeural";
            const speedSlider = document.getElementById("voiceSpeedSlider");
            const rate = speedSlider ? speedSlider.value : "0.85";
            const res = await api.previewVoice(text, voice, rate);
            const audioSrc = res && (res.audio_url || res.preview_url);
            if (audioSrc) {
                const aud = new Audio(audioSrc + "?t=" + Date.now());
                window._sceneAudioPlayer = aud;
                listenBtn.textContent = "⏹️ Stop";
                aud.onended = () => {
                    listenBtn.dataset.playing = "false";
                    listenBtn.textContent = "🔊 Listen Narration";
                    window._sceneAudioPlayer = null;
                };
                aud.onerror = (e) => {
                    listenBtn.dataset.playing = "false";
                    listenBtn.textContent = "🔊 Listen Narration";
                    window._sceneAudioPlayer = null;
                    console.error("Audio playback error:", e);
                };
                await aud.play();
            } else {
                throw new Error("No preview audio returned from server");
            }
        } catch (err) {
            listenBtn.dataset.playing = "false";
            listenBtn.textContent = "🔊 Listen Narration";
            console.error("Audition failed:", err);
            alert("Could not audition voice: " + (err.message || err));
        }
    });

    narrationHeader.appendChild(narrationLabel);
    narrationHeader.appendChild(listenBtn);
    narrationGroup.appendChild(narrationHeader);

    const narrationArea = document.createElement("textarea");
    narrationArea.className = "scene-narration-input";
    narrationArea.rows = 2;
    narrationArea.value = scene.text || "";
    narrationArea.placeholder = "Enter spoken narration for this scene...";

    narrationArea.addEventListener("focus", () => {
        state.setFocusedScene(scene.id);
    });
    narrationArea.addEventListener("blur", () => {
        const val = narrationArea.value.trim();
        if (val !== scene.text && callbacks.onEditText) {
            callbacks.onEditText(scene.id, val);
        }
    });

    narrationGroup.appendChild(narrationArea);
    contentBox.appendChild(narrationGroup);

    // Consolidated Visual Prompt (Google Flow / Realistic B-Roll)
    const promptGroup = document.createElement("div");
    promptGroup.className = "field-group flow-prompt-group";
    promptGroup.style.marginTop = "8px";

    const promptHeader = document.createElement("div");
    promptHeader.className = "field-header-row";

    const promptLabel = document.createElement("label");
    promptLabel.className = "field-label";
    promptLabel.style.color = "#00e6ff";
    promptLabel.textContent = "🎬 Visual Prompt (Google Flow / B-Roll):";

    const promptActions = document.createElement("div");
    promptActions.className = "field-actions";

    const flowPromptVal = scene.google_flow_prompt || scene.video_prompt || scene.image_prompt || "";

    const copyFlowBtn = document.createElement("button");
    copyFlowBtn.type = "button";
    copyFlowBtn.className = "btn-text-action";
    copyFlowBtn.style.color = "#00e6ff";
    copyFlowBtn.style.borderColor = "rgba(0, 230, 255, 0.4)";
    copyFlowBtn.textContent = "📋 Copy for Flow";
    copyFlowBtn.title = "Copy prompt to clipboard for Google Flow / Veo";

    copyFlowBtn.addEventListener("click", async () => {
        try {
            await navigator.clipboard.writeText(promptArea.value || flowPromptVal);
            copyFlowBtn.textContent = "✅ Copied!";
            setTimeout(() => { copyFlowBtn.textContent = "📋 Copy for Flow"; }, 2000);
        } catch {
            promptArea.select();
            document.execCommand("copy");
            copyFlowBtn.textContent = "✅ Copied!";
            setTimeout(() => { copyFlowBtn.textContent = "📋 Copy for Flow"; }, 2000);
        }
    });

    const browseClipBtn = document.createElement("button");
    browseClipBtn.type = "button";
    browseClipBtn.className = "btn-text-action";
    browseClipBtn.textContent = "📁 Browse 10s Clip";
    browseClipBtn.title = "Select a 10s video clip from your computer for this scene";
    browseClipBtn.addEventListener("click", () => {
        fileInput.click();
    });

    promptActions.appendChild(copyFlowBtn);
    promptActions.appendChild(browseClipBtn);

    const curSource = document.getElementById("step2VisualSource")?.value || "video";
    if (curSource === "flux") {
        const genBtn = document.createElement("button");
        genBtn.type = "button";
        genBtn.className = "btn-text-action";
        genBtn.textContent = "⚡ Generate Art";
        genBtn.disabled = isManual;
        genBtn.addEventListener("click", () => {
            if (callbacks.onGenerateMedia) callbacks.onGenerateMedia(scene.id);
        });
        promptActions.appendChild(genBtn);
    }

    promptHeader.appendChild(promptLabel);
    promptHeader.appendChild(promptActions);

    const promptArea = document.createElement("textarea");
    promptArea.className = "scene-prompt-input flow-prompt-input";
    promptArea.rows = 2;
    promptArea.value = flowPromptVal;
    promptArea.placeholder = "Google Flow 10s video prompt or realistic visual description...";
    promptArea.style.borderColor = "rgba(0, 230, 255, 0.25)";
    promptArea.style.background = "rgba(0, 230, 255, 0.04)";

    promptArea.addEventListener("focus", () => {
        state.setFocusedScene(scene.id);
    });
    promptArea.addEventListener("blur", () => {
        const val = promptArea.value.trim();
        scene.google_flow_prompt = val;
        scene.image_prompt = val;
        scene.video_prompt = val;
        if (callbacks.onEditPrompt) {
            callbacks.onEditPrompt(scene.id, val, "google_flow");
        }
    });

    promptGroup.appendChild(promptHeader);
    promptGroup.appendChild(promptArea);
    contentBox.appendChild(promptGroup);

    body.appendChild(contentBox);
    card.appendChild(body);

    // 3. Footer Controls Row: Motion select, Seam Shift, Split, Merge, Delete
    const footer = document.createElement("div");
    footer.className = "scene-footer";

    const motionGroup = document.createElement("div");
    motionGroup.className = "motion-group";

    const motionLabel = document.createElement("span");
    motionLabel.className = "motion-label";
    motionLabel.textContent = "Motion:";

    const motionSelect = document.createElement("select");
    motionSelect.className = "motion-select";
    for (const m of MOTIONS) {
        const opt = document.createElement("option");
        opt.value = m.value;
        opt.textContent = m.label;
        if (m.value === (scene.motion || "push in")) {
            opt.selected = true;
        }
        motionSelect.appendChild(opt);
    }
    motionSelect.addEventListener("change", () => {
        if (callbacks.onEditMotion) {
            callbacks.onEditMotion(scene.id, motionSelect.value);
        }
    });

    motionGroup.appendChild(motionLabel);
    motionGroup.appendChild(motionSelect);
    footer.appendChild(motionGroup);

    const seamGroup = document.createElement("div");
    seamGroup.className = "seam-actions-group";

    // Split
    const splitBtn = document.createElement("button");
    splitBtn.type = "button";
    splitBtn.className = "btn-seam btn-split";
    splitBtn.title = "Split scene at word position";
    splitBtn.textContent = "✂️ Split";
    splitBtn.addEventListener("click", () => {
        state.setActiveSplitScene(scene.id);
    });
    seamGroup.appendChild(splitBtn);

    // Merge with next
    if (index < totalScenes - 1) {
        const mergeBtn = document.createElement("button");
        mergeBtn.type = "button";
        mergeBtn.className = "btn-seam";
        mergeBtn.title = "Merge with next scene";
        mergeBtn.textContent = "🔗 Merge";
        mergeBtn.addEventListener("click", () => {
            if (callbacks.onMerge) callbacks.onMerge(scene.id, "next");
        });
        seamGroup.appendChild(mergeBtn);
    }

    // Delete
    if (totalScenes > 1) {
        const delBtn = document.createElement("button");
        delBtn.type = "button";
        delBtn.className = "btn-seam btn-delete";
        delBtn.title = "Delete scene";
        delBtn.textContent = "🗑️";
        delBtn.addEventListener("click", () => {
            if (callbacks.onDelete) callbacks.onDelete(scene.id);
        });
        seamGroup.appendChild(delBtn);
    }

    footer.appendChild(seamGroup);
    card.appendChild(footer);

    return card;
}
