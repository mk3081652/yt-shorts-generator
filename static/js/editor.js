/**
 * static/js/editor.js - Storyboard Container, Split Modal, Toolbar, and Shortcuts
 */

import { api } from "./api.js";
import { state } from "./state.js";
import { createSceneCard } from "./card.js";

export class StoryboardEditor {
    constructor(elements, showToast) {
        this.el = elements;
        this.showToast = showToast;
        this.initListeners();
    }

    initListeners() {
        // State subscriptions
        state.on("project_updated", (project) => this.render(project));
        state.on("split_modal_requested", (sceneId) => this.openSplitModal(sceneId));

        // Toolbar buttons
        if (this.el.undoBtn) {
            this.el.undoBtn.addEventListener("click", () => this.handleUndo());
        }
        if (this.el.redoBtn) {
            this.el.redoBtn.addEventListener("click", () => this.handleRedo());
        }
        if (this.el.copyAllPromptsBtn) {
            this.el.copyAllPromptsBtn.addEventListener("click", () => this.handleCopyAllPrompts());
        }
        if (this.el.addBeatBtn) {
            this.el.addBeatBtn.addEventListener("click", () => this.handleAddScene());
        }

        // Split Modal close
        if (this.el.closeSplitModal) {
            this.el.closeSplitModal.addEventListener("click", () => this.closeSplitModal());
        }
        if (this.el.splitModal) {
            this.el.splitModal.addEventListener("click", (e) => {
                if (e.target === this.el.splitModal) this.closeSplitModal();
            });
        }

        // Global Keyboard shortcuts (Ctrl+Z, Ctrl+Y, Ctrl+Shift+Z)
        document.addEventListener("keydown", (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
                if (e.shiftKey) {
                    e.preventDefault();
                    this.handleRedo();
                } else {
                    e.preventDefault();
                    this.handleUndo();
                }
            } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "y") {
                e.preventDefault();
                this.handleRedo();
            }
        });

        // Global Clipboard Paste: paste image into focused scene
        document.addEventListener("paste", async (e) => {
            const items = (e.clipboardData || e.originalEvent.clipboardData).items;
            let imageFile = null;
            for (const item of items) {
                if (item.type.indexOf("image") !== -1) {
                    imageFile = item.getAsFile();
                    break;
                }
            }
            if (!imageFile) return;

            const proj = state.project;
            if (!proj || !proj.scenes || proj.scenes.length === 0) return;

            const targetId = state.focusedSceneId || proj.scenes[0].id;
            this.showToast(`Pasting image to Scene...`, "info");
            try {
                const updated = await api.uploadMedia(proj.id, targetId, imageFile);
                state.setProject(updated);
                this.showToast("Pasted image successfully!", "success");
            } catch (err) {
                this.showToast(`Failed to paste image: ${err.message}`, "error");
            }
        });
    }

    render(project) {
        if (!project || !project.scenes || project.scenes.length === 0) {
            if (this.el.storyboardEmptyNotice) this.el.storyboardEmptyNotice.classList.remove("hidden");
            if (this.el.sceneCardsList) this.el.sceneCardsList.innerHTML = "";
            this.updateToolbarStats(0, 0, 0, 0);
            return;
        }

        if (this.el.storyboardEmptyNotice) this.el.storyboardEmptyNotice.classList.add("hidden");
        if (!this.el.sceneCardsList) return;

        // Clear and render fresh cards
        this.el.sceneCardsList.innerHTML = "";
        const scenes = project.scenes;
        const total = scenes.length;

        let blankCount = 0;
        let visualsCount = 0;

        scenes.forEach((sc, idx) => {
            if (sc.media_url || sc.image_url) {
                visualsCount++;
            } else {
                blankCount++;
            }

            const card = createSceneCard(sc, idx, total, {
                onEditText: (id, text) => this.handleEditText(id, text),
                onEditPrompt: (id, prompt) => this.handleEditPrompt(id, prompt),
                onEditMotion: (id, motion) => this.handleEditMotion(id, motion),
                onMoveBoundary: (id, dir, words) => this.handleMoveBoundary(id, dir, words),
                onMerge: (id, dir) => this.handleMerge(id, dir),
                onDelete: (id) => this.handleDelete(id),
                onUploadMedia: (id, file) => this.handleUploadMedia(id, file),
                onClearMedia: (id) => this.handleClearMedia(id),
                onGenerateMedia: (id) => this.handleGenerateMedia(id),
                onSuggestPrompts: (id) => this.handleSuggestPrompts(id)
            });

            this.el.sceneCardsList.appendChild(card);
        });

        this.updateToolbarStats(total, blankCount, project.total_duration || 0, visualsCount);

        // Blank scenes warning banner
        if (this.el.blankScenesWarning) {
            if (blankCount > 0) {
                this.el.blankScenesWarning.classList.remove("hidden");
                if (this.el.blankWarningText) {
                    this.el.blankWarningText.textContent = `${blankCount} scene${blankCount > 1 ? "s have" : " has"} no visual media and will render as black background.`;
                }
            } else {
                this.el.blankScenesWarning.classList.add("hidden");
            }
        }

        // Undo/Redo buttons
        if (this.el.undoBtn) this.el.undoBtn.disabled = !project.can_undo;
        if (this.el.redoBtn) this.el.redoBtn.disabled = !project.can_redo;
    }

    updateToolbarStats(sceneCount, blankCount, totalDur, visualsCount) {
        if (this.el.storyboardSceneCount) this.el.storyboardSceneCount.textContent = `${sceneCount} scene${sceneCount !== 1 ? "s" : ""}`;
        if (this.el.storyboardBlankCount) {
            this.el.storyboardBlankCount.textContent = `${blankCount} blank`;
            if (blankCount > 0) this.el.storyboardBlankCount.classList.remove("hidden");
            else this.el.storyboardBlankCount.classList.add("hidden");
        }
        if (this.el.storyboardTotalDur) this.el.storyboardTotalDur.textContent = `${Number(totalDur).toFixed(1)}s total`;
        if (this.el.storyboardVisualsCount) this.el.storyboardVisualsCount.textContent = `${visualsCount} visual${visualsCount !== 1 ? "s" : ""} loaded`;
    }

    // Split Modal
    openSplitModal(sceneId) {
        const proj = state.project;
        if (!proj) return;
        const target = proj.scenes.find(s => s.id === sceneId || s.segment_id === sceneId);
        if (!target) return;

        const words = (target.text || "").trim().split(/\s+/);
        if (words.length <= 1) {
            this.showToast("Scene has only 1 word, cannot split.", "warning");
            return;
        }

        if (!this.el.splitWordChips || !this.el.splitModal) return;
        this.el.splitWordChips.innerHTML = "";

        words.forEach((w, idx) => {
            const chip = document.createElement("button");
            chip.type = "button";
            chip.className = "split-word-chip";
            chip.textContent = w;

            if (idx > 0) {
                chip.title = `Split before "${w}"`;
                chip.addEventListener("click", async () => {
                    try {
                        const updated = await api.splitScene(proj.id, target.id, idx);
                        state.setProject(updated);
                        this.closeSplitModal();
                        this.showToast(`Scene split at word #${idx + 1}!`, "success");
                    } catch (err) {
                        this.showToast(`Split failed: ${err.message}`, "error");
                    }
                });
            } else {
                chip.disabled = true;
                chip.title = "Cannot split before first word";
            }
            this.el.splitWordChips.appendChild(chip);
        });

        this.el.splitModal.classList.remove("hidden");
    }

    closeSplitModal() {
        if (this.el.splitModal) this.el.splitModal.classList.add("hidden");
    }

    // Handlers
    async handleUndo() {
        const proj = state.project;
        if (!proj || !proj.can_undo) return;
        try {
            const updated = await api.undo(proj.id);
            state.setProject(updated);
            this.showToast("Undo successful", "info");
        } catch (err) {
            this.showToast(`Undo failed: ${err.message}`, "error");
        }
    }

    async handleRedo() {
        const proj = state.project;
        if (!proj || !proj.can_redo) return;
        try {
            const updated = await api.redo(proj.id);
            state.setProject(updated);
            this.showToast("Redo successful", "info");
        } catch (err) {
            this.showToast(`Redo failed: ${err.message}`, "error");
        }
    }

    async handleEditText(sceneId, text) {
        const proj = state.project;
        if (!proj) return;
        try {
            const updated = await api.editText(proj.id, sceneId, text);
            state.setProject(updated);
        } catch (err) {
            this.showToast(`Failed to update text: ${err.message}`, "error");
        }
    }

    async handleEditPrompt(sceneId, prompt) {
        const proj = state.project;
        if (!proj) return;
        try {
            const updated = await api.editPrompt(proj.id, sceneId, prompt);
            state.setProject(updated);
        } catch (err) {
            this.showToast(`Failed to update prompt: ${err.message}`, "error");
        }
    }

    async handleEditMotion(sceneId, motion) {
        const proj = state.project;
        if (!proj) return;
        try {
            const updated = await api.editMeta(proj.id, sceneId, motion);
            state.setProject(updated);
        } catch (err) {
            this.showToast(`Failed to update motion: ${err.message}`, "error");
        }
    }

    async handleMoveBoundary(sceneId, direction, words) {
        const proj = state.project;
        if (!proj) return;
        try {
            const updated = await api.moveBoundary(proj.id, sceneId, direction, words);
            state.setProject(updated);
            this.showToast(`Shifted word ${direction}!`, "success");
        } catch (err) {
            this.showToast(`Shift failed: ${err.message}`, "error");
        }
    }

    async handleMerge(sceneId, direction) {
        const proj = state.project;
        if (!proj) return;
        try {
            const updated = await api.mergeScene(proj.id, sceneId, direction);
            state.setProject(updated);
            this.showToast("Merged scenes!", "success");
        } catch (err) {
            this.showToast(`Merge failed: ${err.message}`, "error");
        }
    }

    async handleDelete(sceneId) {
        const proj = state.project;
        if (!proj) return;
        try {
            const updated = await api.deleteScene(proj.id, sceneId);
            state.setProject(updated);
            this.showToast("Scene deleted", "info");
        } catch (err) {
            this.showToast(`Delete failed: ${err.message}`, "error");
        }
    }

    async handleUploadMedia(sceneId, file) {
        const proj = state.project;
        if (!proj) return;
        this.showToast(`Uploading ${file.name}...`, "info");
        try {
            const updated = await api.uploadMedia(proj.id, sceneId, file);
            state.setProject(updated);
            this.showToast(`Uploaded ${file.name}! Scene locked as manual.`, "success");
        } catch (err) {
            this.showToast(`Upload failed: ${err.message}`, "error");
        }
    }

    async handleClearMedia(sceneId) {
        const proj = state.project;
        if (!proj) return;
        try {
            const updated = await api.clearMedia(proj.id, sceneId);
            state.setProject(updated);
            this.showToast("Media cleared", "info");
        } catch (err) {
            this.showToast(`Clear failed: ${err.message}`, "error");
        }
    }

    async handleGenerateMedia(sceneId) {
        const proj = state.project;
        if (!proj) return;
        this.showToast("Generating image with FLUX...", "info");
        try {
            const updated = await api.generateSceneMedia(proj.id, sceneId);
            state.setProject(updated);
            this.showToast("Image generated successfully!", "success");
        } catch (err) {
            this.showToast(`Generation failed: ${err.message}`, "error");
        }
    }

    async handleSuggestPrompts(sceneId) {
        const proj = state.project;
        if (!proj) return;
        this.showToast("Asking Gemini for prompt suggestions...", "info");
        try {
            const res = await api.suggestPrompts(proj.id, sceneId);
            const prompts = res.prompts || [];
            if (prompts.length === 0) {
                this.showToast("No suggestions returned", "warning");
                return;
            }
            // Use the first suggestion and copy others
            await api.editPrompt(proj.id, sceneId, prompts[0]);
            const updated = await api.getProject(proj.id);
            state.setProject(updated);
            this.showToast(`Applied new prompt: "${prompts[0].slice(0, 50)}..."`, "success");
        } catch (err) {
            this.showToast(`Suggestions failed: ${err.message}`, "error");
        }
    }

    async handleAddScene() {
        const proj = state.project;
        if (!proj) return;
        const lastScene = proj.scenes[proj.scenes.length - 1];
        const lastId = lastScene ? lastScene.id : null;
        try {
            const updated = await api.addScene(proj.id, lastId, "New scene spoken narration...");
            state.setProject(updated);
            this.showToast("Added new scene!", "success");
        } catch (err) {
            this.showToast(`Add scene failed: ${err.message}`, "error");
        }
    }

    async handleCopyAllPrompts() {
        const proj = state.project;
        if (!proj || !proj.scenes || proj.scenes.length === 0) {
            this.showToast("No scenes to export", "warning");
            return;
        }
        try {
            const text = await api.exportPrompts(proj.id);
            await navigator.clipboard.writeText(text);
            this.showToast("All prompts copied to clipboard!", "success");
        } catch (err) {
            this.showToast(`Copy failed: ${err.message}`, "error");
        }
    }
}
