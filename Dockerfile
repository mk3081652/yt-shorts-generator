# Universal Free Cloud Deployment Dockerfile (Hugging Face Spaces, Render, Railway, etc.)
FROM python:3.11-slim

# Install system dependencies including FFmpeg and TrueType fonts for subtitle rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-freefont-ttf \
    fonts-dejavu-core \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Setup non-root user for security (required by Hugging Face Spaces)
RUN useradd -m -u 1000 user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PORT=7860

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY --chown=user:user . .

# Ensure outputs and assets directories are writable
RUN mkdir -p outputs/projects outputs/custom_scenes outputs/ai_previews assets/bgm \
    && chown -R user:user /app


USER user

# Expose standard port (7860 for Hugging Face, overridden by $PORT on Render/Railway)
EXPOSE 7860

# Start server
CMD ["python", "app.py"]
