FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/funclip:/app
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg git build-essential && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /app/requirements-funclip.txt
COPY backend/requirements-api.txt /app/requirements-api.txt
RUN pip install --no-cache-dir -r /app/requirements-funclip.txt && pip install --no-cache-dir -r /app/requirements-api.txt
COPY funclip /app/funclip
COPY backend/api.py /app/backend/api.py
RUN mkdir -p /app/backend && touch /app/backend/__init__.py
ENV CLIP_AI_ASR_MODEL=fun-asr-nano CLIP_AI_LANG=en
EXPOSE 8000
CMD ["uvicorn", "backend.api:app", "--host", "0.0.0.0", "--port", "8000"]
