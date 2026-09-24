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

window.showToast = showToast;

/**
 * Displays a rich assignment summary panel showing which file was assigned to which scene.
 */
function showBulkUploadSummary(succeeded, skipped, failed) {
    // Remove any existing panel
    const existing = document.getElementById("bulkUploadSummaryPanel");
    if (existing) existing.remove();

    const panel = document.createElement("div");
    panel.id = "bulkUploadSummaryPanel";
    panel.className = "bulk-upload-summary-panel";

    const header = document.createElement("div");
    header.className = "bulk-summary-header";
    header.innerHTML = `
        <span class="bulk-summary-title">📥 Upload Assignment Results</span>
        <button class="bulk-summary-close" title="Dismiss">×</button>
    `;
    panel.appendChild(header);

    const body = document.createElement("div");
    body.className = "bulk-summary-body";

    if (succeeded.length > 0) {
        const successTitle = document.createElement("div");
        successTitle.className = "bulk-summary-section-title success";
        successTitle.textContent = `✅ ${succeeded.length} file${succeeded.length > 1 ? "s" : ""} assigned:`;
        body.appendChild(successTitle);

        succeeded.forEach((r, i) => {
            const row = document.createElement("div");
            row.className = "bulk-summary-row success";
            const fname = r.filename || `File ${i + 1}`;
            const shortName = fname.length > 22 ? fname.substring(0, 19) + "..." : fname;
            row.innerHTML = `
                <span class="bulk-row-num">${String(i + 1).padStart(2, "0")}</span>
                <span class="bulk-row-file" title="${fname}">🖼️ ${shortName}</span>
                <span class="bulk-row-arrow">→</span>
                <span class="bulk-row-scene">Scene #${r.scene_index}</span>
            `;
            // Click to scroll to that scene card
            row.style.cursor = "pointer";
            row.addEventListener("click", () => {
                const card = document.querySelector(`[data-scene-id="${r.scene_id}"]`);
                if (card) {
                    card.scrollIntoView({ behavior: "smooth", block: "center" });
                    card.classList.add("scene-just-uploaded");
                    setTimeout(() => card.classList.remove("scene-just-uploaded"), 1800);
                }
            });
            body.appendChild(row);
        });
    }

    if (skipped.length > 0) {
        const skipTitle = document.createElement("div");
        skipTitle.className = "bulk-summary-section-title warn";
        skipTitle.textContent = `⚠️ ${skipped.length} skipped (no scene slot):`;
        body.appendChild(skipTitle);
        skipped.forEach(r => {
            const row = document.createElement("div");
            row.className = "bulk-summary-row warn";
            row.textContent = `⚠️ ${r.filename}`;
            body.appendChild(row);
        });
    }

    if (failed.length > 0) {
        const failTitle = document.createElement("div");
        failTitle.className = "bulk-summary-section-title error";
        failTitle.textContent = `❌ ${failed.length} failed:`;
        body.appendChild(failTitle);
        failed.forEach(r => {
            const row = document.createElement("div");
            row.className = "bulk-summary-row error";
            row.textContent = `❌ ${r.filename}: ${r.reason || "invalid"}`;
            body.appendChild(row);
        });
    }

    panel.appendChild(body);

    // Insert after the editor-actions-row in step2
    const actionsRow = document.querySelector(".editor-actions-row");
    if (actionsRow && actionsRow.parentNode) {
        actionsRow.parentNode.insertBefore(panel, actionsRow.nextSibling);
    } else {
        document.body.appendChild(panel);
    }

    // Auto-dismiss after 12s
    const autoDismiss = setTimeout(() => panel.remove(), 12000);

    panel.querySelector(".bulk-summary-close").addEventListener("click", () => {
        clearTimeout(autoDismiss);
        panel.remove();
    });
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

    if (finalVideoPlayer) {
        finalVideoPlayer.addEventListener("click", () => {
            if (finalVideoPlayer.src) {
                if (finalVideoPlayer.paused) {
                    finalVideoPlayer.play().catch(() => {});
                } else {
                    finalVideoPlayer.pause();
                }
            }
        });
    }

    const seoKitCard = document.getElementById("seoKitCard");
    const seoTitle = document.getElementById("seoTitle");
    const seoDesc = document.getElementById("seoDesc");
    const seoTags = document.getElementById("seoTags");
    const refreshSeoBtn = document.getElementById("refreshSeoBtn");

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
            const styleVal = checkedStyle ? checkedStyle.value : "hyper_yellow";
            const names = {
                hyper_yellow: "Hyper Yellow",
                glacier_cyan: "Glacier Cyan",
                neon_lime: "Neon Lime",
                sunset_coral: "Sunset Coral",
                clean: "Cinematic Clean White",
                viral_pop: "Hyper Yellow",
                mrbeast: "Hyper Yellow",
                neon_pulse: "Glacier Cyan",
                cyberpunk: "Glacier Cyan",
                hormozi: "Neon Lime",
                tok_hype: "Sunset Coral",
                editorial_box: "Cinematic Clean White"
            };
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
            const topic = topicInput ? topicInput.value.trim() : "";
            if (!topic) {
                showToast("Please enter a topic first!", "warning");
                if (topicInput) topicInput.focus();
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
    let hasNotifiedFinished = false;
    function startProjectPolling(projectId) {
        if (projectPollTimer) clearInterval(projectPollTimer);
        hasNotifiedFinished = false;

        // Show progress card immediately
        if (storyboardProgressCard) {
            storyboardProgressCard.classList.remove("hidden");
            if (storyboardProgressPct) storyboardProgressPct.textContent = "0%";
            if (storyboardProgressBar) storyboardProgressBar.style.width = "5%";
            if (storyboardProgressStatus) storyboardProgressStatus.textContent = "Rendering Visuals via FLUX...";
            if (storyboardProgressStep) storyboardProgressStep.textContent = "Generating 9:16 images in background...";
        }

        projectPollTimer = setInterval(async () => {
            try {
                const proj = await api.getProject(projectId);
                state.setProject(proj);

                const isAnyGenerating = proj.scenes.some(s => s.status === "generating" || s.status === "queued");
                if (storyboardProgressCard) {
                    if (isAnyGenerating) {
                        storyboardProgressCard.classList.remove("hidden");
                        const readyCount = proj.scenes.filter(s => s.status === "ready").length;
                        const failedCount = proj.scenes.filter(s => s.status === "failed").length;
                        const finishedCount = readyCount + failedCount;
                        const total = Math.max(1, proj.scenes.length);
                        const pct = Math.min(95, Math.round(15 + (finishedCount / total) * 80));
                        if (storyboardProgressPct) storyboardProgressPct.textContent = `${pct}%`;
                        if (storyboardProgressBar) storyboardProgressBar.style.width = `${pct}%`;
                        if (storyboardProgressStatus) storyboardProgressStatus.textContent = `Generating Images (${readyCount}/${total})...`;
                        if (storyboardProgressStep) storyboardProgressStep.textContent = `Completed ${finishedCount} of ${total} scenes...`;
                    } else {
                        storyboardProgressCard.classList.add("hidden");
                        clearInterval(projectPollTimer);
                        projectPollTimer = null;

                        if (!hasNotifiedFinished) {
                            hasNotifiedFinished = true;
                            const readyCount = proj.scenes.filter(s => s.status === "ready").length;
                            const total = proj.scenes.length;
                            const quotaFailed = proj.scenes.some(s => s.fail_reason === "flux_quota_exhausted");
                            const rateFailed = proj.scenes.some(s => s.fail_reason === "flux_rate_limited");
                            const notCfg = proj.scenes.some(s => s.fail_reason === "flux_not_configured");

                            if (quotaFailed) {
                                showToast("⚠️ Cloudflare daily limit (10,000 neurons) reached. See card tooltips or drop your own media.", "warning", 8000);
                            } else if (rateFailed) {
                                showToast("⚠️ Cloudflare rate limit active. Please wait for cooldown or drop media manually.", "warning", 6000);
                            } else if (notCfg) {
                                showToast("⚠️ Cloudflare credentials not configured in .env. Drop media manually into scenes.", "warning", 6000);
                            } else if (readyCount > 0) {
                                showToast(`✨ Generated ${readyCount}/${total} visuals with FLUX!`, "success", 4000);
                            }
                        }
                    }
                }

                if (!isAnyGenerating) {
                    clearInterval(projectPollTimer);
                    projectPollTimer = null;
                }
            } catch (_) {
                // Ignore polling errors
            }
        }, 1500);
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
                if (state.project && state.project.id) {
                    await api.generateMissingMedia(state.project.id);
                    showToast("Visual generation started!", "success");
                    startProjectPolling(state.project.id);
                } else {
                    const proj = await api.createProject(script, "auto", false);
                    state.setProject(proj);
                    showToast("Visual generation started!", "success");
                    startProjectPolling(proj.id);
                }
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

            const fileArray = Array.from(files);
            showToast(`📥 Uploading ${fileArray.length} file(s) and assigning to scenes...`, "info", 4000);

            // Show per-file loading state on button label
            const dropLabel = multiMediaInput.closest("label");
            const origText = dropLabel ? dropLabel.childNodes[0] && dropLabel.childNodes[0].textContent : null;
            if (dropLabel) dropLabel.setAttribute("data-uploading", "true");

            try {
                const res = await api.uploadBulk(proj.id, fileArray);
                if (res && res.project) {
                    state.setProject(res.project);

                    // Show assignment results panel
                    const results = res.results || [];
                    const succeeded = results.filter(r => r.status === "success");
                    const skipped = results.filter(r => r.status === "skipped");
                    const failed = results.filter(r => r.status === "failed");

                    // Flash highlight newly assigned scene cards
                    succeeded.forEach(r => {
                        const card = document.querySelector(`[data-scene-id="${r.scene_id}"]`);
                        if (card) {
                            card.classList.add("scene-just-uploaded");
                            // Add file number badge overlay to media box
                            const mediaBox = card.querySelector(".scene-media-box");
                            if (mediaBox) {
                                const existingBadge = mediaBox.querySelector(".upload-seq-badge");
                                if (existingBadge) existingBadge.remove();
                                const badge = document.createElement("div");
                                badge.className = "upload-seq-badge";
                                const fname = r.filename || "";
                                const shortName = fname.length > 18 ? fname.substring(0, 15) + "..." : fname;
                                badge.innerHTML = `<span class="upload-badge-num">📥 ${shortName}</span>`;
                                mediaBox.appendChild(badge);
                                setTimeout(() => {
                                    badge.classList.add("fade-out");
                                    setTimeout(() => badge.remove(), 600);
                                }, 3500);
                            }
                            setTimeout(() => card.classList.remove("scene-just-uploaded"), 2500);
                        }
                    });

                    // Show summary toast
                    if (succeeded.length > 0) {
                        const lines = succeeded.map(r => `📷 ${r.filename} → Scene #${r.scene_index}`).join("\n");
                        showBulkUploadSummary(succeeded, skipped, failed);
                    }
                    if (skipped.length > 0) {
                        showToast(`⚠️ ${skipped.length} file(s) skipped — no available scene slot.`, "warning", 5000);
                    }
                    if (failed.length > 0) {
                        showToast(`❌ ${failed.length} file(s) failed validation.`, "error", 5000);
                    }
                }
            } catch (err) {
                showToast(`Bulk upload failed: ${err.message}`, "error");
            } finally {
                multiMediaInput.value = "";
                if (dropLabel) dropLabel.removeAttribute("data-uploading");
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
            const subtitleStyle = document.querySelector('input[name="subtitleStyle"]:checked')?.value || "hyper_yellow";
            const bgmTrack = bgmSelect.value;
            const bgmVol = parseFloat(bgmVolume.value) || 0.18;

            generateBtn.disabled = true;
            generateBtn.classList.add("btn-loading");
            if (progressCard) progressCard.classList.remove("hidden");
            if (playerPlaceholder) playerPlaceholder.classList.remove("hidden");
            if (playerActions) playerActions.classList.add("hidden");
            if (seoKitCard) seoKitCard.classList.add("hidden");

            // Reset video player state
            if (finalVideoPlayer) {
                try {
                    finalVideoPlayer.pause();
                } catch (e) {}
                finalVideoPlayer.removeAttribute("src");
                finalVideoPlayer.classList.remove("visible", "active");
                finalVideoPlayer.style.display = "none";
                finalVideoPlayer.load();
            }

            const resolution = document.getElementById("ytResolutionSelect")?.value || "720p";
            const payload = {
                script,
                voice,
                voice_rate: voiceRate,
                subtitle_style: subtitleStyle,
                bgm_track: bgmTrack,
                bgm_volume: bgmVol,
                resolution: resolution,
                project_id: state.project ? state.project.id : null
            };

            showToast("Starting master video rendering...", "info");

            try {
                const res = await api.generateShort(payload);
                if (res && res.job_id) {
                    renderJobId = res.job_id;
                    state._lastJobId = res.job_id;   // persist for replace-thumbnail handler
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

                    // Load video in player and activate visibility
                    if (finalVideoPlayer && job.video_url) {
                        finalVideoPlayer.src = job.video_url;
                        finalVideoPlayer.classList.add("visible", "active");
                        finalVideoPlayer.style.display = "block";
                        if (playerPlaceholder) playerPlaceholder.classList.add("hidden");
                        finalVideoPlayer.load();
                        const playPromise = finalVideoPlayer.play();
                        if (playPromise !== undefined) {
                            playPromise.catch((err) => {
                                console.warn("Autoplay waiting for user interaction:", err);
                            });
                        }
                    }

                    if (playerActions) playerActions.classList.remove("hidden");
                    if (downloadVideoBtn && job.video_url) {
                        downloadVideoBtn.href = job.video_url;
                    }
                    const downloadThumbBtn = document.getElementById("downloadThumbBtn");
                    const replaceThumbnailBtn = document.getElementById("replaceThumbnailBtn");
                    const thumbnailPreviewArea = document.getElementById("thumbnailPreviewArea");
                    const thumbnailPreviewImg = document.getElementById("thumbnailPreviewImg");

                    if (job.thumbnail_url) {
                        if (downloadThumbBtn) {
                            downloadThumbBtn.href = job.thumbnail_url;
                            downloadThumbBtn.classList.remove("hidden");
                            downloadThumbBtn.style.display = "flex";
                        }
                        if (replaceThumbnailBtn) {
                            replaceThumbnailBtn.classList.remove("hidden");
                        }
                        if (thumbnailPreviewArea && thumbnailPreviewImg) {
                            thumbnailPreviewImg.src = job.thumbnail_url + "?t=" + Date.now();
                            thumbnailPreviewArea.classList.remove("hidden");
                        }
                    } else {
                        if (downloadThumbBtn) { downloadThumbBtn.classList.add("hidden"); downloadThumbBtn.style.display = "none"; }
                        if (replaceThumbnailBtn) replaceThumbnailBtn.classList.add("hidden");
                        if (thumbnailPreviewArea) thumbnailPreviewArea.classList.add("hidden");
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

    // ── Replace Thumbnail ──────────────────────────────────────────────────
    const replaceThumbnailBtnEl = document.getElementById("replaceThumbnailBtn");
    const replaceThumbnailInputEl = document.getElementById("replaceThumbnailInput");

    if (replaceThumbnailBtnEl && replaceThumbnailInputEl) {
        replaceThumbnailBtnEl.addEventListener("click", () => {
            replaceThumbnailInputEl.click();
        });

        replaceThumbnailInputEl.addEventListener("change", async (e) => {
            const file = e.target.files[0];
            if (!file) return;

            // Determine current job_id from the active polling job
            const jobId = state._lastJobId || null;
            if (!jobId) {
                showToast("No active render job found — generate a video first.", "warning");
                return;
            }

            const origText = replaceThumbnailBtnEl.textContent;
            replaceThumbnailBtnEl.disabled = true;
            replaceThumbnailBtnEl.textContent = "⏳ Generating...";
            showToast("🖼️ Generating 16:9 thumbnail with your image...", "info", 5000);

            try {
                const fd = new FormData();
                fd.append("file", file);
                const resp = await fetch(`/api/jobs/${jobId}/replace_thumbnail`, {
                    method: "POST",
                    body: fd,
                });
                if (!resp.ok) {
                    const err = await resp.json().catch(() => ({}));
                    throw new Error(err.detail || `Server error ${resp.status}`);
                }
                const data = await resp.json();
                const newThumbUrl = data.thumbnail_url + "?t=" + Date.now();

                // Refresh preview
                const thumbPreviewImg = document.getElementById("thumbnailPreviewImg");
                if (thumbPreviewImg) thumbPreviewImg.src = newThumbUrl;
                const thumbDownload = document.getElementById("downloadThumbBtn");
                if (thumbDownload) thumbDownload.href = data.thumbnail_url;

                showToast("✅ Thumbnail replaced! Download the new 16:9 version below.", "success", 5000);
            } catch (err) {
                showToast(`Replace thumbnail failed: ${err.message}`, "error");
            } finally {
                replaceThumbnailBtnEl.disabled = false;
                replaceThumbnailBtnEl.textContent = origText;
                replaceThumbnailInputEl.value = "";
            }
        });
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

    // Refresh SEO Kit Button
    if (refreshSeoBtn) {
        refreshSeoBtn.addEventListener("click", async () => {
            let script = scriptInput ? scriptInput.value.trim() : "";
            if (!script && state.project && state.project.script) {
                script = state.project.script.trim();
            }
            if (!script) {
                showToast("Please enter a script first!", "warning");
                return;
            }
            refreshSeoBtn.disabled = true;
            refreshSeoBtn.textContent = "⏳ Generating...";
            showToast("Generating SEO metadata tailored to your script...", "info");
            try {
                const meta = await api.generateMetadata(script);
                if (meta) {
                    if (seoKitCard) seoKitCard.classList.remove("hidden");
                    if (seoTitle) seoTitle.value = meta.title || "";
                    if (seoDesc) seoDesc.value = meta.description || "";
                    if (seoTags) seoTags.value = Array.isArray(meta.tags) ? meta.tags.join(", ") : (meta.tags || "");
                    showToast("SEO kit updated with script-tailored title and tags!", "success");
                }
            } catch (err) {
                showToast(`Failed to update SEO kit: ${err.message}`, "error");
            } finally {
                refreshSeoBtn.disabled = false;
                refreshSeoBtn.textContent = "🔄 Regenerate";
            }
        });
    }

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

    // ==========================================
    // YOUTUBE MULTI-CHANNEL & PUBLISH LOGIC
    // ==========================================
    const ytChannelSelect = document.getElementById("ytChannelSelect");
    const ytChannelSelectStep4 = document.getElementById("ytChannelSelectStep4");
    const manageChannelsBtn = document.getElementById("manageChannelsBtn");
    const channelModalOverlay = document.getElementById("channelModalOverlay");
    const closeChannelModalBtn = document.getElementById("closeChannelModalBtn");
    const channelsListContainer = document.getElementById("channelsListContainer");
    const addNewChannelOAuthBtn = document.getElementById("addNewChannelOAuthBtn");
    const uploadTokenFileInput = document.getElementById("uploadTokenFileInput");
    const triggerTokenFileUploadBtn = document.getElementById("triggerTokenFileUploadBtn");
    const togglePasteTokenBtn = document.getElementById("togglePasteTokenBtn");
    const pasteTokenArea = document.getElementById("pasteTokenArea");
    const tokenJsonInput = document.getElementById("tokenJsonInput");
    const submitImportTokenBtn = document.getElementById("submitImportTokenBtn");

    const ytPrivacySelect = document.getElementById("ytPrivacySelect");
    const ytPrivacySelectStep4 = document.getElementById("ytPrivacySelectStep4");
    const ytPacingMode = document.getElementById("ytPacingMode");
    const oneClickPublishBtn = document.getElementById("oneClickPublishBtn");
    const publishProjectToYoutubeBtn = document.getElementById("publishProjectToYoutubeBtn");
    const ytPublishedBanner = document.getElementById("ytPublishedBanner");
    const ytVideoUrlInput = document.getElementById("ytVideoUrlInput");
    const openYtLinkBtn = document.getElementById("openYtLinkBtn");
    const viewYouTubeBtn = document.getElementById("viewYouTubeBtn");

    // Sync Privacy status between Step 1 and Step 4 & remember in localStorage
    const savedPrivacy = localStorage.getItem("yt_privacy") || "public";
    if (ytPrivacySelect) ytPrivacySelect.value = savedPrivacy;
    if (ytPrivacySelectStep4) ytPrivacySelectStep4.value = savedPrivacy;

    if (ytPrivacySelect) {
        ytPrivacySelect.addEventListener("change", (e) => {
            const val = e.target.value;
            localStorage.setItem("yt_privacy", val);
            if (ytPrivacySelectStep4) ytPrivacySelectStep4.value = val;
        });
    }
    if (ytPrivacySelectStep4) {
        ytPrivacySelectStep4.addEventListener("change", (e) => {
            const val = e.target.value;
            localStorage.setItem("yt_privacy", val);
            if (ytPrivacySelect) ytPrivacySelect.value = val;
        });
    }

    // 🔁 1-Click Infinity Loop Action
    const loopScriptBtn = document.getElementById("loopScriptBtn");
    if (loopScriptBtn) {
        loopScriptBtn.addEventListener("click", async () => {
            const script = scriptInput ? scriptInput.value.trim() : "";
            if (!script) {
                showToast("Please paste or write a script first to apply the loop.", "warning");
                return;
            }
            const origHtml = loopScriptBtn.innerHTML;
            loopScriptBtn.disabled = true;
            loopScriptBtn.innerHTML = "⏳ Looping...";
            try {
                const res = await api.loopScript(script);
                if (res && res.script) {
                    if (scriptInput) {
                        scriptInput.value = res.script;
                        scriptInput.dispatchEvent(new Event("input"));
                    }
                    showToast("🔁 Seamless Infinity Loop applied! The ending now loops into the hook.", "success");
                }
            } catch (err) {
                showToast(`Loop error: ${err.message}`, "error");
            } finally {
                loopScriptBtn.disabled = false;
                loopScriptBtn.innerHTML = origHtml;
            }
        });
    }

    let connectedChannels = [];
    let currentActiveChannelId = null;

    async function loadYouTubeChannels() {
        try {
            let res = await api.getYouTubeChannels();
            let channels = (res && res.channels) ? res.channels : [];

            // Read browser-side localStorage channel vault
            const rawVault = localStorage.getItem("yt_channel_vault");
            let localVault = {};
            try {
                if (rawVault) localVault = JSON.parse(rawVault);
            } catch (e) {}

            const localVaultKeys = Object.keys(localVault);

            // Auto-restore: If server wiped tokens (Render container restart/sleep), seamlessly restore from browser vault!
            if (channels.length === 0 && localVaultKeys.length > 0) {
                console.log(`[YouTube Vault] Restoring ${localVaultKeys.length} channels from browser vault...`);
                try {
                    const savedActiveId = localStorage.getItem("yt_active_channel_id") || localVaultKeys[0];
                    const restoreRes = await fetch("/api/youtube/channels/restore_vault", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            vault: localVault,
                            active_channel_id: savedActiveId
                        })
                    }).then(r => r.json());
                    if (restoreRes && restoreRes.success) {
                        res = restoreRes;
                        channels = res.channels || [];
                    }
                } catch (restoreErr) {
                    console.warn("[YouTube Vault] Auto-restore notice:", restoreErr);
                }
            }

            // Sync fresh server vault credentials into browser localStorage
            if (res && res.vault && Object.keys(res.vault).length > 0) {
                const mergedVault = { ...localVault, ...res.vault };
                localStorage.setItem("yt_channel_vault", JSON.stringify(mergedVault));
            }

            // Determine active channel: prioritize user's saved choice in localStorage
            const savedActiveId = localStorage.getItem("yt_active_channel_id");
            if (savedActiveId && channels.some(c => c.channel_id === savedActiveId)) {
                currentActiveChannelId = savedActiveId;
                if (res.active_channel_id !== savedActiveId) {
                    api.selectYouTubeChannel(savedActiveId).catch(() => {});
                }
            } else {
                currentActiveChannelId = res ? (res.active_channel_id || (channels[0] ? channels[0].channel_id : null)) : null;
                if (currentActiveChannelId) {
                    localStorage.setItem("yt_active_channel_id", currentActiveChannelId);
                }
            }

            connectedChannels = channels;
            populateChannelSelect(ytChannelSelect, connectedChannels, currentActiveChannelId);
            populateChannelSelect(ytChannelSelectStep4, connectedChannels, currentActiveChannelId);
            return res;
        } catch (err) {
            console.warn("[Load YouTube Channels Error]:", err);
            return null;
        }
    }

    function populateChannelSelect(selectElem, channels, activeId) {
        if (!selectElem) return;
        selectElem.innerHTML = "";

        if (!channels || channels.length === 0) {
            const opt = document.createElement("option");
            opt.value = "";
            opt.textContent = "⚪ No Channels Linked (+ Add)";
            selectElem.appendChild(opt);
            selectElem.style.color = "#a0a5b8";
            selectElem.style.borderColor = "rgba(255, 255, 255, 0.2)";
            return;
        }

        channels.forEach(ch => {
            const opt = document.createElement("option");
            opt.value = ch.channel_id;
            const handle = ch.custom_url ? ` (${ch.custom_url})` : "";
            opt.textContent = `${ch.is_active ? "🟢" : "⚪"} ${ch.channel_title || ch.channel_id}${handle}`;
            if (ch.channel_id === activeId || ch.is_active) {
                opt.selected = true;
            }
            selectElem.appendChild(opt);
        });

        selectElem.style.color = "#00e676";
        selectElem.style.borderColor = "rgba(0, 230, 118, 0.5)";
    }

    async function handleChannelDropdownChange(channelId) {
        if (!channelId) {
            openChannelModal();
            return;
        }
        try {
            await api.selectYouTubeChannel(channelId);
            currentActiveChannelId = channelId;
            localStorage.setItem("yt_active_channel_id", channelId);
            const targetCh = connectedChannels.find(c => c.channel_id === channelId);
            const title = targetCh ? targetCh.channel_title : channelId;
            showToast(`Switched active channel to: ${title}`, "info");
            await loadYouTubeChannels();
        } catch (err) {
            showToast(`Failed to switch channel: ${err.message}`, "error");
        }
    }

    if (ytChannelSelect) {
        ytChannelSelect.addEventListener("change", (e) => {
            handleChannelDropdownChange(e.target.value);
            if (ytChannelSelectStep4) ytChannelSelectStep4.value = e.target.value;
        });
    }
    if (ytChannelSelectStep4) {
        ytChannelSelectStep4.addEventListener("change", (e) => {
            handleChannelDropdownChange(e.target.value);
            if (ytChannelSelect) ytChannelSelect.value = e.target.value;
        });
    }

    function renderChannelsModalList() {
        if (!channelsListContainer) return;
        channelsListContainer.innerHTML = "";

        if (!connectedChannels || connectedChannels.length === 0) {
            channelsListContainer.innerHTML = `
                <div style="text-align: center; padding: 24px; color: #8f95b2; font-size: 13px; background: rgba(0,0,0,0.2); border-radius: 8px;">
                    No YouTube channels connected yet.<br>Click below to link your channel or import token credentials.
                </div>
            `;
            return;
        }

        connectedChannels.forEach(ch => {
            const card = document.createElement("div");
            card.style.cssText = "display: flex; align-items: center; justify-content: space-between; padding: 12px 14px; background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; gap: 12px;";
            
            const thumb = ch.thumbnail_url 
                ? `<img src="${ch.thumbnail_url}" style="width: 38px; height: 38px; border-radius: 50%; object-fit: cover; border: 2px solid ${ch.is_active ? '#00e676' : 'rgba(255,255,255,0.2)'};">` 
                : `<div style="width: 38px; height: 38px; border-radius: 50%; background: #ff0033; display: flex; align-items: center; justify-content: center; font-size: 18px; color: #fff;">▶️</div>`;

            const activeBadge = ch.is_active 
                ? `<span style="background: rgba(0, 230, 118, 0.15); color: #00e676; border: 1px solid rgba(0, 230, 118, 0.4); font-size: 10px; font-weight: 700; padding: 2px 6px; border-radius: 10px;">ACTIVE</span>`
                : "";

            card.innerHTML = `
                <div style="display: flex; align-items: center; gap: 12px; min-width: 0;">
                    ${thumb}
                    <div style="min-width: 0;">
                        <div style="display: flex; align-items: center; gap: 6px;">
                            <span style="font-weight: 600; font-size: 14px; color: #fff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${ch.channel_title || "Unknown Channel"}</span>
                            ${activeBadge}
                        </div>
                        <div style="font-size: 11px; color: #8f95b2;">${ch.custom_url || ch.channel_id}</div>
                    </div>
                </div>
                <div style="display: flex; align-items: center; gap: 6px; flex-shrink: 0;">
                    ${!ch.is_active ? `<button class="btn-secondary btn-sm set-active-btn" data-cid="${ch.channel_id}" style="padding: 4px 8px; font-size: 11px;">Set Active</button>` : ""}
                    <a href="/api/youtube/channels/${encodeURIComponent(ch.channel_id)}/download" class="btn-secondary btn-sm" title="Download token.json file to upload directly to Render" style="padding: 4px 8px; font-size: 11px; text-decoration: none; color: #60a5fa;" download="token.json">⬇️ File</a>
                    <button class="btn-secondary btn-sm export-btn" data-cid="${ch.channel_id}" title="Copy token JSON" style="padding: 4px 8px; font-size: 11px;">📋 Copy</button>
                    <button class="btn-secondary btn-sm remove-btn" data-cid="${ch.channel_id}" title="Disconnect Channel" style="padding: 4px 8px; font-size: 11px; color: #ff5268; border-color: rgba(255, 82, 104, 0.3);">🗑️</button>
                </div>
            `;

            // Button listeners
            const setActiveBtn = card.querySelector(".set-active-btn");
            if (setActiveBtn) {
                setActiveBtn.addEventListener("click", async () => {
                    await handleChannelDropdownChange(ch.channel_id);
                    renderChannelsModalList();
                });
            }

            const exportBtn = card.querySelector(".export-btn");
            if (exportBtn) {
                exportBtn.addEventListener("click", async () => {
                    try {
                        const creds = await api.exportYouTubeToken(ch.channel_id);
                        const jsonStr = JSON.stringify(creds, null, 2);
                        try {
                            await navigator.clipboard.writeText(jsonStr);
                        } catch (clipErr) {
                            console.warn("Clipboard copy failed, using fallback:", clipErr);
                        }
                        if (tokenJsonInput) tokenJsonInput.value = jsonStr;
                        if (pasteTokenArea) pasteTokenArea.style.display = "block";
                        showToast(`Token for '${ch.channel_title}' copied! (Also placed in paste box below)`, "success", 4000);
                    } catch (e) {
                        showToast(`Export failed: ${e.message}`, "error");
                    }
                });
            }

            const removeBtn = card.querySelector(".remove-btn");
            if (removeBtn) {
                removeBtn.addEventListener("click", async () => {
                    if (confirm(`Disconnect YouTube channel '${ch.channel_title}'?`)) {
                        try {
                            await api.removeYouTubeChannel(ch.channel_id);
                            // Also purge from browser vault
                            const rawVault = localStorage.getItem("yt_channel_vault");
                            if (rawVault) {
                                try {
                                    const v = JSON.parse(rawVault);
                                    delete v[ch.channel_id];
                                    localStorage.setItem("yt_channel_vault", JSON.stringify(v));
                                } catch (e) {}
                            }
                            if (localStorage.getItem("yt_active_channel_id") === ch.channel_id) {
                                localStorage.removeItem("yt_active_channel_id");
                            }
                            showToast(`Disconnected '${ch.channel_title}'`, "info");
                            await loadYouTubeChannels();
                            renderChannelsModalList();
                        } catch (e) {
                            showToast(`Failed to remove channel: ${e.message}`, "error");
                        }
                    }
                });
            }

            channelsListContainer.appendChild(card);
        });
    }

    function openChannelModal() {
        if (!channelModalOverlay) return;
        renderChannelsModalList();
        channelModalOverlay.style.display = "flex";
    }

    function closeChannelModal() {
        if (!channelModalOverlay) return;
        channelModalOverlay.style.display = "none";
    }

    if (manageChannelsBtn) {
        manageChannelsBtn.addEventListener("click", openChannelModal);
    }
    if (closeChannelModalBtn) {
        closeChannelModalBtn.addEventListener("click", closeChannelModal);
    }
    if (channelModalOverlay) {
        channelModalOverlay.addEventListener("click", (e) => {
            if (e.target === channelModalOverlay) closeChannelModal();
        });
    }

    // Modal Action: Add via Browser OAuth (1-Click Web Redirect)
    if (addNewChannelOAuthBtn) {
        addNewChannelOAuthBtn.addEventListener("click", () => {
            showToast("Redirecting to Google Account Sign-In...", "info");
            window.location.href = "/api/youtube/oauth/login";
        });
    }

    // Modal Action: File Upload
    if (triggerTokenFileUploadBtn && uploadTokenFileInput) {
        triggerTokenFileUploadBtn.addEventListener("click", () => {
            uploadTokenFileInput.click();
        });

        uploadTokenFileInput.addEventListener("change", async (e) => {
            const file = e.target.files[0];
            if (!file) return;
            showToast(`Uploading ${file.name}...`, "info");
            try {
                const res = await api.uploadYouTubeTokenFile(file);
                if (res.success && res.channel) {
                    showToast(`Connected channel: ${res.channel.channel_title}! 🎉`, "success", 4000);
                    await loadYouTubeChannels();
                    renderChannelsModalList();
                }
            } catch (err) {
                showToast(`Failed to import file: ${err.message}`, "error");
            } finally {
                uploadTokenFileInput.value = "";
            }
        });
    }

    // Modal Action: Paste JSON toggle & submit
    if (togglePasteTokenBtn && pasteTokenArea) {
        togglePasteTokenBtn.addEventListener("click", () => {
            const isHidden = pasteTokenArea.style.display === "none";
            pasteTokenArea.style.display = isHidden ? "block" : "none";
        });
    }

    if (submitImportTokenBtn && tokenJsonInput) {
        submitImportTokenBtn.addEventListener("click", async () => {
            const raw = tokenJsonInput.value.trim();
            if (!raw) {
                showToast("Please paste token JSON before submitting.", "warning");
                return;
            }
            showToast("Validating credentials with YouTube...", "info");
            try {
                const res = await api.importYouTubeToken(raw);
                if (res.success && res.channel) {
                    showToast(`Connected channel: ${res.channel.channel_title}! 🎉`, "success", 4000);
                    tokenJsonInput.value = "";
                    if (pasteTokenArea) pasteTokenArea.style.display = "none";
                    await loadYouTubeChannels();
                    renderChannelsModalList();
                }
            } catch (err) {
                showToast(`Import error: ${err.message}`, "error");
            }
        });
    }

    // Initialize channels on page load & check OAuth return params
    loadYouTubeChannels();

    try {
        const urlParams = new URLSearchParams(window.location.search);
        const connectedChannel = urlParams.get("connected");
        const connectedChannelId = urlParams.get("channel_id");
        const oauthErr = urlParams.get("oauth_error");

        if (connectedChannel) {
            if (connectedChannelId) {
                localStorage.setItem("yt_active_channel_id", connectedChannelId);
            }
            showToast(`🎉 Connected to YouTube Channel: ${connectedChannel}!`, "success", 6000);
            window.history.replaceState({}, document.title, window.location.pathname);
            loadYouTubeChannels();
        } else if (oauthErr) {
            showToast(`YouTube OAuth Note: ${oauthErr}`, "warning", 8000);
            window.history.replaceState({}, document.title, window.location.pathname);
        }
    } catch (e) {
        console.debug("[OAuth URL Params Check]:", e);
    }

    async function triggerYouTubePublish(isFromProject = false) {
        const script = scriptInput ? scriptInput.value.trim() : "";
        if (!script && !isFromProject) {
            showToast("Please paste or write a script before publishing!", "warning");
            if (scriptInput) scriptInput.focus();
            return;
        }

        const voice = voiceSelect ? voiceSelect.value : "en-US-ChristopherNeural";
        const voiceRate = speedSelect ? speedSelect.value : "+10%";
        const subtitleStyle = document.querySelector('input[name="subtitleStyle"]:checked')?.value || "hyper_yellow";
        const bgmTrack = bgmSelect ? bgmSelect.value : "mystery_suspense";
        const bgmVol = bgmVolume ? (parseFloat(bgmVolume.value) || 0.18) : 0.18;
        
        // Pick privacy from active step or localStorage, defaulting to public
        const privacy = (isFromProject && ytPrivacySelectStep4 ? ytPrivacySelectStep4.value : null)
            || (ytPrivacySelect ? ytPrivacySelect.value : null)
            || localStorage.getItem("yt_privacy")
            || "public";

        // Pick channel from active step or active channel state
        const targetChannelId = (isFromProject && ytChannelSelectStep4 ? ytChannelSelectStep4.value : null)
            || (ytChannelSelect ? ytChannelSelect.value : null)
            || currentActiveChannelId;

        const rapid = ytPacingMode ? (ytPacingMode.value === "rapid") : true;

        // Check if visuals are already generated and ready
        if (!isFromProject) {
            let currentProj = state.project;
            const needsNewProject = !currentProj || currentProj.script !== script;

            if (needsNewProject) {
                if (oneClickPublishBtn) {
                    oneClickPublishBtn.disabled = true;
                    oneClickPublishBtn.classList.add("btn-loading");
                }
                showToast("Analyzing script & planning storyboard...", "info");
                try {
                    currentProj = await api.createProject(script, "manual", false);
                    state.setProject(currentProj);
                } catch (err) {
                    showToast(`Failed to plan storyboard: ${err.message}`, "error");
                    if (oneClickPublishBtn) {
                        oneClickPublishBtn.disabled = false;
                        oneClickPublishBtn.classList.remove("btn-loading");
                    }
                    return;
                } finally {
                    if (oneClickPublishBtn) {
                        oneClickPublishBtn.disabled = false;
                        oneClickPublishBtn.classList.remove("btn-loading");
                    }
                }
            }

            // Check if all visuals are generated and ready
            const scenes = currentProj?.scenes || [];
            const allVisualsReady = scenes.length > 0 && scenes.every(s => (s.status === "ready" || s.status === "manual") && (s.image_url || s.media_url || s.image_path));

            if (!allVisualsReady) {
                // Not all visuals are ready -> Go to Step 2 in Manual Mode to review and rectify
                goToStep(2);
                const modeManualBtn = document.getElementById("modeManualBtn");
                if (modeManualBtn) modeManualBtn.click();
                showToast("🎨 Storyboard created! Review and rectify your scene visuals below, then click Publish.", "info", 6500);
                return;
            }
        } else {
            // When publishing from Step 2 or Step 4: verify scenes have visuals
            const scenes = state.project?.scenes || [];
            const hasMissing = scenes.some(s => s.status !== "ready" && s.status !== "manual" && !s.image_url && !s.media_url && !s.image_path);
            if (hasMissing) {
                showToast("⚠️ Some scenes are still missing visuals! Click '⚡ Generate Visuals' or upload files before publishing.", "warning", 5000);
                return;
            }
        }

        if (oneClickPublishBtn) {
            oneClickPublishBtn.disabled = true;
            oneClickPublishBtn.classList.add("btn-loading");
        }
        if (publishProjectToYoutubeBtn) {
            publishProjectToYoutubeBtn.disabled = true;
            publishProjectToYoutubeBtn.classList.add("btn-loading");
        }
        const publishFromStep2Btn = document.getElementById("publishFromStep2Btn");
        if (publishFromStep2Btn) {
            publishFromStep2Btn.disabled = true;
            publishFromStep2Btn.classList.add("btn-loading");
        }

        if (progressCard) progressCard.classList.remove("hidden");
        if (playerPlaceholder) playerPlaceholder.classList.remove("hidden");
        if (playerActions) playerActions.classList.add("hidden");
        if (ytPublishedBanner) ytPublishedBanner.classList.add("hidden");
        const enableSfx = document.getElementById("ytEnableSfx") ? document.getElementById("ytEnableSfx").checked : true;
        const enableProgressBar = document.getElementById("ytProgressBar") ? document.getElementById("ytProgressBar").checked : true;
        const resolution = document.getElementById("ytResolutionSelect")?.value || "720p";

        const payload = {
            script: script,
            privacy_status: privacy,
            channel_id: targetChannelId || null,
            voice: voice,
            voice_rate: voiceRate,
            subtitle_style: subtitleStyle,
            bgm_track: bgmTrack,
            bgm_volume: bgmVol,
            rapid_pacing: rapid,
            enable_sfx: enableSfx,
            enable_progress_bar: enableProgressBar,
            resolution: resolution,
            project_id: isFromProject && state.project ? state.project.id : null
        };

        showToast("Starting 1-Click YouTube Publishing pipeline...", "info");

        try {
            const res = await api.publishToYouTube(payload);
            if (res && res.job_id) {
                state._lastJobId = res.job_id;  // persist for replace-thumbnail handler
                pollPublishJob(res.job_id);
            }
        } catch (err) {
            showToast(`Failed to start publish: ${err.message}`, "error");
            if (oneClickPublishBtn) {
                oneClickPublishBtn.disabled = false;
                oneClickPublishBtn.classList.remove("btn-loading");
            }
            if (publishProjectToYoutubeBtn) {
                publishProjectToYoutubeBtn.disabled = false;
                publishProjectToYoutubeBtn.classList.remove("btn-loading");
            }
            const pStep2 = document.getElementById("publishFromStep2Btn");
            if (pStep2) {
                pStep2.disabled = false;
                pStep2.classList.remove("btn-loading");
            }
            if (progressCard) progressCard.classList.add("hidden");
        }
    }

    if (oneClickPublishBtn) {
        oneClickPublishBtn.addEventListener("click", () => triggerYouTubePublish(false));
    }

    if (publishProjectToYoutubeBtn) {
        publishProjectToYoutubeBtn.addEventListener("click", () => triggerYouTubePublish(true));
    }

    const publishFromStep2BtnElem = document.getElementById("publishFromStep2Btn");
    if (publishFromStep2BtnElem) {
        publishFromStep2BtnElem.addEventListener("click", () => triggerYouTubePublish(true));
    }

    function pollPublishJob(jobId) {
        const interval = setInterval(async () => {
            try {
                const job = await api.pollJob(jobId);
                if (!job) return;

                const pct = job.progress || 0;
                if (progressPct) progressPct.textContent = `${pct}%`;
                if (progressBar) progressBar.style.width = `${pct}%`;
                if (progressStatus) progressStatus.textContent = job.status === "processing" ? "Publishing to YouTube..." : job.status;
                if (progressStep) progressStep.textContent = job.message || "Working...";

                if (job.status === "completed") {
                    clearInterval(interval);
                    if (oneClickPublishBtn) {
                        oneClickPublishBtn.disabled = false;
                        oneClickPublishBtn.classList.remove("btn-loading");
                    }
                    if (publishProjectToYoutubeBtn) {
                        publishProjectToYoutubeBtn.disabled = false;
                        publishProjectToYoutubeBtn.classList.remove("btn-loading");
                    }
                    const pStep2 = document.getElementById("publishFromStep2Btn");
                    if (pStep2) {
                        pStep2.disabled = false;
                        pStep2.classList.remove("btn-loading");
                    }
                    if (progressCard) progressCard.classList.add("hidden");

                    // Load video player
                    if (finalVideoPlayer && job.video_url) {
                        finalVideoPlayer.src = job.video_url;
                        finalVideoPlayer.classList.add("visible", "active");
                        finalVideoPlayer.style.display = "block";
                        if (playerPlaceholder) playerPlaceholder.classList.add("hidden");
                        finalVideoPlayer.load();
                        try { finalVideoPlayer.play(); } catch(e) {}
                    }

                    if (playerActions) playerActions.classList.remove("hidden");
                    if (downloadVideoBtn && job.video_url) {
                        downloadVideoBtn.href = job.video_url;
                    }
                    const downloadThumbBtn = document.getElementById("downloadThumbBtn");
                    const replaceThumbnailBtn = document.getElementById("replaceThumbnailBtn");
                    const thumbnailPreviewArea = document.getElementById("thumbnailPreviewArea");
                    const thumbnailPreviewImg = document.getElementById("thumbnailPreviewImg");
                    if (job.thumbnail_url) {
                        if (downloadThumbBtn) {
                            downloadThumbBtn.href = job.thumbnail_url;
                            downloadThumbBtn.classList.remove("hidden");
                            downloadThumbBtn.style.display = "flex";
                        }
                        if (replaceThumbnailBtn) replaceThumbnailBtn.classList.remove("hidden");
                        if (thumbnailPreviewArea && thumbnailPreviewImg) {
                            thumbnailPreviewImg.src = job.thumbnail_url + "?t=" + Date.now();
                            thumbnailPreviewArea.classList.remove("hidden");
                        }
                    } else {
                        if (downloadThumbBtn) { downloadThumbBtn.classList.add("hidden"); downloadThumbBtn.style.display = "none"; }
                        if (replaceThumbnailBtn) replaceThumbnailBtn.classList.add("hidden");
                        if (thumbnailPreviewArea) thumbnailPreviewArea.classList.add("hidden");
                    }


                    // Populate SEO kit
                    if (job.metadata && seoKitCard) {
                        seoKitCard.classList.remove("hidden");
                        if (seoTitle) seoTitle.value = job.metadata.title || "";
                        if (seoDesc) seoDesc.value = job.metadata.description || "";
                        if (seoTags) seoTags.value = Array.isArray(job.metadata.tags) ? job.metadata.tags.join(", ") : (job.metadata.tags || "");
                    }

                    // Handle YouTube published state
                    if (job.youtube_published && job.youtube_url) {
                        const actualPriv = (job.actual_privacy_status || job.privacy_status || "unlisted").toLowerCase();
                        const reqPriv = (job.privacy_status || "public").toLowerCase();
                        const editInStudioBtn = document.getElementById("editInStudioBtn");
                        const ytPrivacyNotice = document.getElementById("ytPrivacyNotice");
                        const ytPublishedSubtext = document.getElementById("ytPublishedSubtext");

                        showToast(`🎉 Short Published to YouTube as ${actualPriv.toUpperCase()}!`, "success", 5000);
                        if (ytPublishedBanner) {
                            ytPublishedBanner.classList.remove("hidden");
                            if (ytVideoUrlInput) ytVideoUrlInput.value = job.youtube_url;
                            if (openYtLinkBtn) openYtLinkBtn.href = job.youtube_url;
                            if (editInStudioBtn && job.video_id) {
                                editInStudioBtn.href = `https://studio.youtube.com/video/${job.video_id}/edit`;
                            }
                            if (ytPublishedSubtext) {
                                const targetChName = job.channel_title ? ` on <strong>${job.channel_title}</strong>` : "";
                                ytPublishedSubtext.innerHTML = `Your Short is live on YouTube${targetChName}! Privacy: <strong style="color: #00e676;">${actualPriv.toUpperCase()}</strong>`;
                            }
                            if (ytPrivacyNotice) {
                                if (reqPriv === "public" && actualPriv !== "public") {
                                    ytPrivacyNotice.style.display = "block";
                                    ytPrivacyNotice.innerHTML = `⚠️ <strong>Note from YouTube:</strong> Because this video was uploaded from a private developer project, YouTube initially set it to <strong>${actualPriv}</strong>. Click <a href="https://studio.youtube.com/video/${job.video_id}/edit" target="_blank" style="color: #60a5fa; text-decoration: underline; font-weight: 600;">Edit in Studio</a> to switch it to Public with 1-click!`;
                                } else {
                                    ytPrivacyNotice.style.display = "none";
                                }
                            }
                        }
                        if (viewYouTubeBtn) {
                            viewYouTubeBtn.classList.remove("hidden");
                            viewYouTubeBtn.href = job.youtube_url;
                        }
                    } else if (job.youtube_auth_needed) {
                        showToast("Video rendered! Connect YouTube to auto-upload next time.", "warning", 6000);
                    } else if (job.youtube_error) {
                        showToast(`Video rendered! YouTube upload note: ${job.youtube_error}`, "warning", 6000);
                    } else {
                        showToast("Video generated successfully!", "success");
                    }
                } else if (job.status === "error") {
                    clearInterval(interval);
                    if (oneClickPublishBtn) {
                        oneClickPublishBtn.disabled = false;
                        oneClickPublishBtn.classList.remove("btn-loading");
                    }
                    if (publishProjectToYoutubeBtn) {
                        publishProjectToYoutubeBtn.disabled = false;
                        publishProjectToYoutubeBtn.classList.remove("btn-loading");
                    }
                    const pStep2 = document.getElementById("publishFromStep2Btn");
                    if (pStep2) {
                        pStep2.disabled = false;
                        pStep2.classList.remove("btn-loading");
                    }
                    showToast(`Error: ${job.message || "Operation failed"}`, "error");
                }
            } catch (err) {
                console.error("[Poll Publish Error]:", err);
            }
        }, 1500);
    }
});

