/**
 * static/js/capcut_timeline.js - CapCut-Style Multi-Track Timeline & Synced Video Editor
 */

import { api } from "./api.js";
import { state } from "./state.js";

export class CapCutTimelineEditor {
    constructor(elements, showToast) {
        this.el = elements;
        this.showToast = showToast;
        this.activeSceneId = null;
        this.isPlaying = false;
        this.pixelsPerSecond = 80; // Default zoom scale (px per second)
        this.animFrameId = null;
        this.searchTargetSceneId = null;

        this.initDOM();
        this.initListeners();
    }

    initDOM() {
        // Cache references
        this.container = document.getElementById("capcutEditorContainer");
        this.monitorVideo = document.getElementById("capcutCanvasVideo");
        this.monitorImg = document.getElementById("capcutCanvasImg");
        this.placeholder = document.getElementById("capcutCanvasPlaceholder");
        this.subtitleOverlay = document.getElementById("capcutSubtitleOverlay");

        // Transport
        this.playBtn = document.getElementById("capcutPlayBtn");
        this.rwBtn = document.getElementById("capcutRwBtn");
        this.fwBtn = document.getElementById("capcutFwBtn");
        this.timecodeBadge = document.getElementById("capcutCurrentTime");

        // Inspector
        this.inspectorHeader = document.getElementById("capcutInspectorHeader");
        this.inspectorText = document.getElementById("capcutInspectorText");
        this.saveTextBtn = document.getElementById("capcutSaveTextBtn");
        this.durationInput = document.getElementById("capcutDurationInput");
        this.durMinusBtn = document.getElementById("capcutDurMinusBtn");
        this.durPlusBtn = document.getElementById("capcutDurPlusBtn");
        this.findVideoBtn = document.getElementById("capcutFindVideoBtn");
        this.genFluxBtn = document.getElementById("capcutGenFluxBtn");
        this.uploadBtn = document.getElementById("capcutUploadBtn");
        this.uploadInput = document.getElementById("capcutUploadInput");
        this.splitBtn = document.getElementById("capcutSplitBtn");
        this.clearMediaBtn = document.getElementById("capcutClearMediaBtn");

        // Screen frame for live CSS filter preview
        this.screenFrame = document.querySelector(".capcut-screen-frame");

        // Tabs
        this.tabBtnInspector = document.getElementById("capcutTabBtnInspector");
        this.tabBtnAutoSync = document.getElementById("capcutTabBtnAutoSync");
        this.tabBtnProTools = document.getElementById("capcutTabBtnProTools");
        this.panelInspector = document.getElementById("capcutPanelInspector");
        this.panelAutoSync = document.getElementById("capcutPanelAutoSync");
        this.panelProTools = document.getElementById("capcutPanelProTools");

        // Auto-Sync elements
        this.voiceLockBtn = document.getElementById("capcutVoiceLockBtn");
        this.viralPaceBtn = document.getElementById("capcutViralPaceBtn");
        this.maxCutSelect = document.getElementById("capcutMaxCutSelect");
        this.retentionBadge = document.getElementById("capcutRetentionBadge");
        this.statTotalDur = document.getElementById("capcutStatTotalDur");
        this.statSceneCount = document.getElementById("capcutStatSceneCount");
        this.statAvgPace = document.getElementById("capcutStatAvgPace");
        this.statLongest = document.getElementById("capcutStatLongest");

        // Pro Tools elements
        this.splitAtPlayheadBtn = document.getElementById("capcutSplitAtPlayheadBtn");
        this.smartMatchAllBtn = document.getElementById("capcutSmartMatchAllBtn");
        this.forceMatchAllCheck = document.getElementById("capcutForceMatchAllCheck");
        this.colorFilterSelect = document.getElementById("capcutColorFilterSelect");

        // Toolbar quick-access
        this.toolbarSplitBtn = document.getElementById("capcutToolbarSplitBtn");

        // Timeline tracks
        this.viewport = document.getElementById("capcutTimelineViewport");
        this.rulerTrack = document.getElementById("capcutRulerTrack");
        this.visualsTrack = document.getElementById("capcutVisualsTrack");
        this.audioTrack = document.getElementById("capcutAudioTrack");
        this.playhead = document.getElementById("capcutPlayhead");

        // Zoom & Stitch
        this.zoomInBtn = document.getElementById("capcutZoomInBtn");
        this.zoomOutBtn = document.getElementById("capcutZoomOutBtn");
        this.stitchBtn = document.getElementById("capcutStitchBtn");

        // Audio element for voice playback
        this.audioEl = document.getElementById("standaloneVoiceAudio") || document.getElementById("voiceAudioPreview");

        // Stock Modal
        this.stockModal = document.getElementById("stockSearchModal");
        this.closeStockModal = document.getElementById("closeStockSearchModal");
        this.stockInput = document.getElementById("stockSearchInput");
        this.stockSubmit = document.getElementById("stockSearchSubmitBtn");
        this.stockGrid = document.getElementById("stockSearchResultsGrid");
        this.stockContext = document.getElementById("stockSearchSceneContext");
    }

