/**
 * static/js/state.js - Reactive Application State and Event Bus
 */

class StateManager {
    constructor() {
        this.listeners = {};
        this.state = {
            project: null,
            currentStep: 1,
            mode: "auto", // "auto" | "manual"
            config: null,
            isGenerating: false,
            focusedSceneId: null,
            activeSplitSceneId: null
        };
    }

    on(event, callback) {
        if (!this.listeners[event]) {
            this.listeners[event] = [];
        }
        this.listeners[event].push(callback);
    }

    off(event, callback) {
        if (!this.listeners[event]) return;
        this.listeners[event] = this.listeners[event].filter(cb => cb !== callback);
    }

    emit(event, data) {
        if (!this.listeners[event]) return;
        for (const cb of this.listeners[event]) {
            try {
                cb(data);
            } catch (err) {
                console.error(`[State Event Error] ${event}:`, err);
            }
        }
    }

    get project() {
        return this.state.project;
    }

    get currentStep() {
        return this.state.currentStep;
    }

    get mode() {
        return this.state.mode;
    }

    get config() {
        return this.state.config;
    }

    get isGenerating() {
        return this.state.isGenerating;
    }

    get focusedSceneId() {
        return this.state.focusedSceneId;
    }

    get activeSplitSceneId() {
        return this.state.activeSplitSceneId;
    }

    setProject(project) {
        this.state.project = project;
        this.emit("project_updated", project);
    }

    setStep(step) {
        this.state.currentStep = step;
        this.emit("step_changed", step);
    }

    setMode(mode) {
        this.state.mode = mode;
        this.emit("mode_changed", mode);
    }

    setConfig(config) {
        this.state.config = config;
        this.emit("config_loaded", config);
    }

    setGenerating(flag) {
        this.state.isGenerating = flag;
        this.emit("generating_changed", flag);
    }

    setFocusedScene(sceneId) {
        this.state.focusedSceneId = sceneId;
        this.emit("scene_focused", sceneId);
    }

    setActiveSplitScene(sceneId) {
        this.state.activeSplitSceneId = sceneId;
        this.emit("split_modal_requested", sceneId);
    }

    updateScene(sceneId, updates) {
        if (!this.state.project || !this.state.project.scenes) return;
        const sc = this.state.project.scenes.find(s => s.id === sceneId || s.segment_id === sceneId);
        if (sc) {
            Object.assign(sc, updates);
            this.emit("scene_updated", { sceneId, updates, scene: sc });
        }
    }

    canUndo() {
        return !!(this.state.project && this.state.project.can_undo);
    }

    canRedo() {
        return !!(this.state.project && this.state.project.can_redo);
    }
}

export const state = new StateManager();
