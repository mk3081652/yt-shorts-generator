/**
 * static/js/main.js - Application Bootstrap & Step Coordination
 */

import { api } from "./api.js";
import { state } from "./state.js";
import { StoryboardEditor } from "./editor.js";

// Toast Notifications
export function showToast(message, type = "info", duration = 3500) {
    const toastContainer = document.getElementById("toastContainer");
    if (!toastContainer) {
        console.log(`[Toast ${type}] ${message}`);
        return;
    }

    const icons = {
        success: "✅",
        error: "❌",
        warning: "⚠️",
        info: "💡"
    };

    const toast = document.createElement("div");
    toast.className = `google-toast toast-${type}`;

    const iconSpan = document.createElement("span");
    iconSpan.className = "toast-icon";
    iconSpan.textContent = icons[type] || "💡";

    const msgSpan = document.createElement("span");
    msgSpan.className = "toast-message";
    msgSpan.textContent = message;

    const closeBtn = document.createElement("button");
    closeBtn.className = "toast-close";
    closeBtn.title = "Dismiss";
    closeBtn.textContent = "×";

    function removeToast() {
        toast.style.animation = "toastFadeOut 0.25s forwards";
        setTimeout(() => {
            if (toast.parentNode) toast.parentNode.removeChild(toast);
        }, 250);
    }

    closeBtn.addEventListener("click", removeToast);

    toast.appendChild(iconSpan);
    toast.appendChild(msgSpan);
    toast.appendChild(closeBtn);
    toastContainer.appendChild(toast);

    if (duration > 0) {
        setTimeout(removeToast, duration);
    }
}