    initListeners() {
        // State updates
        state.on("project_updated", (proj) => {
            if (this.isVisible()) {
                this.render(proj);
            }
        });

        // Tab switching
        if (this.tabBtnInspector) {
            this.tabBtnInspector.addEventListener("click", () => this.switchTab("inspector"));
        }
        if (this.tabBtnAutoSync) {
            this.tabBtnAutoSync.addEventListener("click", () => this.switchTab("autoSync"));
        }
        if (this.tabBtnProTools) {
            this.tabBtnProTools.addEventListener("click", () => this.switchTab("proTools"));
        }

        // Toolbar quick actions
        if (this.toolbarSplitBtn) {
            this.toolbarSplitBtn.addEventListener("click", () => this.handleSplitAtPlayhead());
        }

        // Auto-Sync actions
        if (this.voiceLockBtn) {
            this.voiceLockBtn.addEventListener("click", () => this.handleAutoSync("voice_lock"));
        }
        if (this.viralPaceBtn) {
            this.viralPaceBtn.addEventListener("click", () => {
                const maxDur = parseFloat(this.maxCutSelect?.value) || 2.8;
                this.handleAutoSync("rapid_cuts", maxDur);
            });
        }

        // Pro Tools actions
        if (this.splitAtPlayheadBtn) {
            this.splitAtPlayheadBtn.addEventListener("click", () => this.handleSplitAtPlayhead());
        }
        if (this.smartMatchAllBtn) {
            this.smartMatchAllBtn.addEventListener("click", () => this.handleSmartMatchAll());
        }
        if (this.colorFilterSelect) {
            this.colorFilterSelect.addEventListener("change", (e) => this.handleColorFilterChange(e.target.value));
        }
        if (this.clearMediaBtn) {
            this.clearMediaBtn.addEventListener("click", () => this.handleClearMedia());
        }

        // Transport controls
        if (this.playBtn) {
            this.playBtn.addEventListener("click", () => this.togglePlay());
        }
        if (this.rwBtn) {
            this.rwBtn.addEventListener("click", () => this.seekBy(-1.0));
        }
        if (this.fwBtn) {
            this.fwBtn.addEventListener("click", () => this.seekBy(1.0));
        }

        // Global Keyboard shortcuts: Space for Play/Pause, S for Split at playhead
        document.addEventListener("keydown", (e) => {
            if (!this.isVisible()) return;
            if (e.target.tagName === "TEXTAREA" || e.target.tagName === "INPUT") return;

            if (e.code === "Space") {
                e.preventDefault();
                this.togglePlay();
            } else if (e.key === "s" || e.key === "S") {
                e.preventDefault();
                this.handleSplitAtPlayhead();
            }
        });

        // Ruler scrubbing / click to seek
        if (this.rulerTrack) {
            this.rulerTrack.addEventListener("mousedown", (e) => this.handleRulerScrub(e));
        }

        // Zoom controls
        if (this.zoomInBtn) {
            this.zoomInBtn.addEventListener("click", () => {
                this.pixelsPerSecond = Math.min(200, this.pixelsPerSecond + 20);
                this.render(state.project);
            });
        }
        if (this.zoomOutBtn) {
            this.zoomOutBtn.addEventListener("click", () => {
                this.pixelsPerSecond = Math.max(30, this.pixelsPerSecond - 20);
                this.render(state.project);
            });
        }

        // Inspector actions
        if (this.saveTextBtn && this.inspectorText) {
            this.saveTextBtn.addEventListener("click", async () => {
                if (!state.project || !this.activeSceneId) return;
                const newText = this.inspectorText.value.trim();
                try {
                    const updated = await api.editText(state.project.id, this.activeSceneId, newText);
                    state.setProject(updated);
                    this.showToast("Scene narration updated!", "success");
                } catch (err) {
                    this.showToast(`Failed to update text: ${err.message}`, "error");
                }
            });
        }

        // Duration adjustments
        if (this.durMinusBtn) {
            this.durMinusBtn.addEventListener("click", () => this.nudgeDuration(-0.5));
        }
        if (this.durPlusBtn) {
            this.durPlusBtn.addEventListener("click", () => this.nudgeDuration(0.5));
        }
        if (this.durationInput) {
            this.durationInput.addEventListener("change", () => {
                const val = parseFloat(this.durationInput.value);
                if (val && val >= 0.5) this.setDuration(val);
            });
        }

        // Visual replacement tools
        if (this.findVideoBtn) {
            this.findVideoBtn.addEventListener("click", () => this.openStockSearch(this.activeSceneId));
        }
        if (this.genFluxBtn) {
            this.genFluxBtn.addEventListener("click", async () => {
                if (!state.project || !this.activeSceneId) return;
                this.showToast("Generating visual via FLUX...", "info");
                try {
                    const updated = await api.generateSceneMedia(state.project.id, this.activeSceneId);
                    state.setProject(updated);
                    this.showToast("FLUX visual generated!", "success");
                } catch (err) {
                    this.showToast(`Generation failed: ${err.message}`, "error");
                }
            });
        }
        if (this.uploadBtn && this.uploadInput) {
            this.uploadBtn.addEventListener("click", () => this.uploadInput.click());
            this.uploadInput.addEventListener("change", async (e) => {
                const file = e.target.files[0];
                if (!file || !state.project || !this.activeSceneId) return;
                this.showToast("Uploading media...", "info");
                try {
                    const updated = await api.uploadMedia(state.project.id, this.activeSceneId, file);
                    state.setProject(updated);
                    this.showToast("Uploaded media successfully!", "success");
                } catch (err) {
                    this.showToast(`Upload failed: ${err.message}`, "error");
                } finally {
                    this.uploadInput.value = "";
                }
            });
        }

        if (this.splitBtn) {
            this.splitBtn.addEventListener("click", () => {
                if (this.activeSceneId) {
                    state.emit("split_modal_requested", this.activeSceneId);
                }
            });
        }

        // Stock Search Modal
        if (this.closeStockModal) {
            this.closeStockModal.addEventListener("click", () => this.closeStockSearch());
        }
        if (this.stockModal) {
            this.stockModal.addEventListener("click", (e) => {
                if (e.target === this.stockModal) this.closeStockSearch();
            });
        }
        if (this.stockSubmit && this.stockInput) {
            this.stockSubmit.addEventListener("click", () => this.executeStockSearch());
            this.stockInput.addEventListener("keydown", (e) => {
                if (e.key === "Enter") this.executeStockSearch();
            });
        }

        // Manual Stitch button
        if (this.stitchBtn) {
            this.stitchBtn.addEventListener("click", () => this.handleStitchTimeline());
        }
    }

