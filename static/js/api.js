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

function isNetworkUploadIssue(err) {
    if (!err) return false;
    const status = err.status;
    if (status === 413 || status === 502 || status === 504 || status === 403 || status === 0) {
        return true;
    }
    const msg = (err.message || "").toLowerCase();
    return (
        msg.includes("network error") ||
        msg.includes("failed to fetch") ||
        msg.includes("413") ||
        msg.includes("payload") ||
        msg.includes("proxy") ||
        msg.includes("stream already read")
    );
}

/**
 * In-browser canvas image optimizer.
 * Scales down large images to max 1080x1920 (YouTube Shorts native format)
 * and compresses to lightweight high-quality JPEG.
 */
export async function optimizeImageFile(file, maxWidth = 1080, maxHeight = 1920, quality = 0.88) {
    if (!file || !file.type || !file.type.startsWith("image/")) {
        return file;
    }
    if (file.type === "image/gif" || file.type === "image/svg+xml") {
        return file;
    }

    return new Promise((resolve) => {
        const img = new Image();
        const url = URL.createObjectURL(file);
        img.onload = () => {
            URL.revokeObjectURL(url);
            let { width, height } = img;
            if (!width || !height) {
                resolve(file);
                return;
            }

            let targetWidth = width;
            let targetHeight = height;
            if (targetWidth > maxWidth || targetHeight > maxHeight) {
                const ratio = Math.min(maxWidth / targetWidth, maxHeight / targetHeight);
                targetWidth = Math.round(targetWidth * ratio);
                targetHeight = Math.round(targetHeight * ratio);
            }

            const canvas = document.createElement("canvas");
            canvas.width = targetWidth;
            canvas.height = targetHeight;
            const ctx = canvas.getContext("2d");
            if (!ctx) {
                resolve(file);
                return;
            }
            ctx.drawImage(img, 0, 0, targetWidth, targetHeight);

            canvas.toBlob(
                (blob) => {
                    if (blob && blob.size < file.size) {
                        const baseName = file.name.replace(/\.[^/.]+$/, "");
                        const optimized = new File([blob], `${baseName}_optimized.jpg`, {
                            type: "image/jpeg",
                            lastModified: Date.now()
                        });
                        resolve(optimized);
                    } else {
                        resolve(file);
                    }
                },
                "image/jpeg",
                quality
            );
        };
        img.onerror = () => {
            URL.revokeObjectURL(url);
            resolve(file);
        };
        img.src = url;
    });
}

async function request(url, options = {}) {
    try {
        const res = await fetch(url, options);
        if (!res.ok) {
            let errorMsg = `Request failed (${res.status})`;
            try {
                // Read text ONCE to prevent "Failed to execute 'text' on 'Response': body stream already read"
                const text = await res.text();
                try {
                    const errData = JSON.parse(text);
                    errorMsg = errData.detail || errData.message || errorMsg;
                } catch (_) {
                    // Non-JSON response (e.g. corporate proxy HTML block page or 413)
                    if (res.status === 413) {
                        errorMsg = "File payload is too large for your network/proxy connection (HTTP 413).";
                    } else if (res.status === 502 || res.status === 504) {
                        errorMsg = `Network gateway timeout or proxy error (HTTP ${res.status}).`;
                    } else if (res.status === 403) {
                        errorMsg = "Upload blocked by corporate network policy or proxy filter (HTTP 403).";
                    } else if (text && text.trim().length > 0 && !text.includes("<html") && text.length < 250) {
                        errorMsg = text.trim();
                    }
                }
            } catch (_) {
                // Keep default errorMsg if reading body fails
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
        const doUpload = async (uploadFile) => {
            const formData = new FormData();
            formData.append("file", uploadFile);
            formData.append("segment_id", sceneId);
            return await request(`/api/projects/${projectId}/upload_media`, {
                method: "POST",
                body: formData
            });
        };

        try {
            // Normal flow: always upload original file untouched first!
            return await doUpload(file);
        } catch (err) {
            // Only trigger optimization if there was a network / proxy / payload limit issue:
            if (isNetworkUploadIssue(err) && file && file.type && file.type.startsWith("image/")) {
                console.warn("[Upload Resilience] Network rejected raw image upload, auto-optimizing:", err);
                if (typeof window !== "undefined" && window.showToast) {
                    window.showToast("⚠️ Network rejected raw upload. Auto-optimizing image for your connection...", "warning", 5000);
                }
                const optimizedFile = await optimizeImageFile(file);
                if (optimizedFile) {
                    const res = await doUpload(optimizedFile);
                    if (typeof window !== "undefined" && window.showToast) {
                        window.showToast("✅ Uploaded successfully after optimizing for connection!", "success", 5000);
                    }
                    return res;
                }
            }
            throw err;
        }
    },

    async uploadBulk(projectId, files) {
        const doUpload = async (uploadFiles) => {
            const formData = new FormData();
            for (const file of uploadFiles) {
                formData.append("files", file);
            }
            return await request(`/api/projects/${projectId}/upload_bulk`, {
                method: "POST",
                body: formData
            });
        };

        try {
            // Normal flow: always upload original files untouched first!
            return await doUpload(files);
        } catch (err) {
            // Only trigger optimization if there was a network / proxy / payload limit issue:
            const hasImages = Array.isArray(files) && files.some(f => f.type && f.type.startsWith("image/"));
            if (isNetworkUploadIssue(err) && hasImages) {
                console.warn("[Upload Resilience] Network rejected bulk upload, auto-optimizing images:", err);
                if (typeof window !== "undefined" && window.showToast) {
                    window.showToast("⚠️ Network rejected raw upload. Auto-optimizing images for your connection...", "warning", 5000);
                }
                const optimizedFiles = await Promise.all(
                    files.map(f => (f.type && f.type.startsWith("image/") ? optimizeImageFile(f) : f))
                );
                const res = await doUpload(optimizedFiles);
                if (typeof window !== "undefined" && window.showToast) {
                    window.showToast("✅ Media uploaded successfully after optimizing for connection!", "success", 5000);
                }
                return res;
            }
            throw err;
        }
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
    },

    // YouTube Data API v3 methods
    async getYouTubeAuthStatus(channelId = null) {
        const query = channelId ? `?channel_id=${encodeURIComponent(channelId)}` : "";
        return await request(`/api/youtube/auth_status${query}`);
    },

    async authorizeYouTube() {
        return await request("/api/youtube/authorize", { method: "POST" });
    },

    async getYouTubeOAuthLoginUrl() {
        return await request("/api/youtube/oauth/url");
    },

    async getYouTubeChannels() {
        return await request("/api/youtube/channels");
    },

    async selectYouTubeChannel(channelId) {
        return await request("/api/youtube/channels/select", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ channel_id: channelId })
        });
    },

    async importYouTubeToken(tokenJson) {
        return await request("/api/youtube/channels/import", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ token_json: tokenJson })
        });
    },

    async uploadYouTubeTokenFile(file) {
        const formData = new FormData();
        formData.append("file", file);
        return await request("/api/youtube/channels/upload_token", {
            method: "POST",
            body: formData
        });
    },

    async exportYouTubeToken(channelId) {
        return await request(`/api/youtube/channels/${encodeURIComponent(channelId)}/export`);
    },

    async removeYouTubeChannel(channelId) {
        return await request(`/api/youtube/channels/${encodeURIComponent(channelId)}`, {
            method: "DELETE"
        });
    },

    async publishToYouTube(payload) {
        return await request("/api/youtube/publish", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
    }
};