document.addEventListener("DOMContentLoaded", async () => {
    // DOM Elements - Step 1
    const topicInput = document.getElementById("topicInput");
    const generateScriptBtn = document.getElementById("generateScriptBtn");
    const scriptInput = document.getElementById("scriptInput");
    const wordCount = document.getElementById("wordCount");
    const estDuration = document.getElementById("estDuration");
    const pacingText = document.getElementById("pacingText");
    const retentionStatus = document.getElementById("retentionStatus");
    const templateSelect = document.getElementById("templateSelect");
    const hookSelect = document.getElementById("hookSelect");

    const voiceSelect = document.getElementById("voiceSelect");
    const speedSelect = document.getElementById("speedSelect");
    const previewVoiceBtn = document.getElementById("previewVoiceBtn");
    const voiceAudioPreview = document.getElementById("voiceAudioPreview");

    // DOM Elements - Step 2
    const modeAutoBtn = document.getElementById("modeAutoBtn");
    const modeManualBtn = document.getElementById("modeManualBtn");
    const generateAllScenesBtn = document.getElementById("generateAllScenesBtn");
    const generateMissingBtn = document.getElementById("generateMissingBtn");
    const bannerGenerateMissingBtn = document.getElementById("bannerGenerateMissingBtn");
    const multiMediaInput = document.getElementById("multiMediaInput");

    const storyboardProgressCard = document.getElementById("storyboardProgressCard");
    const storyboardProgressStatus = document.getElementById("storyboardProgressStatus");
    const storyboardProgressStep = document.getElementById("storyboardProgressStep");
    const storyboardProgressPct = document.getElementById("storyboardProgressPct");
    const storyboardProgressBar = document.getElementById("storyboardProgressBar");

    // DOM Elements - Step 3
    const bgmSelect = document.getElementById("bgmSelect");
    const bgmVolume = document.getElementById("bgmVolume");
    const volLabel = document.getElementById("volLabel");

    // DOM Elements - Step 4 & Preview
    const generateBtn = document.getElementById("generateBtn");
    const progressCard = document.getElementById("progressCard");
    const progressStatus = document.getElementById("progressStatus");
    const progressStep = document.getElementById("progressStep");
    const progressPct = document.getElementById("progressPct");
    const progressBar = document.getElementById("progressBar");

    const sumScriptLength = document.getElementById("sumScriptLength");
    const sumVoice = document.getElementById("sumVoice");
    const sumStoryboard = document.getElementById("sumStoryboard");
    const sumSubtitles = document.getElementById("sumSubtitles");

    const finalVideoPlayer = document.getElementById("finalVideoPlayer");
    const playerPlaceholder = document.getElementById("playerPlaceholder");
    const playerActions = document.getElementById("playerActions");
    const downloadVideoBtn = document.getElementById("downloadVideoBtn");

    const seoKitCard = document.getElementById("seoKitCard");
    const seoTitle = document.getElementById("seoTitle");
    const seoDesc = document.getElementById("seoDesc");
    const seoTags = document.getElementById("seoTags");

    // Step Navigation buttons
    const toStep2Btn = document.getElementById("toStep2Btn");
    const backToStep1Btn = document.getElementById("backToStep1Btn");
    const toStep3Btn = document.getElementById("toStep3Btn");
    const backToStep2Btn = document.getElementById("backToStep2Btn");
    const toStep4Btn = document.getElementById("toStep4Btn");
    const backToStep3Btn = document.getElementById("backToStep3Btn");

    // Initialize Storyboard Editor
    const editorElements = {
        sceneCardsList: document.getElementById("sceneCardsList"),
        storyboardEmptyNotice: document.getElementById("storyboardEmptyNotice"),
        storyboardToolbar: document.getElementById("storyboardToolbar"),
        storyboardSceneCount: document.getElementById("storyboardSceneCount"),
        storyboardBlankCount: document.getElementById("storyboardBlankCount"),
        storyboardTotalDur: document.getElementById("storyboardTotalDur"),
        storyboardVisualsCount: document.getElementById("storyboardVisualsCount"),
        undoBtn: document.getElementById("undoBtn"),
        redoBtn: document.getElementById("redoBtn"),
        copyAllPromptsBtn: document.getElementById("copyAllPromptsBtn"),
        addBeatBtn: document.getElementById("addBeatBtn"),
        blankScenesWarning: document.getElementById("blankScenesWarning"),
        blankWarningText: document.getElementById("blankWarningText"),
        splitModal: document.getElementById("splitModal"),
        closeSplitModal: document.getElementById("closeSplitModal"),
        splitWordChips: document.getElementById("splitWordChips")
    };

    const storyboardEditor = new StoryboardEditor(editorElements, showToast);

    // ==========================================
    // STEP NAVIGATION
    // ==========================================
    function goToStep(stepNum) {
        if (stepNum < 1 || stepNum > 4) return;

        if (stepNum > 1 && !scriptInput.value.trim()) {
            showToast("Please enter a script before proceeding!", "warning");
            scriptInput.focus();
            return;
        }

        for (let i = 1; i <= 4; i++) {
            const panel = document.getElementById(`stepPanel${i}`);
            const btn = document.getElementById(`stepBtn${i}`);
            if (panel) {
                if (i === stepNum) panel.classList.remove("hidden");
                else panel.classList.add("hidden");
            }
            if (btn) {
                btn.classList.remove("active");
                if (i < stepNum) btn.classList.add("completed");
                else btn.classList.remove("completed");
                if (i === stepNum) btn.classList.add("active");
            }
        }

        state.setStep(stepNum);

        // Update Step 4 Summary if entering Step 4
        if (stepNum === 4) {
            updateStep4Summary();
        }
    }

    function updateStep4Summary() {
        const words = (scriptInput.value.trim().split(/\s+/) || []).filter(Boolean);
        const wCount = words.length;
        const dur = Math.max(1, Math.round(wCount / 2.7));
        if (sumScriptLength) sumScriptLength.textContent = `${wCount} words (~${dur}s)`;

        if (sumVoice && voiceSelect) {
            const opt = voiceSelect.options[voiceSelect.selectedIndex];
            sumVoice.textContent = opt ? opt.text : "Neural Voice";
        }

        if (sumStoryboard) {
            sumStoryboard.textContent = state.mode === "auto" ? "⚡ Auto (FLUX)" : "✂️ Manual Segment";
        }

        if (sumSubtitles) {
            const checkedStyle = document.querySelector('input[name="subtitleStyle"]:checked');
            const styleVal = checkedStyle ? checkedStyle.value : "mrbeast";
            const names = { mrbeast: "MrBeast Yellow", hormozi: "Hormozi Neon Green", cyberpunk: "Cyberpunk Glow", clean: "Clean Modern" };
            sumSubtitles.textContent = names[styleVal] || styleVal;
        }
    }

    // Stepper header clicks
    for (let i = 1; i <= 4; i++) {
        const btn = document.getElementById(`stepBtn${i}`);
        if (btn) {
            btn.addEventListener("click", () => goToStep(i));
        }
    }

    if (toStep2Btn) toStep2Btn.addEventListener("click", () => handleProceedToStep2());
    if (backToStep1Btn) backToStep1Btn.addEventListener("click", () => goToStep(1));
    if (toStep3Btn) toStep3Btn.addEventListener("click", () => goToStep(3));
    if (backToStep2Btn) backToStep2Btn.addEventListener("click", () => goToStep(2));
    if (toStep4Btn) toStep4Btn.addEventListener("click", () => goToStep(4));
    if (backToStep3Btn) backToStep3Btn.addEventListener("click", () => goToStep(3));

    // ==========================================
    // STEP 1: SCRIPT & VOICE
    // ==========================================
    function updateScriptStats() {
        const text = scriptInput.value.trim();
        const words = text ? text.split(/\s+/).filter(Boolean) : [];
        const count = words.length;
        const dur = Math.max(0, Math.round(count / 2.7));

        if (wordCount) wordCount.textContent = count;
        if (estDuration) estDuration.textContent = `${dur}s`;

        if (pacingText && retentionStatus) {
            if (count === 0) {
                pacingText.textContent = "Empty";
                retentionStatus.className = "stat-badge";
            } else if (count <= 45) {
                pacingText.textContent = "Ultra Punchy (15-20s)";
                retentionStatus.className = "stat-badge status-good";
            } else if (count <= 95) {
                pacingText.textContent = "Viral Sweet Spot (25-40s)";
                retentionStatus.className = "stat-badge status-good";
            } else if (count <= 140) {
                pacingText.textContent = "Maximum Shorts Length (50-60s)";
                retentionStatus.className = "stat-badge status-warning";
            } else {
                pacingText.textContent = "Too Long (>60s YouTube Limit)";
                retentionStatus.className = "stat-badge status-danger";
            }
        }
    }

    scriptInput.addEventListener("input", updateScriptStats);

    // AI Script Generator
    if (generateScriptBtn) {
        generateScriptBtn.addEventListener("click", async () => {
            const topic = topicInput.value.trim();
            if (!topic) {
                showToast("Please enter a topic first!", "warning");
                topicInput.focus();
                return;
            }
            generateScriptBtn.disabled = true;
            generateScriptBtn.textContent = "✨ Generating...";
            showToast(`Generating viral script for "${topic}"...`, "info");

            try {
                const res = await api.generateScript(topic);
                if (res && res.script) {
                    scriptInput.value = res.script;
                    updateScriptStats();
                    showToast("Viral script generated successfully!", "success");
                }
            } catch (err) {
                showToast(`Script generation failed: ${err.message}`, "error");
            } finally {
                generateScriptBtn.disabled = false;
                generateScriptBtn.textContent = "✨ Generate Script";
            }
        });
    }

    // Audition Voice
    if (previewVoiceBtn) {
        previewVoiceBtn.addEventListener("click", async () => {
            const voice = voiceSelect.value;
            const rate = speedSelect.value;
            const sampleText = scriptInput.value.trim().slice(0, 100) || "Welcome to the ultimate YouTube Shorts Creator!";

            previewVoiceBtn.disabled = true;
            previewVoiceBtn.textContent = "🔊 Generating...";

            try {
                const res = await api.previewVoice(sampleText, voice, rate);
                if (res && res.audio_url) {
                    voiceAudioPreview.src = res.audio_url;
                    voiceAudioPreview.play();
                    showToast("Playing voice audition!", "info");
                }
            } catch (err) {
                showToast(`Voice audition failed: ${err.message}`, "error");
            } finally {
                previewVoiceBtn.disabled = false;
                previewVoiceBtn.textContent = "🔊 Audition Voice";
            }
        });
    }

    // Step 1 -> Step 2
    async function handleProceedToStep2() {
        const script = scriptInput.value.trim();
        if (!script) {
            showToast("Please enter a script before proceeding!", "warning");
            scriptInput.focus();
            return;
        }

        // If project already exists with same script, just go to Step 2
        if (state.project && state.project.script === script) {
            goToStep(2);
            return;
        }

        toStep2Btn.disabled = true;
        toStep2Btn.textContent = "Planning Storyboard...";
        showToast("Director is analyzing script & planning visual beats...", "info");

        try {
            const proj = await api.createProject(script, state.mode, false);
            state.setProject(proj);
            goToStep(2);
            showToast("Storyboard planned successfully!", "success");
            startProjectPolling(proj.id);
        } catch (err) {
            showToast(`Failed to plan storyboard: ${err.message}`, "error");
        } finally {
            toStep2Btn.disabled = false;
            toStep2Btn.textContent = "Continue to Visual Storyboard ➔";
        }
    }

    // Background Project Polling (when scenes are generating in background)
    let projectPollTimer = null;
    function startProjectPolling(projectId) {
        if (projectPollTimer) clearInterval(projectPollTimer);

        projectPollTimer = setInterval(async () => {
            try {
                const proj = await api.getProject(projectId);
                state.setProject(proj);

                const isAnyGenerating = proj.scenes.some(s => s.status === "generating" || s.status === "queued");
                if (storyboardProgressCard) {
                    if (isAnyGenerating) {
                        storyboardProgressCard.classList.remove("hidden");
                        const readyCount = proj.scenes.filter(s => s.status === "ready").length;
                        const pct = Math.round((readyCount / Math.max(1, proj.scenes.length)) * 100);
                        if (storyboardProgressPct) storyboardProgressPct.textContent = `${pct}%`;
                        if (storyboardProgressBar) storyboardProgressBar.style.width = `${pct}%`;
                        if (storyboardProgressStatus) storyboardProgressStatus.textContent = `Generating Images (${readyCount}/${proj.scenes.length})...`;
                    } else {
                        storyboardProgressCard.classList.add("hidden");
                        clearInterval(projectPollTimer);
                        projectPollTimer = null;
                    }
                }

                if (!isAnyGenerating) {
                    clearInterval(projectPollTimer);
                    projectPollTimer = null;
                }
            } catch (_) {
                // Ignore polling errors
            }
        }, 2000);
    }

    // ==========================================
    // STEP 2: STORYBOARD & SCENE EDITOR
    // ==========================================
    if (modeAutoBtn) {
        modeAutoBtn.addEventListener("click", () => {
            modeAutoBtn.classList.add("active");
            if (modeManualBtn) modeManualBtn.classList.remove("active");
            state.setMode("auto");
            showToast("Switched to Auto Mode: FLUX generates visuals automatically.", "info");
        });
    }

    if (modeManualBtn) {
        modeManualBtn.addEventListener("click", () => {
            modeManualBtn.classList.add("active");
            if (modeAutoBtn) modeAutoBtn.classList.remove("active");
            state.setMode("manual");
            showToast("Switched to Manual Segment: Drop or upload your own B-roll files.", "info");
        });
    }

    if (generateAllScenesBtn) {
        generateAllScenesBtn.addEventListener("click", async () => {
            const script = scriptInput.value.trim();
            if (!script) {
                showToast("Please enter a script first!", "warning");
                goToStep(1);
                return;
            }
            generateAllScenesBtn.disabled = true;
            generateAllScenesBtn.textContent = "⚡ Generating...";
            showToast("Director is generating scene visuals...", "info");

            try {
                const proj = await api.createProject(script, "auto", false);
                state.setProject(proj);
                showToast("Visual generation started!", "success");
                startProjectPolling(proj.id);
            } catch (err) {
                showToast(`Visual generation failed: ${err.message}`, "error");
            } finally {
                generateAllScenesBtn.disabled = false;
                generateAllScenesBtn.textContent = "⚡ Generate Visuals";
            }
        });
    }

    if (generateMissingBtn) {
        generateMissingBtn.addEventListener("click", () => handleGenerateMissing());
    }
    if (bannerGenerateMissingBtn) {
        bannerGenerateMissingBtn.addEventListener("click", () => handleGenerateMissing());
    }

    async function handleGenerateMissing() {
        const proj = state.project;
        if (!proj) return;
        showToast("Generating images for blank scenes...", "info");
        try {
            await api.generateMissingMedia(proj.id);
            startProjectPolling(proj.id);
        } catch (err) {
            showToast(`Failed to generate missing: ${err.message}`, "error");
        }
    }

    // Bulk Media Upload
    if (multiMediaInput) {
        multiMediaInput.addEventListener("change", async (e) => {
            const files = e.target.files;
            if (!files || files.length === 0) return;
            const proj = state.project;
            if (!proj) {
                showToast("Please create a project first before uploading files!", "warning");
                return;
            }
            showToast(`Uploading ${files.length} file(s)...`, "info");
            try {
                const res = await api.uploadBulk(proj.id, Array.from(files));
                if (res && res.project) {
                    state.setProject(res.project);
                    showToast(`Assigned ${files.length} file(s) to scenes!`, "success");
                }
            } catch (err) {
                showToast(`Bulk upload failed: ${err.message}`, "error");
            }
        });
    }

    // ==========================================
    // STEP 3: SUBTITLES & MUSIC
    // ==========================================
    // Subtitle style preset cards
    document.querySelectorAll(".preset-option").forEach((card) => {
        card.addEventListener("click", () => {
            document.querySelectorAll(".preset-option").forEach((c) => c.classList.remove("active"));
            card.classList.add("active");
            const radio = card.querySelector('input[type="radio"]');
            if (radio) radio.checked = true;
        });
    });

    if (bgmVolume && volLabel) {
        bgmVolume.addEventListener("input", (e) => {
            const pct = Math.round(e.target.value * 100);
            volLabel.textContent = `${pct}%`;
        });
    }

    // ==========================================
    // STEP 4: PRODUCE & EXPORT
    // ==========================================
    let renderJobId = null;
    let renderPollInterval = null;

    if (generateBtn) {
        generateBtn.addEventListener("click", async () => {
            const script = scriptInput.value.trim();
            if (!script) {
                showToast("Please enter a script before generating video!", "warning");
                goToStep(1);
                return;
            }

            const voice = voiceSelect.value;
            const voiceRate = speedSelect.value;
            const subtitleStyle = document.querySelector('input[name="subtitleStyle"]:checked')?.value || "mrbeast";
            const bgmTrack = bgmSelect.value;
            const bgmVol = parseFloat(bgmVolume.value) || 0.18;

            generateBtn.disabled = true;
            generateBtn.classList.add("btn-loading");
            if (progressCard) progressCard.classList.remove("hidden");
            if (playerPlaceholder) playerPlaceholder.classList.remove("hidden");
            if (playerActions) playerActions.classList.add("hidden");
            if (seoKitCard) seoKitCard.classList.add("hidden");

            const payload = {
                script,
                voice,
                voice_rate: voiceRate,
                subtitle_style: subtitleStyle,
                bgm_track: bgmTrack,
                bgm_volume: bgmVol,
                project_id: state.project ? state.project.id : null
            };

            showToast("Starting master video rendering...", "info");

            try {
                const res = await api.generateShort(payload);
                if (res && res.job_id) {
                    renderJobId = res.job_id;
                    startRenderPolling(renderJobId);
                }
            } catch (err) {
                showToast(`Render failed to start: ${err.message}`, "error");
                generateBtn.disabled = false;
                generateBtn.classList.remove("btn-loading");
                if (progressCard) progressCard.classList.add("hidden");
            }
        });
    }

    function startRenderPolling(jobId) {
        if (renderPollInterval) clearInterval(renderPollInterval);

        renderPollInterval = setInterval(async () => {
            try {
                const job = await api.pollJob(jobId);
                if (!job) return;

                const pct = job.progress || 0;
                if (progressPct) progressPct.textContent = `${pct}%`;
                if (progressBar) progressBar.style.width = `${pct}%`;
                if (progressStatus) progressStatus.textContent = job.status === "processing" ? "Rendering Short..." : job.status;
                if (progressStep) progressStep.textContent = job.message || "Working...";

                if (job.status === "completed") {
                    clearInterval(renderPollInterval);
                    renderPollInterval = null;
                    generateBtn.disabled = false;
                    generateBtn.classList.remove("btn-loading");
                    if (progressCard) progressCard.classList.add("hidden");

                    showToast("Viral YouTube Short generated successfully!", "success");

                    // Load video in player
                    if (finalVideoPlayer && job.video_url) {
                        finalVideoPlayer.src = job.video_url;
                        if (playerPlaceholder) playerPlaceholder.classList.add("hidden");
                        finalVideoPlayer.play();
                    }

                    if (playerActions) playerActions.classList.remove("hidden");
                    if (downloadVideoBtn && job.video_url) {
                        downloadVideoBtn.href = job.video_url;
                    }

                    // Populate SEO kit
                    if (job.metadata && seoKitCard) {
                        seoKitCard.classList.remove("hidden");
                        if (seoTitle) seoTitle.value = job.metadata.title || "";
                        if (seoDesc) seoDesc.value = job.metadata.description || "";
                        if (seoTags) seoTags.value = Array.isArray(job.metadata.tags) ? job.metadata.tags.join(", ") : (job.metadata.tags || "");
                    }
                } else if (job.status === "error") {
                    clearInterval(renderPollInterval);
                    renderPollInterval = null;
                    generateBtn.disabled = false;
                    generateBtn.classList.remove("btn-loading");
                    showToast(`Render error: ${job.message || "Unknown error"}`, "error");
                }
            } catch (err) {
                console.error("[Render Poll Error]:", err);
            }
        }, 1500);
    }

    // SEO Copy buttons
    document.querySelectorAll(".btn-copy").forEach((btn) => {
        btn.addEventListener("click", () => {
            const targetId = btn.dataset.target;
            const targetEl = document.getElementById(targetId);
            if (targetEl && targetEl.value) {
                navigator.clipboard.writeText(targetEl.value);
                showToast("Copied to clipboard!", "success");
            }
        });
    });

    // ==========================================
    // INITIAL CONFIG LOAD
    // ==========================================
    try {
        const cfg = await api.fetchConfig();
        state.setConfig(cfg);

        // Populate voices (supports both Array and Object formats)
        if (voiceSelect && cfg.voices) {
            voiceSelect.innerHTML = "";
            const voiceList = Array.isArray(cfg.voices)
                ? cfg.voices
                : Object.entries(cfg.voices).map(([id, info]) => ({ id, ...info }));

            voiceList.forEach((v) => {
                const opt = document.createElement("option");
                opt.value = v.id || v.name;
                opt.textContent = `${v.name || v.id} (${v.gender || "Neural"})`;
                if (v.id === "en-US-ChristopherNeural") opt.selected = true;
                voiceSelect.appendChild(opt);
            });
        }

        // Populate BGM
        if (bgmSelect && cfg.bgm_tracks) {
            bgmSelect.innerHTML = "";
            const bgmList = Array.isArray(cfg.bgm_tracks)
                ? cfg.bgm_tracks
                : Object.entries(cfg.bgm_tracks).map(([id, info]) => ({ id, ...info }));

            bgmList.forEach((b) => {
                const opt = document.createElement("option");
                opt.value = b.id || b.name;
                opt.textContent = b.name || b.id;
                if (b.id === "mystery_suspense") opt.selected = true;
                bgmSelect.appendChild(opt);
            });
        }

        // Populate Viral Templates (supports both Array and Object formats)
        if (templateSelect && cfg.templates) {
            templateSelect.innerHTML = '<option value="">✨ Load Viral Template...</option>';
            const templateList = Array.isArray(cfg.templates)
                ? cfg.templates
                : Object.entries(cfg.templates).map(([key, val]) => ({ key, ...val }));

            templateList.forEach((t) => {
                const opt = document.createElement("option");
                opt.value = t.script || t.text;
                opt.textContent = t.title || t.name || t.key;
                templateSelect.appendChild(opt);
            });
            templateSelect.addEventListener("change", (e) => {
                if (e.target.value) {
                    scriptInput.value = e.target.value;
                    updateScriptStats();
                    showToast("Loaded viral script template!", "info");
                }
            });
        }

        // Populate Hooks (supports both Array of strings and Array of objects)
        if (hookSelect && cfg.hooks) {
            hookSelect.innerHTML = '<option value="">🪝 Add Viral Hook...</option>';
            cfg.hooks.forEach((h) => {
                const opt = document.createElement("option");
                if (typeof h === "string") {
                    opt.value = h;
                    opt.textContent = h.length > 55 ? `${h.slice(0, 52)}...` : h;
                } else {
                    opt.value = h.hook || h.text || "";
                    opt.textContent = h.title || h.hook || h.text || "";
                }
                hookSelect.appendChild(opt);
            });
            hookSelect.addEventListener("change", (e) => {
                if (e.target.value) {
                    scriptInput.value = `${e.target.value}\n\n${scriptInput.value}`.trim();
                    updateScriptStats();
                    showToast("Prepended viral hook to script!", "info");
                }
            });
        }
    } catch (err) {
        console.error("[Init Config Error]:", err);
        showToast("Failed to load initial configuration.", "error");
    }
});
