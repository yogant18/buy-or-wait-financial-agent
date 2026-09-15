# ── Base image: slim Python 3.11 ──────────────────────────────────────────────
FROM python:3.11-slim

# HF Spaces runs as user 1000 — set up a non-root user to match
RUN useradd -m -u 1000 appuser

# System deps for EasyOCR (OpenCV / libGL)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1-mesa-glx \
        libglib2.0-0 \
        libsm6 \
        libxrender1 \
        libxext6 \
        git \
    && rm -rf /var/lib/apt/lists/*

# ── Working directory ─────────────────────────────────────────────────────────
WORKDIR /app

# ── Copy requirements first (layer cache) ────────────────────────────────────
COPY chainlit_app/requirements.txt /app/chainlit_app/requirements.txt
RUN pip install --no-cache-dir -r chainlit_app/requirements.txt

# ── Copy rest of the repo ─────────────────────────────────────────────────────
COPY code/           /app/code/
COPY dataset/        /app/dataset/
COPY chainlit_app/   /app/chainlit_app/

# ── EasyOCR model pre-download (avoids cold-start download in prod) ──────────
RUN python -c "import easyocr; easyocr.Reader(['en'], gpu=False)" || true

# ── Permissions ──────────────────────────────────────────────────────────────
RUN chown -R appuser:appuser /app
USER appuser

# HF Spaces expects port 7860
EXPOSE 7860

# Chainlit needs CHAINLIT_AUTH_SECRET to be set for production
# Set GROQ_API_KEY via HF Spaces → Settings → Repository Secrets
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# ── Launch ───────────────────────────────────────────────────────────────────
CMD ["chainlit", "run", "chainlit_app/app.py", "--host", "0.0.0.0", "--port", "7860"]
