/**
 * static/js/api.js - REST API Client for YouTube Shorts Studio
 */

export class ApiError extends Error {
    constructor(message, status = 500, details = null) {
        super(message);
        this.name = "ApiError";
        this.status = status;
        this.details = details;
    }
}

async function request(url, options = {}) {
    try {
        const res = await fetch(url, options);
        if (!res.ok) {
            let errorMsg = `Request failed (${res.status})`;
            try {
                const errData = await res.json();
                errorMsg = errData.detail || errData.message || errorMsg;
            } catch (_) {
                const text = await res.text();
                if (text) errorMsg = text;
            }
            throw new ApiError(errorMsg, res.status);
        }
        const contentType = res.headers.get("content-type") || "";
        if (contentType.includes("application/json")) {
            return await res.json();
        }
        return await res.text();
    } catch (err) {
        if (err instanceof ApiError) throw err;
        throw new ApiError(err.message || "Network error", 0);
    }
}

export const api = {
    // Config & metadata
    async fetchConfig() {
        return await request("/api/config");
    },

    async generateScript(topic) {
        return await request("/api/generate_script", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ topic })
        });
    },

    async previewVoice(text, voice, rate = "+0%") {
        return await request("/api/preview_voice", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text, voice, rate })
        });
    },

    // Project Operations
    async createProject(script, start = "auto", manualDelimiter = false) {
        return await request("/api/projects", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                script,
                start,
                manual_delimiter: manualDelimiter
            })
        });
    },

    async getProject(projectId) {
        return await request(`/api/projects/${projectId}`);
    },

    async editText(projectId, sceneId, newText) {
        return await request(`/api/projects/${projectId}/edit_text`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ segment_id: sceneId, new_text: newText })
        });
    },

    async editPrompt(projectId, sceneId, newPrompt, kind = "image") {
        return await request(`/api/projects/${projectId}/edit_prompt`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ segment_id: sceneId, new_prompt: newPrompt, kind })
        });
    },

    async editMeta(projectId, sceneId = null, motion = null, styleLock = null) {
        return await request(`/api/projects/${projectId}/edit_meta`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                segment_id: sceneId,
                motion,
                style_lock: styleLock
            })
        });
    },

    async splitScene(projectId, sceneId, splitAtWordIndex) {
        return await request(`/api/projects/${projectId}/split`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                segment_id: sceneId,
                split_at_word_index: splitAtWordIndex
            })
        });
    },

    async mergeScene(projectId, sceneId, direction = "next") {
        return await request(`/api/projects/${projectId}/merge`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                segment_id: sceneId,
                direction
            })
        });
    },

    async moveBoundary(projectId, sceneId, direction = "left", words = 1) {
        return await request(`/api/projects/${projectId}/move_boundary`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                segment_id: sceneId,
                direction,
                words
            })
        });
    },

    async addScene(projectId, afterSceneId, text) {
        return await request(`/api/projects/${projectId}/add`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                after_segment_id: afterSceneId,
                text
            })
        });
    },

    async deleteScene(projectId, sceneId) {
        return await request(`/api/projects/${projectId}/delete`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ segment_id: sceneId })
        });
    },

    async uploadMedia(projectId, sceneId, file) {
        const formData = new FormData();
        formData.append("file", file);
        formData.append("segment_id", sceneId);
        return await request(`/api/projects/${projectId}/upload_media`, {
            method: "POST",
            body: formData
        });
    },

    async uploadBulk(projectId, files) {
        const formData = new FormData();
        for (const file of files) {
            formData.append("files", file);
        }
        return await request(`/api/projects/${projectId}/upload_bulk`, {
            method: "POST",
            body: formData
        });
    },

    async clearMedia(projectId, sceneId) {
        return await request(`/api/projects/${projectId}/clear_media`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ segment_id: sceneId })
        });
    },

    async generateSceneMedia(projectId, sceneId) {
        return await request(`/api/projects/${projectId}/generate`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ segment_id: sceneId })
        });
    },

    async generateMissingMedia(projectId) {
        return await request(`/api/projects/${projectId}/generate_missing`, {
            method: "POST"
        });
    },

    async cancelGeneration(projectId) {
        return await request(`/api/projects/${projectId}/cancel`, {
            method: "POST"
        });
    },

    async suggestPrompts(projectId, sceneId) {
        return await request(`/api/projects/${projectId}/suggest_prompts`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ segment_id: sceneId })
        });
    },

    async exportPrompts(projectId) {
        return await request(`/api/projects/${projectId}/export_prompts`);
    },

    async undo(projectId) {
        return await request(`/api/projects/${projectId}/undo`, { method: "POST" });
    },

    async redo(projectId) {
        return await request(`/api/projects/${projectId}/redo`, { method: "POST" });
    },

    async prepareVoice(projectId, voice, rate = "+10%") {
        return await request(`/api/projects/${projectId}/prepare_voice`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ voice, rate })
        });
    },

    // Final Short Render & Job Polling
    async generateShort(payload) {
        return await request("/api/generate_short", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
    },

    async pollJob(jobId) {
        return await request(`/api/job/${jobId}`);
    },

    async generateMetadata(script) {
        return await request("/api/generate_metadata", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ script })
        });
    }
};