    isVisible() {
        return this.container && !this.container.classList.contains("hidden");
    }

    render(project) {
        if (!project || !project.scenes || project.scenes.length === 0) return;

        const scenes = project.scenes;
        const totalDuration = project.total_duration || scenes.reduce((acc, s) => acc + (s.duration || 3.0), 0);
        const totalWidth = Math.max(800, totalDuration * this.pixelsPerSecond);

        // Resize track viewport
        if (this.rulerTrack) this.rulerTrack.style.width = `${totalWidth}px`;
        if (this.visualsTrack) this.visualsTrack.style.width = `${totalWidth}px`;
        if (this.audioTrack) this.audioTrack.style.width = `${totalWidth}px`;

        // 1. Render Time Ruler
        this.renderRuler(totalDuration, totalWidth);

        // 2. Render Visuals Track
        this.renderVisualsTrack(scenes);

        // 3. Render Audio Track
        this.renderAudioTrack(project, totalDuration);

        // If no active scene selected, select first scene
        if (!this.activeSceneId || !scenes.some(s => s.id === this.activeSceneId)) {
            this.selectScene(scenes[0].id);
        } else {
            const currentScene = scenes.find(s => s.id === this.activeSceneId);
            this.updateInspector(currentScene);
            this.updateCanvasMedia(currentScene);
        }

        // Update timecode readout
        this.updateTimecode(this.getCurrentTime(), totalDuration);

        // Sync color filter & LUT
        if (project.color_filter) {
            if (this.colorFilterSelect) this.colorFilterSelect.value = project.color_filter;
            if (this.screenFrame) this.screenFrame.dataset.filter = project.color_filter;
        }

        // Update Retention & Pacing health stats
        this.updatePacingStats(project);
    }

    renderRuler(totalDuration, totalWidth) {
        if (!this.rulerTrack) return;
        this.rulerTrack.innerHTML = "";

        // Add tick marks every second (or 2 seconds depending on zoom)
        const step = this.pixelsPerSecond < 50 ? 2.0 : 1.0;
        for (let t = 0; t <= totalDuration + step; t += step) {
            const left = t * this.pixelsPerSecond;
            const tick = document.createElement("div");
            const isMajor = Math.round(t) % 2 === 0;
            tick.className = `capcut-ruler-tick ${isMajor ? "major" : ""}`;
            tick.style.left = `${left}px`;

            const mins = Math.floor(t / 60);
            const secs = Math.floor(t % 60);
            tick.textContent = isMajor ? `${mins}:${secs < 10 ? '0' : ''}${secs}` : '';
            this.rulerTrack.appendChild(tick);
        }
    }

