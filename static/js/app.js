document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
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
    
    const bgSelect = document.getElementById('bgSelect');
    const videoUploadInput = document.getElementById('videoUploadInput');
    const uploadNotice = document.getElementById('uploadNotice');
    
    const bgmSelect = document.getElementById('bgmSelect');
    const bgmVolume = document.getElementById('bgmVolume');
    const volLabel = document.getElementById('volLabel');

    // Storyboard Elements
    const previewScenesBtn = document.getElementById('previewScenesBtn');
    const batchImageInput = document.getElementById('batchImageInput');
    const storyboardToolbar = document.getElementById('storyboardToolbar');
    const storyboardGrid = document.getElementById('storyboardGrid');
    const storyboardEmptyNotice = document.getElementById('storyboardEmptyNotice');
    const storyboardTopic = document.getElementById('storyboardTopic');
    const storyboardSceneCount = document.getElementById('storyboardSceneCount');
    const storyboardCustomCount = document.getElementById('storyboardCustomCount');
    const resetStoryboardBtn = document.getElementById('resetStoryboardBtn');
    const storyboardProgressCard = document.getElementById('storyboardProgressCard');
    const storyboardProgressStatus = document.getElementById('storyboardProgressStatus');
    const storyboardProgressStep = document.getElementById('storyboardProgressStep');
    const storyboardProgressPct = document.getElementById('storyboardProgressPct');
    const storyboardProgressBar = document.getElementById('storyboardProgressBar');
    
    // Segment Studio Elements
    const toggleSegmentStudioBtn = document.getElementById('toggleSegmentStudioBtn');
    const segmentStudioContainer = document.getElementById('segmentStudioContainer');
    const segmentStudioStats = document.getElementById('segmentStudioStats');
    const segmentStudioDirtyBadge = document.getElementById('segmentStudioDirtyBadge');
    const replanDirtyBtn = document.getElementById('replanDirtyBtn');
    const useSegmentsBtn = document.getElementById('useSegmentsBtn');
    const closeSegmentStudioBtn = document.getElementById('closeSegmentStudioBtn');
    const segmentStudioCards = document.getElementById('segmentStudioCards');

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

    let configData = null;
    let pollInterval = null;

    // Storyboard state: maps scene_id -> image_url or local_path
    let currentScenes = [];
    let sceneOverrides = {};
    let currentStep = 1;
    let currentSession = null;

    // ==========================================
    // GOOGLE MATERIAL TOAST NOTIFICATIONS
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
    // GOOGLE FLOW STEPPER NAVIGATION
    // ==========================================
    function goToStep(stepNum) {
        if (stepNum < 1 || stepNum > 4) return;

        // Validation when leaving step 1
        if (currentStep === 1 && stepNum > 1) {
            const scriptVal = scriptInput.value.trim();
            if (!scriptVal) {
                showToast("Please write or paste your script first before proceeding!", "warning");
                scriptInput.focus();
                return;
            }
        }

        // Update step panels
        for (let i = 1; i <= 4; i++) {
            const panel = document.getElementById(`stepPanel${i}`);
            const btn = document.getElementById(`stepBtn${i}`);
            if (panel) {
                if (i === stepNum) {
                    panel.classList.remove('hidden');
                } else {
                    panel.classList.add('hidden');
                }
            }
            if (btn) {
                btn.classList.remove('active');
                if (i < stepNum) {
                    btn.classList.add('completed');
                } else {
                    btn.classList.remove('completed');
                }
                if (i === stepNum) {
                    btn.classList.add('active');
                }
            }
        }

        currentStep = stepNum;

        // If entering Step 4, update summary
        if (stepNum === 4) {
            updateStep4Summary();
        }

        // Smooth scroll to top of controls panel
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
        const sumPacing = document.getElementById('sumPacing');
        const sumSubtitles = document.getElementById('sumSubtitles');

        if (sumScriptLength) sumScriptLength.textContent = `${words} words (~${dur})`;
        if (sumVoice && voiceSelect && voiceSelect.options && voiceSelect.selectedIndex >= 0) {
            const voiceOpt = voiceSelect.options[voiceSelect.selectedIndex];
            sumVoice.textContent = voiceOpt ? voiceOpt.text.split('[')[0].trim() : 'Neural Voice';
        }
        if (sumPacing && bgSelect && bgSelect.options && bgSelect.selectedIndex >= 0) {
            const bgOpt = bgSelect.options[bgSelect.selectedIndex];
            sumPacing.textContent = bgOpt ? bgOpt.text.split('(')[0].trim() : 'AI Ultra';
        }
        if (sumSubtitles) {
            const activePreset = document.querySelector('.preset-option.active .preset-label');
            sumSubtitles.textContent = activePreset ? activePreset.textContent : 'MrBeast Yellow';
        }
    }

    // Step button event listeners
    for (let i = 1; i <= 4; i++) {
        const btn = document.getElementById(`stepBtn${i}`);
        if (btn) {
            btn.addEventListener('click', () => goToStep(i));
        }
    }

    // Continue / Back buttons
    const toStep2Btn = document.getElementById('toStep2Btn');
    if (toStep2Btn) toStep2Btn.addEventListener('click', () => goToStep(2));

    const backToStep1Btn = document.getElementById('backToStep1Btn');
    if (backToStep1Btn) backToStep1Btn.addEventListener('click', () => goToStep(1));

    const toStep3Btn = document.getElementById('toStep3Btn');
    if (toStep3Btn) toStep3Btn.addEventListener('click', () => goToStep(3));

    const backToStep2Btn = document.getElementById('backToStep2Btn');
    if (backToStep2Btn) backToStep2Btn.addEventListener('click', () => goToStep(2));

    const toStep4Btn = document.getElementById('toStep4Btn');
    if (toStep4Btn) toStep4Btn.addEventListener('click', () => goToStep(4));

    const backToStep3Btn = document.getElementById('backToStep3Btn');
    if (backToStep3Btn) backToStep3Btn.addEventListener('click', () => goToStep(3));

    // 1. Fetch initial configuration
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

            // Populate backgrounds
            bgSelect.innerHTML = '';
            configData.backgrounds.forEach(bg => {
                const opt = document.createElement('option');
                opt.value = bg.id;
                opt.textContent = `${bg.name} (${bg.description})`;
                if (bg.id === 'ai_gemini') opt.selected = true;
                bgSelect.appendChild(opt);
            });

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

            // Populate Viral Hooks
            hookSelect.innerHTML = '<option value="">🪝 Add Viral Hook...</option>';
            configData.hooks.forEach((hook, i) => {
                const opt = document.createElement('option');
                opt.value = hook;
                opt.textContent = hook.length > 42 ? hook.substring(0, 42) + '...' : hook;
                hookSelect.appendChild(opt);
            });

        } catch (err) {
            console.error('Failed to load configuration:', err);
        }
    }

    // 2. Script Stats & Duration Calculator
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
    bgSelect.addEventListener('change', () => {
        if (!storyboardGrid.classList.contains('hidden') && scriptInput.value.trim()) {
            loadStoryboard(true);
        }
    });

    // 3. Template Selection
    templateSelect.addEventListener('change', (e) => {
        const key = e.target.value;
        if (key && configData && configData.templates[key]) {
            scriptInput.value = configData.templates[key].script;
            updateScriptStats();
            sceneOverrides = {};
            currentScenes = [];
            storyboardGrid.classList.add('hidden');
            storyboardToolbar.classList.add('hidden');
            storyboardEmptyNotice.classList.remove('hidden');
        }
    });

    // 4. Hook Selection
    hookSelect.addEventListener('change', (e) => {
        const hook = e.target.value;
        if (hook) {
            const current = scriptInput.value.trim();
            if (current) {
                scriptInput.value = `${hook} ${current}`;
            } else {
                scriptInput.value = hook;
            }
            updateScriptStats();
            hookSelect.value = '';
        }
    });

    // 5. Subtitle Style Preset Click
    document.querySelectorAll('.preset-option').forEach(opt => {
        opt.addEventListener('click', () => {
            document.querySelectorAll('.preset-option').forEach(o => o.classList.remove('active'));
            opt.classList.add('active');
            const radio = opt.querySelector('input[type="radio"]');
            if (radio) radio.checked = true;
        });
    });

    // 6. Volume Slider
    bgmVolume.addEventListener('input', (e) => {
        const pct = Math.round(parseFloat(e.target.value) * 100);
        volLabel.textContent = `${pct}%`;
    });

    // 7. Voice Audition / Preview
    previewVoiceBtn.addEventListener('click', async () => {
        const sampleText = scriptInput.value.trim().substring(0, 100) || "Welcome to the ultimate YouTube Shorts Creator!";
        const voice = voiceSelect.value;
        const speed = speedSelect.value;

        previewVoiceBtn.textContent = "⏳ Loading...";
        previewVoiceBtn.disabled = true;

        try {
            const res = await fetch('/api/preview_voice', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    text: sampleText,
                    voice: voice,
                    voice_rate: speed
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

    // 8. Custom Full Video Background Upload
    videoUploadInput.addEventListener('change', async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        uploadNotice.textContent = "Uploading video...";
        uploadNotice.classList.remove('hidden');

        const formData = new FormData();
        formData.append('file', file);

        try {
            const res = await fetch('/api/upload_background', {
                method: 'POST',
                body: formData
            });
            const data = await res.json();
            if (data.id) {
                const opt = document.createElement('option');
                opt.value = data.id;
                opt.textContent = `Custom Upload: ${data.name}`;
                opt.selected = true;
                bgSelect.insertBefore(opt, bgSelect.firstChild);
                uploadNotice.textContent = `Uploaded: ${data.name}`;
            }
        } catch (err) {
            uploadNotice.textContent = "Upload failed.";
        }
    });

    // ==========================================
    // 9. VISUAL STORYBOARD & MANUAL SCENE EDITOR
    // ==========================================

    function updateStoryboardStats() {
        const customCount = Object.keys(sceneOverrides).length;
        storyboardSceneCount.textContent = `${currentScenes.length} scenes`;
        storyboardCustomCount.textContent = `${customCount} custom photo${customCount === 1 ? '' : 's'}`;
    }

    function renderStoryboard() {
        storyboardGrid.innerHTML = '';
        currentScenes.forEach((sc) => {
            const overrideVal = sceneOverrides[sc.scene_id];
            const isCustom = Boolean(overrideVal);
            const displayImgUrl = isCustom ? overrideVal : sc.image_url;

            const card = document.createElement('div');
            card.className = `scene-card ${isCustom ? 'custom-active' : ''}`;
            card.id = `sceneCard_${sc.scene_id}`;

            // Build coherent Google Flow prompt (never copy raw narration directly)
            let copyPromptText = sc.image_prompt || sc.prompt;
            if (!copyPromptText || !copyPromptText.trim()) {
                const desc = sc.visual_description || sc.text || "cinematic scene";
                copyPromptText = `Photorealistic vertical 9:16 cinematic shot: ${desc}, 8k, dramatic lighting`;
            }

            // Validation score quality badge (>=80 green, 60-79 yellow, <60 red)
            const score = sc.validation_score !== undefined ? sc.validation_score : 85;
            let scoreClass = 'score-high';
            if (score < 60) scoreClass = 'score-low';
            else if (score < 80) scoreClass = 'score-med';

            // Source tier badge if not primary AI
            const tier = (sc.source_tier || '').toLowerCase();
            let tierBadge = '';
            if (tier.includes('stock') || tier.includes('curated')) {
                tierBadge = `<span class="scene-tier-badge tier-stock" title="Source: Curated Stock Photo">STOCK PHOTO</span>`;
            } else if (tier.includes('openverse') || tier.includes('wikimedia') || tier.includes('archive')) {
                tierBadge = `<span class="scene-tier-badge tier-archive" title="Source: Authentic Photo Archive">ARCHIVE</span>`;
            } else if (tier.includes('pollinations') || tier.includes('fallback')) {
                tierBadge = `<span class="scene-tier-badge tier-fallback" title="Source: Fallback AI">FALLBACK AI</span>`;
            }

            card.innerHTML = `
                <div class="scene-header">
                    <span>Scene ${sc.scene_id + 1}</span>
                    <span class="scene-time">${sc.start_time}s - ${sc.end_time}s (${sc.duration}s)</span>
                </div>
                <div class="scene-preview-box">
                    <img src="${displayImgUrl}" class="scene-thumb" id="sceneImg_${sc.scene_id}" alt="Scene ${sc.scene_id + 1}" loading="lazy">
                    <span class="scene-badge ${isCustom ? 'badge-custom' : 'badge-auto'}" id="sceneBadge_${sc.scene_id}" title="${sc.visual_description || ''}">
                        ${isCustom ? 'CUSTOM' : (sc.shot_type ? sc.shot_type.toUpperCase() : (sc.prompt || bgSelect.value === 'ai_gemini' ? 'AI ULTRA' : 'AUTHENTIC'))}
                    </span>
                    <span class="scene-score-badge ${scoreClass}" title="Quality Score: ${score}/100">
                        ${score}%
                    </span>
                    ${tierBadge}
                </div>
                <div class="scene-body">
                    <div class="scene-script-text" title="${sc.visual_description ? 'Director: ' + sc.visual_description + ' | ' : ''}${sc.text}">"${sc.text}"</div>
                    <div class="scene-actions">
                        <button class="btn-copy-prompt" data-prompt="${copyPromptText.replace(/"/g, '&quot;')}" title="Copy exact prompt for Google Flow">
                            📋 Copy Prompt
                        </button>
                        <label class="btn-replace-img" title="Upload your Google Flow image for this scene">
                            📁 Replace
                            <input type="file" class="scene-file-input" data-scene-id="${sc.scene_id}" accept="image/jpeg,image/png,image/webp" style="display:none;">
                        </label>
                        <button class="btn-refresh-scene" data-scene-id="${sc.scene_id}" title="Get alternate authentic photo or re-roll AI image">
                            🔄 Alt
                        </button>
                    </div>
                </div>
            `;

            storyboardGrid.appendChild(card);
        });

        // Hook copy prompt buttons for Google Flow
        document.querySelectorAll('.btn-copy-prompt').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const promptText = btn.getAttribute('data-prompt');
                try {
                    if (navigator.clipboard && window.isSecureContext) {
                        await navigator.clipboard.writeText(promptText);
                    } else {
                        const textArea = document.createElement("textarea");
                        textArea.value = promptText;
                        textArea.style.position = "fixed";
                        textArea.style.left = "-999999px";
                        document.body.appendChild(textArea);
                        textArea.focus();
                        textArea.select();
                        document.execCommand('copy');
                        textArea.remove();
                    }
                    showToast("📋 Copied prompt for Google Flow! Paste into flow.google", "success");
                    const oldText = btn.innerHTML;
                    btn.innerHTML = "✅ Copied!";
                    setTimeout(() => { btn.innerHTML = oldText; }, 2000);
                } catch (err) {
                    showToast("Failed to copy prompt: " + err.message, "error");
                }
            });
        });

        // Hook single scene upload inputs
        document.querySelectorAll('.scene-file-input').forEach(input => {
            input.addEventListener('change', async (e) => {
                const file = e.target.files[0];
                const sceneId = parseInt(e.target.getAttribute('data-scene-id'));
                if (!file) return;

                const card = document.getElementById(`sceneCard_${sceneId}`);
                const img = document.getElementById(`sceneImg_${sceneId}`);
                const badge = document.getElementById(`sceneBadge_${sceneId}`);

                badge.textContent = "UPLOADING...";
                badge.className = "scene-badge badge-custom";

                const formData = new FormData();
                formData.append('file', file);
                formData.append('scene_id', sceneId);

                try {
                    const res = await fetch('/api/upload_scene_image', {
                        method: 'POST',
                        body: formData
                    });
                    const data = await res.json();
                    if (data.local_path) {
                        sceneOverrides[sceneId] = data.local_path;
                        img.src = data.image_url;
                        badge.textContent = "CUSTOM";
                        card.classList.add('custom-active');
                        updateStoryboardStats();
                    }
                } catch (err) {
                    showToast('Image upload failed: ' + err.message, 'error');
                    badge.textContent = "ERROR";
                }
            });
        });

        // Hook alternate image refresh buttons
        document.querySelectorAll('.btn-refresh-scene').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const sceneId = parseInt(btn.getAttribute('data-scene-id'));
                const sc = currentScenes[sceneId];
                if (!sc) return;

                btn.textContent = "⏳";
                btn.disabled = true;

                // Collect excluded URLs so it doesn't pick an already used one
                const excluded = currentScenes.map(s => s.image_url);
                Object.values(sceneOverrides).forEach(v => excluded.push(v));

                try {
                    const res = await fetch('/api/refresh_scene_image', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            script: scriptInput.value.trim(),
                            scene_id: sceneId,
                            scene_text: sc.text,
                            exclude_urls: excluded,
                            bg_choice: bgSelect.value
                        })
                    });
                    const data = await res.json();
                    if (data.found && data.image_url) {
                        sceneOverrides[sceneId] = data.image_url;
                        const img = document.getElementById(`sceneImg_${sceneId}`);
                        const badge = document.getElementById(`sceneBadge_${sceneId}`);
                        const card = document.getElementById(`sceneCard_${sceneId}`);

                        img.src = data.image_url;
                        badge.textContent = bgSelect.value === 'ai_gemini' ? "AI ULTRA" : "AUTHENTIC";
                        badge.className = "scene-badge badge-auto";
                        card.classList.remove('custom-active');
                        updateStoryboardStats();
                        showToast("✨ Alternative scene image applied!", "success");
                    } else {
                        showToast(data.message || 'No additional alternative photo found.', 'warning');
                    }
                } catch (err) {
                    console.error('Alternate failed:', err);
                    showToast('Failed to get alternative image: ' + err.message, 'error');
                } finally {
                    btn.textContent = "🔄 Alt";
                    btn.disabled = false;
                }
            });
        });
    }

    async function loadStoryboard(useOverrides = true) {
        const script = scriptInput.value.trim();
        if (!script) {
            showToast("Please write or paste your script first before opening the storyboard!", "warning");
            scriptInput.focus();
            return;
        }

        // Show progress indicator and disable button
        if (previewScenesBtn) previewScenesBtn.disabled = true;
        if (storyboardProgressCard) storyboardProgressCard.classList.remove('hidden');
        if (storyboardEmptyNotice) storyboardEmptyNotice.classList.add('hidden');
        if (storyboardToolbar) storyboardToolbar.classList.add('hidden');
        if (storyboardGrid) storyboardGrid.classList.add('hidden');

        const isAi = bgSelect.value === 'ai_gemini';
        let progress = 5;

        function setProgress(pct, statusText, stepText) {
            progress = pct;
            if (storyboardProgressBar) storyboardProgressBar.style.width = `${pct}%`;
            if (storyboardProgressPct) storyboardProgressPct.textContent = `${pct}%`;
            if (statusText && storyboardProgressStatus) storyboardProgressStatus.textContent = statusText;
            if (stepText && storyboardProgressStep) storyboardProgressStep.textContent = stepText;
            if (previewScenesBtn) {
                previewScenesBtn.innerHTML = `<span class="spinner" style="width:14px;height:14px;border-width:2px;display:inline-block;vertical-align:middle;margin-right:6px;"></span> Auto-Matching (${pct}%)...`;
            }
        }

        setProgress(8, "Auto-Matching Scenes...", "Analyzing script structure & visual pacing...");

        // Progress simulation timer calibrated for engine mode
        const timerSteps = isAi ? [
            { at: 500, pct: 20, status: "Directing AI Scenes...", step: "Consulting Gemini AI visual director..." },
            { at: 1500, pct: 38, status: "Generating Prompts...", step: "Crafting photorealistic 9:16 scene prompts..." },
            { at: 3200, pct: 58, status: "Synthesizing Visuals...", step: "Generating high-definition visual assets..." },
            { at: 5500, pct: 74, status: "Downloading Assets...", step: "Rendering cinematic scene visuals..." },
            { at: 8000, pct: 88, status: "Verifying Scenes...", step: "Formatting 9:16 vertical frames & aspect ratios..." }
        ] : [
            { at: 250, pct: 25, status: "Detecting Topic...", step: "Identifying historical & encyclopedic entities..." },
            { at: 650, pct: 52, status: "Querying Archives...", step: "Matching authentic Wikimedia Commons archives..." },
            { at: 1300, pct: 75, status: "Filtering Visuals...", step: "Verifying high-resolution imagery & licensing..." },
            { at: 2000, pct: 88, status: "Formatting Storyboard...", step: "Arranging scene cards & timestamps..." }
        ];

        const timeouts = [];
        timerSteps.forEach(s => {
            timeouts.push(setTimeout(() => {
                setProgress(s.pct, s.status, s.step);
            }, s.at));
        });

        const creepInterval = setInterval(() => {
            if (progress < 94) {
                setProgress(progress + 1);
            }
        }, isAi ? 600 : 250);

        try {
            const res = await fetch('/api/prepare_scenes', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    script: script,
                    voice_rate: speedSelect.value,
                    bg_choice: bgSelect.value,
                    scene_overrides: useOverrides ? sceneOverrides : {}
                })
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
            currentScenes = data.scenes || [];

            // Clear timers
            timeouts.forEach(t => clearTimeout(t));
            clearInterval(creepInterval);

            // 100% completion
            setProgress(100, "Scenes Matched!", `Ready! Loaded ${currentScenes.length} scenes.`);
            previewScenesBtn.innerHTML = '✅ Matched (100%)';

            storyboardTopic.innerHTML = `Topic: <strong>${data.topic}</strong>`;
            const callsEl = document.getElementById('storyboardCallsCount');
            if (callsEl && typeof data.gemini_calls_used === 'number') {
                callsEl.textContent = `⚡ ${data.gemini_calls_used} API call${data.gemini_calls_used === 1 ? '' : 's'}`;
            }
            updateStoryboardStats();

            // Short delay so user clearly sees 100% completion
            await new Promise(r => setTimeout(r, 450));

            if (storyboardProgressCard) storyboardProgressCard.classList.add('hidden');
            if (storyboardToolbar) storyboardToolbar.classList.remove('hidden');
            if (storyboardGrid) storyboardGrid.classList.remove('hidden');

            renderStoryboard();

            if (data.warning) {
                showToast(data.warning, 'warning', 15000);
                let warningBanner = document.getElementById('storyboardWarningBanner');
                if (!warningBanner) {
                    warningBanner = document.createElement('div');
                    warningBanner.id = 'storyboardWarningBanner';
                    warningBanner.className = 'storyboard-warning-banner';
                    const container = document.getElementById('storyboardContainer');
                    const grid = document.getElementById('storyboardGrid');
                    if (container && grid) {
                        container.insertBefore(warningBanner, grid);
                    }
                }
                warningBanner.innerHTML = `<span>${data.warning}</span>`;
                warningBanner.classList.remove('hidden');
            } else {
                const warningBanner = document.getElementById('storyboardWarningBanner');
                if (warningBanner) warningBanner.classList.add('hidden');
                showToast(`✨ Storyboard ready! Loaded ${currentScenes.length} scenes.`, 'success');
            }
        } catch (err) {
            timeouts.forEach(t => clearTimeout(t));
            clearInterval(creepInterval);
            if (storyboardProgressCard) storyboardProgressCard.classList.add('hidden');
            if (storyboardEmptyNotice) storyboardEmptyNotice.classList.remove('hidden');
            showToast('Failed to prepare storyboard scenes: ' + err.message, 'error');
        } finally {
            if (previewScenesBtn) {
                previewScenesBtn.innerHTML = '🔍 Auto-Match & Preview Scenes';
                previewScenesBtn.disabled = false;
            }
        }
    }

    previewScenesBtn.addEventListener('click', () => loadStoryboard(true));
    resetStoryboardBtn.addEventListener('click', () => {
        sceneOverrides = {};
        loadStoryboard(false);
    });

    // Batch Image Upload Handler
    batchImageInput.addEventListener('change', async (e) => {
        const files = Array.from(e.target.files);
        if (files.length === 0) return;

        const script = scriptInput.value.trim();
        if (!script) {
            showToast("Please write or paste your script first!", "warning");
            scriptInput.focus();
            return;
        }

        previewScenesBtn.innerHTML = '<span class="spinner" style="width:14px;height:14px;border-width:2px;"></span> Uploading...';
        previewScenesBtn.disabled = true;

        const formData = new FormData();
        files.forEach(f => formData.append('files', f));

        try {
            const res = await fetch('/api/upload_batch_images', {
                method: 'POST',
                body: formData
            });
            const data = await res.json();
            const uploaded = data.uploaded || [];

            if (uploaded.length > 0) {
                // If scenes are not yet loaded, load them
                if (currentScenes.length === 0) {
                    await loadStoryboard(false);
                }

                // Map uploaded photos sequentially to scenes
                uploaded.forEach((u, i) => {
                    if (i < currentScenes.length) {
                        sceneOverrides[i] = u.local_path;
                    }
                });

                updateStoryboardStats();
                renderStoryboard();
                showToast(`Successfully assigned ${uploaded.length} custom photo(s) to scenes!`, 'success');
            }
        } catch (err) {
            showToast('Batch upload failed: ' + err.message, 'error');
        } finally {
            previewScenesBtn.innerHTML = '🔍 Auto-Match & Preview Scenes';
            previewScenesBtn.disabled = false;
            batchImageInput.value = '';
        }
    });

    // ==========================================
    // 9B. SEGMENT STUDIO (MANUAL SEGMENTATION)
    // ==========================================

    function renderSegmentStudio() {
        if (!currentSession || !segmentStudioCards) return;

        const segs = currentSession.segments || [];
        const dirtyCount = segs.filter(s => s.dirty).length;

        if (segmentStudioStats) {
            segmentStudioStats.textContent = `${segs.length} segment${segs.length === 1 ? '' : 's'} • ${currentSession.total_duration}s total`;
        }

        if (segmentStudioDirtyBadge) {
            if (dirtyCount > 0) {
                segmentStudioDirtyBadge.textContent = `${dirtyCount} DIRTY`;
                segmentStudioDirtyBadge.classList.remove('hidden');
            } else {
                segmentStudioDirtyBadge.classList.add('hidden');
            }
        }

        if (replanDirtyBtn) {
            replanDirtyBtn.disabled = dirtyCount === 0;
            replanDirtyBtn.textContent = `↻ Re-plan Dirty (${dirtyCount})`;
        }

        segmentStudioCards.innerHTML = '';

        segs.forEach((seg, idx) => {
            const card = document.createElement('div');
            card.className = `segment-card ${seg.dirty ? 'dirty-card' : ''}`;
            card.id = `segmentCard_${seg.segment_id}`;

            const words = seg.text.trim().split(/\s+/).filter(Boolean);
            const canSplit = words.length >= 2;
            const isLast = idx === segs.length - 1;
            const canDelete = segs.length > 1;

            card.innerHTML = `
                <div class="segment-card-header">
                    <div class="segment-card-title">
                        <span>#${idx + 1}</span>
                        <span class="segment-card-dur">${seg.duration}s</span>
                        ${seg.dirty ? '<span class="badge-dirty">DIRTY</span>' : ''}
                        ${seg.is_custom ? '<span class="badge" style="color:var(--accent-green)">CUSTOM</span>' : ''}
                    </div>
                </div>
                <textarea class="segment-card-textarea" data-segment-id="${seg.segment_id}">${seg.text}</textarea>
                <div class="segment-card-actions">
                    <button class="segment-btn btn-split" data-segment-id="${seg.segment_id}" ${canSplit ? '' : 'disabled'} title="Split into two segments">
                        ✂️ Split
                    </button>
                    <button class="segment-btn btn-merge" data-segment-id="${seg.segment_id}" ${!isLast ? '' : 'disabled'} title="Merge with next segment">
                        🔗 Merge Next
                    </button>
                    <button class="segment-btn btn-add" data-segment-id="${seg.segment_id}" title="Add new segment after this">
                        ➕ Add After
                    </button>
                    <button class="segment-btn btn-danger btn-del" data-segment-id="${seg.segment_id}" ${canDelete ? '' : 'disabled'} title="Delete this segment">
                        🗑️ Delete
                    </button>
                </div>
            `;

            // Textarea edit handling
            const textarea = card.querySelector('.segment-card-textarea');
            let initialVal = seg.text;
            textarea.addEventListener('blur', async () => {
                const newVal = textarea.value.trim();
                if (!newVal || newVal === initialVal) return;
                try {
                    const res = await fetch(`/api/segments/${currentSession.session_id}/edit_text`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ segment_id: seg.segment_id, new_text: newVal })
                    });
                    if (!res.ok) {
                        const err = await res.json();
                        throw new Error(err.detail || 'Edit failed');
                    }
                    currentSession = await res.json();
                    renderSegmentStudio();
                } catch (err) {
                    showToast('Failed to update segment: ' + err.message, 'error');
                    textarea.value = initialVal;
                }
            });

            // Split handling
            const splitBtn = card.querySelector('.btn-split');
            if (splitBtn && canSplit) {
                splitBtn.addEventListener('click', async () => {
                    const maxSplit = words.length - 1;
                    const defaultSplit = Math.max(1, Math.floor(words.length / 2));
                    const input = prompt(`Split segment at word index (1 to ${maxSplit}):\n\nWords: "${seg.text}"`, defaultSplit);
                    if (input === null) return;
                    const splitIdx = parseInt(input.trim());
                    if (isNaN(splitIdx) || splitIdx < 1 || splitIdx > maxSplit) {
                        showToast(`Invalid word index. Must be between 1 and ${maxSplit}.`, 'warning');
                        return;
                    }

                    try {
                        splitBtn.disabled = true;
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
                        renderSegmentStudio();
                        showToast('✂️ Segment split successfully!', 'success');
                    } catch (err) {
                        showToast(err.message, 'error');
                    } finally {
                        splitBtn.disabled = false;
                    }
                });
            }

            // Merge Next handling
            const mergeBtn = card.querySelector('.btn-merge');
            if (mergeBtn && !isLast) {
                mergeBtn.addEventListener('click', async () => {
                    try {
                        mergeBtn.disabled = true;
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
                        renderSegmentStudio();
                        showToast('🔗 Segments merged successfully!', 'success');
                    } catch (err) {
                        showToast(err.message, 'error');
                    } finally {
                        mergeBtn.disabled = false;
                    }
                });
            }

            // Add After handling
            const addBtn = card.querySelector('.btn-add');
            if (addBtn) {
                addBtn.addEventListener('click', async () => {
                    const text = prompt('Enter narration text for the new segment:');
                    if (!text || !text.trim()) return;

                    try {
                        addBtn.disabled = true;
                        const res = await fetch(`/api/segments/${currentSession.session_id}/add`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ after_segment_id: seg.segment_id, text: text.trim() })
                        });
                        if (!res.ok) {
                            const err = await res.json();
                            throw new Error(err.detail || 'Add segment failed');
                        }
                        currentSession = await res.json();
                        renderSegmentStudio();
                        showToast('➕ New segment added!', 'success');
                    } catch (err) {
                        showToast(err.message, 'error');
                    } finally {
                        addBtn.disabled = false;
                    }
                });
            }

            // Delete handling
            const delBtn = card.querySelector('.btn-del');
            if (delBtn && canDelete) {
                delBtn.addEventListener('click', async () => {
                    if (!confirm(`Are you sure you want to delete segment #${idx + 1}?`)) return;

                    try {
                        delBtn.disabled = true;
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
                        renderSegmentStudio();
                        showToast('🗑️ Segment deleted.', 'info');
                    } catch (err) {
                        showToast(err.message, 'error');
                    } finally {
                        delBtn.disabled = false;
                    }
                });
            }

            segmentStudioCards.appendChild(card);
        });
    }

    async function openSegmentStudio() {
        const script = scriptInput.value.trim();
        if (!script) {
            showToast('Please enter or paste your script first before opening Segment Studio!', 'warning');
            scriptInput.focus();
            return;
        }

        if (toggleSegmentStudioBtn) {
            toggleSegmentStudioBtn.disabled = true;
            toggleSegmentStudioBtn.textContent = '⏳ Loading...';
        }

        try {
            if (!currentSession) {
                const manualDelim = script.includes('|||');
                const res = await fetch('/api/segments/create', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ script: script, manual_delimiter: manualDelim })
                });
                if (!res.ok) {
                    const err = await res.json();
                    throw new Error(err.detail || 'Failed to initialize session');
                }
                currentSession = await res.json();
            }

            if (segmentStudioContainer) segmentStudioContainer.classList.remove('hidden');
            if (storyboardEmptyNotice) storyboardEmptyNotice.classList.add('hidden');
            renderSegmentStudio();
            showToast(`✂️ Segment Studio opened with ${currentSession.segments.length} segments.`, 'info');
        } catch (err) {
            showToast('Failed to open Segment Studio: ' + err.message, 'error');
        } finally {
            if (toggleSegmentStudioBtn) {
                toggleSegmentStudioBtn.disabled = false;
                toggleSegmentStudioBtn.textContent = '✂️ Segment Studio';
            }
        }
    }

    function closeSegmentStudio() {
        if (segmentStudioContainer) segmentStudioContainer.classList.add('hidden');
    }

    async function replanDirtySegments() {
        if (!currentSession) return;

        if (replanDirtyBtn) {
            replanDirtyBtn.disabled = true;
            replanDirtyBtn.textContent = '⏳ Re-planning...';
        }

        try {
            const res = await fetch(`/api/segments/${currentSession.session_id}/replan_dirty`, {
                method: 'POST'
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Re-plan failed');
            }
            currentSession = await res.json();
            renderSegmentStudio();

            const callsEl = document.getElementById('storyboardCallsCount');
            if (callsEl && typeof currentSession.gemini_calls_used === 'number') {
                callsEl.textContent = `⚡ ${currentSession.gemini_calls_used} API call${currentSession.gemini_calls_used === 1 ? '' : 's'}`;
            }
            showToast('✨ Re-planned dirty segments successfully!', 'success');
        } catch (err) {
            showToast('Re-plan failed: ' + err.message, 'error');
        } finally {
            if (replanDirtyBtn) {
                const dirtyCount = (currentSession.segments || []).filter(s => s.dirty).length;
                replanDirtyBtn.disabled = dirtyCount === 0;
                replanDirtyBtn.textContent = `↻ Re-plan Dirty (${dirtyCount})`;
            }
        }
    }

    function useSegmentsInStoryboard() {
        if (!currentSession || !currentSession.segments || currentSession.segments.length === 0) {
            showToast('No segments available to apply.', 'warning');
            return;
        }

        let startTime = 0.0;
        currentScenes = currentSession.segments.map((seg, idx) => {
            const sTime = startTime;
            const dur = seg.duration;
            startTime = parseFloat((startTime + dur).toFixed(2));
            return {
                scene_id: idx,
                start_time: sTime,
                end_time: startTime,
                duration: dur,
                text: seg.text,
                image_url: seg.image_url || "/static/placeholder.jpg",
                image_path: seg.image_path || "",
                prompt: seg.image_prompt,
                image_prompt: seg.image_prompt,
                visual_description: seg.visual_description,
                shot_type: seg.shot_type,
                camera_motion: seg.camera_motion,
                source: seg.source,
                source_tier: seg.source,
                validation_score: seg.validation_score,
                is_custom: seg.is_custom
            };
        });

        // Sync back joined script text if modified in studio
        const joinedScript = currentSession.segments.map(s => s.text.trim()).join(' ');
        if (joinedScript && joinedScript !== scriptInput.value.trim()) {
            scriptInput.value = joinedScript;
        }

        renderStoryboard();
        updateStoryboardStats();

        if (storyboardToolbar) storyboardToolbar.classList.remove('hidden');
        if (storyboardGrid) storyboardGrid.classList.remove('hidden');
        if (storyboardEmptyNotice) storyboardEmptyNotice.classList.add('hidden');
        if (segmentStudioContainer) segmentStudioContainer.classList.add('hidden');

        showToast(`✅ Storyboard updated with ${currentScenes.length} scenes from Segment Studio!`, 'success');
    }

    if (toggleSegmentStudioBtn) toggleSegmentStudioBtn.addEventListener('click', openSegmentStudio);
    if (closeSegmentStudioBtn) closeSegmentStudioBtn.addEventListener('click', closeSegmentStudio);
    if (replanDirtyBtn) replanDirtyBtn.addEventListener('click', replanDirtySegments);
    if (useSegmentsBtn) useSegmentsBtn.addEventListener('click', useSegmentsInStoryboard);

    // ==========================================
    // 10. GENERATE MASTER VIDEO (1080x1920)
    // ==========================================

    generateBtn.addEventListener('click', async () => {
        const script = scriptInput.value.trim();
        if (!script) {
            showToast("Please enter or paste your script first!", "warning");
            scriptInput.focus();
            return;
        }

        const selectedStyleRadio = document.querySelector('input[name="subtitleStyle"]:checked');
        const subtitleStyle = selectedStyleRadio ? selectedStyleRadio.value : 'mrbeast';

        // Gather exact previewed scenes from storyboard so the video locks in those approved visuals
        let previewScenesPayload = null;
        if (currentScenes && currentScenes.length > 0) {
            previewScenesPayload = currentScenes.map(sc => {
                const activeImg = sceneOverrides[sc.scene_id] || sc.image_url;
                return {
                    scene_id: sc.scene_id,
                    text: sc.text,
                    image_url: activeImg,
                    duration: sc.duration,
                    start_time: sc.start_time,
                    end_time: sc.end_time
                };
            });
        }

        const payload = {
            script: script,
            voice: voiceSelect.value,
            voice_rate: speedSelect.value,
            subtitle_style: subtitleStyle,
            bg_choice: bgSelect.value,
            bgm_track: bgmSelect.value,
            bgm_volume: parseFloat(bgmVolume.value),
            scene_overrides: Object.keys(sceneOverrides).length > 0 ? sceneOverrides : null,
            preview_scenes: previewScenesPayload
        };

        // UI State: Rendering
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

                        // Reveal video player
                        playerPlaceholder.style.display = 'none';
                        finalVideoPlayer.style.display = 'block';
                        finalVideoPlayer.src = status.video_url;
                        finalVideoPlayer.play();

                        playerActions.classList.remove('hidden');
                        downloadVideoBtn.href = status.video_url;

                        // Reveal SEO Kit
                        if (status.metadata) {
                            seoTitle.value = status.metadata.title;
                            seoDesc.value = status.metadata.description;
                            seoTags.value = status.metadata.tags.join(', ');
                            seoKitCard.classList.remove('hidden');
                        }

                        // Reset button
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

    // 11. Copy SEO Elements
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

    // Load initial setup
    loadConfig();
    updateScriptStats();
});
