document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements - Step 1
    const scriptInput = document.getElementById('scriptInput');
    const wordCount = document.getElementById('wordCount');
    const estDuration = document.getElementById('estDuration');
    const pacingText = document.getElementById('pacingText');
    const retentionStatus = document.getElementById('retentionStatus');
    const templateSelect = document.getElementById('templateSelect');
    const hookSelect = document.getElementById('hookSelect');

    const voiceSelect = document.getElementById('voiceSelect');
    const speedSelect = document.getElementById('speedSelect');
    const previewVoiceBtn = document.getElementById('previewVoiceBtn');
    const voiceAudioPreview = document.getElementById('voiceAudioPreview');

    // DOM Elements - Step 2 (Fast Scene Editor)
    const modeAutoBtn = document.getElementById('modeAutoBtn');
    const modeManualBtn = document.getElementById('modeManualBtn');
    const generateAllScenesBtn = document.getElementById('generateAllScenesBtn');
    const generateMissingBtn = document.getElementById('generateMissingBtn');
    const multiMediaInput = document.getElementById('multiMediaInput');
    const toolbarDropzone = document.getElementById('toolbarDropzone');
    const addBeatBtn = document.getElementById('addBeatBtn');
    const blankScenesWarning = document.getElementById('blankScenesWarning');
    const blankWarningText = document.getElementById('blankWarningText');
    const bannerGenerateMissingBtn = document.getElementById('bannerGenerateMissingBtn');
    const sceneCardsList = document.getElementById('sceneCardsList');
    const storyboardEmptyNotice = document.getElementById('storyboardEmptyNotice');
    const storyboardToolbar = document.getElementById('storyboardToolbar');
    const storyboardSceneCount = document.getElementById('storyboardSceneCount');
    const storyboardTotalDur = document.getElementById('storyboardTotalDur');
    const storyboardVisualsCount = document.getElementById('storyboardVisualsCount');

    const storyboardProgressCard = document.getElementById('storyboardProgressCard');
    const storyboardProgressStatus = document.getElementById('storyboardProgressStatus');
    const storyboardProgressStep = document.getElementById('storyboardProgressStep');
    const storyboardProgressPct = document.getElementById('storyboardProgressPct');
    const storyboardProgressBar = document.getElementById('storyboardProgressBar');

    // DOM Elements - Step 3
    const bgmSelect = document.getElementById('bgmSelect');
    const bgmVolume = document.getElementById('bgmVolume');
    const volLabel = document.getElementById('volLabel');

    // DOM Elements - Step 4 & Preview
    const generateBtn = document.getElementById('generateBtn');
    const progressCard = document.getElementById('progressCard');
    const progressStatus = document.getElementById('progressStatus');
    const progressStep = document.getElementById('progressStep');
    const progressPct = document.getElementById('progressPct');
    const progressBar = document.getElementById('progressBar');

    const finalVideoPlayer = document.getElementById('finalVideoPlayer');
    const playerPlaceholder = document.getElementById('playerPlaceholder');
    const playerActions = document.getElementById('playerActions');
    const downloadVideoBtn = document.getElementById('downloadVideoBtn');

    const seoKitCard = document.getElementById('seoKitCard');
    const seoTitle = document.getElementById('seoTitle');
    const seoDesc = document.getElementById('seoDesc');
    const seoTags = document.getElementById('seoTags');

    // State
    let configData = null;
    let pollInterval = null;
    let currentStep = 1;
    let currentMode = 'auto'; // 'auto' | 'manual'
    let currentSession = null;
    let activePromptTabs = {}; // segment_id -> 'image' | 'video'

    // ==========================================
    // TOAST NOTIFICATIONS
    // ==========================================
    function showToast(message, type = 'info', duration = 3500) {
        const toastContainer = document.getElementById('toastContainer');
        if (!toastContainer) {
            console.log(`[Toast ${type}] ${message}`);
            return;
        }

        const icons = {
            success: '✅',
            error: '❌',
            warning: '⚠️',
            info: '💡'
        };

        const toast = document.createElement('div');
        toast.className = `google-toast toast-${type}`;
        toast.innerHTML = `
            <span class="toast-icon">${icons[type] || '💡'}</span>
            <span class="toast-message">${message}</span>
            <button class="toast-close" title="Dismiss">&times;</button>
        `;

        function removeToast(el) {
            el.style.animation = 'toastFadeOut 0.25s forwards';
            setTimeout(() => {
                if (el.parentNode) el.parentNode.removeChild(el);
            }, 250);
        }

        toast.querySelector('.toast-close').addEventListener('click', () => {
            removeToast(toast);
        });

        toastContainer.appendChild(toast);

        if (duration > 0) {
            setTimeout(() => {
                removeToast(toast);
            }, duration);
        }
    }

    // ==========================================
    // STEP NAVIGATION
    // ==========================================
    function goToStep(stepNum) {
        if (stepNum < 1 || stepNum > 4) return;

        if (currentStep === 1 && stepNum > 1) {
            const scriptVal = scriptInput.value.trim();
            if (!scriptVal) {
                showToast("Please write or paste your script first before proceeding!", "warning");
                scriptInput.focus();
                return;
            }
        }

        for (let i = 1; i <= 4; i++) {
            const panel = document.getElementById(`stepPanel${i}`);
            const btn = document.getElementById(`stepBtn${i}`);
            if (panel) {
                if (i === stepNum) panel.classList.remove('hidden');
                else panel.classList.add('hidden');
            }
            if (btn) {
                btn.classList.remove('active');
                if (i < stepNum) btn.classList.add('completed');
                else btn.classList.remove('completed');
                if (i === stepNum) btn.classList.add('active');
            }
        }

        currentStep = stepNum;

        if (stepNum === 4) {
            updateStep4Summary();
        }

        const controlsPanel = document.querySelector('.controls-panel');
        if (controlsPanel) {
            controlsPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    }

    function updateStep4Summary() {
        const words = scriptInput.value.trim().split(/\s+/).filter(Boolean).length;
        const dur = estDuration.textContent || "0s";
        const sumScriptLength = document.getElementById('sumScriptLength');
        const sumVoice = document.getElementById('sumVoice');
        const sumStoryboard = document.getElementById('sumStoryboard');
        const sumSubtitles = document.getElementById('sumSubtitles');

        if (sumScriptLength) sumScriptLength.textContent = `${words} words (~${dur})`;
        if (sumVoice && voiceSelect && voiceSelect.options && voiceSelect.selectedIndex >= 0) {
            const voiceOpt = voiceSelect.options[voiceSelect.selectedIndex];
            sumVoice.textContent = voiceOpt ? voiceOpt.text.split('[')[0].trim() : 'Neural Voice';
        }
        if (sumStoryboard) {
            sumStoryboard.textContent = currentMode === 'auto' ? '⚡ Auto (FLUX)' : '✂️ Manual Segment';
        }
        if (sumSubtitles) {
            const activePreset = document.querySelector('.preset-option.active .preset-label');
            sumSubtitles.textContent = activePreset ? activePreset.textContent : 'MrBeast Yellow';
        }
    }

    for (let i = 1; i <= 4; i++) {
        const btn = document.getElementById(`stepBtn${i}`);
        if (btn) btn.addEventListener('click', () => goToStep(i));
    }

    document.getElementById('toStep2Btn')?.addEventListener('click', () => goToStep(2));
    document.getElementById('backToStep1Btn')?.addEventListener('click', () => goToStep(1));
    document.getElementById('toStep3Btn')?.addEventListener('click', () => goToStep(3));
    document.getElementById('backToStep2Btn')?.addEventListener('click', () => goToStep(2));
    document.getElementById('toStep4Btn')?.addEventListener('click', () => goToStep(4));
    document.getElementById('backToStep3Btn')?.addEventListener('click', () => goToStep(3));

    // ==========================================
    // INITIAL CONFIG
    // ==========================================
    async function loadConfig() {
        try {
            const res = await fetch('/api/config');
            configData = await res.json();

            // Populate voices
            voiceSelect.innerHTML = '';
            for (const [id, v] of Object.entries(configData.voices)) {
                const opt = document.createElement('option');
                opt.value = id;
                opt.textContent = `${v.name} [${v.vibe}]`;
                if (id === 'en-US-ChristopherNeural') opt.selected = true;
                voiceSelect.appendChild(opt);
            }

            // Populate BGM tracks
            bgmSelect.innerHTML = '';
            configData.bgm_tracks.forEach(b => {
                const opt = document.createElement('option');
                opt.value = b.id;
                opt.textContent = b.name;
                if (b.id === 'phonk_energetic') opt.selected = true;
                bgmSelect.appendChild(opt);
            });

            // Populate Templates
            templateSelect.innerHTML = '<option value="">✨ Load Viral Template...</option>';
            for (const [key, tpl] of Object.entries(configData.templates)) {
                const opt = document.createElement('option');
                opt.value = key;
                opt.textContent = `${tpl.title} (${tpl.category})`;
                templateSelect.appendChild(opt);
            }

            // Populate Hooks
            hookSelect.innerHTML = '<option value="">🪝 Add Viral Hook...</option>';
            configData.hooks.forEach(hook => {
                const opt = document.createElement('option');
                opt.value = hook;
                opt.textContent = hook.length > 42 ? hook.substring(0, 42) + '...' : hook;
                hookSelect.appendChild(opt);
            });

        } catch (err) {
            console.error('Failed to load configuration:', err);
        }
    }

    // Script stats calculation
    function updateScriptStats() {
        const text = scriptInput.value.trim();
        const words = text ? text.split(/\s+/).length : 0;
        wordCount.textContent = words;

        let speedMult = 1.0;
        const rateVal = speedSelect.value;
        if (rateVal === '+10%') speedMult = 1.10;
        else if (rateVal === '+15%') speedMult = 1.15;
        else if (rateVal === '+20%') speedMult = 1.20;

        const sec = words > 0 ? Math.max(2, Math.round((words / (2.5 * speedMult)))) : 0;
        estDuration.textContent = `${sec}s`;

        if (sec === 0) {
            pacingText.textContent = "Paste Script";
            retentionStatus.className = "stat-badge";
        } else if (sec <= 15) {
            pacingText.textContent = "Super Punchy 🚀";
            retentionStatus.className = "stat-badge status-good";
        } else if (sec <= 45) {
            pacingText.textContent = "Optimal for Shorts Feed ⚡";
            retentionStatus.className = "stat-badge status-good";
        } else if (sec <= 58) {
            pacingText.textContent = "Long Form Short ⚠️";
            retentionStatus.className = "stat-badge";
        } else {
            pacingText.textContent = "Exceeds 60s limit! ❌";
            retentionStatus.className = "stat-badge";
            retentionStatus.style.borderColor = "#ff0033";
        }
    }

    scriptInput.addEventListener('input', updateScriptStats);
    speedSelect.addEventListener('change', updateScriptStats);

    templateSelect.addEventListener('change', (e) => {
        const key = e.target.value;
        if (key && configData && configData.templates[key]) {
            scriptInput.value = configData.templates[key].script;
            updateScriptStats();
            currentSession = null;
            renderSceneCards();
        }
    });

    hookSelect.addEventListener('change', (e) => {
        const hook = e.target.value;
        if (hook) {
            const current = scriptInput.value.trim();
            scriptInput.value = current ? `${hook} ${current}` : hook;
            updateScriptStats();
            hookSelect.value = '';
        }
    });

    document.querySelectorAll('.preset-option').forEach(opt => {
        opt.addEventListener('click', () => {
            document.querySelectorAll('.preset-option').forEach(o => o.classList.remove('active'));
            opt.classList.add('active');
            const radio = opt.querySelector('input[type="radio"]');
            if (radio) radio.checked = true;
        });
    });

    bgmVolume.addEventListener('input', (e) => {
        const pct = Math.round(parseFloat(e.target.value) * 100);
        volLabel.textContent = `${pct}%`;
    });

    previewVoiceBtn.addEventListener('click', async () => {
        const sampleText = scriptInput.value.trim().substring(0, 100) || "Welcome to the ultimate YouTube Shorts Creator!";
        previewVoiceBtn.textContent = "⏳ Loading...";
        previewVoiceBtn.disabled = true;

        try {
            const res = await fetch('/api/preview_voice', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    text: sampleText,
                    voice: voiceSelect.value,
                    voice_rate: speedSelect.value
                })
            });
            const data = await res.json();
            if (data.audio_url) {
                voiceAudioPreview.src = data.audio_url;
                voiceAudioPreview.play();
            }
        } catch (err) {
            showToast('Voice preview failed: ' + err.message, 'error');
        } finally {
            previewVoiceBtn.textContent = "🔊 Audition";
            previewVoiceBtn.disabled = false;
        }
    });

    // ==========================================
    // STEP 2: FAST SCENE EDITOR (AUTO & MANUAL)
    // ==========================================

    // Mode Toggle
    modeAutoBtn.addEventListener('click', () => {
        if (currentMode === 'auto') return;
        currentMode = 'auto';
        modeAutoBtn.classList.add('active');
        modeManualBtn.classList.remove('active');
        generateAllScenesBtn.textContent = '⚡ Generate Visuals';
        if (currentSession) {
            currentSession.mode = 'auto';
            renderSceneCards();
        }
    });

    modeManualBtn.addEventListener('click', () => {
        if (currentMode === 'manual') return;
        currentMode = 'manual';
        modeManualBtn.classList.add('active');
        modeAutoBtn.classList.remove('active');
        generateAllScenesBtn.textContent = '✂️ Plan Scenes (No AI)';
        if (currentSession) {
            currentSession.mode = 'manual';
            renderSceneCards();
        }
    });

    // Generate / Plan All Scenes
    generateAllScenesBtn.addEventListener('click', async () => {
        const script = scriptInput.value.trim();
        if (!script) {
            showToast("Please write or paste your script first!", "warning");
            scriptInput.focus();
            return;
        }

        generateAllScenesBtn.disabled = true;
        storyboardProgressCard.classList.remove('hidden');
        storyboardEmptyNotice.classList.add('hidden');
        sceneCardsList.innerHTML = '';

        let pct = 10;
        storyboardProgressBar.style.width = '10%';
        storyboardProgressPct.textContent = '10%';
        storyboardProgressStatus.textContent = currentMode === 'auto' ? 'Auto-Generating Visuals...' : 'Planning Manual Segments...';
        storyboardProgressStep.textContent = 'Splitting script into story beats...';

        const progressTimer = setInterval(() => {
            if (pct < 90) {
                pct += 5;
                storyboardProgressBar.style.width = `${pct}%`;
                storyboardProgressPct.textContent = `${pct}%`;
                if (pct > 30 && currentMode === 'auto') {
                    storyboardProgressStep.textContent = 'Directing scenes with Gemini & rendering FLUX visuals...';
                }
            }
        }, 600);

        try {
            let res;
            if (currentMode === 'auto') {
                res = await fetch('/api/auto/generate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ script })
                });
            } else {
                res = await fetch('/api/segments/create', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        script,
                        mode: 'manual',
                        manual_delimiter: script.includes('|||')
                    })
                });
            }

            clearInterval(progressTimer);

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Failed to generate scenes');
            }

            storyboardProgressBar.style.width = '100%';
            storyboardProgressPct.textContent = '100%';
            storyboardProgressStatus.textContent = 'Scenes Ready!';
            storyboardProgressStep.textContent = 'Loading scene cards...';

            currentSession = await res.json();
            renderSceneCards();
            showToast(`✨ Generated ${currentSession.segments.length} scenes in ${currentMode === 'auto' ? 'Auto' : 'Manual'} mode!`, 'success');

        } catch (err) {
            clearInterval(progressTimer);
            showToast('Generation failed: ' + err.message, 'error');
            storyboardEmptyNotice.classList.remove('hidden');
        } finally {
            setTimeout(() => {
                storyboardProgressCard.classList.add('hidden');
                generateAllScenesBtn.disabled = false;
            }, 400);
        }
    });

    // Generate Missing Media
    async function triggerGenerateMissing() {
        if (!currentSession) return;
        generateMissingBtn.disabled = true;
        bannerGenerateMissingBtn.disabled = true;
        showToast('Generating visuals for blank scenes via FLUX...', 'info');

        try {
            const res = await fetch(`/api/segments/${currentSession.session_id}/generate_missing`, {
                method: 'POST'
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Failed to generate missing media');
            }
            currentSession = await res.json();
            renderSceneCards();
            showToast('✨ Missing scene visuals generated!', 'success');
        } catch (err) {
            showToast('Failed to generate missing: ' + err.message, 'error');
        } finally {
            generateMissingBtn.disabled = false;
            bannerGenerateMissingBtn.disabled = false;
        }
    }

    generateMissingBtn.addEventListener('click', triggerGenerateMissing);
    bannerGenerateMissingBtn.addEventListener('click', triggerGenerateMissing);

    // Multi-File Upload & Toolbar Dropzone
    async function handleMultiFileUpload(files) {
        if (!files || files.length === 0) return;
        const script = scriptInput.value.trim();
        if (!script) {
            showToast("Please enter a script first!", "warning");
            return;
        }

        if (!currentSession) {
            try {
                const cRes = await fetch('/api/segments/create', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ script, mode: currentMode })
                });
                currentSession = await cRes.json();
            } catch (err) {
                showToast("Failed to create session for media: " + err.message, "error");
                return;
            }
        }

        showToast(`Uploading ${files.length} file(s) across scenes...`, 'info');
        const segs = currentSession.segments || [];

        for (let i = 0; i < files.length && i < segs.length; i++) {
            const file = files[i];
            const seg = segs[i];
            const formData = new FormData();
            formData.append('file', file);
            formData.append('segment_id', seg.segment_id);

            try {
                const uRes = await fetch(`/api/segments/${currentSession.session_id}/upload_media`, {
                    method: 'POST',
                    body: formData
                });
                if (uRes.ok) {
                    currentSession = await uRes.json();
                }
            } catch (err) {
                console.error(`Upload error on scene ${i}:`, err);
            }
        }

        renderSceneCards();
        showToast("✨ Files assigned to scenes!", "success");
    }

    multiMediaInput.addEventListener('change', (e) => {
        handleMultiFileUpload(Array.from(e.target.files));
        multiMediaInput.value = '';
    });

    toolbarDropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        toolbarDropzone.classList.add('dragover');
    });

    toolbarDropzone.addEventListener('dragleave', () => {
        toolbarDropzone.classList.remove('dragover');
    });

    toolbarDropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        toolbarDropzone.classList.remove('dragover');
        handleMultiFileUpload(Array.from(e.dataTransfer.files));
    });

    // Add Scene Beat
    addBeatBtn.addEventListener('click', async () => {
        if (!currentSession || !currentSession.segments || currentSession.segments.length === 0) {
            showToast("Please generate or plan scenes first!", "warning");
            return;
        }
        const text = prompt("Enter narration text for the new scene:");
        if (!text || !text.trim()) return;

        const lastSeg = currentSession.segments[currentSession.segments.length - 1];
        try {
            const res = await fetch(`/api/segments/${currentSession.session_id}/add`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    after_segment_id: lastSeg.segment_id,
                    text: text.trim()
                })
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Failed to add scene');
            }
            currentSession = await res.json();
            renderSceneCards();
            showToast("➕ Scene added!", "success");
        } catch (err) {
            showToast(err.message, 'error');
        }
    });

    // Render Scene Cards
    function renderSceneCards() {
        sceneCardsList.innerHTML = '';

        if (!currentSession || !currentSession.segments || currentSession.segments.length === 0) {
            storyboardEmptyNotice.classList.remove('hidden');
            storyboardSceneCount.textContent = '0 scenes';
            storyboardTotalDur.textContent = '0.0s total';
            storyboardVisualsCount.textContent = '0 visuals loaded';
            blankScenesWarning.classList.add('hidden');
            generateMissingBtn.classList.add('hidden');
            return;
        }

        storyboardEmptyNotice.classList.add('hidden');
        const segs = currentSession.segments;

        // Calculate stats
        let loadedVisuals = 0;
        let blankCount = 0;
        segs.forEach(s => {
            const hasMedia = Boolean(s.image_path || s.image_url) && s.media_type !== 'blank';
            if (hasMedia) loadedVisuals++;
            else blankCount++;
        });

        storyboardSceneCount.textContent = `${segs.length} scenes`;
        storyboardTotalDur.textContent = `${currentSession.total_duration}s total`;
        storyboardVisualsCount.textContent = `${loadedVisuals} visuals loaded`;

        // Warning banner
        if (blankCount > 0) {
            blankScenesWarning.classList.remove('hidden');
            blankWarningText.textContent = `${blankCount} scene${blankCount === 1 ? '' : 's'} have no visual media and will render as black background.`;
            if (currentMode === 'auto') {
                generateMissingBtn.classList.remove('hidden');
                bannerGenerateMissingBtn.style.display = 'inline-block';
            } else {
                generateMissingBtn.classList.add('hidden');
                bannerGenerateMissingBtn.style.display = 'none';
            }
        } else {
            blankScenesWarning.classList.add('hidden');
            generateMissingBtn.classList.add('hidden');
        }

        segs.forEach((seg, idx) => {
            const card = document.createElement('div');
            const hasMedia = Boolean(seg.image_path || seg.image_url) && seg.media_type !== 'blank';
            card.className = `scene-editor-card ${hasMedia ? '' : 'blank-card'}`;
            card.id = `sceneCard_${seg.segment_id}`;

            const activeTab = activePromptTabs[seg.segment_id] || 'image';
            const promptText = activeTab === 'video' ? (seg.video_prompt || '') : (seg.image_prompt || '');

            const isVideo = seg.media_type === 'video' || (typeof seg.image_url === 'string' && (seg.image_url.endsWith('.mp4') || seg.image_url.endsWith('.webm')));

            card.innerHTML = `
                <div class="scene-card-top">
                    <div class="scene-card-badge-group">
                        <span class="scene-idx-badge">SCENE #${idx + 1}</span>
                        <span class="segment-card-dur">${seg.duration}s</span>
                        ${seg.source === 'manual' ? '<span class="badge" style="color:var(--accent-green);font-size:0.7rem;font-weight:700;">MANUAL</span>' : ''}
                        ${!hasMedia ? '<span class="badge" style="color:#f59e0b;font-size:0.7rem;font-weight:700;">BLANK</span>' : ''}
                    </div>
                    <div class="segment-card-actions">
                        <button class="segment-btn btn-split" data-segment-id="${seg.segment_id}" title="Split into two scenes">
                            ✂️ Split
                        </button>
                        <button class="segment-btn btn-merge" data-segment-id="${seg.segment_id}" ${idx === segs.length - 1 ? 'disabled' : ''} title="Merge with next scene">
                            🔗 Merge
                        </button>
                        <button class="segment-btn btn-danger btn-del" data-segment-id="${seg.segment_id}" ${segs.length <= 1 ? 'disabled' : ''} title="Delete scene">
                            🗑️
                        </button>
                    </div>
                </div>

                <div class="scene-card-main">
                    <!-- Left: Media Slot -->
                    <div class="scene-media-slot" id="mediaSlot_${seg.segment_id}" title="Click, drop file, or paste image/video here">
                        ${hasMedia ? (
                            isVideo ? `
                                <video src="${seg.image_url}" class="scene-media-thumb" muted loop playsinline></video>
                                <span class="badge" style="position:absolute;top:4px;left:4px;font-size:0.6rem;background:rgba(0,0,0,0.7);">VIDEO</span>
                            ` : `
                                <img src="${seg.image_url}" class="scene-media-thumb" alt="Scene ${idx + 1}">
                            `
                        ) : `
                            <div class="scene-media-empty">
                                <span class="empty-icon">📁</span>
                                <span class="empty-text">Drop or Paste Media</span>
                            </div>
                        `}
                        <div class="scene-media-overlay-btns">
                            <label class="media-mini-btn" title="Replace visual file">
                                📁 Replace
                                <input type="file" class="single-media-input" data-segment-id="${seg.segment_id}" accept="image/*,video/*" style="display:none;">
                            </label>
                            ${hasMedia ? `
                                <button type="button" class="media-mini-btn btn-clear-media" data-segment-id="${seg.segment_id}" title="Clear visual">
                                    ✕ Clear
                                </button>
                            ` : ''}
                            ${currentMode === 'auto' ? `
                                <button type="button" class="media-mini-btn btn-reroll-media" data-segment-id="${seg.segment_id}" title="Re-generate via FLUX">
                                    ↻ Re-roll
                                </button>
                            ` : ''}
                        </div>
                    </div>

                    <!-- Right: Text & Prompts -->
                    <div class="scene-content-col">
                        <div class="segment-field-group">
                            <label class="segment-field-label">SPOKEN NARRATION</label>
                            <textarea class="segment-card-textarea narration-textarea" data-segment-id="${seg.segment_id}">${seg.text}</textarea>
                        </div>

                        <div class="segment-field-group">
                            <div class="prompt-tabs">
                                <span class="segment-field-label" style="margin-right:8px;">PROMPT:</span>
                                <button type="button" class="prompt-tab-btn ${activeTab === 'image' ? 'active' : ''}" data-tab="image" data-segment-id="${seg.segment_id}">
                                    🖼️ Image
                                </button>
                                <button type="button" class="prompt-tab-btn ${activeTab === 'video' ? 'active' : ''}" data-tab="video" data-segment-id="${seg.segment_id}">
                                    🎬 Video
                                </button>
                                <button type="button" class="segment-btn btn-copy-prompt" style="margin-left:auto;" data-segment-id="${seg.segment_id}" title="Copy prompt for external generator">
                                    📋 Copy
                                </button>
                            </div>
                            <textarea class="segment-card-textarea segment-prompt-textarea prompt-textarea" data-segment-id="${seg.segment_id}">${promptText}</textarea>
                        </div>
                    </div>
                </div>
            `;

            // Setup single media input
            const fileInput = card.querySelector('.single-media-input');
            if (fileInput) {
                fileInput.addEventListener('change', async (e) => {
                    const file = e.target.files[0];
                    if (!file) return;
                    const formData = new FormData();
                    formData.append('file', file);
                    formData.append('segment_id', seg.segment_id);

                    try {
                        const res = await fetch(`/api/segments/${currentSession.session_id}/upload_media`, {
                            method: 'POST',
                            body: formData
                        });
                        if (!res.ok) throw new Error("Upload failed");
                        currentSession = await res.json();
                        renderSceneCards();
                        showToast("Visual uploaded!", "success");
                    } catch (err) {
                        showToast(err.message, "error");
                    }
                });
            }

            // Setup Media Slot Drag & Drop and Paste
            const mediaSlot = card.querySelector('.scene-media-slot');
            if (mediaSlot) {
                mediaSlot.addEventListener('dragover', (e) => {
                    e.preventDefault();
                    mediaSlot.classList.add('dragover');
                });
                mediaSlot.addEventListener('dragleave', () => {
                    mediaSlot.classList.remove('dragover');
                });
                mediaSlot.addEventListener('drop', async (e) => {
                    e.preventDefault();
                    mediaSlot.classList.remove('dragover');
                    const file = e.dataTransfer.files[0];
                    if (!file) return;

                    const formData = new FormData();
                    formData.append('file', file);
                    formData.append('segment_id', seg.segment_id);

                    try {
                        const res = await fetch(`/api/segments/${currentSession.session_id}/upload_media`, {
                            method: 'POST',
                            body: formData
                        });
                        if (!res.ok) throw new Error("Upload failed");
                        currentSession = await res.json();
                        renderSceneCards();
                        showToast("Visual dropped!", "success");
                    } catch (err) {
                        showToast(err.message, "error");
                    }
                });

                // Paste from clipboard
                mediaSlot.tabIndex = 0;
                mediaSlot.addEventListener('paste', async (e) => {
                    const items = e.clipboardData.items;
                    for (let i = 0; i < items.length; i++) {
                        if (items[i].type.indexOf('image') !== -1 || items[i].type.indexOf('video') !== -1) {
                            const file = items[i].getAsFile();
                            const formData = new FormData();
                            formData.append('file', file);
                            formData.append('segment_id', seg.segment_id);

                            try {
                                const res = await fetch(`/api/segments/${currentSession.session_id}/upload_media`, {
                                    method: 'POST',
                                    body: formData
                                });
                                if (!res.ok) throw new Error("Paste failed");
                                currentSession = await res.json();
                                renderSceneCards();
                                showToast("Visual pasted from clipboard!", "success");
                            } catch (err) {
                                showToast(err.message, "error");
                            }
                            break;
                        }
                    }
                });
            }

            // Clear Media
            const clearBtn = card.querySelector('.btn-clear-media');
            if (clearBtn) {
                clearBtn.addEventListener('click', async () => {
                    try {
                        const res = await fetch(`/api/segments/${currentSession.session_id}/clear_media`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ segment_id: seg.segment_id })
                        });
                        if (!res.ok) throw new Error("Failed to clear media");
                        currentSession = await res.json();
                        renderSceneCards();
                        showToast("Media cleared.", "info");
                    } catch (err) {
                        showToast(err.message, "error");
                    }
                });
            }

            // Re-roll single scene via FLUX
            const rerollBtn = card.querySelector('.btn-reroll-media');
            if (rerollBtn) {
                rerollBtn.addEventListener('click', async () => {
                    rerollBtn.textContent = '⏳';
                    rerollBtn.disabled = true;
                    try {
                        const res = await fetch(`/api/segments/${currentSession.session_id}/generate`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ segment_id: seg.segment_id })
                        });
                        if (!res.ok) throw new Error("Re-roll failed");
                        currentSession = await res.json();
                        renderSceneCards();
                        showToast("✨ Scene visual regenerated!", "success");
                    } catch (err) {
                        showToast(err.message, "error");
                    } finally {
                        rerollBtn.textContent = '↻ Re-roll';
                        rerollBtn.disabled = false;
                    }
                });
            }

            // Inline Narration Edit
            const narrTextarea = card.querySelector('.narration-textarea');
            narrTextarea.addEventListener('blur', async () => {
                const newVal = narrTextarea.value.trim();
                if (!newVal || newVal === seg.text) return;
                try {
                    const res = await fetch(`/api/segments/${currentSession.session_id}/edit_text`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ segment_id: seg.segment_id, new_text: newVal })
                    });
                    if (res.ok) {
                        currentSession = await res.json();
                        renderSceneCards();
                    }
                } catch (err) {
                    console.error(err);
                }
            });

            // Prompt Tabs (Image vs Video)
            const promptBtns = card.querySelectorAll('.prompt-tab-btn');
            const promptTextarea = card.querySelector('.prompt-textarea');

            promptBtns.forEach(pBtn => {
                pBtn.addEventListener('click', () => {
                    const tabKind = pBtn.getAttribute('data-tab');
                    activePromptTabs[seg.segment_id] = tabKind;
                    promptBtns.forEach(b => b.classList.remove('active'));
                    pBtn.classList.add('active');
                    promptTextarea.value = tabKind === 'video' ? (seg.video_prompt || '') : (seg.image_prompt || '');
                });
            });

            // Inline Prompt Edit
            promptTextarea.addEventListener('blur', async () => {
                const newPrompt = promptTextarea.value.trim();
                const curKind = activePromptTabs[seg.segment_id] || 'image';
                const oldPrompt = curKind === 'video' ? seg.video_prompt : seg.image_prompt;
                if (!newPrompt || newPrompt === oldPrompt) return;

                try {
                    const res = await fetch(`/api/segments/${currentSession.session_id}/edit_prompt`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            segment_id: seg.segment_id,
                            new_prompt: newPrompt,
                            kind: curKind
                        })
                    });
                    if (res.ok) {
                        currentSession = await res.json();
                        showToast("Prompt updated!", "info", 1500);
                    }
                } catch (err) {
                    console.error(err);
                }
            });

            // Copy Prompt
            const copyBtn = card.querySelector('.btn-copy-prompt');
            copyBtn.addEventListener('click', async () => {
                const curPrompt = promptTextarea.value.trim();
                if (!curPrompt) return;
                try {
                    await navigator.clipboard.writeText(curPrompt);
                    copyBtn.textContent = '✅ Copied!';
                    setTimeout(() => { copyBtn.textContent = '📋 Copy'; }, 1800);
                    showToast("Prompt copied to clipboard!", "success");
                } catch (e) {
                    promptTextarea.select();
                    document.execCommand('copy');
                }
            });

            // Split Scene
            const splitBtn = card.querySelector('.btn-split');
            splitBtn.addEventListener('click', async () => {
                const words = seg.text.trim().split(/\s+/).filter(Boolean);
                if (words.length < 2) {
                    showToast("Sentence too short to split.", "warning");
                    return;
                }
                const defaultSplit = Math.max(1, Math.floor(words.length / 2));
                const input = prompt(`Split at word index (1 to ${words.length - 1}):\n\n"${seg.text}"`, defaultSplit);
                if (input === null) return;
                const splitIdx = parseInt(input.trim());
                if (isNaN(splitIdx) || splitIdx < 1 || splitIdx >= words.length) return;

                try {
                    const res = await fetch(`/api/segments/${currentSession.session_id}/split`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ segment_id: seg.segment_id, split_at_word_index: splitIdx })
                    });
                    if (!res.ok) {
                        const err = await res.json();
                        throw new Error(err.detail || 'Split failed');
                    }
                    currentSession = await res.json();
                    renderSceneCards();
                    showToast("✂️ Scene split!", "success");
                } catch (err) {
                    showToast(err.message, "error");
                }
            });

            // Merge Scene
            const mergeBtn = card.querySelector('.btn-merge');
            if (mergeBtn && idx < segs.length - 1) {
                mergeBtn.addEventListener('click', async () => {
                    try {
                        const res = await fetch(`/api/segments/${currentSession.session_id}/merge`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ segment_id: seg.segment_id, direction: 'next' })
                        });
                        if (!res.ok) {
                            const err = await res.json();
                            throw new Error(err.detail || 'Merge failed');
                        }
                        currentSession = await res.json();
                        renderSceneCards();
                        showToast("🔗 Scenes merged!", "success");
                    } catch (err) {
                        showToast(err.message, "error");
                    }
                });
            }

            // Delete Scene
            const delBtn = card.querySelector('.btn-del');
            if (delBtn && segs.length > 1) {
                delBtn.addEventListener('click', async () => {
                    if (!confirm(`Delete Scene #${idx + 1}?`)) return;
                    try {
                        const res = await fetch(`/api/segments/${currentSession.session_id}/delete`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ segment_id: seg.segment_id })
                        });
                        if (!res.ok) {
                            const err = await res.json();
                            throw new Error(err.detail || 'Delete failed');
                        }
                        currentSession = await res.json();
                        renderSceneCards();
                        showToast("🗑️ Scene deleted.", "info");
                    } catch (err) {
                        showToast(err.message, "error");
                    }
                });
            }

            sceneCardsList.appendChild(card);
        });
    }

    // ==========================================
    // STEP 4: GENERATE MASTER VIDEO (1080x1920)
    // ==========================================
    generateBtn.addEventListener('click', async () => {
        const script = scriptInput.value.trim();
        if (!script && (!currentSession || !currentSession.script_text)) {
            showToast("Please enter or paste your script first!", "warning");
            scriptInput.focus();
            return;
        }

        // Check for blank scenes
        if (currentSession && currentSession.segments) {
            const blankCount = currentSession.segments.filter(s => !s.image_path && !s.image_url).length;
            if (blankCount > 0) {
                const proceed = confirm(`⚠️ Warning: ${blankCount} scene(s) have no visual media and will render as black background.\n\nDo you want to continue rendering anyway?`);
                if (!proceed) return;
            }
        }

        const selectedStyleRadio = document.querySelector('input[name="subtitleStyle"]:checked');
        const subtitleStyle = selectedStyleRadio ? selectedStyleRadio.value : 'mrbeast';

        const payload = {
            script: script,
            voice: voiceSelect.value,
            voice_rate: speedSelect.value,
            subtitle_style: subtitleStyle,
            bgm_track: bgmSelect.value,
            bgm_volume: parseFloat(bgmVolume.value),
            session_id: currentSession ? currentSession.session_id : null
        };

        generateBtn.disabled = true;
        generateBtn.innerHTML = '<span class="spinner" style="width:20px;height:20px;border-width:2px;"></span> Rendering Viral Short...';
        progressCard.classList.remove('hidden');
        progressBar.style.width = '5%';
        progressPct.textContent = '5%';
        progressStatus.textContent = 'Initializing Queue...';
        progressStep.textContent = 'Preparing audio & visual pipeline...';

        try {
            const res = await fetch('/api/generate_short', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (!res.ok) {
                let errMsg = `Server returned ${res.status}`;
                try {
                    const errData = await res.json();
                    if (errData && errData.detail) errMsg = errData.detail;
                } catch (_) {
                    errMsg = await res.text();
                }
                throw new Error(errMsg);
            }
            const data = await res.json();
            const jobId = data.job_id;
            showToast("🚀 Rendering started! Tracking live progress...", "info", 3500);

            let notFoundRetries = 0;
            if (pollInterval) clearInterval(pollInterval);
            pollInterval = setInterval(async () => {
                try {
                    const sRes = await fetch(`/api/status/${jobId}`);
                    if (!sRes.ok) {
                        notFoundRetries++;
                        if (notFoundRetries > 12) {
                            clearInterval(pollInterval);
                            showToast('Rendering was interrupted by server restart. Please try again.', 'error', 6000);
                            progressCard.classList.add('hidden');
                            generateBtn.disabled = false;
                            generateBtn.innerHTML = '<span class="btn-icon">⚡</span><span class="btn-text">GENERATE VIRAL SHORT (1080x1920)</span>';
                        }
                        return;
                    }
                    notFoundRetries = 0;
                    const status = await sRes.json();

                    if (status.status === 'processing' || status.status === 'queued') {
                        progressBar.style.width = `${status.progress}%`;
                        progressPct.textContent = `${status.progress}%`;
                        progressStatus.textContent = 'Rendering Viral Short...';
                        progressStep.textContent = status.message || 'Processing frames...';
                    } else if (status.status === 'completed') {
                        clearInterval(pollInterval);
                        progressBar.style.width = '100%';
                        progressPct.textContent = '100%';
                        progressStatus.textContent = 'Ready!';
                        progressStep.textContent = 'Your viral short is finished.';

                        playerPlaceholder.style.display = 'none';
                        finalVideoPlayer.style.display = 'block';
                        finalVideoPlayer.src = status.video_url;
                        finalVideoPlayer.play();

                        playerActions.classList.remove('hidden');
                        downloadVideoBtn.href = status.video_url;

                        if (status.metadata) {
                            seoTitle.value = status.metadata.title;
                            seoDesc.value = status.metadata.description;
                            seoTags.value = status.metadata.tags.join(', ');
                            seoKitCard.classList.remove('hidden');
                        }

                        generateBtn.disabled = false;
                        generateBtn.innerHTML = '<span class="btn-icon">⚡</span><span class="btn-text">GENERATE VIRAL SHORT (1080x1920)</span>';
                        showToast("🎉 Your viral 1080x1920 Short is ready!", "success", 5000);
                    } else if (status.status === 'error') {
                        clearInterval(pollInterval);
                        showToast('Render error: ' + status.message, 'error');
                        progressCard.classList.add('hidden');
                        generateBtn.disabled = false;
                        generateBtn.innerHTML = '<span class="btn-icon">⚡</span><span class="btn-text">GENERATE VIRAL SHORT (1080x1920)</span>';
                    }
                } catch (pErr) {
                    console.error('Poll error:', pErr);
                }
            }, 1000);

        } catch (err) {
            showToast('Failed to start render: ' + err.message, 'error');
            generateBtn.disabled = false;
            generateBtn.innerHTML = '<span class="btn-icon">⚡</span><span class="btn-text">GENERATE VIRAL SHORT (1080x1920)</span>';
            progressCard.classList.add('hidden');
        }
    });

    // Copy SEO Elements
    document.querySelectorAll('.btn-copy').forEach(btn => {
        btn.addEventListener('click', () => {
            const targetId = btn.getAttribute('data-target');
            const el = document.getElementById(targetId);
            if (el) {
                el.select();
                navigator.clipboard.writeText(el.value).then(() => {
                    const originalText = btn.textContent;
                    btn.textContent = "✅ Copied!";
                    setTimeout(() => { btn.textContent = originalText; }, 1800);
                });
            }
        });
    });

    // Initial load
    loadConfig();
    updateScriptStats();
});