    renderVisualsTrack(scenes) {
        if (!this.visualsTrack) return;
        this.visualsTrack.innerHTML = "";

        let cumTime = 0.0;
        scenes.forEach((sc, idx) => {
            const dur = sc.duration || 3.0;
            const left = cumTime * this.pixelsPerSecond;
            const width = Math.max(30, dur * this.pixelsPerSecond);

            const block = document.createElement("div");
            block.className = `capcut-clip-block ${sc.id === this.activeSceneId ? "selected" : ""}`;
            block.style.left = `${left}px`;
            block.style.width = `${width}px`;
            block.dataset.sceneId = sc.id;
            block.dataset.startTime = cumTime;
            block.dataset.duration = dur;

            // Thumbnail or icon
            const mediaUrl = sc.media_url || sc.image_url;
            const isVid = (sc.media_type === "video" || (mediaUrl && mediaUrl.endsWith(".mp4")));
            let thumbHtml = "";
            if (mediaUrl) {
                if (isVid) {
                    thumbHtml = `<video src="${mediaUrl}#t=0.5" class="capcut-clip-thumb" preload="metadata" muted></video>`;
                } else {
                    thumbHtml = `<img src="${mediaUrl}" class="capcut-clip-thumb" alt="Clip ${idx+1}">`;
                }
            } else {
                thumbHtml = `<div class="capcut-clip-thumb" style="display:flex;align-items:center;justify-content:center;background:#1e293b;color:#64748b;font-size:16px;">🎬</div>`;
            }

            block.innerHTML = `
                ${thumbHtml}
                <div class="capcut-clip-info">
                    <span class="capcut-clip-badge">Scene ${idx + 1} • ${dur.toFixed(1)}s</span>
                    <span class="capcut-clip-text">${sc.text || ''}</span>
                </div>
            `;

            block.addEventListener("click", () => {
                this.selectScene(sc.id);
                this.seekTo(parseFloat(block.dataset.startTime));
            });

            this.visualsTrack.appendChild(block);
            cumTime += dur;
        });
    }

    renderAudioTrack(project, totalDuration) {
        if (!this.audioTrack) return;
        this.audioTrack.innerHTML = "";

        const tl = project.timeline;
        const segments = (tl && tl.scenes) ? tl.scenes : project.scenes.map((s, idx) => ({
            scene_id: s.id,
            scene_index: idx,
            start: idx * 3.0,
            end: (idx + 1) * 3.0,
            duration: s.duration || 3.0,
            text: s.text
        }));

        segments.forEach((seg, idx) => {
            const start = seg.start || 0;
            const dur = seg.duration || 3.0;
            const left = start * this.pixelsPerSecond;
            const width = Math.max(30, dur * this.pixelsPerSecond);

            const aBlock = document.createElement("div");
            aBlock.className = "capcut-audio-block";
            aBlock.style.left = `${left}px`;
            aBlock.style.width = `${width}px`;
            aBlock.title = `VO Scene ${idx + 1} (${dur.toFixed(1)}s): ${seg.text || ''}`;
            aBlock.innerHTML = `
                <span>🎙️</span>
                <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">Line ${idx + 1}: ${seg.text || ''}</span>
            `;

            aBlock.addEventListener("click", () => {
                this.seekTo(start);
            });

            this.audioTrack.appendChild(aBlock);
        });
    }

    selectScene(sceneId) {
        this.activeSceneId = sceneId;
        state.focusedSceneId = sceneId;

        // Highlight block
        const blocks = this.visualsTrack?.querySelectorAll(".capcut-clip-block");
        blocks?.forEach(b => {
            if (b.dataset.sceneId === sceneId) {
                b.classList.add("selected");
            } else {
                b.classList.remove("selected");
            }
        });

        const target = state.project?.scenes.find(s => s.id === sceneId);
        if (target) {
            this.updateInspector(target);
            this.updateCanvasMedia(target);
        }
    }

    updateInspector(scene) {
        if (!scene) return;
        const scenes = state.project?.scenes || [];
        const idx = scenes.findIndex(s => s.id === scene.id);

        if (this.inspectorHeader) {
            this.inspectorHeader.textContent = `Scene ${idx + 1} of ${scenes.length}`;
        }
        if (this.inspectorText) {
            this.inspectorText.value = scene.text || "";
        }
        if (this.durationInput) {
            this.durationInput.value = (scene.duration || 3.0).toFixed(1);
        }
    }

