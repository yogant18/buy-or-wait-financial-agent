# ── Base image: slim Python 3.11 ──────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py          .
COPY gradio_app/     ./gradio_app/
COPY code/           ./code/
COPY dataset/        ./dataset/

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Render injects PORT; default to 7860 for local/HF
EXPOSE 7860

CMD ["python", "app.py"]