    updateCanvasMedia(scene) {
        if (!scene) return;
        const mediaUrl = scene.media_url || scene.image_url;
        const isVid = (scene.media_type === "video" || (mediaUrl && (mediaUrl.endsWith(".mp4") || mediaUrl.includes(".mp4"))));

        if (mediaUrl) {
            if (this.placeholder) this.placeholder.classList.add("hidden");
            if (isVid) {
                if (this.monitorImg) this.monitorImg.classList.add("hidden");
                if (this.monitorVideo) {
                    this.monitorVideo.classList.remove("hidden");
                    if (this.monitorVideo.src !== mediaUrl && !this.monitorVideo.src.endsWith(mediaUrl)) {
                        this.monitorVideo.src = mediaUrl;
                    }
                    if (this.isPlaying) {
                        this.monitorVideo.play().catch(() => {});
                    }
                }
            } else {
                if (this.monitorVideo) {
                    this.monitorVideo.classList.add("hidden");
                    this.monitorVideo.pause();
                }
                if (this.monitorImg) {
                    this.monitorImg.classList.remove("hidden");
                    this.monitorImg.src = mediaUrl;
                }
            }
        } else {
            if (this.monitorVideo) {
                this.monitorVideo.classList.add("hidden");
                this.monitorVideo.pause();
            }
            if (this.monitorImg) this.monitorImg.classList.add("hidden");
            if (this.placeholder) this.placeholder.classList.remove("hidden");
        }

        if (this.subtitleOverlay) {
            this.subtitleOverlay.textContent = scene.text || "";
        }
    }

    // Playback & Synchronization Loop
    togglePlay() {
        if (this.isPlaying) {
            this.pause();
        } else {
            this.play();
        }
    }

    play() {
        const totalDur = state.project?.total_duration || 
            (state.project?.scenes ? state.project.scenes.reduce((acc, s) => acc + (s.duration || 3.0), 0) : 20.0);
        
        // If already at or very near end, restart from beginning
        if (this.getCurrentTime() >= totalDur - 0.1) {
            this.seekTo(0);
        }

        const audio = this.getAudioElement();
        if (audio && audio.src) {
            audio.play().catch(() => {});
        }
        if (this.monitorVideo && !this.monitorVideo.classList.contains("hidden")) {
            this.monitorVideo.play().catch(() => {});
        }

        this.isPlaying = true;
        if (this.playBtn) this.playBtn.innerHTML = "⏸";
        this.startSyncLoop();
    }

    pause() {
        const audio = this.getAudioElement();
        if (audio) audio.pause();
        if (this.monitorVideo) this.monitorVideo.pause();

        this.isPlaying = false;
        if (this.playBtn) this.playBtn.innerHTML = "▶";
        if (this.animFrameId) {
            cancelAnimationFrame(this.animFrameId);
            this.animFrameId = null;
        }
    }

    startSyncLoop() {
        if (this.animFrameId) {
            cancelAnimationFrame(this.animFrameId);
            this.animFrameId = null;
        }

        let lastWallTime = performance.now();

        const tick = (now) => {
            if (!this.isPlaying) return;

            const delta = Math.max(0, (now - lastWallTime) / 1000);
            lastWallTime = now;

            const audio = this.getAudioElement();
            const totalDur = state.project?.total_duration || 
                (state.project?.scenes ? state.project.scenes.reduce((acc, s) => acc + (s.duration || 3.0), 0) : 20.0);

            let curTime;
            // If voiceover audio is active and playing, use audio.currentTime as the master sync clock
            if (audio && audio.src && !audio.paused && !audio.ended && !isNaN(audio.currentTime)) {
                curTime = audio.currentTime;
                this._simulatedTime = curTime;
            } else {
                // Standby mode or video without VO: advance simulated time smoothly by frame delta
                this._simulatedTime = (this._simulatedTime || 0.0) + delta;
                curTime = this._simulatedTime;
            }

            if (curTime >= totalDur) {
                this.pause();
                this.seekTo(0);
                return;
            }

            this.updatePlayheadPosition(curTime);
            this.syncSceneAtTime(curTime);
            this.updateTimecode(curTime, totalDur);

            this.animFrameId = requestAnimationFrame(tick);
        };
        this.animFrameId = requestAnimationFrame(tick);
    }

    getCurrentTime() {
        const audio = this.getAudioElement();
        if (audio && audio.src && !audio.paused && !audio.ended && !isNaN(audio.currentTime)) {
            return audio.currentTime;
        }
        return this._simulatedTime || 0.0;
    }

    seekTo(targetSeconds) {
        const audio = this.getAudioElement();
        const safeT = Math.max(0, targetSeconds);
        this._simulatedTime = safeT;
        if (audio && audio.src) {
            try {
                audio.currentTime = safeT;
            } catch (e) {}
        }

        this.updatePlayheadPosition(safeT);
        this.syncSceneAtTime(safeT);
        const totalDur = state.project?.total_duration || 
            (state.project?.scenes ? state.project.scenes.reduce((acc, s) => acc + (s.duration || 3.0), 0) : 20.0);
        this.updateTimecode(safeT, totalDur);
    }

    seekBy(deltaSeconds) {
        this.seekTo(this.getCurrentTime() + deltaSeconds);
    }

    updatePlayheadPosition(time) {
        if (!this.playhead) return;
        const left = time * this.pixelsPerSecond;
        this.playhead.style.left = `${left}px`;
    }

    syncSceneAtTime(time) {
        const scenes = state.project?.scenes || [];
        let cum = 0.0;
        let activeSc = null;
        let sceneStartTime = 0.0;

        for (const sc of scenes) {
            const dur = sc.duration || 3.0;
            if (time >= cum && time < (cum + dur)) {
                activeSc = sc;
                sceneStartTime = cum;
                break;
            }
            cum += dur;
        }

        if (!activeSc && scenes.length > 0) {
            activeSc = scenes[scenes.length - 1];
            sceneStartTime = Math.max(0, cum - (activeSc.duration || 3.0));
        }

        if (activeSc) {
            if (activeSc.id !== this.activeSceneId) {
                this.selectScene(activeSc.id);
            }
            // Sync monitor video offset if a video clip is active
            if (this.monitorVideo && !this.monitorVideo.classList.contains("hidden")) {
                const clipOffset = Math.max(0, time - sceneStartTime);
                if (!this.isPlaying || Math.abs(this.monitorVideo.currentTime - clipOffset) > 0.3) {
                    try {
                        this.monitorVideo.currentTime = clipOffset;
                    } catch (e) {}
                }
            }
        }
    }

    handleRulerScrub(e) {
        if (!this.rulerTrack) return;
        const rect = this.rulerTrack.getBoundingClientRect();
        const clickX = e.clientX - rect.left;
        const targetTime = Math.max(0, clickX / this.pixelsPerSecond);
        this.seekTo(targetTime);

        const onMouseMove = (moveEvent) => {
            const curX = moveEvent.clientX - rect.left;
            const t = Math.max(0, curX / this.pixelsPerSecond);
            this.seekTo(t);
        };
        const onMouseUp = () => {
            window.removeEventListener("mousemove", onMouseMove);
            window.removeEventListener("mouseup", onMouseUp);
        };
        window.addEventListener("mousemove", onMouseMove);
        window.addEventListener("mouseup", onMouseUp);
    }

    updateTimecode(cur, total) {
        if (!this.timecodeBadge) return;
        const fmt = (s) => {
            const m = Math.floor(s / 60);
            const sec = (s % 60).toFixed(1);
            return `${m}:${sec < 10 ? '0' : ''}${sec}`;
        };
        this.timecodeBadge.textContent = `${fmt(cur)} / ${fmt(total)}`;
    }

    getAudioElement() {
        const audio = document.getElementById("standaloneVoiceAudio") || document.getElementById("voiceAudioPreview");
        return audio;
    }

    async nudgeDuration(delta) {
        if (!state.project || !this.activeSceneId) return;
        const sc = state.project.scenes.find(s => s.id === this.activeSceneId);
        if (!sc) return;
        const newDur = Math.max(0.8, (sc.duration || 3.0) + delta);
        await this.setDuration(newDur);
    }

    async setDuration(val) {
        if (!state.project || !this.activeSceneId) return;
        try {
            const updated = await api.editDuration(state.project.id, this.activeSceneId, val);
            state.setProject(updated);
            this.showToast(`Scene duration updated to ${val.toFixed(1)}s`, "success");
        } catch (err) {
            this.showToast(`Failed to update duration: ${err.message}`, "error");
        }
    }

    // Pexels Stock Video Search Modal
    openStockSearch(sceneId) {
        if (!sceneId || !state.project) return;
        this.searchTargetSceneId = sceneId;
        const sc = state.project.scenes.find(s => s.id === sceneId);
        if (!sc) return;

        if (this.stockContext) {
            this.stockContext.textContent = `Finding visuals for Scene duration: ${(sc.duration || 3.0).toFixed(1)}s • "${sc.text || ''}"`;
        }

        // Auto-fill query from keywords or text
        let initialQuery = (sc.search_queries && sc.search_queries[0]) ||
                           (sc.broll_keywords && sc.broll_keywords[0]) ||
                           sc.text.split(' ').slice(0, 4).join(' ');

        if (this.stockInput) {
            this.stockInput.value = initialQuery;
        }

        if (this.stockModal) this.stockModal.classList.remove("hidden");
        this.executeStockSearch();
    }

    closeStockSearch() {
        if (this.stockModal) this.stockModal.classList.add("hidden");
        this.searchTargetSceneId = null;
    }

    async executeStockSearch() {
        const q = this.stockInput?.value.trim();
        if (!q || !this.stockGrid) return;

        this.stockGrid.innerHTML = `
            <div style="grid-column: 1/-1; text-align: center; padding: 40px; color: #94a3b8;">
                <div class="spinner" style="margin: 0 auto 12px auto;"></div>
                <span>Searching vertical stock clips on Pexels for "${q}"...</span>
            </div>
        `;

        try {
            const data = await api.searchStockVideos(q, 12, "portrait");
            const results = data.results || [];
            if (results.length === 0) {
                this.stockGrid.innerHTML = `
                    <div style="grid-column: 1/-1; text-align: center; padding: 40px; color: #94a3b8;">
                        No vertical videos found for "${q}". Try another query like "foggy night", "ocean storm", or "airplane cockpit".
                    </div>
                `;
                return;
            }

            this.stockGrid.innerHTML = "";
            results.forEach(v => {
                const card = document.createElement("div");
                card.className = "stock-candidate-card";

                const thumb = v.thumbnail || "";
                const dur = v.duration ? `${v.duration.toFixed(1)}s` : "";
                const dlUrl = v.download_url || "";

                card.innerHTML = `
                    <div style="position: relative;">
                        <img src="${thumb}" class="stock-candidate-preview" alt="Pexels Video ${v.id}">
                        ${dur ? `<span class="stock-candidate-dur">${dur}</span>` : ''}
                    </div>
                    <div class="stock-candidate-actions">
                        <button type="button">✔ Use This Clip</button>
                    </div>
                `;

                card.querySelector("button").addEventListener("click", async () => {
                    if (!state.project || !this.searchTargetSceneId) return;
                    this.showToast("Downloading and assigning stock clip to scene...", "info");
                    try {
                        const updated = await api.assignStockVideo(state.project.id, this.searchTargetSceneId, v.id, dlUrl);
                        state.setProject(updated);
                        this.showToast("Stock video assigned to scene!", "success");
                        this.closeStockSearch();
                    } catch (err) {
                        this.showToast(`Failed to assign clip: ${err.message}`, "error");
                    }
                });

                this.stockGrid.appendChild(card);
            });
        } catch (err) {
            this.stockGrid.innerHTML = `
                <div style="grid-column: 1/-1; text-align: center; padding: 40px; color: #ff334b;">
                    Search failed: ${err.message}
                </div>
            `;
        }
    }

    // Manual Stitch Timeline & Render
    handleStitchTimeline() {
        if (!state.project) {
            this.showToast("No active project to stitch!", "warning");
            return;
        }

        // Transition to Step 4 Produce & trigger render
        const toStep4Btn = document.getElementById("toStep4Btn");
        const generateBtn = document.getElementById("generateBtn");

        if (toStep4Btn) {
            toStep4Btn.click();
            this.showToast("Timeline synced! Producing master short...", "info");
            setTimeout(() => {
                if (generateBtn) generateBtn.click();
            }, 300);
        }
    }

    switchTab(tabName) {
        const isInspector = tabName === "inspector";
        const isAutoSync = tabName === "autoSync";
        const isProTools = tabName === "proTools";

        this.tabBtnInspector?.classList.toggle("active", isInspector);
        this.tabBtnAutoSync?.classList.toggle("active", isAutoSync);
        this.tabBtnProTools?.classList.toggle("active", isProTools);

        this.panelInspector?.classList.toggle("hidden", !isInspector);
        this.panelAutoSync?.classList.toggle("hidden", !isAutoSync);
        this.panelProTools?.classList.toggle("hidden", !isProTools);
    }

    async handleAutoSync(mode, maxCutDur = 2.8) {
        if (!state.project) {
            this.showToast("No active project to auto-sync", "warning");
            return;
        }

        const msg = mode === "voice_lock" 
            ? "⚡ Locking visual durations to exact voiceover boundaries..."
            : `✂️ Sub-cutting long scenes for viral retention (Max ${maxCutDur}s)...`;
        this.showToast(msg, "info", 4000);

        try {
            const updated = await api.autoSync(state.project.id, mode, maxCutDur);
            state.setProject(updated);
            const successMsg = mode === "voice_lock"
                ? "✅ Timeline visuals locked to spoken voice!"
                : "✅ Retention sub-cuts applied! Timeline pacing optimized.";
            this.showToast(successMsg, "success");
        } catch (err) {
            this.showToast(`Auto-sync failed: ${err.message}`, "error");
        }
    }

    async handleSplitAtPlayhead() {
        if (!state.project) {
            this.showToast("No active project to split", "warning");
            return;
        }

        const playheadTime = this.getCurrentTime();
        const scenes = state.project.scenes || [];
        let cum = 0;
        let targetScene = null;

        for (const sc of scenes) {
            const dur = sc.duration || 3.0;
            if (playheadTime >= cum && playheadTime <= (cum + dur)) {
                targetScene = sc;
                break;
            }
            cum += dur;
        }

        if (!targetScene && this.activeSceneId) {
            targetScene = scenes.find(s => s.id === this.activeSceneId);
        }

        if (!targetScene) {
            this.showToast("Position playhead inside a scene to split", "warning");
            return;
        }

        try {
            const updated = await api.splitAtPlayhead(state.project.id, targetScene.id, playheadTime);
            state.setProject(updated);
            this.showToast("✂️ Split scene cleanly at playhead needle!", "success");
        } catch (err) {
            this.showToast(`Split failed: ${err.message}`, "error");
        }
    }

    async handleSmartMatchAll() {
        if (!state.project) {
            this.showToast("No active project to match visuals", "warning");
            return;
        }

        const forceAll = Boolean(this.forceMatchAllCheck?.checked);
        this.showToast("🤖 Analyzing narration and matching vertical B-roll from Pexels...", "info", 5000);

        try {
            const updated = await api.smartMatchAll(state.project.id, forceAll);
            state.setProject(updated);
            this.showToast("✅ All scenes matched with vertical stock video clips!", "success");
        } catch (err) {
            this.showToast(`Auto-match failed: ${err.message}`, "error");
        }
    }

    async handleColorFilterChange(filterVal) {
        if (!state.project) return;
        if (this.colorFilterSelect) this.colorFilterSelect.value = filterVal;
        if (this.toolbarLutSelect) this.toolbarLutSelect.value = filterVal;
        if (this.screenFrame) this.screenFrame.dataset.filter = filterVal;

        try {
            const updated = await api.setColorFilter(state.project.id, filterVal);
            state.setProject(updated);
            const label = filterVal === "none" ? "Original" : filterVal.replace("_", " ").toUpperCase();
            this.showToast(`🎨 Color Grade LUT set: ${label}`, "success");
        } catch (err) {
            this.showToast(`Failed to set color filter: ${err.message}`, "error");
        }
    }

    async handleReorder(direction) {
        if (!state.project || !this.activeSceneId) {
            this.showToast("Please select a clip to reorder", "warning");
            return;
        }

        try {
            const updated = await api.reorderScene(state.project.id, this.activeSceneId, direction);
            state.setProject(updated);
            this.showToast(`Clip moved ${direction === 'left' ? 'earlier' : 'later'}!`, "success");
        } catch (err) {
            this.showToast(`Reorder failed: ${err.message}`, "error");
        }
    }

    async handleClearMedia() {
        if (!state.project || !this.activeSceneId) return;
        try {
            const updated = await api.clearMedia(state.project.id, this.activeSceneId);
            state.setProject(updated);
            this.showToast("Media removed from scene", "info");
        } catch (err) {
            this.showToast(`Failed to clear media: ${err.message}`, "error");
        }
    }

    updatePacingStats(project) {
        if (!project || !project.scenes) return;
        const scenes = project.scenes;
        const totalDur = project.total_duration || scenes.reduce((acc, s) => acc + (s.duration || 3.0), 0);
        const count = scenes.length;
        const avgPace = count > 0 ? (totalDur / count) : 0;
        const longest = scenes.length > 0 ? Math.max(...scenes.map(s => s.duration || 3.0)) : 0;

        if (this.statTotalDur) this.statTotalDur.textContent = `${totalDur.toFixed(1)}s`;
        if (this.statSceneCount) this.statSceneCount.textContent = `${count}`;
        if (this.statAvgPace) this.statAvgPace.textContent = `${avgPace.toFixed(1)}s`;
        if (this.statLongest) this.statLongest.textContent = `${longest.toFixed(1)}s`;

        if (this.retentionBadge) {
            if (longest > 4.0) {
                this.retentionBadge.textContent = "Retention: ⚠️ Warning (>4s clip)";
                this.retentionBadge.style.color = "#f87171";
                this.retentionBadge.style.background = "rgba(239, 68, 68, 0.15)";
                this.retentionBadge.style.borderColor = "rgba(239, 68, 68, 0.4)";
            } else if (longest > 2.8) {
                this.retentionBadge.textContent = "Retention: Moderate (<2.8s ideal)";
                this.retentionBadge.style.color = "#fbbf24";
                this.retentionBadge.style.background = "rgba(245, 158, 11, 0.15)";
                this.retentionBadge.style.borderColor = "rgba(245, 158, 11, 0.4)";
            } else {
                this.retentionBadge.textContent = "Retention: 🔥 Viral Peak";
                this.retentionBadge.style.color = "#34d399";
                this.retentionBadge.style.background = "rgba(16, 185, 129, 0.15)";
                this.retentionBadge.style.borderColor = "rgba(16, 185, 129, 0.4)";
            }
        }
    }
}
